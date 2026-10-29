# Master specification implementation status

This matrix maps the requested product to actual delivery. It is a scope and gap record, not an architecture-completion or production-readiness claim. The authoritative request is preserved unchanged in `MASTER_SPECIFICATION.md`. See `release-readiness.md` for executed test counts.

The current product is a synthetic, read-only investigation foundation with deterministic default behavior and optional constrained model assistance. It is not an autonomous AI SOC platform yet. The first vertical slice and PostgreSQL foundation are integration-tested; the OIDC adapter is fixture-tested with real signatures and mocked HTTPS. Durable deterministic workflows are integration-tested: the complete 326-test PostgreSQL/SQLite suite passed with zero skips, including real worker termination after checkpoint commit and explicit resume without another REST search.

## Requested foundations and delivery

| Master sections | Current delivery | Remaining material requirements |
|---|---|---|
| 0–3: identity and architecture | Working modular Python package, capability-oriented investigator, protocol-independent gateway | Full enterprise platform and broad integration categories remain roadmap scope |
| 4–5: stack and boundaries | FastAPI/Pydantic/JSON Schema, SQLAlchemy/Alembic, official MCP SDK, trusted backend policy | LangGraph, complete dashboard coverage, enterprise identity/deployment/observability, live model-runtime verification |
| 6–8: integrations, registry and CDK | Typed connector/manifests, reviewed registration, compatible schemas, generic capability names, explicit tenant/connector grants, real reference adapters | Complete CDK packaging/signing, external plugin isolation, credential lifecycle, arbitrary production scopes/protocols |
| 9: MCP | Official SDK local stdio client/server, reviewed tool discovery and poisoning checks | Remote OAuth, broader transport/protocol compatibility and production server administration |
| 10: agent | Deterministic bounded collection/reporting workflow with durable read-boundary checkpoints | General AI planning, hypothesis evaluation, autonomous correlation, multi-step review and full specialist/runtime design |
| 11: model gateway | Typed provider contract, offline fixture, configured HTTPS adapter, strict plans/quotations, retries/circuit, durable usage and cache | Live-provider verification, broader routing/health, tokenizer-aware admission, enterprise redaction and independent AI evaluations |
| 12–13: SOC/evidence | Literal-query synthetic telemetry, source-attributed evidence/reports, assignment/escalation, single-source incident lifecycle and evidence-linked note history | Full OCSF model, triage, hunting, intelligence, detections, full incident lifecycle and evidence governance |
| 14–16: policy/security/privacy | Independent read-only authorization, synthetic tenant isolation, JWT verification option, manifest/result checks | Live sensitive-executor integration, real multi-tenant identity, production TLS/RLS, privacy/retention/residency controls and formal security review |
| 17–18: reliability/storage | SQLAlchemy/PostgreSQL, migrations, audit, deadlines, invocation/model usage bounds | Distributed observability, operational alerts, performance/recovery evidence, secure production storage |
| 19–22: user experience/demo/CLI | Local demo API/CLI, actual REST/MCP fixtures, Next.js workbench using real APIs, evidence citations, review/response queues and connector status | Remaining SOC modules, OIDC redirect login/first-run wizard, broad labeled scenarios and complete CLI surface |
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
| Human review checkpoints | Durable post-report acceptance gate, separate reviewer identity, expiry/refresh and rejection implemented. General multi-step/pre-tool human review remains incomplete. |
| Execution tracing | Structured audit rows and checkpoint/source metadata exist. Distributed OpenTelemetry traces and operational dashboards are unimplemented. |
| Idempotency | Header keys are scoped by tenant and subject, bound to query/limit/configured budgets. Replays reuse stable committed evidence/report identifiers. Changed arguments conflict. |

## Section 10.3 — Execution limits

| Requested limit | Current implementation and gap |
|---|---|
| Reasoning steps | Optional assistance performs one bounded search plan and one quotation assessment. A general multi-step reasoning loop is unimplemented. |
| Tool calls | Default two actual invocations per workflow, persisted across retries, crashes and connector fallback. Constructor configuration supports one through eight; API clients cannot enlarge it. |
| Investigation duration | Default 120 seconds persisted at enqueue, including waiting time; configurable backend range 0.01–600 seconds. No deadline reset on resume. |
| Token expenditure | Conservative reservations and reported usage persist per attempt; independent tokenizer/provider accounting remains incomplete. |
| Investigation cost | Configured-price reservations and calculated cost persist; live price catalogs and independent billing verification remain incomplete. |
| Query scope | Strict literal query length and event-limit schemas; synthetic-events policy only. No arbitrary backend query language. |
| Result size | Connector/gateway schema and byte bounds plus bounded checkpoint storage. |
| Concurrent investigations | Four API execution slots; deferred enqueue also uses the admission guard. Database leases prevent concurrent workers completing the same workflow. This is not a fleet-wide concurrency scheduler. |
| Queued work | Maximum 100 nonterminal workflows per tenant/subject, enforced atomically. Terminal/audit retention and broader request-rate control remain future work. |

