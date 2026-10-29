# Implementation progress

Increment sections retain the evidence and gaps recorded when each increment shipped; the final guided-onboarding section records the latest delivery.

The synthetic vertical slice and PostgreSQL store are `integration_tested`; the OIDC verifier/API adapter is `fixture_tested` with actual signatures and mocked HTTPS. The broader phases remain partial. Production mode is disabled.

| Phase | State | Scope / remaining gate |
|---|---|---|
| 0 — Discovery and architecture | implemented | Specification, architecture, trust boundaries and initial threat model documented |
| 1 — Secure foundation | in_progress | API, backend authorization, SQLAlchemy/Alembic, SQLite/PostgreSQL and OIDC JWT adapter implemented; enterprise identity operations, TLS/RLS and hardening pending |
| 2 — Universal integration framework | in_progress | Reviewed contracts, registration, resolver and read-only gateway integration-tested; full CDK/production policy incomplete |
| 3 — MCP infrastructure | in_progress | Official SDK local stdio transport integration-tested; remote OAuth and broader compatibility pending |
| 4 — Protocol independence | in_progress | Real API REST/MCP replacement passed; full A–J architecture gate incomplete |
| 5–7 — Runtime, evidence, demo | in_progress | Durable workflow plus constrained structured planning/quotation assistance and persisted model usage implemented; durable human review and synthetic approvals added; live-model evaluation and broad reasoning pending |
| 8 — First live integration | blocked | Requires an authorized service and infrastructure; no live vendor verification |
| 9–14 — SOC, dashboard, advanced features, response, CDK, hardening | in_progress | Phase 10 has a working Next.js investigation/review/approval workbench; Phase 12 has synthetic dry runs. Broad SOC modules, live execution and other later gates remain incomplete |

Initial discovery found an unborn checkout. Read-only Git checks failed inside the command sandbox, but network-permitted checks succeeded and returned no advertised refs before initial publication. Those initial errors did not establish a broken proxy. Repository publication does not establish deployment validation.

## Verification record

`.venv/bin/python scripts/test_postgres.py` completed **392 tests in 128.362 seconds with zero skips** on real PostgreSQL 17.11 and SQLite: 17 authentication verifier, 14 OIDC API, 24 core, four real end-to-end, 13 foundation storage/migration, six transport, 27 workflow storage, 19 orchestration, four workflow API, 24 model gateway, 21 model storage, 13 grounding/reasoning, six model API, 25 review storage/migration and 13 review policy/API tests, 22 workbench storage cases, ten workbench API/static cases, 21 case storage/migration, ten case policy/API, 29 incident storage/migration, six incident API, 25 multi-source storage/migration, five link API, 18 operational-queue storage, four queue API and 12 onboarding tests.

Migration `0002_workflows` adds owner-scoped idempotency and atomic 100-pending-workflow admission, checkpoint/revision/lease fencing, manual resume/cancel/state APIs and persisted invocation/deadline budgets. Four end-to-end tests terminate a real worker with `os._exit` after checkpoint commit, restart the API and resume after lease expiry on SQLite and PostgreSQL. Evidence remained stable and no second REST search occurred.

Workflow API checks cover queue quota 429, cancellation freeing capacity, foreign-owner 404, unauthenticated 401, filtered state metadata, trusted environment budget settings and rejected request-body limit injection. See `prompt-status.md` for detailed section 10.2/10.3 coverage and gaps.

OIDC tests use actual RSA signatures with mocked HTTPS JWKS; no live provider or browser login was verified. Current wheel static assets, CSP, authenticated identity, case coordination, multi-source incident lifecycle and migration 0007 passed in an isolated install. Installed-wheel human review/dry-run completion passed in an earlier increment. Clean installation of all 42 locked distributions, version verification and `pip check` passed. The generated lock has no downloaded-artifact hashes; Python advisories and comprehensive scans remain unreviewed.

A native GitHub CI status query returned Forbidden, so remote CI remains unverified. Compose startup and backend production deployment remain unrun; the isolated runner did start and test the pinned database image.

Controls include trusted tenant/connector grants, read-only policy, definition integrity before schema use, schema validation, request/result/deadline bounds, evidence hashes and tenant-scoped persistence. Four investigation slots are configured; load saturation is unverified. Authenticated `/ready` probes enabled connectors; public `/health` is liveness only.

Manual resume reuses validated durable checkpoints after interruption/restart; automatic scheduling and general multi-step recovery remain incomplete. Approval expiry, binding, replay and revocation are tested against a synthetic dry-run consumer; sensitive live-executor acceptance H remains incomplete. Current reusable environment install/start draft instructions were saved with migration 0007, the workbench build and backend/browser runners. The managed runtime reports healthy/running with enforced networking, but cloud snapshot publication and fresh-task restoration remain unverified. Publication still requires the product UI; no new publication attempt or failure cause has been established.


## Structured model increment

