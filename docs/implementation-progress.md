# Implementation progress

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

`.venv/bin/python scripts/test_postgres.py` completed **243 tests in 92.805 seconds with zero skips** on real PostgreSQL 17.11 and SQLite: 17 authentication verifier, nine OIDC API, 24 core, four real end-to-end, 13 foundation storage/migration, six transport, 27 workflow storage, 19 orchestration, four workflow API, 24 model gateway, 21 model storage, 13 grounding/reasoning, six model API, 25 review storage/migration and 13 review policy/API tests, 12 workbench storage cases and six workbench API/static cases.

Migration `0002_workflows` adds owner-scoped idempotency and atomic 100-pending-workflow admission, checkpoint/revision/lease fencing, manual resume/cancel/state APIs and persisted invocation/deadline budgets. Four end-to-end tests terminate a real worker with `os._exit` after checkpoint commit, restart the API and resume after lease expiry on SQLite and PostgreSQL. Evidence remained stable and no second REST search occurred.

Workflow API checks cover queue quota 429, cancellation freeing capacity, foreign-owner 404, unauthenticated 401, filtered state metadata, trusted environment budget settings and rejected request-body limit injection. See `prompt-status.md` for detailed section 10.2/10.3 coverage and gaps.

OIDC tests use actual RSA signatures with mocked HTTPS JWKS; no live provider or browser login was verified. Current wheel static assets, CSP, authenticated identity and migration 0004 passed in an isolated install. Installed-wheel human review/dry-run completion passed in the preceding increment. Clean installation of all 42 locked distributions, version verification and `pip check` passed. The generated lock has no downloaded-artifact hashes; Python advisories and comprehensive scans remain unreviewed.

A native GitHub CI status query returned Forbidden, so remote CI remains unverified. Compose startup and backend production deployment remain unrun; the isolated runner did start and test the pinned database image.

Controls include trusted tenant/connector grants, read-only policy, definition integrity before schema use, schema validation, request/result/deadline bounds, evidence hashes and tenant-scoped persistence. Four investigation slots are configured; load saturation is unverified. Authenticated `/ready` probes enabled connectors; public `/health` is liveness only.

Manual resume reuses validated durable checkpoints after interruption/restart; automatic scheduling and general multi-step recovery remain incomplete. Approval expiry, binding, replay and revocation are tested against a synthetic dry-run consumer; sensitive live-executor acceptance H remains incomplete. Current reusable environment install/start draft instructions were saved with migration 0004, the workbench build and backend/browser runners. The managed runtime reports healthy/running with enforced networking, but cloud snapshot publication and fresh-task restoration remain unverified. Publication still requires the product UI; no new publication attempt or failure cause has been established.


## Structured model increment

Migration `0003_models` adds persistent inference reservations, completed-result caches and frozen route/budget configuration. The HTTP adapter is fixture-tested against mocked HTTPS, while the offline provider exercises the complete model-assisted API/REST/MCP/checkpoint path on PostgreSQL and SQLite. Model plans cannot expand the authorized original query/limit, and reported observations require exact full source-summary quotations. Retries, circuit breaking, cancellation fences, unknown-outcome reservations and revalidated cache reuse are tested. No live provider call or independent billing/AI-accuracy claim is made.


## Human-review increment

Migration `0004_reviews` adds durable report decisions and single-use synthetic response approvals. Optional mandatory review is bound to each workflow; collection completion and human acceptance are distinct states. Default-off workflows may request review manually. Reviewer/requester separation, report/request hashes, expiry, rotated pending review IDs, revocation, current source permissions and atomic one-consumer execution are verified. Four real-process end-to-end paths persist review decisions and action approvals across API restarts. OIDC reviewer roles are backend-mapped and cannot run investigations or simulate responses.

Review found private notes accessible through the tenant-wide report endpoint; the API now strips review metadata for unrelated nonreviewers, with a passing regression. All production response adapters and privileged isolation boundaries remain unimplemented. The simulated consumer records no performed action, so its lifecycle evidence does not establish live response readiness.

## Analyst workbench increment

The packaged Next.js/React/TypeScript static workbench uses authenticated same-origin API calls for case lists, investigation creation, evidence citations, human review, separate action approvals, dry-run consumption and connector health. Tokens remain in memory and are cleared on reload/sign-out. Session-generation checks and aborted requests prevent old-session results from repopulating a new session. Telemetry/comments render as text. CSP hashes compiled inline scripts and permits no unsafe-inline or unsafe-eval; data responses use no-store.

The production build and TypeScript check passed. Three real Chromium workflow/session/mobile tests passed in 16.068 seconds without CSP violations. Desktop and 390px mobile rendering were inspected. The installed wheel serves HTML and seven JavaScript assets with CSP, authenticated identity and migration 0004. All 42 Python pins and pip check passed in the isolated environment. Setup was rerun and reused matching dashboard assets. npm's production-dependency advisory audit returned zero known vulnerabilities; comprehensive scans remain incomplete. CI includes build/typecheck/browser commands, but remote execution remains unverified. See the workbench tutorial for limitations.
