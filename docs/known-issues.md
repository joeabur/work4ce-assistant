# Known issues and limitations

- Initial sandbox proxy errors did not establish network failure. Network-permitted Git checks succeeded; current dependency advisories and official stable-version status remain unreviewed.
- Production mode remains disabled even with OIDC. Signed-token verification and backend role mapping are tested against fixtures, not a live provider. Browser login, account administration, enterprise identity lifecycle and deployed TLS remain pending.
- SQLite and PostgreSQL use SQLAlchemy with Alembic migrations. PostgreSQL 17.11 integration passed, but production TLS, least-privilege migration/runtime separation, database RLS, encryption, backup/restore and operational recovery remain incomplete.
- Persistence is synchronous and can block the API event loop. Engine pools are bounded to four connections; this does not establish scalable concurrency. Auth request rate limits and audit retention are unbounded.
- Reports and connector disablement survive restart, but interrupted investigations do not automatically resume. Distributed state, cancellation/recovery guarantees and idempotency are incomplete.
- The investigator is deterministic. No live LLM, provider gateway, LangGraph runtime or AI accuracy evaluation is implemented.
- MCP support targets one approved local stdio server through the official SDK. Remote MCP OAuth and general interoperability are unverified. Reference security telemetry is synthetic; no live SIEM/EDR/cloud integration is verified.
- JWT `JWT` and `at+jwt` header types are supported. Configure a dedicated API audience to avoid browser ID-token substitution. Valid cached JWKS keys may remain usable for up to 300 seconds after provider removal; broader revocation policy is absent.
- Production response execution and approval lifecycle, complete CDK packaging, dashboard, operational monitoring and application deployment validation remain pending.
- Audit records are stored locally or in the configured database without a tamper-resistant remote trust boundary. Hashes do not prove source truth or protect against a privileged database writer.
- No connector enable/review administration API exists. Built-ins are approved by trusted bootstrap; existing disablement persists. New connector enablement requires reviewed backend configuration.
- The 40-package dependency lock pins Python 3.12/Linux versions without downloaded-artifact hashes. Clean installation of all 40 distributions and `pip check` passed; wheel build and isolated installed-wheel persistence/migrations also passed. This is not a security/advisory scan.
- The Compose service provisions only a development database. Its Compose startup is unrun; the isolated test runner did start the pinned database image successfully. Remote GitHub CI and production application deployment have not executed.
- No repository license is assumed. The owner should choose licensing before external distribution.

Record exact final verification counts and unrun checks in `release-readiness.md`.
