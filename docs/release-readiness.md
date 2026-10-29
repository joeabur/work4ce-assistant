# Release readiness

Increment sections retain the evidence and gaps recorded when each increment shipped; the final connector-administration section records the latest delivery.

Recommendation: **no-go for production**. The synthetic vertical slice and PostgreSQL foundation are `integration_tested`; OIDC authentication is `fixture_tested` using actual signatures and mocked HTTPS. The complete architecture and phases 1–7 remain partial. No live security integration, live IdP, independent security assessment or compliance certification is claimed.

## Executed evidence

`.venv/bin/python scripts/test_postgres.py` completed **431 tests in 129.209 seconds with zero skips** on real PostgreSQL 17.11 and SQLite: 17 authentication verifier, 15 OIDC API, 24 core, four real end-to-end, 13 foundation storage/migration, six transport, 27 workflow storage, 19 orchestration, four workflow API, 24 model gateway, 21 model storage, 13 grounding/reasoning, six model API, 29 review storage/migration and 14 review policy/API tests, 22 workbench storage cases, ten workbench API/static cases, 21 case storage/migration, ten case policy/API, 29 incident storage/migration, six incident API, 25 multi-source storage/migration, five link API, 18 operational-queue storage, four queue API, 12 onboarding, 21 connector-control storage/migration and 12 connector administration API/policy tests.

Migration `0002_workflows`, owner-scoped idempotency, atomic pending quota, persisted budgets/deadlines, checkpoint integrity, revision/lease fencing and cancellation passed. Four end-to-end tests terminate a real worker via `os._exit` after checkpoint commit, restart the API and resume after lease expiry. Both databases preserved evidence and made no second REST search. API tests verify quota 429, cancellation freeing capacity, owner/auth denial, filtered state metadata and rejected request-body budget injection.

OIDC uses actual signatures and mocked HTTPS JWKS; no live IdP was verified. Current wheel build and isolated installed-wheel dashboard HTML/seven script assets, CSP, authenticated identity, history, case coordination, multi-source incident lifecycle, two-page operational queues, onboarding status, reviewed connector controls and migration 0008 passed. Installed-wheel human review/dry-run completion passed in an earlier increment. All 42 locked dependencies were clean-installed and verified; `pip check` passed. The lock lacks downloaded-artifact hashes and is not an advisory assessment.

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

Production is disabled. OIDC operational lifecycle, TLS/RLS, database least privilege and recovery, distributed scheduling/general multi-step recovery, broader provider-independent reasoning and live-model verification, remote tamper-resistant audit, live response execution/approval integration, complete CDK packaging, monitoring and live integrations remain incomplete. Store calls block synchronously, auth rate limiting and audit retention are unbounded, and connector registration/configuration remains operator-managed. Dedicated API audiences are required because generic `JWT` token types are accepted. JWKS cache retention is up to 300 seconds.

Before enterprise deployment, provide live identity and authorization results, database operational evidence, connector isolation and credential reviews, supported capability/MCP versions, labeled AI evaluations, independent security findings, load measurements, restore/recovery drills, verified deployment artifacts and a residual-risk decision.

Current install/start draft instructions were saved with migration 0008, the workbench build and backend/browser runners. Runtime status is healthy/running with enforced networking. Cloud snapshot publication and restoration in a new task remain unverified; publication requires the product UI. A saved draft does not execute scripts or prove publication. No new publication attempt or failure cause has been established.


## Model assistance evidence and limits

The current suite includes strict model contracts, mock HTTPS adapter calls, durable reservation races, migration compatibility, sensitive-pattern rejection, hallucinated-reference/quote rejection, policy denial and cache reuse after interruption. Both model-enabled real-process end-to-end tests use an explicitly labelled offline fixture; neither establishes live LLM reasoning. Worker crash recovery preserves cached planning/assessment results and evidence without another inference/search when the completed cache exists. Reservations bound application admission at configured prices, not external provider billing. General autonomous planning, model health routing across multiple live providers and independent labeled AI evaluations remain incomplete.


