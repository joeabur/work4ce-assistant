"""Authenticated demo API. Production mode intentionally fails closed."""

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Header
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .auth import OIDCConfig, OIDCVerifier
from .connectors import McpConnector, RestConnector
from .contracts import CapabilityManifest, ConnectorManifest, ExecutionContext, Work4ceError
from .fixtures import SEARCH_CAPABILITY
from .gateway import Gateway
from .investigation import Investigator
from .storage import Store

TENANT = "synthetic-demo"
CONNECTORS = frozenset({"demo-rest", "demo-mcp"})
PERMISSIONS = frozenset({"events:read", "investigations:run", "investigations:read"})


@dataclass(frozen=True)
class Settings:
    demo_token: str = field(default="", repr=False)
    admin_token: str = field(default="", repr=False)
    database: str = field(default=".local/work4ce.db", repr=False)
    rest_url: str = "http://127.0.0.1:8766"
    mode: str = "demo"
    auth_mode: str = "demo"
    oidc_config: OIDCConfig | None = None
    oidc_subject_roles: tuple[tuple[str, str], ...] = ()
    workflow_max_tool_calls: int = 2
    workflow_duration_seconds: float = 120

    def __post_init__(self):
        if self.mode != "demo":
            raise ValueError("Production remains disabled pending deployment, isolation, and operational security controls")
        if (type(self.workflow_max_tool_calls) is not int or not 1 <= self.workflow_max_tool_calls <= 8
                or type(self.workflow_duration_seconds) not in (int, float)
                or not .01 <= self.workflow_duration_seconds <= 600):
            raise ValueError("Workflow budgets require 1..8 tool calls and .01..600 seconds")
        if self.auth_mode not in {"demo", "oidc"}:
            raise ValueError("WORK4CE_AUTH_MODE must be demo or oidc")
        if self.auth_mode == "demo" and (len(self.demo_token) < 32 or len(self.admin_token) < 32
                or self.demo_token == self.admin_token
                or not self.demo_token.isascii() or not self.admin_token.isascii()):
            raise ValueError("Set distinct ASCII WORK4CE_DEMO_TOKEN and WORK4CE_ADMIN_TOKEN of at least 32 characters")
        if self.auth_mode == "oidc":
            if not isinstance(self.oidc_config, OIDCConfig) or not self.oidc_subject_roles:
                raise ValueError("OIDC requires trusted issuer, audience, JWKS URL and server-configured subject roles")
            if len(self.oidc_subject_roles) > 100:
                raise ValueError("OIDC subject mapping exceeds limit")
            seen = set()
            for subject, role in self.oidc_subject_roles:
                if (not isinstance(subject, str) or not 1 <= len(subject) <= 256
                        or subject in seen or not isinstance(role, str) or role not in {"analyst", "admin"}):
                    raise ValueError("Invalid or duplicate OIDC subject role mapping")
                seen.add(subject)
        # Validate destination before startup, without making a network request.
        RestConnector(self.rest_url)

    @classmethod
    def from_environment(cls) -> "Settings":
        auth_mode = os.environ.get("WORK4CE_AUTH_MODE", "demo")
        config = None
        roles = ()
        if auth_mode == "oidc":
            config = OIDCConfig(issuer=os.environ.get("WORK4CE_OIDC_ISSUER", ""),
                                audience=os.environ.get("WORK4CE_OIDC_AUDIENCE", ""),
                                jwks_url=os.environ.get("WORK4CE_OIDC_JWKS_URL", ""))
            try:
                def unique_mapping(pairs):
                    mapping = {}
                    for subject, role in pairs:
                        if subject in mapping:
                            raise ValueError("Duplicate OIDC subject")
                        mapping[subject] = role
                    return mapping
                value = json.loads(os.environ.get("WORK4CE_OIDC_SUBJECT_ROLES", "{}"), object_pairs_hook=unique_mapping)
                if not isinstance(value, dict):
                    raise ValueError()
                roles = tuple(value.items())
            except (TypeError, ValueError):
                raise ValueError("WORK4CE_OIDC_SUBJECT_ROLES must be a JSON object mapping subjects to analyst/admin") from None
        return cls(demo_token=os.environ.get("WORK4CE_DEMO_TOKEN", ""),
                   admin_token=os.environ.get("WORK4CE_ADMIN_TOKEN", ""),
                   database=os.environ.get("WORK4CE_DB", ".local/work4ce.db"),
                   rest_url=os.environ.get("WORK4CE_REST_URL", "http://127.0.0.1:8766"),
                   mode=os.environ.get("WORK4CE_MODE", "demo"),
                   auth_mode=auth_mode, oidc_config=config, oidc_subject_roles=roles,
                   workflow_max_tool_calls=int(os.environ.get("WORK4CE_MAX_TOOL_CALLS", "2")),
                   workflow_duration_seconds=float(os.environ.get("WORK4CE_INVESTIGATION_TIMEOUT_SECONDS", "120")))


class BodyLimit:
    """Bound bytes before framework JSON parsing, including chunked requests."""
    def __init__(self, app, max_bytes: int = 16_384):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=5)
            except TimeoutError:
                return await JSONResponse({"error": "request_timeout"}, status_code=408)(scope, receive, send)
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                return await JSONResponse({"error": "request_too_large"}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        consumed = False
        async def bounded_receive():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, bounded_receive, send)


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=100)
    defer: bool = False


