"""Authenticated demo API. Production mode intentionally fails closed."""

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

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
    demo_token: str = field(repr=False)
    admin_token: str = field(repr=False)
    database: str = ".local/work4ce.db"
    rest_url: str = "http://127.0.0.1:8766"
    mode: str = "demo"

    def __post_init__(self):
        if self.mode != "demo":
            raise ValueError("Production is disabled until OIDC, PostgreSQL, and deployment controls are implemented")
        if (len(self.demo_token) < 32 or len(self.admin_token) < 32
                or self.demo_token == self.admin_token
                or not self.demo_token.isascii() or not self.admin_token.isascii()):
            raise ValueError("Set distinct ASCII WORK4CE_DEMO_TOKEN and WORK4CE_ADMIN_TOKEN of at least 32 characters")
        # Validate destination before startup, without making a network request.
        RestConnector(self.rest_url)

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(demo_token=os.environ.get("WORK4CE_DEMO_TOKEN", ""),
                   admin_token=os.environ.get("WORK4CE_ADMIN_TOKEN", ""),
                   database=os.environ.get("WORK4CE_DB", ".local/work4ce.db"),
                   rest_url=os.environ.get("WORK4CE_REST_URL", "http://127.0.0.1:8766"),
                   mode=os.environ.get("WORK4CE_MODE", "demo"))


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


def create_app(settings: Settings, gateway: Gateway | None = None) -> FastAPI:
    own_store = gateway is None
    store = gateway.store if gateway else Store(settings.database)
    gateway = gateway or Gateway(store)
    investigator = Investigator(gateway, store)
    slots = asyncio.Semaphore(4)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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
                store.close()
                raise RuntimeError("No demo connector could be verified")
        try:
            yield
        finally:
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
        if token.isascii() and hmac.compare_digest(token, settings.admin_token):
            return ExecutionContext(TENANT, "demo-admin", PERMISSIONS | {"connectors:admin"}, CONNECTORS, True)
        if token.isascii() and hmac.compare_digest(token, settings.demo_token):
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

    @app.post("/investigations", status_code=201)
    async def investigate(body: InvestigationRequest, ctx: Context):
        try:
            async with asyncio.timeout(0.1):
                await slots.acquire()
        except TimeoutError:
            raise Work4ceError("investigation_capacity_exceeded", 429) from None
        try:
            return await investigator.investigate(ctx, body.query, body.limit)
        finally:
            slots.release()

    @app.get("/investigations/{identity}")
    async def report(identity: str, ctx: Context):
        if "investigations:read" not in ctx.permissions:
            raise Work4ceError("permission_denied", 403)
        return store.get(ctx.tenant_id, identity)

    return app