## Review and approval evidence

The 290-test suite verifies report-review persistence, requester/reviewer separation, stale review identifiers, action/report binding, expired/missing/mismatched/revoked/reused approvals, transaction rollback, source disablement and concurrent single consumption on SQLite/PostgreSQL. API tests reject forged actors and client-disabled review policy, validate the limited reviewer role, and protect private review notes from unrelated analysts. The installed wheel exercises migration 0004 and human review/approval/simulation through the same policy service.

All simulated results record `dry_run:true` and `performed:false`. No privileged connector or command executes. Approval acceptance H remains partial until a separately isolated sensitive executor and authorized live integration undergo equivalent validation. Report-review backlog/retention, approval retraction workflows and production rate/identity controls remain incomplete.

## Workbench evidence and limits

Four real Chromium checks passed in 19.439 seconds against actual API/reference services: full analyst/reviewer/single-use simulation flow; no browser storage or cookies and sign-out on reload; literal markup rendering and 390px mobile usability; paginated history and delayed-page refresh fencing. No CSP violations occurred. Desktop/mobile screenshots were inspected. The Next.js static production build, TypeScript check, repeated build-cache check, setup refresh and isolated wheel asset/auth checks passed. npm's production-dependency audit returned zero known vulnerabilities at this verification; it is not an independent security assessment.

The dashboard implements a bounded loaded case view, evidence timeline/citations, report review, synthetic response approval/consumption, and integration status. Other SOC modules, full case/incident lifecycle, server-side history search, OIDC redirect login, first-run onboarding and accessibility certification remain incomplete. Authentication uses an already-issued token in memory only. Production remains no-go.

## Investigation history evidence

The history increment's 257-test backend suite added strict cursor parsing/scope rejection, tied-time ordering, exact/final/empty pages, no duplication across newer inserts, current grants, compatibility and private-field/integrity checks on SQLite/PostgreSQL. The fourth browser check loads older cases beyond the first 50, verifies unique coverage of 55 tied-time archived records, and holds a page response until after Refresh to verify it cannot repopulate the refreshed view. Mobile overflow and session reset remain checked. The isolated installed wheel serves and authenticates two history pages at migration 0004. No schema/dependency changes were introduced. Cursors do not grant authorization or freeze a database snapshot; server-side search, large-history load testing and other queue pagination remain incomplete.

## Case coordination evidence and limits

The current 290-test suite includes assignment/escalation persistence and policy on PostgreSQL/SQLite, a two-store CAS race, scope revocation after reassignment, private metadata boundaries, unchanged reports/workflow/requester bindings, audit rollback and SQLite v4 migration preservation. Signed JWT tests confirm that server mappings determine assignee eligibility and management authority; JWT role claims cannot grant either. Five Chromium checks passed in 27.206 seconds, including real assignment/escalation/manager acknowledgment, literal hostile markup in the reason, and a concurrently changed assignment rejecting an open stale dialog. The installed wheel exercises migration 0005 and case operations through authenticated APIs. Desktop/mobile coordination screenshots were inspected.

This is a partial section 12.6/19 delivery. It has one current escalation reason, actor/timestamps and mutation audit references. Full incident creation/linking, status/resolution, independent note history, SLA routing, external directory synchronization/notifications and coordination-queue pagination remain incomplete. Manager acknowledgment is operational metadata, separate from report acceptance and response approval. PostgreSQL operators must migrate before starting this version; production remains no-go.

## Incident lifecycle evidence and limits

The current 326-test suite includes 29 incident storage/migration cases and six incident API cases, plus a signed-token role test. SQLite/PostgreSQL checks verify case-derived scope, reassignment revocation despite incident authorship, unique source binding, incomplete/corrupt report rejection, valid evidence references, legal state transitions, manager-only closing/reopening, escalation barriers, append-only activity continuity, current disposition/history consistency, snapshot reads during another Store commit, concurrent creation/CAS, atomic audit rollback and the 200-entry bound. SQLite v5 reports/case assignments survive migration6 without implicit incidents.

