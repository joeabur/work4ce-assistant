# Release readiness

Recommendation: **no-go for production**. The synthetic vertical slice and PostgreSQL foundation are `integration_tested`; OIDC authentication is `fixture_tested` using actual signatures and mocked HTTPS. The complete architecture and phases 1–7 remain partial. No live security integration, live IdP, independent security assessment or compliance certification is claimed.

## Executed evidence

`.venv/bin/python scripts/test_postgres.py` completed **257 tests in 91.863 seconds with zero skips** on real PostgreSQL 17.11 and SQLite: 17 authentication verifier, nine OIDC API, 24 core, four real end-to-end, 13 foundation storage/migration, six transport, 27 workflow storage, 19 orchestration, four workflow API, 24 model gateway, 21 model storage, 13 grounding/reasoning, six model API, 25 review storage/migration and 13 review policy/API tests, 22 workbench storage cases and ten workbench API/static cases.

Migration `0002_workflows`, owner-scoped idempotency, atomic pending quota, persisted budgets/deadlines, checkpoint integrity, revision/lease fencing and cancellation passed. Four end-to-end tests terminate a real worker via `os._exit` after checkpoint commit, restart the API and resume after lease expiry. Both databases preserved evidence and made no second REST search. API tests verify quota 429, cancellation freeing capacity, owner/auth denial, filtered state metadata and rejected request-body budget injection.

OIDC uses actual signatures and mocked HTTPS JWKS; no live IdP was verified. Current wheel build and isolated installed-wheel dashboard HTML/seven script assets, CSP, authenticated identity and migration 0004 passed. Installed-wheel human review/dry-run completion passed in the preceding increment. All 42 locked dependencies were clean-installed and verified; `pip check` passed. The lock lacks downloaded-artifact hashes and is not an advisory assessment.

Phase 5 remains in progress: the structured planner and quotation assessment are constrained and fixture-tested; live model behavior, broader reasoning, general multi-step review coordination and automatic scheduling remain incomplete. See `prompt-status.md` for requirement correlation.

Controls tested include trusted tenant/role/connector context, no demo fallback under OIDC, definition-integrity checks before schema use, a 16 KiB pre-parse body bound, schema/result/deadline bounds, evidence hashes, tenant-scoped reports, audit records and persisted disablement. `/health` is liveness; authenticated `/ready` probes enabled connectors. Four investigation slots are configured; saturation/load testing is unrun.

AI evaluations, backup/restore drills, remote MCP OAuth, live OIDC interoperability, Compose startup and production application deployment checks are **unrun**. A native GitHub CI status query returned Forbidden; remote CI remains **unverified**. Database-container execution does not validate backend container deployment. Resume is explicit and bounded: checkpointed read results are reused without another query; interrupted reads before checkpoint commit may repeat. Automatic scheduling and broad recovery drills remain incomplete.

## Critical acceptance matrix

| Test | Required behavior | Current evidence |
|---|---|---|
| A | Same capability over MCP and REST | Real transport/API end-to-end passed |
| B | Authorized connector replacement | REST disable → MCP passed without investigator changes; restart retains revocation |
| C | Reject unauthorized execution | Core/API policy and signed-token backend role tests passed |
| D | Detect tool/manifest poisoning | Definition-integrity and transport discovery checks passed |
| E | Preserve state across connector failure | Failure-state persistence passed; manual checkpoint resume added; automatic scheduling incomplete |
| F | Register previously unknown capability | Generic capability contract test passed |
| G | Valid source-attributed evidence | Core integrity and real transport reports passed |
| H | Reject missing/expired/reused/mismatched response approvals | Lifecycle guards pass against synthetic dry runs; live sensitive executor integration remains unimplemented |
| I | Isolate demo data | Synthetic-schema/core isolation passed; no live ingestion exists |
| J | Reject unauthorized cross-tenant access | Core context/storage checks passed; production multi-tenant identity and database RLS incomplete |

The architecture cannot be called complete while H and the remaining requirements are unmet. Fixture/core tests establish the specific tested controls, not universal enterprise compatibility.

