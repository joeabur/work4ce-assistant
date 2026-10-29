# Next steps

1. Preserve the passing integration baseline, including authenticated REST-to-MCP replacement and restart persistence. Add review/enable administration, bounded audit retention and nonblocking storage design. Complete acceptance H with a separate approved-response executor before declaring architecture completion.
2. Use network-permitted commands for remote access. Read-only Git checks succeeded and showed no advertised refs before initial publication; preserve local work when synchronizing subsequent changes. Verify current package versions, official MCP documentation and security advisories. Add reproducible dependency and scanning evidence.
3. Continue Phase 1 beyond the implemented PostgreSQL/SQLAlchemy/Alembic and fixture-tested OIDC adapter: verify a live synthetic IdP, secure TLS, database least privilege/RLS, credential lifecycle, backup/restore and explicit deployment trust boundaries. Keep production disabled.
4. Extend the implemented durable read-boundary checkpoints, manual resume, cancellation, idempotency and persisted budgets with general multi-step partial results, human review, automatic scheduling, clock/lease operational hardening and recovery drills. Preserve reauthorization of every resumed checkpoint.
5. Extend the implemented provider contract, structured planning/quotation boundary and persistent usage ledger with live synthetic-provider verification, tokenizer-aware admission, independent labeled evaluations, broader reasoning and data-sharing controls. Retain deterministic authorization and evidence validation.
6. Expand demo scenarios and connector/CDK contract coverage, including poisoning, tenant substitution, malicious responses and resource exhaustion.
7. Select one authorized live integration after infrastructure and credentials are available. Keep fixture-tested, integration-tested and live-verified states distinct.
8. Add analyst-facing SOC workflows and dashboard incrementally. Implement response approvals and isolated execution only after the authorization lifecycle passes missing, expired, reused and mismatched approval tests.
9. Complete production hardening: CI scans, SBOM, TLS, secrets lifecycle, rate limits, telemetry, load tests, recovery drills, deployment verification and security review.

See the master specification for full phase acceptance criteria. Production remains no-go until evidence supports the required controls.
