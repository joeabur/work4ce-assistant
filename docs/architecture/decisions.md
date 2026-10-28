# Architecture decisions

Status: initial design for the first vertical slice; verification remains recorded separately in release readiness.

## ADR-001 — Capability-first modular backend

Use one Python application with typed, validated contracts for registration, resolution, policy and execution. The investigator asks for `security.events.search` version `1.0`; it must not contain transport or vendor branches. Capability namespaces are extensible. Registration must validate compatibility and preserve a reviewed definition so unauthorized mutation is detectable.

Keep these trust boundaries separate: authenticated principal creation, policy, integration execution, evidence normalization and storage. Connector-supplied identity or permissions are never authoritative. Untrusted arbitrary connector code is not dynamically loaded.

## ADR-002 — FastAPI and schema validation

Use installed Python 3.12, FastAPI, Pydantic and JSON Schema validation for the local API and contracts. Package versions are pinned to the runtime used for verification. Current official documentation, stable-version status and advisories have not been checked; installed versions are observations, not security endorsements. Initial sandbox proxy errors did not establish a broken proxy: Git succeeds with network permission.

## ADR-003 — Two real demo transports

Use the official MCP Python SDK, installed version 1.29.0, for a fixed local stdio server. Use HTTP for a separate loopback REST fixture service. Both advertise the same capability and produce synthetic events. They exercise actual protocol boundaries rather than merely renaming in-process functions.

Only reviewed tool identifiers, schemas and descriptions may execute. Revalidate discovery against the reviewed snapshot before invocation. The REST demo adapter accepts only its approved loopback destination and does not follow redirects. This special-case local demo permission is not an enterprise SSRF policy.

The installed SDK determines actual negotiated MCP behavior. Do not claim compatibility with every MCP specification version or remote OAuth deployment without tests.

## ADR-004 — Fail closed and read only

The initial gateway permits authorized read-only synthetic capabilities. Resolve only among healthy, enabled, reviewed connectors assigned to the authenticated tenant and allowlisted for the principal. Connector substitution must undergo the same policy checks. A cheaper or healthier connector cannot override authorization.

Bound arguments, output size, runtime and execution attempts. Do not automatically retry side-effecting operations. Sensitive response execution and approval tokens are intentionally absent; adding them requires a separate executor and immediate authorization revalidation.

## ADR-005 — SQLite development persistence

Use SQLite for a self-contained local demonstration of report, evidence, audit and investigation-state persistence. This departs from the recommended PostgreSQL/SQLAlchemy/Alembic stack to avoid claiming an unconfigured production dependency. It is a development alternative only.

PostgreSQL support, migration discipline, encrypted storage, tenant row-level policies, backup/restore, retention and tamper-resistant remote audit are required before enterprise deployment. Persisted state alone does not establish resumable workflows.

## ADR-006 — Deterministic first investigator

Use a deterministic bounded workflow for capability selection, event retrieval, evidence attribution and report creation. It is not an LLM, autonomous threat analyst, or quality-evaluated AI system. Record observed event facts and unknowns without inventing threat conclusions.

A future provider-independent model interface must consume untrusted telemetry as data, validate structured output, track cost and provenance, and remain unable to grant permissions. No live provider integration is claimed.

## ADR-007 — Demo identity boundary

Only demo mode is supported initially. Operator-supplied analyst and administration tokens must differ and each have at least 32 ASCII characters. No universal credentials are shipped. The server assigns the fixed `synthetic-demo` tenant and connector grants; client-supplied tenant or permission fields cannot change them. Production configuration must fail closed until real authentication is implemented.

## Initial execution path

Authenticated API request → deterministic investigator → capability registry/resolver → independent policy → integration gateway → approved REST or MCP connector → schema validation → normalized source-attributed synthetic evidence → stored incident report and audit.

The services are logical components, not a commitment to deploy independent microservices. PostgreSQL, OIDC, workflow workers, a dashboard and model-provider calls are future components with separate readiness requirements.