Migration `0003_models` adds persistent inference reservations, completed-result caches and frozen route/budget configuration. The HTTP adapter is fixture-tested against mocked HTTPS, while the offline provider exercises the complete model-assisted API/REST/MCP/checkpoint path on PostgreSQL and SQLite. Model plans cannot expand the authorized original query/limit, and reported observations require exact full source-summary quotations. Retries, circuit breaking, cancellation fences, unknown-outcome reservations and revalidated cache reuse are tested. No live provider call or independent billing/AI-accuracy claim is made.


## Human-review increment

Migration `0004_reviews` adds durable report decisions and single-use synthetic response approvals. Optional mandatory review is bound to each workflow; collection completion and human acceptance are distinct states. Default-off workflows may request review manually. Reviewer/requester separation, report/request hashes, expiry, rotated pending review IDs, revocation, current source permissions and atomic one-consumer execution are verified. Four real-process end-to-end paths persist review decisions and action approvals across API restarts. OIDC reviewer roles are backend-mapped and cannot run investigations or simulate responses.

Review found private notes accessible through the tenant-wide report endpoint; the API now strips review metadata for unrelated nonreviewers, with a passing regression. All production response adapters and privileged isolation boundaries remain unimplemented. The simulated consumer records no performed action, so its lifecycle evidence does not establish live response readiness.

## Analyst workbench increment

The packaged Next.js/React/TypeScript static workbench uses authenticated same-origin API calls for case lists, investigation creation, evidence citations, human review, separate action approvals, dry-run consumption and connector health. Tokens remain in memory and are cleared on reload/sign-out. Session-generation checks and aborted requests prevent old-session results from repopulating a new session. Telemetry/comments render as text. CSP hashes compiled inline scripts and permits no unsafe-inline or unsafe-eval; data responses use no-store.

The production build and TypeScript check passed. Four real Chromium workflow/session/mobile/history tests passed in 19.439 seconds without CSP violations. Desktop and 390px mobile rendering were inspected. The installed wheel serves HTML and seven JavaScript assets with CSP, authenticated identity and migration 0004. All 42 Python pins and pip check passed in the isolated environment. Setup was rerun and reused matching dashboard assets. npm's production-dependency advisory audit returned zero known vulnerabilities; comprehensive scans remain incomplete. CI includes build/typecheck/browser commands, but remote execution remains unverified. See the workbench tutorial for limitations.

## Investigation history increment

GET `/investigations/history` returns bounded safe summaries and a scope-bound position cursor, while legacy GET `/investigations` retains its array contract. Shared projection preserves report integrity and review privacy. Equal timestamps use the investigation ID tie-breaker; newer inserts do not shift older pages. Every request reapplies current tenant/owner/reviewer grants independently of the unsigned marker.

The workbench loads older pages explicitly, deduplicates IDs and fences delayed responses after refresh/logout. Search, filters and metrics cover loaded history; refresh starts from the newest page. No schema or dependency changes were needed. The complete PostgreSQL/SQLite suite passed 257 tests in 91.863 seconds with zero skips; four Chromium checks passed in 19.439 seconds, including 55 tied-timestamp archived cases and a delayed-page refresh race. Production build, typecheck and installed-wheel HTML/assets/auth/two-page history/migration checks passed. Large-history performance, global search and review/response-queue pagination remain unverified or incomplete.

## Case coordination increment

Migration `0005_cases` adds a separate assignment/escalation record, leaving immutable reports, collection ownership, human review and response approvals intact. Eligible analysts/admins come from trusted demo/OIDC subject configuration. Creators/current assignees may assign, unassign and escalate; managers may coordinate any tenant case and acknowledge a pending escalation. Reviewers read coordination without edit grants. Default reads create no rows, and unrelated analysts cannot read private coordination through tenant-wide report routes.

Mutation authorization, expected-revision comparison, state transition and audit commit are one transaction. SQLite serializes before authorization reads; PostgreSQL locks the parent and coordination rows. Tests cover a single concurrent CAS winner, reassignment revocation, stale edits, atomic rollback, v4 SQLite report/review preservation, restart persistence, signed-token role/directory checks and unchanged workflow/report authority. The full suite passed 290 tests in 90.610 seconds with zero skips on PostgreSQL/SQLite. Five Chromium checks passed in 27.206 seconds, including assignment, escalation, manager acknowledgment, literal reason rendering and stale-dialog rejection. Production build, typecheck and installed-wheel migration/history/case lifecycle passed. Desktop/mobile coordination rendering was inspected. No live response or external notification is added.

## Incident lifecycle and note-history increment

Migration `0006_incidents` adds one incident per source investigation and append-only authored activity. Collected synthetic reports are integrity-checked and hash-bound to incidents. Current creator/assignee/manager case scope controls reads and mutations; reviewers read without edit grants. Human title/severity, open/in-progress/resolved/closed states, resolution notes, manager closing/reopening and evidence-linked notes use transactional revision checks. Pending escalations block resolution/closing. Notes and status transitions preserve the original report, workflow requester, case assignment and independent approval gates.

