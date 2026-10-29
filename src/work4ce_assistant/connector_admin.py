"""Scoped human review and reversible activation of already trusted read connectors."""
from __future__ import annotations

import asyncio
import re

from .contracts import CapabilityManifest, ExecutionContext, Work4ceError, digest
from .gateway import Gateway, Registration


class ConnectorAdministration:
    def __init__(self, gateway: Gateway):
        self.gateway=gateway
        self.store=gateway.store

    @staticmethod
    def _authorize(context: ExecutionContext):
        if 'connectors:admin' not in context.permissions:
            raise Work4ceError('permission_denied',403)

    def _entry(self, context: ExecutionContext, identity: str) -> Registration:
        self._authorize(context)
        entry=self.gateway._entries.get(identity)
        if entry is None or not self.gateway._permitted(entry,context):
            raise Work4ceError('connector_not_found',404)
        return entry

    @staticmethod
    def _update(revision: int, reason: str) -> str:
        if (type(revision) is not int or not 0 <= revision <= 2_147_483_646
                or not isinstance(reason,str) or not reason.strip() or len(reason)>1000):
            raise Work4ceError('invalid_connector_update',422)
        return reason.strip()

    @staticmethod
    def _project(entry: Registration, state: dict) -> dict:
        manifest=entry.manifest
        cap=manifest.capability
        return {'connector_id':manifest.connector_id,'protocol':manifest.protocol,'synthetic':manifest.synthetic,
            'manifest_hash':entry.manifest_hash,'capability_id':cap.capability_id,'capability_version':cap.version,
            'description':cap.description,'required_permissions':list(cap.required_permissions),
            'resource_scope':cap.resource_scope,'data_classification':cap.data_classification,
            'execution_class':cap.execution_class,'side_effects':cap.side_effects,'approval_required':cap.approval_required,
            **state}

    def list(self, context: ExecutionContext) -> list[dict]:
        self._authorize(context)
        entries=[entry for entry in self.gateway._entries.values() if self.gateway._permitted(entry,context)]
        if len(entries)>100:
            raise Work4ceError('registry_budget_exceeded',503)
        return [self._project(entry,self.store.connector_administration(context.tenant_id,entry.manifest.connector_id))
                for entry in sorted(entries,key=lambda item:item.manifest.connector_id)]

    def disable(self, context: ExecutionContext, identity: str, revision: int, reason: str) -> dict:
        entry=self._entry(context,identity)
        reason=self._update(revision,reason)
        state=self.store.change_connector_state(context.tenant_id,context.subject,identity,revision,False,reason)
        return self._project(entry,state)

    async def review_enable(self, context: ExecutionContext, identity: str, revision: int,
                            manifest_hash: str, reason: str) -> dict:
        entry=self._entry(context,identity)
        reason=self._update(revision,reason)
        if not isinstance(manifest_hash,str) or re.fullmatch(r'[0-9a-f]{64}',manifest_hash) is None:
            raise Work4ceError('invalid_connector_update',422)
        if manifest_hash!=entry.manifest_hash:
            raise Work4ceError('connector_review_mismatch',409)
        state=self.store.connector_administration(context.tenant_id,identity)
        if state['enabled'] or state['revision']!=revision:
            raise Work4ceError('connector_revision_conflict',409)
        deadline=min(3,entry.manifest.capability.timeout_seconds)
        try:
            async with asyncio.timeout(deadline):
                discovered=await entry.connector.discover()
        except Exception:
            raise Work4ceError('connector_discovery_failed',503) from None
        try:
            if not isinstance(discovered,list) or len(discovered)!=1:
                raise ValueError('Expected one pinned capability')
            cap=CapabilityManifest.model_validate(discovered[0])
            if digest(cap.model_dump())!=digest(entry.manifest.capability.model_dump()):
                raise ValueError('Capability changed')
        except Exception:
            raise Work4ceError('connector_contract_mismatch',409) from None
        try:
            async with asyncio.timeout(deadline):
                healthy=await entry.connector.health()
        except Exception:
            raise Work4ceError('connector_unhealthy',503) from None
        if healthy is not True:
            raise Work4ceError('connector_unhealthy',503)
        # Recheck trusted definitions after awaits; the database CAS also fences
        # a later disablement, including another legacy disable of an inactive source.
        if (self.gateway._entries.get(identity) is not entry or not self.gateway._permitted(entry,context)
                or entry.manifest_hash!=manifest_hash):
            raise Work4ceError('connector_definition_changed',409)
        state=self.store.change_connector_state(context.tenant_id,context.subject,identity,revision,True,reason,
                                                manifest_hash=manifest_hash)
        return self._project(entry,state)
