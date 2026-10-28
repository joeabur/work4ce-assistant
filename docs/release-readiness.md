# Release readiness

Recommendation: **no-go for production**. The synthetic vertical slice and PostgreSQL foundation are `integration_tested`; OIDC authentication is `fixture_tested` using actual signatures and mocked HTTPS. The complete architecture and phases 1–7 remain partial. No live security integration, live IdP, independent security assessment or compliance certification is claimed.

## Executed evidence

`.venv/bin/python scripts/test_postgres.py` completed **70 tests in 26.290 seconds with zero skips** on PostgreSQL 17.11 plus SQLite: 17 verifier, eight OIDC API, 24 core, two real end-to-end, 13 storage/migration and six transport tests. The runner uses a digest-pinned disposable database container and removes its own data.

The suite includes actual REST/MCP transport and authenticated API replacement, persisted reports/revocation after restart, SQLAlchemy/Alembic migration behavior, SQLite legacy data preservation and PostgreSQL storage operations. OIDC has 17 verifier tests plus signed-token API tests; these verify cryptography and authorization boundaries against mocked HTTPS JWKS, not a live identity provider.

Setup refreshed the editable package, verified all 40 locked versions and passed `pip check`. Clean isolated installation of all 40 distributions also passed `pip check`. Wheel build and installed-wheel migration/report-persistence checks passed with isolated imports outside the checkout, verifying bundled migrations. The generated lock includes build/development requirements and pins the tested Python 3.12/Linux closure. It lacks downloaded-artifact hashes. Package advisories and current stable-version status remain unreviewed.

Controls tested include trusted tenant/role/connector context, no demo fallback under OIDC, definition-integrity checks before schema use, a 16 KiB pre-parse body bound, schema/result/deadline bounds, evidence hashes, tenant-scoped reports, audit records and persisted disablement. `/health` is liveness; authenticated `/ready` probes enabled connectors. Four investigation slots are configured; saturation/load testing is unrun.

AI evaluations, recovery drills, remote MCP OAuth, live OIDC interoperability, Compose startup, remote GitHub CI and production application deployment checks are **unrun**. Database-container execution does not validate backend container deployment. Stored reports do not establish resumable investigations.

## Critical acceptance matrix

| Test | Required behavior | Current evidence |
|---|---|---|
| A | Same capability over MCP and REST | Real transport/API end-to-end passed |
| B | Authorized connector replacement | REST disable → MCP passed without investigator changes; restart retains revocation |
| C | Reject unauthorized execution | Core/API policy and signed-token backend role tests passed |
| D | Detect tool/manifest poisoning | Definition-integrity and transport discovery checks passed |
| E | Preserve state across connector failure | Failure-state persistence passed; automatic resume unimplemented |
| F | Register previously unknown capability | Generic capability contract test passed |
| G | Valid source-attributed evidence | Core integrity and real transport reports passed |
| H | Reject missing/expired/reused/mismatched response approvals | Unimplemented; read-only denial does not satisfy this test |
| I | Isolate demo data | Synthetic-schema/core isolation passed; no live ingestion exists |
| J | Reject unauthorized cross-tenant access | Core context/storage checks passed; production multi-tenant identity and database RLS incomplete |

The architecture cannot be called complete while H and the remaining requirements are unmet. Fixture/core tests establish the specific tested controls, not universal enterprise compatibility.

## Residual risks and release gates

Production is disabled. OIDC operational lifecycle, TLS/RLS, database least privilege and recovery, distributed resumable workflows, provider-independent AI, remote tamper-resistant audit, response approvals, complete CDK packaging, monitoring and live integrations remain incomplete. Store calls block synchronously, auth rate limiting and audit retention are unbounded, and no connector enable/review API exists. Dedicated API audiences are required because generic `JWT` token types are accepted. JWKS cache retention is up to 300 seconds.

Before enterprise deployment, provide live identity and authorization results, database operational evidence, connector isolation and credential reviews, supported capability/MCP versions, labeled AI evaluations, independent security findings, load measurements, restore/recovery drills, verified deployment artifacts and a residual-risk decision.

Environment draft instructions and publication are separate from this test evidence. A saved draft does not execute scripts or demonstrate restoration in a new task.
