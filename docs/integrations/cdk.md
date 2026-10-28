# Initial connector development contract

Status: foundation implemented and fixture/integration-tested; this is not a complete separately packaged CDK or a general plugin sandbox.

`src/work4ce_assistant/contracts.py` defines the typed `Connector` protocol: asynchronous `health() -> bool`, `discover() -> list[dict]`, and `invoke(capability_id, arguments) -> dict`. Implement adapters at the integration boundary; do not add protocol branches to the investigator. The reference adapters in `connectors.py` demonstrate real REST and official-SDK MCP stdio transport.

## Registration and compatibility

Construct a validated `CapabilityManifest` with a namespaced capability identifier, version, input/output schemas, execution classification, permission requirements, resource scope, data classification and bounds. JSON Schemas are local bounded objects; references are rejected to prevent schema-driven network access. A `ConnectorManifest` binds that capability to a connector identifier, version, protocol, tenant, synthetic designation and optional credential reference. Credential references are identifiers, never secret values.

The connector declaration has `default_enabled=False`. Only trusted backend bootstrap/CDK code may call `Gateway.register(manifest, adapter, reviewed=True)`. This explicit approval verifies discovery matches the reviewed capability, pins the definition hash and initializes the built-in connector's persisted enabled state. Omitting review is rejected. Existing persisted disablement survives registration after restart. There is no public registration or enable endpoint.

Both reference connectors advertise `security.events.search` version `1.0` with identical contracts. Duplicate identities and incompatible definitions are rejected. Before invocation, the gateway checks its pinned manifest and rediscovers the adapter contract. The MCP adapter additionally pins reviewed tool definitions and permits only the reviewed tool. Treat descriptions and results as untrusted data.

## Authorization and extensions

The backend supplies immutable execution context: tenant, subject, permissions, connector allowlist and synthetic designation. An adapter cannot grant itself permission. Selection requires tenant matching, connector grants, required permissions and enabled state. Health or performance does not override policy. Revocation is checked immediately before entering an adapter.

Capability namespaces are generic; a previously unknown read capability can register without modifying orchestration. The current policy deliberately permits only synthetic, read-only, side-effect-free operations in the `synthetic-events` resource scope. Merely registering a write or live-data capability does not authorize it. Expanding production scopes requires policy and security review.

Do not load arbitrary third-party code into the API process or accept client-selected executable commands. These reference adapters are reviewed built-ins. General external connector isolation, packaging/signing, remote authentication, credential rotation, network enforcement and resource limits remain future work.

## Verification

Run `PYTHONPATH=src python -m unittest discover -s tests -v`. The integration suite covers core authorization/contracts, six real transport tests and one real API/REST/MCP replacement/restart path. Add contract, malformed-output, timeout, poisoning, substitution and tenant-isolation tests for each new adapter. Do not claim live vendor verification from synthetic fixtures.
