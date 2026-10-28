# Contributing

Read `AGENTS.md`, the master specification and current progress before changing code. Keep changes small and reviewable. Prefer stable capability contracts over vendor-specific agent logic. Do not introduce empty architectural modules.

Run `PYTHONPATH=src python -m unittest discover -s tests -v` from the repository root. Add regression tests for authorization, tenant isolation, malformed inputs, transport failure and evidence attribution when changing those paths. Tests must not require live tenant data or production credentials.

Document new dependencies and compatibility assumptions. Keep reproducible dependency pins and verification enabled. Never commit secrets, local databases, generated environments or vendor telemetry. Do not infer a repository license; the owner must choose one before external distribution.

For each phase report implementation, actual verification, security controls, limitations and next steps. A completed implementation is not production validation. External deployment requires explicit authorization.
