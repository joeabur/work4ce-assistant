# Known issues and limitations

- Initial sandboxed commands could not reach the configured proxy. Repeating read-only Git commands with network permission succeeded; no proxy repair is required. Online package/advisory checks remain unrun.
- The initial checkout was unborn. A subsequent successful `git ls-remote origin` returned no advertised refs, confirming no remote branch was available to fetch before initial publication. GitHub source publication does not establish deployment or production validation.
- Authentication is demo-only, with operator-configured tokens. OIDC, token expiry/revocation, TLS and enterprise identity mapping are unimplemented.
- SQLite is local development storage. PostgreSQL, SQLAlchemy/Alembic migrations, distributed state, backup/restore, retention, encryption and database-enforced tenant isolation remain pending.
- The investigator is deterministic. No live LLM, provider gateway, LangGraph runtime or AI accuracy evaluation is implemented.
- MCP support initially targets one approved local stdio reference server through the installed official SDK. Remote transport authentication and universal protocol compatibility are unverified.
- Reference connectors and telemetry are synthetic. Live SIEM, EDR, cloud or identity integration is not verified.
- Production response execution, approval lifecycle, full CDK packaging, dashboard, operational monitoring and container/deployment validation remain pending.
- Local audit records do not provide a tamper-resistant external audit trail. Hashes do not establish source truth or protect against a privileged database writer.
- Connector disablement persists, but no enable/review administration API exists. Approved built-ins are initialized by trusted bootstrap; adding or restoring connectors requires reviewed backend changes.
- SQLite calls are synchronous and can block the event loop. Audit retention is unbounded; database size, retention, rate limits and operational cleanup need production design.
- The lock pins installed dependencies without downloaded-artifact hashes. Offline editable installation and `pip check` passed; clean online installation, CI and container recipes have not executed.
- No repository license is assumed. The owner should choose licensing before external distribution.

Test failures and actual execution counts belong in `release-readiness.md`; do not hide failures in a generic readiness claim.
