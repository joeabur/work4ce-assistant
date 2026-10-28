# Master specification implementation status

This matrix maps the requested product to actual delivery. It is a scope and gap record, not an architecture-completion or production-readiness claim. The authoritative request is preserved unchanged in `MASTER_SPECIFICATION.md`. See `release-readiness.md` for executed test counts.

The current product is a deterministic, synthetic, read-only investigation foundation. It is not an autonomous AI SOC platform yet. The first vertical slice and PostgreSQL foundation are integration-tested; the OIDC adapter is fixture-tested with real signatures and mocked HTTPS. Durable deterministic workflows are integration-tested: the complete 120-test PostgreSQL/SQLite suite passed with zero skips, including real worker termination after checkpoint commit and explicit resume without another REST search.

## Requested foundations and delivery

| Master sections | Current delivery | Remaining material requirements |
|---|---|---|
| 0–3: identity and architecture | Working modular Python package, capability-oriented investigator, protocol-independent gateway | Full enterprise platform and broad integration categories remain roadmap scope |
| 4–5: stack and boundaries | FastAPI/Pydantic/JSON Schema, SQLAlchemy/Alembic, official MCP SDK, trusted backend policy | LangGraph, frontend, enterprise identity/deployment/observability, provider-independent model runtime |
| 6–8: integrations, registry and CDK | Typed connector/manifests, reviewed registration, compatible schemas, generic capability names, explicit tenant/connector grants, real reference adapters | Complete CDK packaging/signing, external plugin isolation, credential lifecycle, arbitrary production scopes/protocols |
| 9: MCP | Official SDK local stdio client/server, reviewed tool discovery and poisoning checks | Remote OAuth, broader transport/protocol compatibility and production server administration |
| 10: agent | Deterministic bounded collection/reporting workflow with durable read-boundary checkpoints | AI planning, hypothesis evaluation, autonomous correlation, human review and full specialist/runtime design |
| 11: model gateway | No provider is connected | Routing, structured model outputs, cost/token accounting, provider retries, redaction and evaluations |
| 12–13: SOC/evidence | Literal-query synthetic telemetry, normalized source-attributed evidence, hashes and stored reports | Full OCSF model, triage, hunting, intelligence, detections, incident lifecycle and evidence governance |
| 14–16: policy/security/privacy | Independent read-only authorization, synthetic tenant isolation, JWT verification option, manifest/result checks | Sensitive execution approvals, real multi-tenant identity, production TLS/RLS, privacy/retention/residency controls and formal security review |
| 17–18: reliability/cost | Audit, liveness/readiness, deadlines and tool-call bounds | Distributed observability, operational alerts, performance evidence, provider cost control |
| 19–22: user experience/demo/CLI | Local demo API/CLI, actual REST/MCP fixtures, guided setup | Dashboard, browser login/first-run wizard, broad labeled scenarios and complete CLI surface |
| 23–24: repository/docs | Modular source/tests, exact specification, agent guidance, progress/threat/readiness records | Ongoing documentation verification as implementation expands |
| 25–27: tests/CI | Core, transport, OIDC fixture, storage/migration and real end-to-end tests; CI workflow prepared | Full A–J acceptance, AI evaluations, complete security/supply-chain scans, remote CI evidence |
| 28–31: deployment/roadmap/readiness | Digest-pinned development PostgreSQL service, isolated database runner, explicit production no-go | Backend deployment validation, secure enterprise operations and most later roadmap phases |
| 32–33: first vertical slice | Authenticated request → deterministic investigator → registry/resolver/policy → REST or MCP → evidence → persisted report, including connector replacement | No production-ready or complete AI platform claim; continue incremental acceptance gates |

## Section 10.2 — Durable execution

| Requirement | Current implementation and practical limit |
|---|---|
| Typed investigation state | Validated request/evidence/checkpoint models plus durable workflow state. Typed state does not turn the deterministic engine into an LLM agent. |
| Persistent checkpoints | Validated connector result and attributed evidence are stored with a hash at the read boundary before final report commit. |
| Resume after restart | Explicit authenticated resume retrieves durable state after lease expiry/release; a saved checkpoint is reauthorized and reused without another query. No automatic background scheduler exists. |
| Cancellation | Explicit cancellation invalidates the worker lease and fences later checkpoint/report writes. It does not guarantee termination of remote I/O already in flight. Task interruption preserves recoverable state. |
| Execution deadlines | Persisted default 120-second wall-clock deadline includes queue time. A resume cannot reset it. Each execution attempt is also bounded; clocks and synchronous storage still need operational hardening. |
| Bounded retries | Tool-call reservations are persisted before each actual connector invocation, including fallback. An interrupted read without a checkpoint may be repeated within the remaining budget. This is not exactly-once execution. |
| Partial results | The single read's collected checkpoint survives interruption/finalization failure. Multi-step partial-result merging and analyst-visible coverage aggregation are not implemented. |
| Human review checkpoints | Unimplemented. Report assessment requests analyst review but there is no durable approval/review workflow. |
| Execution tracing | Structured audit rows and checkpoint/source metadata exist. Distributed OpenTelemetry traces and operational dashboards are unimplemented. |
| Idempotency | Header keys are scoped by tenant and subject, bound to query/limit/configured budgets. Replays reuse stable committed evidence/report identifiers. Changed arguments conflict. |

## Section 10.3 — Execution limits

| Requested limit | Current implementation and gap |
|---|---|
| Reasoning steps | No model reasoning loop exists; only the deterministic read/report stages. A general planning-step budget is unimplemented. |
| Tool calls | Default two actual invocations per workflow, persisted across retries, crashes and connector fallback. Constructor configuration supports one through eight; API clients cannot enlarge it. |
| Investigation duration | Default 120 seconds persisted at enqueue, including waiting time; configurable backend range 0.01–600 seconds. No deadline reset on resume. |
| Token expenditure | Unimplemented: no model provider/token use exists. |
| Investigation cost | Unimplemented: no model price/cost gateway exists. |
| Query scope | Strict literal query length and event-limit schemas; synthetic-events policy only. No arbitrary backend query language. |
| Result size | Connector/gateway schema and byte bounds plus bounded checkpoint storage. |
| Concurrent investigations | Four API execution slots; deferred enqueue also uses the admission guard. Database leases prevent concurrent workers completing the same workflow. This is not a fleet-wide concurrency scheduler. |
| Queued work | Maximum 100 nonterminal workflows per tenant/subject, enforced atomically. Terminal/audit retention and broader request-rate control remain future work. |

## Phase 5 quality gate

Phase 5 remains **in_progress** despite the passing 120-test integration suite. This increment implements deterministic orchestration state, checkpoints, manual resume, idempotency, lease fencing, deadlines, persisted invocation budgets and explicit cancellation. It does not implement an AI planning runtime, model-provider gateway, human review checkpoints, general multi-step recovery, token/cost controls or distributed execution observability. Passing durable workflow tests does not complete Phase 5 or sensitive response acceptance H.
