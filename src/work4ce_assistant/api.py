"""Authenticated demo API. Production mode intentionally fails closed."""

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Header, Query
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .auth import OIDCConfig, OIDCVerifier
from .cases import CaseService
from .connectors import McpConnector, RestConnector
from .contracts import CapabilityManifest, ConnectorManifest, ExecutionContext, Work4ceError
from .fixtures import SEARCH_CAPABILITY
from .gateway import Gateway
from .investigation import Investigator
from .incidents import IncidentService
from .models import FixtureProvider, OpenAICompatibleProvider, ModelGateway
from .reasoning import Reasoner
from .reviews import ReviewService
from .web import PrivateResponses, mount_workbench
from .storage import Store

TENANT = "synthetic-demo"
CONNECTORS = frozenset({"demo-rest", "demo-mcp"})
PERMISSIONS = frozenset({"events:read", "investigations:run", "investigations:read",
                         "responses:read", "responses:propose", "responses:simulate",
                         "cases:read", "cases:coordinate"})
ADMIN_PERMISSIONS = frozenset({"connectors:admin", "investigations:review", "responses:approve", "cases:manage"})
REVIEWER_PERMISSIONS = frozenset({"events:read", "investigations:read", "investigations:review",
                                "responses:read", "responses:approve", "cases:read"})


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
    require_human_review: bool = False
    reasoning_mode: str = "deterministic"
    model_endpoint: str = ""
    model_name: str = ""
    model_api_key: str = field(default="", repr=False)
    model_allow_synthetic_egress: bool = False
    model_input_price: int | None = None
    model_output_price: int | None = None
    max_model_calls: int = 4
    max_model_tokens: int = 36_000
    max_model_cost_microusd: int = 1_000_000

    def __post_init__(self):
        if self.mode != "demo":
            raise ValueError("Production remains disabled pending deployment, isolation, and operational security controls")
        if (type(self.workflow_max_tool_calls) is not int or not 1 <= self.workflow_max_tool_calls <= 8
                or type(self.workflow_duration_seconds) not in (int, float)
                or not .01 <= self.workflow_duration_seconds <= 600):
            raise ValueError("Workflow budgets require 1..8 tool calls and .01..600 seconds")
        if type(self.require_human_review) is not bool:
            raise ValueError("Human review requirement must be an explicit boolean")
        if self.reasoning_mode not in {"deterministic", "fixture", "provider"}:
            raise ValueError("WORK4CE_REASONING_MODE must be deterministic, fixture or provider")
        if (type(self.max_model_calls) is not int or not 1 <= self.max_model_calls <= 8
                or type(self.max_model_tokens) is not int or not 1 <= self.max_model_tokens <= 262144
                or type(self.max_model_cost_microusd) is not int or not 0 <= self.max_model_cost_microusd <= 1_000_000_000):
            raise ValueError("Invalid model call/token/cost budgets")
        if self.reasoning_mode == "provider":
            if self.model_allow_synthetic_egress is not True:
                raise ValueError("Provider mode requires explicit WORK4CE_MODEL_ALLOW_SYNTHETIC_EGRESS=true")
            # Validate trusted route without opening a client or disclosing credentials.
            from urllib.parse import urlsplit
            if any(not isinstance(value, str) for value in (self.model_endpoint,self.model_name,self.model_api_key)):
                raise ValueError("Model endpoint, name and credential must be strings")
            url = urlsplit(self.model_endpoint)
            if (url.scheme != "https" or not url.hostname or url.username is not None or url.password is not None
                    or url.query or url.fragment or "?" in self.model_endpoint or "#" in self.model_endpoint
                    or "\\" in self.model_endpoint or not self.model_endpoint.isascii()
                    or any(c.isspace() for c in self.model_endpoint)
                    or not url.path.endswith("/chat/completions")):
                raise ValueError("Configure an explicit trusted HTTPS chat completions endpoint")
            _ = url.port
            if (not self.model_api_key or not self.model_api_key.isascii()
                    or any(ord(c) <= 32 or ord(c) == 127 for c in self.model_api_key)
                    or not self.model_name or len(self.model_name) > 200 or not self.model_name.isascii()
                    or any(ord(c) < 32 or ord(c) == 127 for c in self.model_name)):
                raise ValueError("Provider mode requires valid WORK4CE_MODEL_NAME and WORK4CE_MODEL_API_KEY")
            if any(type(p) is not int or not 0 <= p <= 1_000_000_000_000 for p in (self.model_input_price,self.model_output_price)):
                raise ValueError("Provider mode requires explicit input/output prices in microUSD per million tokens")
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
                        or subject in seen or not isinstance(role, str) or role not in {"analyst", "admin", "reviewer"}):
                    raise ValueError("Invalid or duplicate OIDC subject role mapping")
                seen.add(subject)
        # Validate destination before startup, without making a network request.
        RestConnector(self.rest_url)

    @classmethod
    def from_environment(cls) -> "Settings":
        review_flag=os.environ.get("WORK4CE_REQUIRE_HUMAN_REVIEW", "false")
        if review_flag not in {"true", "false"}:
            raise ValueError("WORK4CE_REQUIRE_HUMAN_REVIEW must be true or false")
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
                raise ValueError("WORK4CE_OIDC_SUBJECT_ROLES must be a JSON object mapping subjects to analyst/admin/reviewer") from None
        return cls(demo_token=os.environ.get("WORK4CE_DEMO_TOKEN", ""),
                   admin_token=os.environ.get("WORK4CE_ADMIN_TOKEN", ""),
                   database=os.environ.get("WORK4CE_DB", ".local/work4ce.db"),
                   rest_url=os.environ.get("WORK4CE_REST_URL", "http://127.0.0.1:8766"),
                   mode=os.environ.get("WORK4CE_MODE", "demo"),
                   auth_mode=auth_mode, oidc_config=config, oidc_subject_roles=roles,
                   workflow_max_tool_calls=int(os.environ.get("WORK4CE_MAX_TOOL_CALLS", "2")),
                   workflow_duration_seconds=float(os.environ.get("WORK4CE_INVESTIGATION_TIMEOUT_SECONDS", "120")),
                   require_human_review=(review_flag == "true"),
                   reasoning_mode=os.environ.get("WORK4CE_REASONING_MODE", "deterministic"),
                   model_endpoint=os.environ.get("WORK4CE_MODEL_ENDPOINT", ""),
                   model_name=os.environ.get("WORK4CE_MODEL_NAME", ""),
                   model_api_key=os.environ.get("WORK4CE_MODEL_API_KEY", ""),
                   model_allow_synthetic_egress=os.environ.get("WORK4CE_MODEL_ALLOW_SYNTHETIC_EGRESS", "false") == "true",
                   model_input_price=int(os.environ["WORK4CE_MODEL_INPUT_PRICE_MICROUSD_PER_MILLION"]) if "WORK4CE_MODEL_INPUT_PRICE_MICROUSD_PER_MILLION" in os.environ else None,
                   model_output_price=int(os.environ["WORK4CE_MODEL_OUTPUT_PRICE_MICROUSD_PER_MILLION"]) if "WORK4CE_MODEL_OUTPUT_PRICE_MICROUSD_PER_MILLION" in os.environ else None,
                   max_model_calls=int(os.environ.get("WORK4CE_MAX_MODEL_CALLS", "4")),
                   max_model_tokens=int(os.environ.get("WORK4CE_MAX_MODEL_TOKENS", "36000")),
                   max_model_cost_microusd=int(os.environ.get("WORK4CE_MAX_MODEL_COST_MICROUSD", "1000000")))


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


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    decision: Literal["approved","rejected"]
    comment: str = Field(default="",max_length=2000)