## Phase 5 quality gate

Phase 5 remains **in_progress** despite the passing 326-test suite. Implemented controls include durable orchestration, manual recovery, invocation budgets and optional structured plan/quotation assistance with persistent model usage. Live-model verification, general multi-step reasoning, coordinated review, tokenizer/billing assurance and distributed execution observability remain incomplete. Passing durable workflow tests does not complete Phase 5 or sensitive response acceptance H.

The structured model increment implements part of section 11 and Phase 5. The default and offline fixture are deterministic; the HTTP adapter is fixture-tested. No live model, broad SOC reasoning accuracy, production deployment or response approval completion is claimed.

Migration `0004_reviews` implements durable human report acceptance and synthetic action approvals. Requester/reviewer separation, exact request/report binding, current source grants, expiry, revocation and single use pass on SQLite/PostgreSQL. Approval acceptance H is only exercised against a no-effect dry-run consumer, so a live privileged executor and production response validation remain incomplete.

## Section 19 / Phase 10 — First dashboard slice

Next.js, React and TypeScript implement investigations, evidence timelines/citations, independent report review, separate synthetic response approvals and connector status. API identity drives visible controls, while backend policy authorizes every operation. Analysts list their own cases; reviewers list cases in their tenant. GET `/me` and bounded GET `/investigations` expose summaries without private notes or approval nonces. The static export is packaged with FastAPI under `/workbench/`.

Four Chromium checks passed: analyst → reviewer → action approval → original-analyst dry run; memory-only sessions and literal untrusted markup; mobile usability without horizontal overflow; older-case pagination and delayed-page refresh fencing. The production build, typecheck and installed-wheel static assets passed. This is a partial Phase 10 delivery. Overview analytics, alerts/incidents, AI chat, hunting, detection/intelligence, registry/MCP administration, audit/admin views, connector registration/enablement, first-run wizard and OIDC redirect login remain incomplete. Existing resume/cancel/review controls are available in the case view; no automatic worker or live action is added.

## Investigation history increment

Section 19 / Phase 10 now includes paginated investigation history through a backwards-compatible cursor endpoint and explicit loading of older cases in the workbench. Every page rechecks current tenant/owner/reviewer grants. Search, status filters and counts cover loaded history. A refresh begins again at the newest page; old responses are fenced from the refreshed or signed-out view. This does not add global analytics, assignment/escalation, server-side search or pagination of the review/response queues.

## Section 12.6 / 19 — Case assignment and escalation

A separate migration-0005 coordination record supports eligible-principal assignment/unassignment, escalation with a bounded reason and manager acknowledgment. A dedicated dashboard queue and case details use actual scoped APIs. Backend role/tenant/creator/current-assignee checks and transactional revision comparisons authorize each mutation; report execution ownership and independent review/approval bindings remain unchanged. Reviewers read operational context without edit grants. The latest backend/browser counts and installed-wheel evidence are in release readiness.

This is partial incident-management delivery. Full incident creation/linking, status/resolution, independent note history, SLA routing, directory synchronization, external notifications and coordination-queue pagination remain incomplete. An acknowledgment does not constitute report acceptance or response approval.

## Section 12.6 / 19 — Linked incident lifecycle and notes

Migration6 implements one human-created incident per collected investigation, work/resolution/manager-close/reopen states, and authored append-only activity with validated source evidence references. The workbench uses real scoped incident/list/activity APIs and expected revisions. Current case assignment controls access, while report/workflow/approval ownership remains unchanged. Tests verify races, read consistency, state/history integrity and the durable 200-entry bound.

This adds the first incident lifecycle beyond assignment/escalation. Standalone incidents, multi-investigation grouping, SLA routing, notifications, title/severity editing, cursor-paginated incident queues and broader enterprise incident operations remain incomplete. Human incident disposition is separate from report review and response approval.
