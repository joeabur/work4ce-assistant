# Architecture decisions

Status: initial design for the first vertical slice; verification remains recorded separately in release readiness.

## ADR-001 — Capability-first modular backend

Use one Python application with typed, validated contracts for registration, resolution, policy and execution. The investigator asks for `security.events.search` version `1.0`; it must not contain transport or vendor branches. Capability namespaces are extensible. Registration must validate compatibility and preserve a reviewed definition so unauthorized mutation is detectable.

Keep these trust boundaries separate: authenticated principal creation, policy, integration execution, evidence normalization and storage. Connector-supplied identity or permissions are never authoritative. Untrusted arbitrary connector code is not dynamically loaded.

## ADR-002 — FastAPI and schema validation

Use installed Python 3.12, FastAPI, Pydantic and JSON Schema validation for the local API and contracts. Package versions are pinned to the runtime used for verification. Current official documentation, stable-version status and advisories have not been checked; installed versions are observations, not security endorsements. Initial sandbox proxy errors did not establish a broken proxy: Git succeeds with network permission.

## ADR-003 — Two real demo transports

Use the official MCP Python SDK, installed version 1.29.0, for a fixed local stdio server. Use HTTP for a separate loopback REST fixture service. Both advertise the same capability and produce synthetic events. They exercise actual protocol boundaries rather than merely renaming in-process functions.

Only reviewed tool identifiers, schemas and descriptions may execute. Revalidate discovery against the reviewed snapshot before invocation. The REST demo adapter accepts only its approved loopback destination and does not follow redirects. This special-case local demo permission is not an enterprise SSRF policy.

The installed SDK determines actual negotiated MCP behavior. Do not claim compatibility with every MCP specification version or remote OAuth deployment without tests.

## ADR-004 — Fail closed and read only

The initial gateway permits authorized read-only synthetic capabilities. Resolve only among healthy, enabled, reviewed connectors assigned to the authenticated tenant and allowlisted for the principal. Connector substitution must undergo the same policy checks. A cheaper or healthier connector cannot override authorization.

Bound arguments, output size, runtime and execution attempts. Do not automatically retry side-effecting operations. Sensitive response execution and approval tokens are intentionally absent; adding them requires a separate executor and immediate authorization revalidation.

## ADR-005 — SQLAlchemy, Alembic and development storage

The store now uses SQLAlchemy with bundled Alembic revisions through `0002_workflows`. SQLite paths/URLs remain the default and auto-migrate. Exact legacy SQLite schemas can be adopted without losing existing rows; unknown schemas are rejected. Back up useful data before upgrades.

PostgreSQL uses psycopg, requires an explicit `database migrate` before startup, and is integration-tested against PostgreSQL 17.11 in an isolated digest-pinned container. Pools are bounded to four connections. This replaces the earlier SQLite-only persistence decision.

The implementation remains synchronous and may block the API event loop. TLS, database least privilege/RLS, encrypted storage, backup/restore, retention and tamper-resistant remote audit remain required for enterprise deployment. Workflow checkpoint/revision/lease state supports explicit owner-scoped resume; it does not establish an automatic distributed scheduler. See the database tutorial.

## ADR-006 — Deterministic first investigator

Use a deterministic bounded workflow for capability selection, event retrieval, evidence attribution and report creation. It is not an LLM, autonomous threat analyst, or quality-evaluated AI system. Record observed event facts and unknowns without inventing threat conclusions.

A future provider-independent model interface must consume untrusted telemetry as data, validate structured output, track cost and provenance, and remain unable to grant permissions. No live provider integration is claimed.

## ADR-007 — Synthetic realm with interchangeable authentication

Only `WORK4CE_MODE=demo` is supported. Default demo authentication uses distinct operator-selected ASCII analyst/admin tokens of at least 32 characters. `WORK4CE_AUTH_MODE=oidc` instead verifies signed access tokens using an explicitly configured HTTPS issuer, dedicated API audience and JWKS URL. Demo tokens cannot fall back in OIDC mode.