Six real Chromium checks passed in 38.215 seconds. The incident path creates a linked incident, appends literal hostile note text with a working source citation, records work/resolution/manager closing/reopening, rejects a stale note, and reconciles a note committed between detail and activity requests. The original report and pending human review remain unchanged. Desktop/mobile incident rendering was inspected; no tested CSP violations occurred. The isolated installed wheel serves assets/authenticated APIs and exercises notes, resolution and manager closure at migration6.

One incident links one collected investigation. Human severity/disposition are operational judgments, separate from acceptance of report facts or response authorization. Activity is capped at 200 entries and the queue loads 50 records by default (API max100) without cursor pagination. Multi-investigation grouping, standalone incidents, title/severity editing, SLA routing, notification delivery and production operations remain incomplete. Application append-only history is not tamper-resistant against privileged database writers. PostgreSQL requires migration before startup; production remains no-go.

## Multi-investigation incident evidence and limits

The current 357-test suite adds 25 source storage/migration cases, five link API cases and a signed-token all-source permission test. PostgreSQL/SQLite evidence covers current all-source scope, reassignment revocation, hidden-row filtering before queue limits, secondary lookup, qualified references with repeated local evidence IDs, primary-only legacy notes, v6 primary/note preservation, source/hash/chronology integrity, all-source escalation, limits10/200, atomic rollback, membership-drift fencing, link/create races without orphans, sorted cross-link locking and consistent snapshots. Primary incident fields, reports, case records, workflow requester and approvals remain unchanged.

Seven real Chromium checks passed in 43.238 seconds. The new path links a related collected investigation, renders a hostile reason as text, adds a secondary-source citation, opens/highlights the correct report and successfully refreshes status while viewing that source. Existing session, approval, incident lifecycle, stale-view, mobile and pagination checks still pass without tested CSP violations. The isolated installed wheel serves assets/authenticated APIs and exercises multi-source links, qualified notes and disposition at migration7. Desktop/mobile rendering was inspected.

Combined records require access to every source, which can narrow the audience after linking or reassignment. Ten sources and 200 activity entries are bounded per incident; unlinking/merging and queue pagination remain incomplete. Selected-group validation performs per-source reads under snapshots, and large queues/remote database latency remain unbenchmarked. PostgreSQL requires migration before startup. Production remains no-go; application grouping does not establish AI correlation accuracy or privileged response readiness.


## Operational queue pagination evidence and limits

GET `/cases/history` and `/incidents/history` add creation-ordered page envelopes while preserving the legacy latest-update arrays. Coordination follows investigation creation; incidents follow incident creation. Updates do not move records between pages. Strict unsigned markers bind queue kind, tenant and read scope, while every request independently reapplies current permissions. Incident all-source scope is filtered before the limit. Safe DTOs and report/review/response authority remain unchanged. No schema or dependency change was needed; head remains `0007_incident_sources`.

The workbench starts each queue with 50 records, appends older pages without duplicate IDs and fences delayed pages across Refresh and session changes. Counts cover loaded records. The complete PostgreSQL/SQLite suite passed **379 tests in 120.761 seconds with zero skips**, including 18 queue storage and four queue API cases. **Eight Chromium checks passed in 53.342 seconds**, including 55 tied-time records in each operational queue, unique coverage, delayed-page refresh protection and mobile overflow checks. Build/typecheck, isolated installed-wheel two-page queue APIs and migration7 passed; desktop/mobile rendering was inspected.

Paging preserves position rather than freezing live state or permissions; newly visible records before a marker require Refresh. Review/response queues remain bounded. Server-side queue search, unlink/merge governance and large-queue/remote-database performance remain incomplete. This advances the requested workbench and incident-management scope; production and live privileged response remain disabled. See [the queue guide](tutorials/queues.md).


## Guided onboarding increment

