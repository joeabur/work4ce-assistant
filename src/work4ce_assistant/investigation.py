"""Deterministic demo investigator. Telemetry is data, never policy or instructions."""
from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from .contracts import ExecutionContext, Work4ceError, digest
from .gateway import Gateway
from .storage import Store, now


class Investigator:
    def __init__(self, gateway: Gateway, store: Store):
        self.gateway, self.store = gateway, store

    async def investigate(self, context: ExecutionContext, query: str, limit: int = 20) -> dict[str, Any]:
        if "investigations:run" not in context.permissions or not context.synthetic:
            self.store.audit(context.tenant_id, context.subject, "investigation.start", "request", "denied")
            raise Work4ceError("permission_denied", 403)
        # Validate before storing or dispatching anything.
        if not isinstance(query, str) or not 1 <= len(query) <= 200 or type(limit) is not int or not 1 <= limit <= 100:
            raise Work4ceError("invalid_arguments", 422)
        identity = self.store.begin(context.tenant_id, context.subject)
        try:
            resolved = await self.gateway.execute(context, "security.events.search", {"query": query, "limit": limit})
            evidence = []
            for event in resolved["data"]["events"]:
                if event["synthetic"] is not True:
                    raise Work4ceError("demo_isolation_failure", 502)
                evidence.append({"evidence_id": str(uuid4()), "tenant_id": context.tenant_id,
                                 "source_event_id": event["id"], "connector_id": resolved["connector_id"],
                                 "protocol": resolved["protocol"], "capability_id": resolved["capability_id"],
                                 "capability_version": resolved["capability_version"],
                                 "manifest_hash": resolved["manifest_hash"], "collected_at": now(),
                                 "content_hash": digest(event), "synthetic": True, "content": event})
            findings = ([{"finding_id": str(uuid4()), "statement": "Synthetic telemetry matched the literal search query; malicious intent is not established.",
                          "evidence_ids": [e["evidence_id"] for e in evidence]}] if evidence else [])
            report = {"id": identity, "tenant_id": context.tenant_id, "synthetic": True,
                      "engine": "deterministic-demo-v1", "query": query, "evidence": evidence,
                      "findings": findings, "assessment": "needs_analyst_review" if evidence else "inconclusive",
                      "limitations": ["Synthetic telemetry only; no live vendor or AI model invoked.",
                                      "Missing telemetry cannot establish absence of compromise."]}
            self.store.finish(context.tenant_id, context.subject, identity, report, "completed")
            return self.store.get(context.tenant_id, identity)
        except (Exception, asyncio.CancelledError) as exc:
            code = exc.code if isinstance(exc, Work4ceError) else "investigation_failed"
            self.store.finish(context.tenant_id, context.subject, identity,
                              {"id": identity, "synthetic": True, "error": code, "evidence": [], "findings": []},
                              "failed")
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, Work4ceError):
                raise
            raise Work4ceError(code, 503) from None
