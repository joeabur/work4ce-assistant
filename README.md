# Work4ce Assistant

A vendor-neutral security operations platform under active development. This initial implementation targets a small, synthetic investigation workflow through interchangeable REST and MCP connectors. It is a development demo, not a production SOC deployment.

The [master specification](docs/MASTER_SPECIFICATION.md) is the requested roadmap. [Implementation progress](docs/implementation-progress.md), [known issues](docs/known-issues.md), and [release readiness](docs/release-readiness.md) distinguish delivered behavior from planned work.

## Local development

Use Python 3.12 and run commands from the repository root. In this prepared cloud snapshot:

```sh
./scripts/setup.sh
. .venv/bin/activate
```

The setup creates a virtual environment reusing installed runtime packages, installs the project editable without downloading dependencies, and runs `pip check`. It passed here. It depends on the prepared snapshot; it does not install missing packages on an arbitrary machine.

On a fresh machine with working package-registry access:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install setuptools==84.0.0 -r requirements.lock
python -m pip install --no-build-isolation --no-deps -e .
python -m pip check
```

The lock pins the 31-package Python 3.12/Linux dependency closure used here; setuptools 84.0.0 is pinned separately for editable builds. Downloaded-artifact hashes, clean-machine installation and current advisory checks remain unverified. Git connectivity succeeds when commands have network permission; sandboxed commands can report proxy connection errors.

Set two different operator-selected random tokens, each at least 32 ASCII characters long, through secure environment configuration:

- `WORK4CE_DEMO_TOKEN`: analyst API bearer token.
- `WORK4CE_ADMIN_TOKEN`: connector administration bearer token.

Do not commit these values or use this authentication for production. Only demo mode is supported. The backend assigns the fixed synthetic demo tenant; callers cannot select a production tenant.

Start the isolated REST fixture service in one terminal:

```sh
PYTHONPATH=src python -m work4ce_assistant.reference_servers rest --port 8766
```

Start the API in another terminal with the configured token variables:

```sh
PYTHONPATH=src python -m work4ce_assistant serve
```

The MCP connector launches its approved local reference server through the official SDK over stdio. No production vendor credentials are used.

The API defaults to port 8765. `WORK4CE_REST_URL` defaults to `http://127.0.0.1:8766`; the reference adapter is restricted to the approved loopback demo service. `WORK4CE_DB` defaults to `.local/work4ce.db`. Protect local database permissions; it contains synthetic reports and audit records.

```sh
PYTHONPATH=src python -m work4ce_assistant demo investigate --query PowerShell
PYTHONPATH=src python -m unittest discover -s tests -v
```

## API workflow

All operations except `/health` require bearer authentication. `/health` is process liveness; authenticated `/ready` probes enabled connectors. The CLI delegates to the backend and does not bypass policy.

| Operation | Purpose |
|---|---|
| `POST /investigations` with `{"query":"PowerShell","limit":20}` | Collect synthetic events and store an evidence-backed report |
| `GET /investigations/{id}` | Retrieve an authorized report |
| `GET /capabilities` | Discover registered capabilities |
| `GET /connectors` | Inspect approved connectors |
| `POST /connectors/{id}/disable` | Disable a connector using the separate admin token |
| `GET /health` | Check API liveness |
| `GET /ready` | Probe enabled connectors using authenticated context |

Read a report's evidence provenance to identify the selected transport. Disable the selected connector with admin authorization, repeat the investigation, and inspect the remaining authorized connector's provenance. Connector failure must remain an explicit investigation limitation.

## Scope and safety

The investigator is deterministic code. No LLM provider is connected, and no AI accuracy claims are made. Events and findings are clearly synthetic; suspicious event text does not prove compromise. SQLite supplies local persistence, not PostgreSQL readiness or a production audit trust boundary. Production OIDC, migrations, resumable workflows, response approvals, dashboard and live integrations remain pending.

Verification: `PYTHONPATH=src python -m unittest discover -s tests -v` passed all 31 tests, including real REST/MCP replacement through the authenticated API and persistence across restart. This does not constitute production validation.

See [architecture decisions](docs/architecture/decisions.md), the [threat model](docs/security/threat-model.md), and [next steps](docs/next-steps.md).