Master specification §20.2 / Phase 10 now has a Getting started flow: Welcome, current setup validation and a first synthetic PowerShell investigation through the existing form. Authenticated GET `/onboarding/status` reports safe configured modes/policy, actual schema readiness and currently permitted connector health. Current grants, tenant, allowlist and definition integrity govern probes; disabled sources are skipped. Failed/pending checks clear prior readiness. The guide performs no model inference, event search, credential provisioning or settings mutation. Investigation submission independently reauthorizes using the existing workflow.

The full PostgreSQL/SQLite suite passed **392 tests in 128.362 seconds with zero skips**, including 11 SQLite onboarding checks, one PostgreSQL observation/revocation check and a new signed-token role/admin-mapping test. **Nine Chromium checks passed in 59.679 seconds**: actual guided collection/citations, unchanged connector configuration, degraded/failed rechecks, late results across navigation/sign-out, and mobile/session checks. Production static build/typecheck, installed-wheel onboarding API/assets/auth/migration7, all 42 pins and pip check passed. Desktop/mobile layouts were inspected. No schema or dependency changes were required.

This is partial first-run delivery: account/provider/connector/MCP provisioning, security-policy editing and OIDC redirect login remain incomplete. Setup does not verify a live IdP, inference, provider billing, deployment or recovery. Administrator presence describes trusted configuration rather than a tested admin login. Readiness is a current observation rather than future authority. Production remains disabled. See [guided onboarding](tutorials/onboarding.md).

Initial focused test runs found incorrect fixture-field and mocked-store setup; those test fixtures were corrected. The initial nine-browser run had one error because the race test navigated before its held backend response was captured and the application correctly aborted the request. After deterministic interception and an explicitly uncancellable test transport, the focused wizard check passed in 12.538 seconds and the full nine-check rerun above passed. Application assertions and cancellation/authorization controls were retained.


## Connector administration increment

Master specification §8.2/19.1 now includes admin-only disable and review/re-enable controls for already trusted registered synthetic read sources. Fresh capability discovery, health, exact pinned hash, current scope and expected revision gate activation. Migration `0008_connector_controls` preserves old enabled/disabled rows and all unrelated records while adding current change/last enable-review metadata. Legacy disable remains compatible and advances the revision even when already disabled, fencing an in-flight enable. State/review/audit commit atomically. Stored review hashes must also match runtime definitions after re-registration; changed definitions are inactive until reviewed again.

The final PostgreSQL/SQLite suite passed **431 tests in 129.209 seconds with zero skips**. This adds 21 connector-control storage/migration tests, 12 admin API/policy tests, a signed-token admin mapping test and five review-consumption regression cases. **Ten Chromium checks passed in 71.655 seconds**, including actual admin controls, literal reasons, stale dialogs, complete source disablement/recovery, role switching and a real investigation after recovery. Production static build/typecheck, isolated installed-wheel assets/auth/admin lifecycle/legacy-disable/revision/migration8, all 42 dependency pins and pip check passed. Desktop/mobile controls were inspected; no tested CSP violations occurred. No dependencies were added.

Review found a source-definition race between response policy and final approval consumption. The final transaction now locks source state and requires a nonnull reviewed definition to match every immutable evidence binding. Concurrent reactivation under a different hash leaves the approval unconsumed. Missing legacy hashes are compatible only with bootstrap-null review; malformed hashes fail closed. The three new SQLite/policy regressions fail against the baseline consumption code and pass with this fix; equivalent shared PostgreSQL cases pass in the final suite. The earlier 426-test/ten-browser run passed before this additional review finding; the full checks above were rerun after the fix.

Registration/configuration, credential/network/dependency/isolation review, complete historical reason content, live vendor verification and production deployment remain incomplete. Admin reasons stay on scoped APIs; ordinary source lists retain their four-field contract. PostgreSQL operators must migrate before startup; SQLite auto-upgrades known schemas after data backup. Production remains disabled. See [connector controls](tutorials/connector-controls.md).
