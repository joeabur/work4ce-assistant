# Work4ce Assistant development guidance

Build a vendor-neutral security operations platform. The complete requested scope is in `docs/MASTER_SPECIFICATION.md`; the progress and readiness documents describe actual delivery. Never equate that scope with implemented functionality.

## Architecture and invariants

- Investigators request versioned capabilities; vendor and transport details belong in connectors.
- Authorization is trusted backend code, independent of model output and connector metadata.
- Tenant identity, permissions and connector allowlists come from authenticated server configuration, never request bodies or telemetry.
- Deny side effects by default. Do not implement privileged response inside the reasoning runtime.
- Validate inputs and outputs; bound time, tool calls and result sizes. Treat event text, tool descriptions and responses as untrusted data.
- Preserve source attribution and raw event integrity. Every factual finding needs evidence references; missing telemetry is inconclusive.
- Synthetic demo data must remain isolated from production tenants. Demo authentication must never be accepted in production mode.
- Do not log secrets or store credentials in manifests, fixtures, source, or reports.

## Layout and commands

`src/work4ce_assistant/` contains the application and connector contracts. `tests/` contains executable verification. `docs/` holds architecture, security, progress and operational guidance.

Use the existing isolated checkout; do not create Git worktrees unless explicitly requested. Preserve pre-existing work. Use the selected Python runtime and pinned dependencies. Run `./scripts/setup.sh` in the prepared snapshot and activate `.venv`; see the README for fresh-machine installation. From the repository root:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m work4ce_assistant.reference_servers rest --port 8766
PYTHONPATH=src python -m work4ce_assistant serve
```

See `README.md` for token configuration. Production services and credentials are not prerequisites for isolated synthetic tests. `python scripts/test_postgres.py` provisions its own disposable PostgreSQL integration database; never point tests at useful data. SQLite auto-migrates; PostgreSQL requires `python -m work4ce_assistant database migrate` before API startup.

The Next.js/React/TypeScript workbench lives in `apps/dashboard`. Setup builds its static export with Node 24/npm and the frozen npm lockfile, then stages ignored assets in the Python package. Use `python scripts/build_dashboard.py` after UI changes, `npm run typecheck` from the dashboard directory, and `python scripts/test_workbench_browser.py` with Chromium/Chrome installed. The API serves the built workbench at `/workbench/`; see `docs/tutorials/workbench.md`. Browser credentials stay in memory, and UI controls never replace backend authorization. Preserve the strict CSP and safe text rendering of telemetry/comments.

## Contributions and phase gates

Use typed Python interfaces and validated schemas. Keep dependencies and deployment components proportional to the feature. Tests must exercise failures, authorization and transport contracts, not merely object creation. Never weaken assertions or policy to pass a test. Verify actual transport behavior before claiming interoperability.

Update progress, known issues, next steps and release readiness after material changes. Record the exact checks run, failed and unrun. Keep implemented, fixture-tested, integration-tested, live-verified and production-validated states distinct. Do not claim architecture acceptance tests A–J have passed without execution evidence. See `CONTRIBUTING.md` and `SECURITY.md`.

Human review is a separate post-collection gate. Synthetic response simulation must always record `performed:false`; do not connect an approval to live execution inside the reasoning process. Preserve requester/reviewer separation, expiry, exact request/report bindings and atomic single use. Review metadata is private to owners/reviewers even where tenant report-read access is broader. See `docs/tutorials/reviews.md`.

Case assignment is operational metadata, separate from immutable workflow requester and review/approval bindings. Preserve creator/current-assignee/manager scope, trusted assignee-directory admission, and atomic revision/audit changes. Reviewers can read coordination but cannot edit it. Keep reasons private to scoped case APIs and render them as text. See `docs/tutorials/cases.md`; migration head is `0007_incident_sources`.

Incidents inherit current case scope, not permanent author access. Keep source report hash binding, manager-only closing/reopening, pending-escalation barriers and atomic revision/activity/audit writes. Activity is append-only through the API and bounded to 200 entries; validate evidence references and disposition/history continuity. Multi-query reads require a coherent snapshot. See `docs/tutorials/incidents.md`.

Combined incidents require current case scope for every linked source, including queue filtering before limit. Keep primary fields stable, unique source membership, qualified evidence references and all-source escalation checks. Lock the complete parent set in sorted order before case/incident rows; abort membership drift before writing. Link history/report hashes and legacy primary-only note citations must remain valid.

Operational queue pages use immutable creation time plus ID, never mutable update time. Coordination follows investigation creation; incidents follow incident creation. Keep legacy array contracts and unsigned, kind/scope-bound cursor validation. Apply current scope before pagination; markers never authorize access. Fence delayed UI pages across refresh/session changes and describe counts as loaded records. See `docs/tutorials/queues.md`.

Guided onboarding is read-only metadata and bounded connector health observation, not provisioning or production verification. Keep routes, tokens, role maps, database URLs and model credentials/prices private. No model inference or event search during setup checks. Every investigation launch reuses backend authorization; readiness is advisory and must be cleared on failed/rechecking status and fenced across navigation/session changes. See `docs/tutorials/onboarding.md`.