def create_app(settings: Settings, gateway: Gateway | None = None, *, verifier: OIDCVerifier | None = None) -> FastAPI:
    own_store = gateway is None
    store = gateway.store if gateway else Store(settings.database)
    gateway = gateway or Gateway(store)
    investigator = Investigator(gateway, store, max_tool_calls=settings.workflow_max_tool_calls,
                                duration_seconds=settings.workflow_duration_seconds)
    slots = asyncio.Semaphore(4)
    own_verifier = settings.auth_mode == "oidc" and verifier is None
    if own_verifier:
        verifier = OIDCVerifier(settings.oidc_config)
    subject_roles = dict(settings.oidc_subject_roles)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            if own_store:
                for identity, protocol, adapter in [
                    ("demo-rest", "rest", RestConnector(settings.rest_url)),
                    ("demo-mcp", "mcp", McpConnector()),
                ]:
                    try:
                        await gateway.register(ConnectorManifest(
                            connector_id=identity, name=identity, protocol=protocol, tenant_id=TENANT,
                            synthetic=True, capability=CapabilityManifest(**SEARCH_CAPABILITY)), adapter, reviewed=True)
                    except Work4ceError:
                        store.audit(TENANT, "bootstrap", "connector.register", identity, "failed")
                if not gateway.list_connectors(ExecutionContext(TENANT, "bootstrap", PERMISSIONS, CONNECTORS, True)):
                    raise RuntimeError("No demo connector could be verified")
            yield
        finally:
            if own_verifier and verifier is not None:
                await verifier.close()
            if own_store:
                store.close()

    app = FastAPI(title="Work4ce Assistant", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit)
    app.state.gateway = gateway
    app.state.store = store
    bearer = HTTPBearer(auto_error=False)

    async def context(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> ExecutionContext:
        token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
        if settings.auth_mode == "oidc":
            try:
                subject = await verifier.verify(token)
            except Work4ceError as error:
                store.audit(TENANT, "unauthenticated", "authentication", "api", "unavailable" if error.status == 503 else "denied")
                raise
            role = subject_roles.get(subject)
            if role is None:
                store.audit(TENANT, "unmapped-subject", "authentication", "api", "denied")
                raise Work4ceError("permission_denied", 403)
            permissions = PERMISSIONS | {"connectors:admin"} if role == "admin" else PERMISSIONS
            return ExecutionContext(TENANT, subject, permissions, CONNECTORS, True)
        if token and token.isascii() and hmac.compare_digest(token, settings.admin_token):
            return ExecutionContext(TENANT, "demo-admin", PERMISSIONS | {"connectors:admin"}, CONNECTORS, True)
        if token and token.isascii() and hmac.compare_digest(token, settings.demo_token):
            return ExecutionContext(TENANT, "demo-analyst", PERMISSIONS, CONNECTORS, True)
        store.audit(TENANT, "unauthenticated", "authentication", "api", "denied")
        raise Work4ceError("authentication_required", 401)

    Context = Annotated[ExecutionContext, Depends(context)]

    @app.exception_handler(Work4ceError)
    async def error_handler(request: Request, error: Work4ceError):
        return JSONResponse({"error": error.code}, status_code=error.status,
                            headers={"WWW-Authenticate": "Bearer"} if error.status == 401 else {})

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "demo", "synthetic": True}

    @app.get("/ready")
    async def ready(ctx: Context):
        available = []
        for item in gateway.list_connectors(ctx):
            if item["enabled"]:
                entry = gateway._entries[item["connector_id"]]
                try:
                    async with asyncio.timeout(3):
                        if await entry.connector.health():
                            available.append(item["connector_id"])
                except Exception:
                    pass
        if not available:
            raise Work4ceError("no_healthy_connector", 503)
        return {"status": "ready", "connectors": available, "synthetic": True}

    @app.get("/capabilities")
    async def capabilities(ctx: Context):
        return gateway.capabilities(ctx)

    @app.get("/connectors")
    async def connectors(ctx: Context):
        return gateway.list_connectors(ctx)

    @app.post("/connectors/{identity}/disable")
    async def disable(identity: str, ctx: Context):
        gateway.disable(ctx, identity)
        return {"connector_id": identity, "enabled": False}

    async def bounded_run(operation):
        try:
            async with asyncio.timeout(0.1):
                await slots.acquire()
        except TimeoutError:
            raise Work4ceError("investigation_capacity_exceeded", 429) from None
        try:
            return await operation()
        finally:
            slots.release()

    @app.post("/investigations", status_code=201)
    async def investigate(body: InvestigationRequest, ctx: Context,
                          idempotency_key: Annotated[str | None, Header(max_length=128)] = None):
        if body.defer:
            async def enqueue():
                return investigator.enqueue(ctx, body.query, body.limit, idempotency_key=idempotency_key)
            state = await bounded_run(enqueue)
            return JSONResponse({"id": state["id"], "status": state["state"]}, status_code=202)
        return await bounded_run(lambda: investigator.investigate(ctx, body.query, body.limit,
                                                                  idempotency_key=idempotency_key))

    @app.post("/investigations/{identity}/resume")
    async def resume(identity: str, ctx: Context):
        return await bounded_run(lambda: investigator.resume(ctx, identity))

    @app.post("/investigations/{identity}/cancel")
    async def cancel(identity: str, ctx: Context):
        return await investigator.cancel(ctx, identity)

    @app.get("/investigations/{identity}/state")
    async def workflow_state(identity: str, ctx: Context):
        if "investigations:read" not in ctx.permissions:
            raise Work4ceError("permission_denied", 403)
        state = store.get_workflow(ctx.tenant_id, ctx.subject, identity)
        return {"id": state["id"], "status": state["state"], "checkpointed": state["checkpoint"] is not None,
                "tool_calls": state["tool_calls"], "max_tool_calls": state["max_tool_calls"],
                "deadline": state["deadline"]}

    @app.get("/investigations/{identity}")
    async def report(identity: str, ctx: Context):
        if "investigations:read" not in ctx.permissions:
            raise Work4ceError("permission_denied", 403)
        return store.get(ctx.tenant_id, identity)

    return app