class ReviewDecision(Decision):
    review_id: UUID = Field(strict=False)


class SimulationParameters(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    duration_minutes: int = Field(ge=1,le=60)


class ResponseProposal(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    investigation_id: UUID = Field(strict=False)
    action: Literal["endpoint.isolate"]
    target: Literal["demo-host-1","demo-host-2"]
    parameters: SimulationParameters
    lifetime_seconds: int = Field(default=300,ge=1,le=900)


class ApprovalUse(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    approval_id: UUID = Field(strict=False)


class CaseRevision(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    expected_revision: int = Field(ge=0,le=2_147_483_646)


class CaseAssignment(CaseRevision):
    assignee: str | None = Field(min_length=1,max_length=256)


class CaseEscalation(CaseRevision):
    reason: str = Field(min_length=1,max_length=1000)


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    investigation_id: UUID = Field(strict=False)
    title: str = Field(min_length=1,max_length=200)
    description: str = Field(default="",max_length=2000)
    severity: Literal["low","medium","high","critical"]


class IncidentRevision(BaseModel):
    model_config = ConfigDict(extra="forbid",strict=True)
    expected_revision: int = Field(ge=1,le=200)


class IncidentStatus(IncidentRevision):
    status: Literal["open","in_progress","resolved","closed"]
    comment: str = Field(default="",max_length=2000)


class IncidentNote(IncidentRevision):
    body: str = Field(min_length=1,max_length=2000)
    evidence_ids: list[Annotated[str,Field(min_length=1,max_length=128)]] = Field(default_factory=list,max_length=10)


def create_app(settings: Settings, gateway: Gateway | None = None, *, verifier: OIDCVerifier | None = None, reasoner: Reasoner | None = None) -> FastAPI:
    own_store = gateway is None
    store = gateway.store if gateway else Store(settings.database)
    gateway = gateway or Gateway(store)
    try:
        own_reasoner = settings.reasoning_mode != "deterministic" and reasoner is None
        if own_reasoner:
            provider = FixtureProvider() if settings.reasoning_mode == "fixture" else OpenAICompatibleProvider(
                settings.model_endpoint, settings.model_name, settings.model_api_key,
                input_price_microusd_per_million=settings.model_input_price,
                output_price_microusd_per_million=settings.model_output_price)
            reasoner = Reasoner(ModelGateway(provider), store, max_calls=settings.max_model_calls,
                                max_tokens=settings.max_model_tokens,max_cost_microusd=settings.max_model_cost_microusd)
        investigator = Investigator(gateway, store, max_tool_calls=settings.workflow_max_tool_calls,
                                    duration_seconds=settings.workflow_duration_seconds, reasoner=reasoner,
                                    require_review=settings.require_human_review)
    except Exception:
        if own_store:
            store.close()
        raise
    reviews = ReviewService(store,gateway)
    assignees = (frozenset({'demo-analyst','demo-admin'}) if settings.auth_mode=='demo' else
                 frozenset(subject for subject,role in settings.oidc_subject_roles if role in {'analyst','admin'}))
    cases = CaseService(store,TENANT,assignees)
    incidents = IncidentService(cases)
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
            try:
                if own_verifier and verifier is not None:
                    await verifier.close()
            finally:
                try:
                    if own_reasoner and reasoner is not None:
                        await reasoner.close()
                finally:
                    if own_store:
                        store.close()

    app = FastAPI(title="Work4ce Assistant", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit)
    app.add_middleware(PrivateResponses)
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
            permissions = (REVIEWER_PERMISSIONS if role == "reviewer" else
                           PERMISSIONS | ADMIN_PERMISSIONS if role == "admin" else PERMISSIONS)
            return ExecutionContext(TENANT, subject, permissions, CONNECTORS, True)
        if token and token.isascii() and hmac.compare_digest(token, settings.admin_token):
            return ExecutionContext(TENANT, "demo-admin", PERMISSIONS | ADMIN_PERMISSIONS, CONNECTORS, True)
        if token and token.isascii() and hmac.compare_digest(token, settings.demo_token):
            return ExecutionContext(TENANT, "demo-analyst", PERMISSIONS, CONNECTORS, True)
        store.audit(TENANT, "unauthenticated", "authentication", "api", "denied")
        raise Work4ceError("authentication_required", 401)

    Context = Annotated[ExecutionContext, Depends(context)]

    @app.exception_handler(Work4ceError)
    async def error_handler(request: Request, error: Work4ceError):
        return JSONResponse({"error": error.code}, status_code=error.status,
                            headers={"WWW-Authenticate": "Bearer"} if error.status == 401 else {})

    @app.get("/me")
    async def me(ctx: Context):
        return {"subject":ctx.subject,"tenant_id":ctx.tenant_id,"permissions":sorted(ctx.permissions),
                "synthetic":ctx.synthetic,"review_required":settings.require_human_review,
                "model_mode":settings.reasoning_mode}

    @app.get("/investigations")
    async def investigations(ctx: Context,limit: int=Query(default=50,ge=1,le=100)):
        if "investigations:read" not in ctx.permissions:
            raise Work4ceError("permission_denied",403)
        return store.list_investigations(ctx.tenant_id,
            subject=None if "investigations:review" in ctx.permissions else ctx.subject,limit=limit)

    @app.get("/investigations/history")
    async def investigation_history(ctx: Context,limit: int=Query(default=50,ge=1,le=100),
                                    cursor: str | None = None):
        if "investigations:read" not in ctx.permissions:
            raise Work4ceError("permission_denied",403)
        return store.page_investigations(ctx.tenant_id,
            subject=None if "investigations:review" in ctx.permissions else ctx.subject,
            limit=limit,cursor=cursor)

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": "demo", "synthetic": True}

    @app.get("/case-assignees")
    async def case_assignees(ctx: Context):
        return cases.directory(ctx)

    @app.get("/cases")
    async def case_queue(ctx: Context,limit: int=Query(default=50,ge=1,le=100)):
        return cases.list(ctx,limit=limit)

    @app.get("/investigations/{identity}/case")
    async def case_state(identity: UUID,ctx: Context):
        return cases.get(ctx,str(identity))

    @app.post("/investigations/{identity}/case/assignment")
    async def case_assignment(identity: UUID,body: CaseAssignment,ctx: Context):
        return cases.assign(ctx,str(identity),body.expected_revision,body.assignee)

    @app.post("/investigations/{identity}/case/escalation")
    async def case_escalation(identity: UUID,body: CaseEscalation,ctx: Context):
        return cases.escalate(ctx,str(identity),body.expected_revision,body.reason)

    @app.post("/investigations/{identity}/case/acknowledge")
    async def case_acknowledgment(identity: UUID,body: CaseRevision,ctx: Context):
        return cases.acknowledge(ctx,str(identity),body.expected_revision)

    @app.post("/incidents",status_code=201)
    async def create_incident(body: IncidentCreate,ctx: Context):
        return incidents.create(ctx,str(body.investigation_id),body.title,body.description,body.severity)

    @app.get("/incidents")
    async def incident_queue(ctx: Context,limit: int=Query(default=50,ge=1,le=100)):
        return incidents.list(ctx,limit=limit)

    @app.get("/investigations/{identity}/incident")
    async def investigation_incident(identity: UUID,ctx: Context):
        return incidents.for_investigation(ctx,str(identity))

    @app.get("/incidents/{identity}")
    async def incident_detail(identity: UUID,ctx: Context):
        return incidents.get(ctx,str(identity))

    @app.get("/incidents/{identity}/activity")
    async def incident_activity(identity: UUID,ctx: Context):
        return incidents.activity(ctx,str(identity))

    @app.post("/incidents/{identity}/status")
    async def incident_status(identity: UUID,body: IncidentStatus,ctx: Context):
        return incidents.transition(ctx,str(identity),body.expected_revision,body.status,body.comment)

    @app.post("/incidents/{identity}/notes")
    async def incident_note(identity: UUID,body: IncidentNote,ctx: Context):
        return incidents.add_note(ctx,str(identity),body.expected_revision,body.body,body.evidence_ids)

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
        response = {"id": state["id"], "status": state["state"], "checkpointed": state["checkpoint"] is not None,
                    "tool_calls": state["tool_calls"], "max_tool_calls": state["max_tool_calls"],
                    "deadline": state["deadline"]}
        if state["review_required"]:
            response["execution_status"] = state["state"]
        if state["state"] == "completed":
            report=store.get(ctx.tenant_id,identity)
            if "review" in report:
                response["execution_status"]=state["state"]
                response["status"]=report["status"]
                response["review"]=report["review"]
        if state["reasoning_config_hash"] is not None:
            response["model_usage"] = store.model_usage(ctx.tenant_id, ctx.subject, identity)
        return response

    @app.post("/investigations/{identity}/review")
    async def request_review(identity: UUID, ctx: Context):
        return reviews.request_review(ctx,str(identity))

    @app.get("/investigations/{identity}/review")
    async def get_review(identity: UUID, ctx: Context):
        return reviews.get_review(ctx,str(identity))

    @app.post("/investigations/{identity}/review/decision")
    async def review_decision(identity: UUID, body: ReviewDecision, ctx: Context):
        return reviews.decide_review(ctx,str(identity),str(body.review_id),body.decision,body.comment)

    @app.get("/reviews")
    async def review_queue(ctx: Context):
        return reviews.list_reviews(ctx)

    @app.post("/responses",status_code=201)
    async def propose_response(body: ResponseProposal,ctx: Context):
        return reviews.propose(ctx,str(body.investigation_id),body.action,body.target,
                               body.parameters.model_dump(),lifetime_seconds=body.lifetime_seconds)

    @app.get("/responses")
    async def responses(ctx: Context):
        return reviews.list_responses(ctx)

    @app.get("/responses/{identity}")
    async def get_response(identity: UUID,ctx: Context):
        return reviews.get_response(ctx,str(identity))

    @app.post("/responses/{identity}/decision")
    async def response_decision(identity: UUID,body: Decision,ctx: Context):
        return reviews.decide_response(ctx,str(identity),body.decision,body.comment)

    @app.post("/responses/{identity}/revoke")
    async def revoke_response(identity: UUID,ctx: Context):
        return reviews.revoke(ctx,str(identity))

    @app.post("/responses/{identity}/simulate")
    async def simulate_response(identity: UUID,body: ApprovalUse,ctx: Context):
        return reviews.simulate(ctx,str(identity),str(body.approval_id))

    @app.get("/investigations/{identity}")
    async def report(identity: str, ctx: Context):
        if "investigations:read" not in ctx.permissions:
            raise Work4ceError("permission_denied", 403)
        result=store.get(ctx.tenant_id, identity)
        review=result.get("review")
        if (review is not None and review["requester"]!=ctx.subject
                and "investigations:review" not in ctx.permissions):
            # Tenant report-read access does not grant access to private review notes.
            result={key:value for key,value in result.items() if key!="review"}
        return result

    mount_workbench(app)
    return app
