# Release readiness

Recommendation: **no-go for production**. The synthetic vertical slice and PostgreSQL foundation are `integration_tested`; OIDC authentication is `fixture_tested` using actual signatures and mocked HTTPS. The complete architecture and phases 1–7 remain partial. No live security integration, live IdP, independent security assessment or compliance certification is claimed.

## Executed evidence

`.venv/bin/python scripts/test_postgres.py` completed **120 tests in 39.650 seconds with zero skips** on PostgreSQL 17.11 and SQLite: 17 verifier, eight OIDC API, 24 core, two real end-to-end, 13 foundation storage/migration, six transport, 27 workflow storage, 19 orchestration and four workflow API tests.

Migration `0002_workflows`, owner-scoped idempotency, atomic pending quota, persisted budgets/deadlines, checkpoint integrity, revision/lease fencing and cancellation passed. Two end-to-end tests terminate a real worker via `os._exit` after checkpoint commit, restart the API and resume after lease expiry. Both databases preserved evidence and made no second REST search. API tests verify quota 429, cancellation freeing capacity, owner/auth denial, filtered state metadata and rejected request-body budget injection.

OIDC uses actual signatures and mocked HTTPS JWKS; no live IdP was verified. Current wheel build and isolated installed-wheel migration 0002/workflow completion passed. All 40 locked dependencies were clean-installed and verified; `pip check` passed. The lock lacks downloaded-artifact hashes and is not an advisory assessment.

Phase 5 remains in progress: no AI planner, human review workflow, provider gateway, token/cost controls or general multi-step scheduler exists. See `prompt-status.md` for requirement correlation.

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
| H | Reject missing/expired/reused/mismatched response approvals | Unimplemented; read-only denial does not satisfy this test |
| I | Isolate demo data | Synthetic-schema/core isolation passed; no live ingestion exists |
| J | Reject unauthorized cross-tenant access | Core context/storage checks passed; production multi-tenant identity and database RLS incomplete |

The architecture cannot be called complete while H and the remaining requirements are unmet. Fixture/core tests establish the specific tested controls, not universal enterprise compatibility.

## Residual risks and release gates

Production is disabled. OIDC operational lifecycle, TLS/RLS, database least privilege and recovery, distributed scheduling/general multi-step recovery, provider-independent AI, remote tamper-resistant audit, response approvals, complete CDK packaging, monitoring and live integrations remain incomplete. Store calls block synchronously, auth rate limiting and audit retention are unbounded, and no connector enable/review API exists. Dedicated API audiences are required because generic `JWT` token types are accepted. JWKS cache retention is up to 300 seconds.

Before enterprise deployment, provide live identity and authorization results, database operational evidence, connector isolation and credential reviews, supported capability/MCP versions, labeled AI evaluations, independent security findings, load measurements, restore/recovery drills, verified deployment artifacts and a residual-risk decision.

Current install/start draft instructions were saved with migration 0002 and the 120-test runner. Runtime status is healthy/running with enforced networking. Cloud snapshot publication and restoration in a new task remain unverified; publication requires the product UI. A saved draft does not execute scripts or prove publication. No new publication attempt or failure cause has been established.
