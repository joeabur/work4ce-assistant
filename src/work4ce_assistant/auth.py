"""Bounded RS256 verification against an operator-configured OIDC JWKS endpoint.

This module authenticates subjects only. Tenant and permission grants must be
assigned by the backend; JWT claims never authorize connector execution.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from .contracts import Work4ceError


def _https_url(value: str) -> None:
    if not isinstance(value, str):
        raise ValueError("OIDC URLs must be strings")
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username is not None
                or url.password is not None or url.query or url.fragment
                or "?" in value or "#" in value or any(c.isspace() for c in value)
                or "\\" in value or not value.isascii()):
            raise ValueError
        _ = url.port
    except (ValueError, TypeError):
        raise ValueError("OIDC URLs require explicit trusted HTTPS hosts without credentials, query or fragment") from None


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    audience: str
    jwks_url: str

    def __post_init__(self) -> None:
        _https_url(self.issuer)
        _https_url(self.jwks_url)
        if not isinstance(self.audience, str) or not 1 <= len(self.audience) <= 512:
            raise ValueError("OIDC audience is required")


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _json(raw: bytes) -> dict:
    result = json.loads(raw, object_pairs_hook=_unique_object,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    if not isinstance(result, dict):
        raise ValueError("expected JSON object")
    return result


def _segment(value: str) -> dict:
    return _json(base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True))


class OIDCVerifier:
    CACHE_TTL_SECONDS = 300
    REFRESH_INTERVAL_SECONDS = 30
    MAX_TOKEN_BYTES = 16_384
    MAX_JWKS_BYTES = 65_536

    def __init__(self, config: OIDCConfig, client: httpx.AsyncClient | None = None):
        self.config = config
        self._owned_client = client is None
        # Preserve environment proxy and CA trust. No interactive discovery or login.
        self._client = client or httpx.AsyncClient(timeout=5.0, follow_redirects=False)
        self._lock = asyncio.Lock()
        self._keys: dict[str, RSAPublicKey] = {}
        self._expires_at = 0.0
        self._last_attempt = float("-inf")

    async def close(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def _refresh(self) -> None:
        self._last_attempt = time.monotonic()
        try:
            async with asyncio.timeout(5):
                async with self._client.stream("GET", self.config.jwks_url,
                                               timeout=5.0, follow_redirects=False) as response:
                    if response.status_code != 200:
                        raise ValueError("JWKS unavailable")
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > self.MAX_JWKS_BYTES:
                            raise ValueError("JWKS exceeds bound")
            document = _json(bytes(raw))
            entries = document.get("keys")
            if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
                raise ValueError("invalid JWKS keys")
            keys = {}
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError("invalid JWK")
                kid = entry.get("kid")
                if not isinstance(kid, str) or not 1 <= len(kid) <= 200 or kid in keys:
                    raise ValueError("invalid JWK identity")
                if (entry.get("kty") != "RSA" or entry.get("alg", "RS256") != "RS256"
                        or entry.get("use", "sig") != "sig"
                        or entry.get("key_ops", ["verify"]) != ["verify"]
                        or any(k in entry for k in ("d", "p", "q", "dp", "dq", "qi", "oth"))):
                    raise ValueError("unsupported JWK")
                key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(entry))
                if not isinstance(key, RSAPublicKey) or not 2048 <= key.key_size <= 8192:
                    raise ValueError("unsupported RSA key size")
                keys[kid] = key
            self._keys = keys
            self._expires_at = time.monotonic() + self.CACHE_TTL_SECONDS
        except Exception:
            # Never expose HTTP errors, key material or bearer tokens.
            raise Work4ceError("auth_service_unavailable", 503) from None

    async def _key(self, kid: str) -> RSAPublicKey:
        async with self._lock:
            current = time.monotonic()
            fresh = current < self._expires_at
            if fresh and kid in self._keys:
                return self._keys[kid]
            if current - self._last_attempt >= self.REFRESH_INTERVAL_SECONDS:
                await self._refresh()
            elif not fresh:
                raise Work4ceError("auth_service_unavailable", 503)
            if time.monotonic() >= self._expires_at:
                raise Work4ceError("auth_service_unavailable", 503)
            if kid not in self._keys:
                raise Work4ceError("authentication_required", 401)
            return self._keys[kid]

    async def verify(self, token: str) -> str:
        try:
            if not isinstance(token, str) or not token.isascii() or len(token) > self.MAX_TOKEN_BYTES:
                raise ValueError("invalid token")
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("invalid token")
            header, payload = _segment(parts[0]), _segment(parts[1])
            kid = header.get("kid")
            if (header.get("alg") != "RS256" or header.get("typ") not in {"JWT", "at+jwt"}
                    or not isinstance(kid, str) or not 1 <= len(kid) <= 200
                    or set(header) - {"alg", "typ", "kid"}):
                raise ValueError("unsupported token header")
            # Reject invalid claim shapes before any attacker-triggered key fetch.
            for claim in ("exp", "iat"):
                value = payload.get(claim)
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("invalid NumericDate")
            if "nbf" in payload and (type(payload["nbf"]) not in (int, float)
                                     or not math.isfinite(payload["nbf"])):
                raise ValueError("invalid NumericDate")
            if (not isinstance(payload.get("sub"), str) or not 1 <= len(payload["sub"]) <= 512
                    or payload.get("iss") != self.config.issuer
                    or payload.get("aud") != self.config.audience
                    or not 0 < payload["exp"] - payload["iat"] <= 3600
                    or payload["iat"] > time.time()):
                raise ValueError("invalid claims")
        except Exception:
            raise Work4ceError("authentication_required", 401) from None
        key = await self._key(kid)
        try:
            claims = jwt.decode(token, key=key, algorithms=["RS256"],
                                issuer=self.config.issuer, audience=self.config.audience,
                                options={"require": ["exp", "iat", "iss", "aud", "sub"],
                                         "strict_aud": True})
            return claims["sub"]
        except Exception:
            raise Work4ceError("authentication_required", 401) from None