The OIDC verifier is fixture-tested with real RS256 signatures and mocked HTTPS. It enforces required identity/time claims, a one-hour lifetime, bounded JWKS fetching, a 300-second cache and 30-second refresh cooldown. Expired cache entries are not accepted during outages. No browser login or live IdP is claimed.

Roles come only from a reviewed server-side subject-role mapping; duplicate keys are rejected. The server always assigns `synthetic-demo` and reviewed connector grants. JWT tenant/role claims cannot self-authorize. Production remains disabled pending broader identity, deployment and operational controls. See the OIDC tutorial.

## Initial execution path

Authenticated API request → deterministic investigator → capability registry/resolver → independent policy → integration gateway → approved REST or MCP connector → schema validation → normalized source-attributed synthetic evidence → stored incident report and audit.

The services are logical components, not a commitment to deploy independent microservices. PostgreSQL and the OIDC adapter are implemented with the evidence above. Automatic workflow workers, complete dashboard coverage, live model-provider verification and enterprise operations remain future work.


## ADR-008 — Bounded durable read workflows

Persist workflow ownership, idempotency binding, deadlines, invocation reservations and validated evidence checkpoints in the same configured database as reports. Use revision checks and a 30-second lease to fence concurrent/stale workers. Enforce a 100-nonterminal-workflow admission cap per tenant/subject atomically. Four API slots guard execution and deferred admission.

Checkpoint immediately after validating the read result, before report commit. Reuse saved evidence only after current source connector/manifest/permission authorization. Persist invocation budget before actual connector invocation, including fallback, so crashes cannot reset it. A pre-checkpoint interruption may repeat a read; there is no exactly-once claim and writes remain denied.

Default deadline is 120 seconds from enqueue and default budget is two invocations. Explicit cancellation invalidates commit authority; it cannot guarantee termination of external I/O already in flight. Task interruption releases the lease when possible and preserves recoverable state; after abrupt worker exit, resume waits for lease expiry. Expose manual resume/cancel/state APIs; do not imply an automatic worker or general workflow scheduler exists.


## ADR-009 — Constrained model assistance and durable usage

Introduce a provider contract, an explicitly labelled offline fixture and a configured HTTPS structured chat-completions adapter. The default remains deterministic. A model may select the authorized literal search and exact evidence quotations; it cannot grant permissions, enlarge scope or introduce unsupported facts/verdicts. Backend policy and evidence validation remain authoritative.

Fingerprint route, model, synthetic designation, prompt, schemas, prices and budgets without credential values. Persist reservations before every attempt, retain failed/unknown usage conservatively, and cache validated results by owner/workflow/stage/input/configuration. Migration 0003 preserves prior deterministic workflows. Provider mode requires explicit synthetic-egress consent; payload allowlisting and recognizable credential-pattern rejection are limited admission controls, not enterprise DLP. No cross-provider fallback or live billing guarantee is claimed.


## ADR-010 — Human acceptance and synthetic approval consumption

Keep machine collection state separate from a durable human report decision, preserving immutable report/evidence/model usage. An operator may require the gate at creation; owners may request it later. Server-mapped reviewers have distinct grants and cannot self-approve or run the simulation. Public report-read access does not imply permission to private review metadata.

A separate policy service accepts only a bounded synthetic action/target/parameter contract and requires approved immutable report evidence plus a distinct action approval. Consumption locks the bound request, report, review and source connector rows; it checks current authorization, expiry and nonce matching, then atomically records a single dry run. No privilege-bearing response adapter or command is installed. This is an approval-lifecycle test boundary, not a production executor or OS isolation boundary. Live execution must be implemented separately and revalidated before use.

## ADR-011 — Same-origin static analyst workbench

