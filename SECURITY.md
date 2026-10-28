# Security status

Work4ce Assistant is an early development demo. Do not connect it to production security platforms or expose its demo API to untrusted networks. Production mode remains disabled, including with OIDC authentication. No security certification or formal assessment is claimed.

Report a suspected vulnerability privately to the repository owner through an established secure channel. Do not include credentials, customer telemetry, or exploit data in public issues. A dedicated security reporting endpoint has not been established.

Default demo authentication uses separate operator-provided analyst and admin tokens; optional OIDC mode uses an explicit server-side subject-role mapping and ignores demo tokens. Keep them in secure environment configuration. Authentication context belongs to the backend, not connectors or model output. All connectors, schemas, URLs and executable entrypoints require explicit review. Treat telemetry and MCP descriptions as untrusted data.

Known gaps and residual risks are recorded in `docs/security/threat-model.md`, `docs/known-issues.md` and `docs/release-readiness.md`. SQLite/PostgreSQL records do not protect against an administrator who can modify the database. OIDC tests use signed fixtures and mocked HTTPS; no live provider, deployed TLS or enterprise identity lifecycle has been verified. Use a dedicated API access-token audience. Demo tokens are not enterprise identity, TLS termination, revocation or OIDC.
