# Analyst workbench

The first dashboard slice uses Next.js, React and TypeScript with real backend APIs. It covers synthetic investigations, source-attributed evidence, human review, separate response approvals and connector status. Production remains disabled.

## Build and start

From the repository root, run `./scripts/setup.sh` with Python 3.12 and Node 24/npm available. Setup uses the frozen npm lockfile, builds the static dashboard and stages assets in the Python package. Matching source/build fingerprints reuse existing assets. No Node server is needed at runtime.

After changing dashboard source:

```sh
.venv/bin/python scripts/build_dashboard.py
(cd apps/dashboard && npm run typecheck)
```

Start the reference REST service and API as described in the README. The API serves the dashboard at `/workbench/`. Its public shell has no case data. Configure tokens securely before startup; no universal credentials are supplied. For an isolated review demonstration, set `WORK4CE_REQUIRE_HUMAN_REVIEW=true` and use different analyst/admin tokens. Optional fixture reasoning is labelled as offline and uses no LLM.

Backend-only setup supports `WORK4CE_BUILD_DASHBOARD=0`. If assets were never built, the dashboard returns `workbench_not_built` with 503 while backend routes remain available. Build before packaging a distributable wheel; ordinary Python packaging does not invoke npm. Generated assets and dependency/build caches are ignored in Git.

## Investigate and review

1. Enter the configured analyst access token. It remains in memory and clears on reload or sign-out. In OIDC mode, use an already-issued API access token; redirect login is not implemented.
2. Select **New investigation**, enter `PowerShell`, and submit. The idempotency key survives a retry of the same open submission. The report displays synthetic designation, findings, evidence timeline and limitations. Select an evidence citation to highlight its source item.
3. Search/filter the loaded case view. Analysts list their own investigations; authorized reviewers can list their tenant. Counts describe loaded cases, not fleet-wide analytics. Owner controls support manual resume/cancel where applicable and report review requests/refresh.
4. Sign out and connect with the different reviewer/admin token. Open **Review queue**, inspect the report and approve or reject with a comment. The backend rejects self-review and stale/expired bindings.

Collection and human acceptance are different states. Required review displays `awaiting_review` until decided. Refresh expired pending review as the owner. See [review policy](reviews.md) for expiry, permissions and immutable report bindings.

## Synthetic response approval

1. As the report owner, open an approved report and propose a bounded dry run for an observed synthetic host.
2. As a different reviewer/admin, open **Response approvals**, inspect the bound request and separately approve it.
3. As the original analyst, choose **Record simulation** and confirm. The backend consumes a matching unexpired approval once. The card displays the consumed result.

Every result records `dry_run:true, performed:false`. No endpoint changes and no response connector or command executes. Expired, rejected, revoked, reused or mismatched approvals fail closed. UI permissions never replace backend authorization.

**Integrations** shows registered source metadata and health from the backend. Registration, enablement and general connector administration are not implemented in this view.

## Verify

```sh
.venv/bin/python scripts/test_postgres.py
.venv/bin/python scripts/test_workbench_browser.py
```

The browser runner requires Chromium/Chrome on PATH or `WORK4CE_BROWSER_EXECUTABLE` pointing to a compatible executable. It creates its own temporary database, random credentials and local API/fixture processes, then cleans up those resources. Playwright is pinned in the Python development lock. No live credentials or external browser service are needed.

Three browser checks cover the full analyst/reviewer/approval/simulation flow, memory-only sessions/reload clearing, literal hostile-markup display and a 390px mobile layout. Screenshots are written under ignored `.local/`. Backend tests separately verify owner/tenant scoping, filtered summaries, integrity checks, cache headers and CSP/static behavior. Test evidence is recorded in [release readiness](../release-readiness.md).

## Limits and security

Case lists load the latest 50 entries; the API accepts at most 100. Search and metrics apply to that view. Pagination, assignment/escalation, full incident management, broader SOC modules, first-run onboarding, OIDC redirect login and complete cross-browser/accessibility validation remain future work.

Tokens are never stored in cookies, localStorage, sessionStorage or URLs. Sign-out clears client state and aborts/fences pending requests, but does not revoke the server token. Telemetry/comments render as text. The server sends no-store and a CSP restricted to local assets and trusted compiled-script hashes. Use TLS and appropriate token lifecycle controls before any deployed use; this synthetic workflow is not production validation.
