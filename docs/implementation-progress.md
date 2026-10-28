# Implementation progress

The synthetic vertical slice and PostgreSQL store are `integration_tested`; the OIDC verifier/API adapter is `fixture_tested` with actual signatures and mocked HTTPS. The broader phases remain partial. Production mode is disabled.

| Phase | State | Scope / remaining gate |
|---|---|---|
| 0 — Discovery and architecture | implemented | Specification, architecture, trust boundaries and initial threat model documented |
| 1 — Secure foundation | in_progress | API, backend authorization, SQLAlchemy/Alembic, SQLite/PostgreSQL and OIDC JWT adapter implemented; enterprise identity operations, TLS/RLS and hardening pending |
| 2 — Universal integration framework | in_progress | Reviewed contracts, registration, resolver and read-only gateway integration-tested; full CDK/production policy incomplete |
| 3 — MCP infrastructure | in_progress | Official SDK local stdio transport integration-tested; remote OAuth and broader compatibility pending |
| 4 — Protocol independence | in_progress | Real API REST/MCP replacement passed; full A–J architecture gate incomplete |
| 5–7 — Runtime, evidence, demo | in_progress | Deterministic durable workflow, manual resume, cancellation, checkpoints and persisted invocation budgets implemented; AI planning, human review and cost/token controls pending |
| 8 — First live integration | blocked | Requires an authorized service and infrastructure; no live vendor verification |
| 9–14 — SOC, dashboard, advanced features, response, CDK, hardening | planned | Not complete |

Initial discovery found an unborn checkout. Read-only Git checks failed inside the command sandbox, but network-permitted checks succeeded and returned no advertised refs before initial publication. Those initial errors did not establish a broken proxy. Repository publication does not establish deployment validation.

## Verification record

`.venv/bin/python scripts/test_postgres.py` completed **120 tests in 39.650 seconds with zero skips** on real PostgreSQL 17.11 and SQLite: 17 authentication verifier, eight OIDC API, 24 core, two real end-to-end, 13 foundation storage/migration, six transport, 27 workflow storage, 19 orchestration and four workflow API tests.

Migration `0002_workflows` adds owner-scoped idempotency and atomic 100-pending-workflow admission, checkpoint/revision/lease fencing, manual resume/cancel/state APIs and persisted invocation/deadline budgets. Two end-to-end tests terminate a real worker with `os._exit` after checkpoint commit, restart the API and resume after lease expiry on SQLite and PostgreSQL. Evidence remained stable and no second REST search occurred.

Workflow API checks cover queue quota 429, cancellation freeing capacity, foreign-owner 404, unauthenticated 401, filtered state metadata, trusted environment budget settings and rejected request-body limit injection. See `prompt-status.md` for detailed section 10.2/10.3 coverage and gaps.

OIDC tests use actual RSA signatures with mocked HTTPS JWKS; no live provider or browser login was verified. Current wheel build and isolated installed-wheel migration 0002/workflow completion passed. Clean installation of all 40 locked distributions, version verification and `pip check` passed. The generated lock has no downloaded-artifact hashes; advisories remain unreviewed.

A native GitHub CI status query returned Forbidden, so remote CI remains unverified. Compose startup and backend production deployment remain unrun; the isolated runner did start and test the pinned database image.

Controls include trusted tenant/connector grants, read-only policy, definition integrity before schema use, schema validation, request/result/deadline bounds, evidence hashes and tenant-scoped persistence. Four investigation slots are configured; load saturation is unverified. Authenticated `/ready` probes enabled connectors; public `/health` is liveness only.

Manual resume reuses validated durable checkpoints after interruption/restart; automatic scheduling and general multi-step recovery remain incomplete. Full approval lifecycle acceptance H remains unimplemented. Current reusable environment install/start draft instructions were saved with migration 0002 and the 120-test runner. The managed runtime reports healthy/running with enforced networking, but cloud snapshot publication and fresh-task restoration remain unverified. Publication still requires the product UI; no new publication attempt or failure cause has been established.
