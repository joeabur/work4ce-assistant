# Guided first synthetic investigation

Start the API and reference services using the [README](../../README.md), then connect to the workbench with an existing API access token. Open **Getting started** in workspace navigation. The guide uses your current sign-in; its state stays in memory and clears on sign-out/reload. It does not create credentials or change server settings.

1. **Welcome** explains the isolated synthetic dataset and human decisions.
2. **Validate setup** checks the database schema and currently permitted connectors. Inspect the configured authentication mode, administrator presence, reasoning mode, review policy and investigation limits. Select **Recheck setup** after your operator changes the environment. A healthy permitted source is enough even if another source is disabled or unavailable.
3. **First investigation** opens the existing investigation form with `PowerShell` filled in. Review the query and submit it explicitly. After collection, select evidence citations to inspect their source events. Use the existing independent review, assignment/escalation and incident controls to continue the walkthrough.

Starting the walkthrough requires current investigation/event-read grants, a ready database and at least one healthy enabled permitted connector. Reviewers can inspect setup and return to their workspace but cannot start investigations. Failed or pending rechecks clear prior readiness and disable guided launch. Requests are aborted/fenced across navigation, rechecks and sign-out. The investigation API independently checks current permissions and source enablement again at submission; a successful setup check is not an authorization token.

## What validation means

| Observation | Meaning and limit |
|---|---|
| Database ready | A connection succeeded and the observed Alembic revision matches `0007_incident_sources`; not a backup/restore, load or deployment check |
| Administrator configured | Demo token configuration passed startup validation, or the trusted OIDC role mapping contains an admin; not a live admin sign-in/provisioning check |
| Connector healthy | A currently permitted enabled connector returned true from its health method; no event search is performed |
| Reasoning mode | Trusted configuration says deterministic, offline fixture or external provider; no inference, provider connectivity or billing check occurs |
| Review policy | The operator's required-review setting; response proposals still require approved report review and a separate approval |
| Synthetic response | Simulation only; results record `dry_run:true, performed:false` |

Provider mode can make an external inference and incur cost when you submit an investigation under the operator's configured policy. Setup validation itself does not invoke a model. Deterministic and fixture modes require no live model credentials.

## API

Authenticated `GET /onboarding/status` returns a no-store observation report with `mode`, `synthetic`, `production_enabled`, `authentication`, `database`, `reasoning`, `policy`, `connectors`, `can_investigate` and `ready_for_investigation`. It requires current `investigations:read` and synthetic-demo tenant context. Connector projection applies current tenant, permissions, allowlist and definition-integrity checks before probing. Disabled sources are not probed; individual failures and timeouts are reported as unhealthy without diagnostic exception text. Probes have three-second individual and six-second aggregate limits, with at most eight simultaneous probes and a 100-source registry bound. Database operations retain the existing synchronous store behavior.

Partial/unavailable setup returns HTTP 200 with `ready_for_investigation:false`, allowing the guide to display the observations. Missing authentication returns 401; denied current scope returns 403. Fields contain no tokens, database URLs, model endpoint/key/name/prices, JWKS routes or subject-role mapping. There is no configuration/provisioning POST operation.

## Scope and verification

This delivers the welcome, current-environment validation, synthetic demo and dashboard/investigation handoff portions of master specification §20.2. Administrator provisioning, model/connector/MCP configuration, security-policy editing and OIDC redirect login remain operator workflows or future development. Production is disabled; setup observations do not establish production readiness.

Backend tests cover permission changes, signed-token role boundaries, schema drift, database failure, disabled/unhealthy/scoped sources, health timeout, redaction and absence of tool/model invocation. Browser checks cover the actual guided report/citation path, degraded/failed rechecks, delayed-response fencing and mobile layout. See [release readiness](../release-readiness.md) for executed evidence.