## Residual risks and release gates

Production is disabled. OIDC operational lifecycle, TLS/RLS, database least privilege and recovery, distributed scheduling/general multi-step recovery, broader provider-independent reasoning and live-model verification, remote tamper-resistant audit, live response execution/approval integration, complete CDK packaging, monitoring and live integrations remain incomplete. Store calls block synchronously, auth rate limiting and audit retention are unbounded, and no connector enable/review API exists. Dedicated API audiences are required because generic `JWT` token types are accepted. JWKS cache retention is up to 300 seconds.

Before enterprise deployment, provide live identity and authorization results, database operational evidence, connector isolation and credential reviews, supported capability/MCP versions, labeled AI evaluations, independent security findings, load measurements, restore/recovery drills, verified deployment artifacts and a residual-risk decision.

Current install/start draft instructions were saved with migration 0004, the workbench build and backend/browser runners. Runtime status is healthy/running with enforced networking. Cloud snapshot publication and restoration in a new task remain unverified; publication requires the product UI. A saved draft does not execute scripts or prove publication. No new publication attempt or failure cause has been established.


## Model assistance evidence and limits

The current suite includes strict model contracts, mock HTTPS adapter calls, durable reservation races, migration compatibility, sensitive-pattern rejection, hallucinated-reference/quote rejection, policy denial and cache reuse after interruption. Both model-enabled real-process end-to-end tests use an explicitly labelled offline fixture; neither establishes live LLM reasoning. Worker crash recovery preserves cached planning/assessment results and evidence without another inference/search when the completed cache exists. Reservations bound application admission at configured prices, not external provider billing. General autonomous planning, model health routing across multiple live providers and independent labeled AI evaluations remain incomplete.


## Review and approval evidence

The 257-test suite verifies report-review persistence, requester/reviewer separation, stale review identifiers, action/report binding, expired/missing/mismatched/revoked/reused approvals, transaction rollback, source disablement and concurrent single consumption on SQLite/PostgreSQL. API tests reject forged actors and client-disabled review policy, validate the limited reviewer role, and protect private review notes from unrelated analysts. The installed wheel exercises migration 0004 and human review/approval/simulation through the same policy service.

All simulated results record `dry_run:true` and `performed:false`. No privileged connector or command executes. Approval acceptance H remains partial until a separately isolated sensitive executor and authorized live integration undergo equivalent validation. Report-review backlog/retention, approval retraction workflows and production rate/identity controls remain incomplete.

## Workbench evidence and limits

Four real Chromium checks passed in 19.439 seconds against actual API/reference services: full analyst/reviewer/single-use simulation flow; no browser storage or cookies and sign-out on reload; literal markup rendering and 390px mobile usability; paginated history and delayed-page refresh fencing. No CSP violations occurred. Desktop/mobile screenshots were inspected. The Next.js static production build, TypeScript check, repeated build-cache check, setup refresh and isolated wheel asset/auth checks passed. npm's production-dependency audit returned zero known vulnerabilities at this verification; it is not an independent security assessment.

The dashboard implements a bounded loaded case view, evidence timeline/citations, report review, synthetic response approval/consumption, and integration status. Other SOC modules, full case/incident lifecycle, server-side history search, OIDC redirect login, first-run onboarding and accessibility certification remain incomplete. Authentication uses an already-issued token in memory only. Production remains no-go.

## Investigation history evidence

The current 257-test backend suite adds strict cursor parsing/scope rejection, tied-time ordering, exact/final/empty pages, no duplication across newer inserts, current grants, compatibility and private-field/integrity checks on SQLite/PostgreSQL. The fourth browser check loads older cases beyond the first 50, verifies unique coverage of 55 tied-time archived records, and holds a page response until after Refresh to verify it cannot repopulate the refreshed view. Mobile overflow and session reset remain checked. The isolated installed wheel serves and authenticates two history pages at migration 0004. No schema/dependency changes were introduced. Cursors do not grant authorization or freeze a database snapshot; server-side search, large-history load testing and other queue pagination remain incomplete.
