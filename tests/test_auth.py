"""OIDC verification with actual RSA signatures and bounded mock HTTPS JWKS."""
import base64
import json
import time
import unittest
from unittest.mock import patch

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from work4ce_assistant.auth import OIDCConfig, OIDCVerifier
from work4ce_assistant.contracts import Work4ceError

ISSUER = "https://identity.example.test/realms/synthetic"
AUDIENCE = "work4ce-synthetic"
URL = ISSUER + "/jwks"


def public_jwk(key, kid="one"):
    return dict(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
                kid=kid, alg="RS256", use="sig", key_ops=["verify"])


class OIDCAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.weak_key = rsa.generate_private_key(public_exponent=65537, key_size=1024)

    async def asyncSetUp(self):
        self.requests = []
        self.document = {"keys": [public_jwk(self.key)]}
        self.response_status = 200
        self.content = None

        async def handle(request):
            self.requests.append(request)
            self.assertEqual(str(request.url), URL)
            self.assertNotIn("authorization", request.headers)
            if self.content is not None:
                return httpx.Response(self.response_status, content=self.content)
            return httpx.Response(self.response_status, json=self.document)

        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        self.verifier = OIDCVerifier(OIDCConfig(ISSUER, AUDIENCE, URL), self.client)

    async def asyncTearDown(self):
        await self.verifier.close()
        await self.client.aclose()

    def token(self, claims=None, headers=None, key=None):
        current = int(time.time())
        payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": "analyst-subject",
                   "iat": current - 1, "exp": current + 300}
        payload.update(claims or {})
        return jwt.encode(payload, key or self.key, algorithm="RS256",
                          headers={"kid": "one", "typ": "at+jwt", **(headers or {})})

    async def assert_error(self, token, status=401, code="authentication_required"):
        with self.assertRaises(Work4ceError) as raised:
            await self.verifier.verify(token)
        self.assertEqual(raised.exception.status, status)
        self.assertEqual(str(raised.exception), code)

    async def test_valid_rs256_subject_only_and_cached_jwks(self):
        self.assertEqual(await self.verifier.verify(self.token(claims={"tenant": "attacker", "roles": ["admin"]})),
                         "analyst-subject")
        self.assertEqual(await self.verifier.verify(self.token(headers={"typ": "JWT"})), "analyst-subject")
        self.assertEqual(len(self.requests), 1)
        await self.verifier.close()
        self.assertFalse(self.client.is_closed)

    async def test_invalid_claims_and_time_bounds(self):
        current = int(time.time())
        cases = [{"iss": "https://attacker.test"}, {"aud": "other"}, {"aud": [AUDIENCE]},
                 {"sub": ""}, {"sub": 123}, {"iat": current + 60}, {"exp": current - 1},
                 {"nbf": current + 60}, {"exp": current + 4000}, {"exp": True},
                 {"iat": "123"}, {"nbf": "123"}, {"exp": None}]
        for claims in cases:
            with self.subTest(claims=claims):
                await self.assert_error(self.token(claims=claims))

    async def test_required_claims(self):
        current = int(time.time())
        for claim in ("exp", "iat", "iss", "aud", "sub"):
            payload = {"iss": ISSUER, "aud": AUDIENCE, "sub": "analyst", "iat": current, "exp": current + 60}
            del payload[claim]
            with self.subTest(claim=claim):
                await self.assert_error(jwt.encode(payload, self.key, algorithm="RS256", headers={"kid": "one"}))

    async def test_invalid_signature_rejected_without_disclosing_details(self):
        await self.assert_error(self.token(key=self.other_key))

    async def test_headers_algorithms_and_token_supplied_urls_rejected_before_fetch(self):
        for headers in ({"typ": "id_token"}, {"jku": "https://attacker.test/jwks"},
                        {"jwk": public_jwk(self.other_key)}, {"x5u": "https://attacker.test/key"},
                        {"crit": ["test"]}, {"kid": ""}):
            with self.subTest(headers=headers):
                await self.assert_error(self.token(headers=headers))
        await self.assert_error(jwt.encode({"sub": "analyst"}, "synthetic-test-hmac-secret-32-characters", algorithm="HS256", headers={"kid": "one"}))
        await self.assert_error(jwt.encode({"sub": "analyst"}, "", algorithm="none", headers={"kid": "one"}))
        await self.assert_error(jwt.encode({"sub": "analyst"}, self.key, algorithm="RS256"))
        self.assertEqual(len(self.requests), 0)

    async def test_duplicate_json_header_or_claim_rejected(self):
        token = self.token()
        parts = token.split(".")
        def segment(raw):
            return base64.urlsafe_b64encode(raw.encode()).rstrip(b"=").decode()
        parts[0] = segment('{"alg":"RS256","typ":"JWT","kid":"one","kid":"two"}')
        await self.assert_error(".".join(parts))
        parts = token.split(".")
        parts[1] = segment('{"sub":"one","sub":"two"}')
        await self.assert_error(".".join(parts))
        self.assertEqual(len(self.requests), 0)

    async def test_malformed_and_large_tokens(self):
        for token in ("garbage", "a.b.c", "x" * 16_385, "é", ".."):
            with self.subTest(token_size=len(token)):
                await self.assert_error(token)
        self.assertEqual(len(self.requests), 0)

    async def test_rotation_and_unknown_kid_refresh_rate_bound(self):
        await self.verifier.verify(self.token())
        unknown = self.token(headers={"kid": "two"}, key=self.other_key)
        await self.assert_error(unknown)
        await self.assert_error(unknown)
        self.assertEqual(len(self.requests), 1)
        self.document = {"keys": [public_jwk(self.other_key, "two")]}
        self.verifier._last_attempt -= 31
        self.assertEqual(await self.verifier.verify(unknown), "analyst-subject")
        self.assertEqual(len(self.requests), 2)

    async def test_expired_cache_not_used_on_endpoint_outage(self):
        await self.verifier.verify(self.token())
        self.response_status = 503
        self.verifier._expires_at = 0
        self.verifier._last_attempt -= 301
        await self.assert_error(self.token(), 503, "auth_service_unavailable")
        await self.assert_error(self.token(), 503, "auth_service_unavailable")
        self.assertEqual(len(self.requests), 2)

    async def test_known_cached_key_works_during_ttl_after_failed_unknown_refresh(self):
        await self.verifier.verify(self.token())
        self.verifier._last_attempt -= 31
        self.response_status = 503
        await self.assert_error(self.token(headers={"kid": "unknown"}), 503, "auth_service_unavailable")
        self.assertEqual(await self.verifier.verify(self.token()), "analyst-subject")

    async def test_jwks_shape_key_identity_and_key_purpose_validation(self):
        good = public_jwk(self.key)
        variants = [{"keys": []}, {"keys": [good] * 33}, {"keys": [good, good]},
                    {"keys": [{k: v for k, v in good.items() if k != "kid"}]},
                    {"keys": [dict(good, kty="oct", k="abc")]},
                    {"keys": [dict(good, use="enc")]}, {"keys": [dict(good, key_ops=["sign"])]},
                    {"keys": [dict(good, alg="RS512")]}, {"keys": [dict(good, d="private")]},
                    {"keys": [public_jwk(self.weak_key)]}]
        for document in variants:
            with self.subTest(document=document):
                self.document = document
                self.verifier._last_attempt = float("-inf")
                await self.assert_error(self.token(), 503, "auth_service_unavailable")

    async def test_jwks_size_json_redirect_and_status_fail_closed(self):
        for status, content in ((200, b"x" * 65_537), (200, b"not json"),
                                (200, b'{"keys": [], "keys": []}'), (302, b""), (500, b"")):
            with self.subTest(status=status, size=len(content)):
                self.response_status, self.content = status, content
                self.verifier._last_attempt = float("-inf")
                await self.assert_error(self.token(), 503, "auth_service_unavailable")

    async def test_network_failure_is_redacted_and_refresh_attempts_are_bounded(self):
        async def fail(request):
            raise httpx.ConnectError("private network failure details", request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            verifier = OIDCVerifier(OIDCConfig(ISSUER, AUDIENCE, URL), client)
            for _ in range(2):
                with self.assertRaises(Work4ceError) as raised:
                    await verifier.verify(self.token())
                self.assertEqual(raised.exception.status, 503)
                self.assertEqual(str(raised.exception), "auth_service_unavailable")

    async def test_concurrent_refresh_is_single_request(self):
        import asyncio
        result = await asyncio.gather(*(self.verifier.verify(self.token()) for _ in range(10)))
        self.assertEqual(result, ["analyst-subject"] * 10)
        self.assertEqual(len(self.requests), 1)

    async def test_cache_ttl_bound(self):
        before = time.monotonic()
        await self.verifier.verify(self.token())
        self.assertLessEqual(self.verifier._expires_at - before, 300.5)

    def test_configuration_rejects_invalid_url_types_predictably(self):
        for value in (None, 123, True, [], {}, b"https://identity.test/jwks"):
            for field in ("issuer", "jwks_url"):
                arguments = {"issuer": ISSUER, "audience": AUDIENCE, "jwks_url": URL}
                arguments[field] = value
                with self.subTest(field=field, value_type=type(value).__name__):
                    with self.assertRaises(ValueError):
                        OIDCConfig(**arguments)

    def test_configuration_rejects_insecure_or_ambiguous_urls(self):
        for url in ("http://identity.test/jwks", "https:///jwks", "https://u:p@identity.test/jwks",
                    "https://identity.test/jwks?secret=x", "https://identity.test/jwks#fragment",
                    "https://identity.test/jwks?", "https://identity.test/\\jwks", "https://identity.test:bad/jwks"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    OIDCConfig(ISSUER, AUDIENCE, url)
        with self.assertRaises(ValueError):
            OIDCConfig(ISSUER, "", URL)
