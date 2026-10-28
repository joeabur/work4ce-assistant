# Implementation progress

The first synthetic vertical slice is `integration_tested`. The broader phases remain partial; this is not architecture completion or production readiness.

| Phase | State | Scope / remaining gate |
|---|---|---|
| 0 — Discovery and architecture | implemented | Master specification preserved; architecture, trust boundaries, threat model and initial acceptance plan documented |
| 1 — Secure foundation | in_progress | Initial API, demo authentication, policy and local persistence targeted; PostgreSQL, migrations, OIDC and production operations pending |
| 2 — Universal integration framework | in_progress | Versioned contracts, reviewed registration, resolver and read-only gateway integration-tested; complete CDK and production policy remain pending |
| 3 — MCP infrastructure | in_progress | Official SDK stdio reference transport integration-tested; remote OAuth and broader compatibility pending |
| 4 — Protocol independence | in_progress | Real API end-to-end replacement passed; full A–J architecture gate remains incomplete |
| 5–7 — Runtime, evidence, demo | in_progress | Deterministic synthetic slice only; provider-independent LLM runtime, durable resume and broader scenarios pending |
| 8 — First live integration | blocked | Requires authorized service, credentials and working network; no live verification |
| 9–14 — SOC, dashboard, advanced features, response, CDK, hardening | planned | Not complete; see next steps and master specification |

Initial repository inspection found an unborn local Git checkout containing no source files or commits. The initial read-only Git checks failed inside the command sandbox. Repeating them with network permission succeeded and returned no advertised refs: the remote had no `main` branch to fetch before initial publication. The earlier diagnosis of a broken proxy was incorrect.

The available runtime includes Python 3.12 and installed FastAPI, Pydantic, JSON Schema, httpx and official MCP packages. Their latest stable status and advisories could not be checked online. Preserve this limitation when reporting dependency readiness.

## Verification record

`./.venv/bin/python -m unittest discover -s tests -v`: **31 passed in 15.220 seconds**. The run contained 24 core/API/persistence tests, six transport tests and one real API/REST/MCP end-to-end test. The end-to-end path disabled REST, selected MCP without changing investigator logic, preserved the report across API restart and retained connector revocation.

`./scripts/setup.sh` completed editable installation and `pip check` successfully using the prepared runtime. The 31-package lock pins the observed Python 3.12/Linux dependency closure. A clean online install, artifact-hash verification, current advisories, CI and container execution are unverified.

Verified controls include authentication, trusted tenant and connector grants, fail-closed read policy, definition-integrity checks before schema use, JSON Schema validation, bounded outputs/deadlines, a 16 KiB pre-parse request-body limit, evidence hashes, tenant-scoped report persistence and audit records. Four concurrent investigation slots are configured; saturation testing is pending. `/health` is liveness; authenticated `/ready` probes enabled connectors.

These tests do not complete OIDC, PostgreSQL, resumable workflows, model-provider integration or sensitive response approval tests.

Reusable environment `install_script` and `start_skill` were saved successfully as a draft. Publication and fresh-task restoration are unverified. Review and save the draft in environment settings, then publish when appropriate.