Use the requested Next.js/React/TypeScript stack as a static export mounted by FastAPI at `/workbench/`. One application origin keeps the existing bearer API and backend policy authoritative without introducing a separate Node runtime or token proxy. Node is required at build time; generated assets are ignored in Git and included in a wheel only after the explicit dashboard build. Backend-only installations remain usable and report an unbuilt workbench as 503.

Hold already-issued access tokens only in browser memory; use neither cookies nor persistent browser storage. Abort/fence old-session requests, render telemetry/comments as text and compute CSP hashes from trusted build output. `/me` exposes server permissions; a bounded case-summary API enforces owner/reviewer scope independently of the UI. Metrics describe loaded data rather than fabricated SOC analytics. This increment covers investigations, evidence, human decisions, synthetic approvals and integration status. OIDC redirect login, full incident/SOC modules and complete integration administration remain separate work.

## ADR-012 — Scoped keyset investigation history

Keep GET `/investigations` compatible and add `/investigations/history` with bounded items and a next cursor. Order by descending creation time and ID, and fetch one additional row to determine continuation. This avoids offset shifts when newer investigations arrive and handles equal timestamps deterministically. Reuse the existing integrity-checked summary projection; never include private review notes or approval material.

A versioned, bounded cursor binds tenant/owner read scope and position. It is an unsigned marker, not a capability; current authentication and independently applied server filters authorize every page. No signing secret or database schema migration is needed. The workbench appends explicit older-page requests and fences them by session and refresh generation. Search/counts cover loaded history, and refreshing resets to the newest page. No snapshot, global-search or large-history performance claim is made.

## ADR-013 — Coordination separate from immutable execution ownership

Store one revisioned coordination record per investigation/tenant, initialized only by a mutation. Assignment identifies the operational coordinator, while the original requester continues to own workflow execution and response requests. Human report decisions and sensitive-action approvals stay separate. Admit assignees from trusted server subject-role configuration; only a manager can acknowledge an escalation.

Lock current ownership/assignment before authorization and revision checks, then atomically commit the change with an audit reference. Keep private coordination metadata on dedicated scoped endpoints; preserve existing report/history contracts. A separate bounded queue surfaces assigned/escalated records without fabricating incidents or global counts. Migration 0005 adds only the coordination table/index. Full incident lifecycle, independent note history and external notification/directory integration remain future work.

## ADR-014 — Source-bound incidents and revisioned activity

Create one incident per collected investigation, inheriting current case scope and assignment. Keep the report immutable and hash-bound; human severity, operational status and notes live separately. A dedicated repository shares the Store transaction boundary and locks in parent→case→incident order. Manager-only closing/reopening and a pending-escalation barrier preserve coordination policy without changing report/response approvals.

Each creation, note or transition appends one authored activity entry and increments the incident revision atomically with audit. Exact source evidence references and continuity/disposition checks preserve a coherent 200-entry bounded history. Snapshot reads keep multi-query data consistent; the workbench reconciles versions when separate HTTP reads race. Migration6 adds only incident/activity tables and indexes. Multi-source grouping, standalone incidents, editable classification, queue pagination and enterprise routing remain later work.

## ADR-015 — Explicit incident membership and all-source authorization

Keep the primary incident source and assignment fields stable, and add up to nine immutable related source memberships. Each investigation belongs to only one incident. A link stores its report hash, actor/time and an activity entry, with current revision and audit committed atomically. Acquire the complete parent set in sorted order before case/incident locks; changed membership fences a stale lock set instead of extending it out of order.

Combined metadata/history is visible only when current case scope covers every linked source. Apply this intersection before queue limits and recheck it for every read/mutation; incident authorship never grants access. Existing broad reviewer/manager scope remains tenant-bound. Qualify citations by investigation/evidence, preserving primary-only fields for old clients. Validate link chronology, membership and report hashes against history. Migration7 backfills v6 primary membership without changing revisions; unlink/merge governance is deferred.
