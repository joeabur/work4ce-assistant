"""Protocol-independent resolution and policy, outside investigation reasoning."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable

from .contracts import CapabilityManifest, Connector, ConnectorManifest, ExecutionContext, Work4ceError, digest
from .storage import Store


@dataclass
class Registration:
    manifest: ConnectorManifest
    connector: Connector
    manifest_hash: str


class Gateway:
    def __init__(self, store: Store):
        self.store = store
        self._entries: dict[str, Registration] = {}
        self._capabilities: dict[tuple[str, str], CapabilityManifest] = {}

    async def register(self, manifest: ConnectorManifest, connector: Connector, *, reviewed: bool = False) -> None:
        """Trusted bootstrap/CDK API; never exposed to connector or model input."""
        if not reviewed:
            raise Work4ceError("connector_review_required", 403)
        identity = manifest.connector_id
        if identity in self._entries:
            raise Work4ceError("duplicate_connector", 409)
        capability = manifest.capability
        # Trust backend approval, not claims returned by a connector.
        try:
            async with asyncio.timeout(capability.timeout_seconds):
                discovered = [CapabilityManifest.model_validate(v) for v in await connector.discover()]
        except Exception:
            raise Work4ceError("connector_discovery_failed", 503) from None
        if len(discovered) != 1 or digest(discovered[0].model_dump()) != digest(capability.model_dump()):
            raise Work4ceError("connector_contract_mismatch", 409)
        key = (capability.capability_id, capability.version)
        previous = self._capabilities.get(key)
        if previous and digest(previous.model_dump()) != digest(capability.model_dump()):
            raise Work4ceError("incompatible_capability", 409)
        # Copy nested objects: Pydantic frozen prevents attribute changes, not dict mutation.
        pinned_manifest = manifest.model_copy(deep=True)
        self._entries[identity] = Registration(pinned_manifest, connector, digest(pinned_manifest.model_dump()))
        self._capabilities[key] = capability.model_copy(deep=True)
        self.store.initialize_connector(manifest.tenant_id, identity)
        self.store.audit(manifest.tenant_id, "bootstrap", "connector.register", identity, "reviewed")

    def _permitted(self, entry: Registration, context: ExecutionContext) -> bool:
        if digest(entry.manifest.model_dump()) != entry.manifest_hash:
            return False
        m = entry.manifest
        c = m.capability
        return (
            m.tenant_id == context.tenant_id
            and m.synthetic == context.synthetic
            and m.connector_id in context.allowed_connectors
            and set(c.required_permissions) <= context.permissions
            and c.resource_scope == "synthetic-events"
            and c.data_classification == "synthetic"
            and context.synthetic
            and c.execution_class == "read" and not c.side_effects and not c.approval_required
        )

    def list_connectors(self, context: ExecutionContext) -> list[dict[str, Any]]:
        return [{"connector_id": e.manifest.connector_id, "protocol": e.manifest.protocol,
                 "enabled": self.store.enabled(context.tenant_id, e.manifest.connector_id),
                 "synthetic": e.manifest.synthetic}
                for e in self._entries.values() if self._permitted(e, context)]

    def capabilities(self, context: ExecutionContext) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for entry in self._entries.values():
            if self._permitted(entry, context) and self.store.enabled(context.tenant_id, entry.manifest.connector_id):
                cap = entry.manifest.capability
                seen[cap.capability_id + ":" + cap.version] = cap.model_dump()
        return list(seen.values())

    def disable(self, context: ExecutionContext, identity: str) -> None:
        if "connectors:admin" not in context.permissions:
            self.store.audit(context.tenant_id, context.subject, "connector.disable", identity, "denied")
            raise Work4ceError("permission_denied", 403)
        entry = self._entries.get(identity)
        if not entry or not self._permitted(entry, context):
            raise Work4ceError("connector_not_found", 404)
        self.store.disable(context.tenant_id, context.subject, identity)

    def authorize_checkpoint(self, context: ExecutionContext, resolved: dict[str, Any]) -> None:
        """Stored evidence cannot restore revoked execution grants or changed definitions."""
        identity = resolved.get("connector_id")
        entry = self._entries.get(identity) if isinstance(identity, str) else None
        if (entry is None or not self._permitted(entry, context)
                or not self.store.enabled(context.tenant_id, identity)):
            raise Work4ceError("no_authorized_connector", 403)
        manifest = entry.manifest
        if (resolved.get("manifest_hash") != entry.manifest_hash
                or resolved.get("capability_id") != manifest.capability.capability_id
                or resolved.get("capability_version") != manifest.capability.version
                or resolved.get("protocol") != manifest.protocol):
            raise Work4ceError("checkpoint_definition_changed", 403)
        manifest.capability.validate_result(resolved.get("data"))

    async def execute(self, context: ExecutionContext, capability_id: str, arguments: dict[str, Any],
                      version: str = "1.0", *, before_invoke: Callable[[], None] | None = None) -> dict[str, Any]:
        if len(self._entries) > 100:
            raise Work4ceError("registry_budget_exceeded", 503)
        eligible = [e for e in self._entries.values()
                    if e.manifest.capability.capability_id == capability_id
                    and e.manifest.capability.version == version
                    and self._permitted(e, context)
                    and self.store.enabled(context.tenant_id, e.manifest.connector_id)]
        if not eligible:
            self.store.audit(context.tenant_id, context.subject, "capability.execute", capability_id, "denied")
            raise Work4ceError("no_authorized_connector", 403)
        # Fixed total deadline and at most two attempts. Failover only for read operations.
        try:
            async with asyncio.timeout(20):
                for entry in eligible[:2]:
                    m = entry.manifest
                    cap = m.capability
                    if digest(m.model_dump()) != entry.manifest_hash:
                        self.store.audit(context.tenant_id, context.subject, "connector.integrity", m.connector_id, "rejected")
                        continue
                    cap.validate_arguments(arguments)
                    try:
                        async with asyncio.timeout(cap.timeout_seconds):
                            discovered = [CapabilityManifest.model_validate(v) for v in await entry.connector.discover()]
                            if len(discovered) != 1 or digest(discovered[0].model_dump()) != digest(cap.model_dump()):
                                raise Work4ceError("connector_definition_changed", 502)
                        async with asyncio.timeout(cap.timeout_seconds):
                            if not await entry.connector.health():
                                raise Work4ceError("connector_unhealthy", 503)
                        # Re-evaluate revocation immediately before entering the adapter.
                        if not self.store.enabled(context.tenant_id, m.connector_id):
                            continue
                        if before_invoke is not None:
                            before_invoke()
                        async with asyncio.timeout(cap.timeout_seconds):
                            result = await entry.connector.invoke(capability_id, arguments.copy())
                        cap.validate_result(result)
                    except Work4ceError as error:
                        if error.code.startswith("workflow_"):
                            raise
                        self.store.audit(context.tenant_id, context.subject, "capability.execute", m.connector_id, "failed")
                        continue
                    except Exception:
                        self.store.audit(context.tenant_id, context.subject, "capability.execute", m.connector_id, "failed")
                        continue
                    self.store.audit(context.tenant_id, context.subject, "capability.execute", m.connector_id, "succeeded")
                    return {"data": result, "connector_id": m.connector_id, "protocol": m.protocol,
                            "capability_id": capability_id, "capability_version": cap.version,
                            "manifest_hash": entry.manifest_hash}
        except TimeoutError:
            pass
        raise Work4ceError("connectors_unavailable", 503)