Repository reads use consistent snapshots to keep scope, revision and activity coherent during concurrent commits. Activity continuity and current resolution/closure metadata are cross-validated; the UI retries one version mismatch between detail/activity requests. Activity is capped at 200 entries, and closed incidents require manager reopening before further notes. PostgreSQL/SQLite tests cover scope revocation, duplicate-creation/CAS races, audit rollback, source bindings, v5 SQLite preservation, read snapshots and the durable history bound. All 326 backend tests passed in 102.555 seconds with zero skips. Six Chromium checks passed in 38.215 seconds, including full incident disposition/note history, literal hostile note text, evidence citations, stale notes and concurrent view loading. Production build/typecheck, installed-wheel migration6/history/case/incident lifecycle, and desktop/mobile inspection passed. This remains a single-source incident slice; broader grouping, queue pagination, SLA routing and notifications are incomplete.

## Multi-investigation incident increment

Migration `0007_incident_sources` backfills primary source membership for v6 incidents and adds qualified evidence references/link activity. One primary plus up to nine related collected synthetic reports are hash-bound to the incident. Current case scope must cover every member for reads and mutations; queue filtering enforces that intersection before its limit. Linking never expands access, and assignment changes can revoke the entire group even from its incident author. Primary fields and independent report/workflow/approval boundaries remain stable.

Sorted parent/case/incident locks, membership-drift fences, unique source bindings and revision/activity/audit commits protect concurrent links and creation without orphans. Notes namespace source/evidence pairs, retain primary-only legacy fields, and validate reference chronology. Resolution/closing checks pending escalation on every source. New tests cover v6 backfill, duplicate local evidence IDs, source/case integrity, caps10/200, audit rollback, snapshot reads, queue scope, link/create races and cross-link lock ordering. The full PostgreSQL/SQLite suite passed 357 tests in 111.674 seconds with zero skips. Seven Chromium checks passed in 43.238 seconds, including linking, literal link text, secondary-source evidence highlighting and mutation refresh while viewing that source. Build/typecheck, isolated wheel migration7/link/citation/disposition checks and desktop/mobile inspection passed. Large-queue performance, unlink/merge governance and operational queue pagination remain unverified or incomplete.


## Operational queue pagination increment

GET `/cases/history` and `/incidents/history` add creation-ordered page envelopes while preserving the legacy latest-update arrays. Coordination follows investigation creation; incidents follow incident creation. Updates do not move records between pages. Strict unsigned markers bind queue kind, tenant and read scope, while every request independently reapplies current permissions. Incident all-source scope is filtered before the limit. Safe DTOs and report/review/response authority remain unchanged. No schema or dependency change was needed; head remains `0007_incident_sources`.

The workbench starts each queue with 50 records, appends older pages without duplicate IDs and fences delayed pages across Refresh and session changes. Counts cover loaded records. The complete PostgreSQL/SQLite suite passed **379 tests in 120.761 seconds with zero skips**, including 18 queue storage and four queue API cases. **Eight Chromium checks passed in 53.342 seconds**, including 55 tied-time records in each operational queue, unique coverage, delayed-page refresh protection and mobile overflow checks. Build/typecheck, isolated installed-wheel two-page queue APIs and migration7 passed; desktop/mobile rendering was inspected.

Paging preserves position rather than freezing live state or permissions; newly visible records before a marker require Refresh. Review/response queues remain bounded. Server-side queue search, unlink/merge governance and large-queue/remote-database performance remain incomplete. This advances the requested workbench and incident-management scope; production and live privileged response remain disabled. See [the queue guide](tutorials/queues.md).


## Guided onboarding increment

Master specification §20.2 / Phase 10 now has a Getting started flow: Welcome, current setup validation and a first synthetic PowerShell investigation through the existing form. Authenticated GET `/onboarding/status` reports safe configured modes/policy, actual schema readiness and currently permitted connector health. Current grants, tenant, allowlist and definition integrity govern probes; disabled sources are skipped. Failed/pending checks clear prior readiness. The guide performs no model inference, event search, credential provisioning or settings mutation. Investigation submission independently reauthorizes using the existing workflow.

The full PostgreSQL/SQLite suite passed **392 tests in 128.362 seconds with zero skips**, including 11 SQLite onboarding checks, one PostgreSQL observation/revocation check and a new signed-token role/admin-mapping test. **Nine Chromium checks passed in 59.679 seconds**: actual guided collection/citations, unchanged connector configuration, degraded/failed rechecks, late results across navigation/sign-out, and mobile/session checks. Production static build/typecheck, installed-wheel onboarding API/assets/auth/migration7, all 42 pins and pip check passed. Desktop/mobile layouts were inspected. No schema or dependency changes were required.

This is partial first-run delivery: account/provider/connector/MCP provisioning, security-policy editing and OIDC redirect login remain incomplete. Setup does not verify a live IdP, inference, provider billing, deployment or recovery. Administrator presence describes trusted configuration rather than a tested admin login. Readiness is a current observation rather than future authority. Production remains disabled. See [guided onboarding](tutorials/onboarding.md).
