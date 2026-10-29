"""Durable deterministic investigation; telemetry never controls policy or execution."""
from __future__ import annotations

import asyncio
import re
import sys
import time
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, ConfigDict

from .contracts import ExecutionContext, Work4ceError, digest
from .gateway import Gateway
from .storage import Store, now
from .reasoning import Reasoner


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_id: str
    tenant_id: str
    source_event_id: str
    connector_id: str
    protocol: str
    capability_id: str
    capability_version: str
    manifest_hash: str
    collected_at: str
    content_hash: str
    synthetic: bool
    content: dict[str, Any]


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    resolved: dict[str, Any]
    evidence: list[Evidence]


class Investigator:
    def __init__(self, gateway: Gateway, store: Store, *, max_tool_calls: int = 2, duration_seconds: float = 120, reasoner: Reasoner | None = None, require_review: bool = False):
        if type(max_tool_calls) is not int or not 1 <= max_tool_calls <= 8:
            raise ValueError("Tool-call budget must be 1..8")
        if type(duration_seconds) not in (int, float) or not .01 <= duration_seconds <= 600:
            raise ValueError("Investigation deadline must be .01..600 seconds")
        self.gateway, self.store = gateway, store
        if reasoner is not None and reasoner.store is not store:
            raise ValueError("Reasoning and investigations must use the same scoped store")
        if type(require_review) is not bool:
            raise ValueError("Review requirement must be an explicit boolean")
        self.require_review = require_review
        self.reasoner = reasoner
        self.max_tool_calls, self.duration_seconds = max_tool_calls, duration_seconds

    def _authorize(self, context: ExecutionContext) -> None:
        if not {"investigations:run", "events:read"} <= context.permissions or not context.synthetic:
            self.store.audit(context.tenant_id, context.subject, "investigation.start", "request", "denied")
            raise Work4ceError("permission_denied", 403)

    def enqueue(self, context: ExecutionContext, query: str, limit: int = 20, *, idempotency_key: str | None = None) -> dict[str, Any]:
        self._authorize(context)
        if not isinstance(query, str) or not 1 <= len(query) <= 200 or type(limit) is not int or not 1 <= limit <= 100:
            raise Work4ceError("invalid_arguments", 422)
        key = idempotency_key if idempotency_key is not None else str(uuid4())
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
            raise Work4ceError("invalid_idempotency_key", 422)
        return self.store.create_workflow(context.tenant_id, context.subject, query, limit, key,
                                          max_tool_calls=self.max_tool_calls, duration_seconds=self.duration_seconds,
                                          reasoning_config_hash=self.reasoner.config_hash if self.reasoner else None,
                                          review_required=self.require_review)

    async def investigate(self, context: ExecutionContext, query: str, limit: int = 20, *, idempotency_key: str | None = None) -> dict[str, Any]:
        state = self.enqueue(context, query, limit, idempotency_key=idempotency_key)
        return await self.resume(context, state["id"])

    def _checkpoint(self, context: ExecutionContext, checkpoint: dict[str, Any]) -> Checkpoint:
        try:
            typed = Checkpoint.model_validate(checkpoint)
            resolved = typed.resolved
            self.gateway.authorize_checkpoint(context, resolved)
            events = resolved["data"]["events"]
            if len(events) != len(typed.evidence):
                raise ValueError("evidence length mismatch")
            for event, item in zip(events, typed.evidence, strict=True):
                if (item.tenant_id != context.tenant_id or item.content != event
                        or item.content_hash != digest(event) or not item.synthetic
                        or event.get("synthetic") is not True
                        or item.source_event_id != event["id"]
                        or any(getattr(item, name) != resolved[name] for name in (
                            "connector_id", "protocol", "capability_id", "capability_version", "manifest_hash"))):
                    raise ValueError("invalid evidence provenance")
            return typed
        except Work4ceError:
            raise
        except Exception:
            raise Work4ceError("checkpoint_integrity_failure", 500) from None

    async def resume(self, context: ExecutionContext, identity: str) -> dict[str, Any]:
        self._authorize(context)
        state = self.store.get_workflow(context.tenant_id, context.subject, identity)
        if bool(state["review_required"]) != self.require_review:
            raise Work4ceError("review_configuration_changed",409)
        if state["reasoning_config_hash"] != (self.reasoner.config_hash if self.reasoner else None):
            raise Work4ceError("model_configuration_changed", 409)
        if state["state"] == "completed":
            if state["checkpoint"] is None:
                raise Work4ceError("checkpoint_integrity_failure", 500)
            self._checkpoint(context, state["checkpoint"])
            return self.store.get(context.tenant_id, identity)
        if state["state"] in {"failed", "cancelled"}:
            raise Work4ceError("workflow_terminal", 409)
        worker = str(uuid4())
        state = self.store.claim_workflow(context.tenant_id, context.subject, identity, worker)
        try:
            remaining = state["deadline"] - time.time()
            async with asyncio.timeout(max(0, min(remaining, 25))):
                checkpoint = state["checkpoint"]
                if checkpoint is None:
                    capability_id, version = "security.events.search", "1.0"
                    arguments = {"query":state["query"], "limit":state["limit"]}
                    if self.reasoner is not None:
                        plan = await self.reasoner.plan(context, identity, worker, state["query"], state["limit"],
                                                        self.gateway.capabilities(context))
                        capability_id, version, arguments = plan["capability_id"], plan["version"], plan["arguments"]
                    resolved = await self.gateway.execute(context, capability_id, arguments, version,
                        before_invoke=lambda: self.store.reserve_tool_call(context.tenant_id, context.subject, identity, worker))
                    evidence = [Evidence(evidence_id=str(uuid4()), tenant_id=context.tenant_id,
                        source_event_id=event["id"], connector_id=resolved["connector_id"], protocol=resolved["protocol"],
                        capability_id=resolved["capability_id"], capability_version=resolved["capability_version"],
                        manifest_hash=resolved["manifest_hash"], collected_at=now(), content_hash=digest(event),
                        synthetic=True, content=event) for event in resolved["data"]["events"]]
                    checkpoint = Checkpoint(resolved=resolved, evidence=evidence).model_dump()
                    self.store.checkpoint_workflow(context.tenant_id, context.subject, identity, worker, checkpoint)
                typed = self._checkpoint(context, checkpoint)
                evidence = [item.model_dump() for item in typed.evidence]
                findings = ([{"finding_id": str(uuid5(NAMESPACE_URL, identity + ":match")),
                    "statement": "Synthetic telemetry matched the literal search query; malicious intent is not established.",
                    "evidence_ids": [e["evidence_id"] for e in evidence]}] if evidence else [])
                report = {"id": identity, "tenant_id": context.tenant_id, "synthetic": True,
                    "engine": "deterministic-demo-v1", "query": state["query"], "evidence": evidence,
                    "findings": findings, "assessment": "needs_analyst_review" if evidence else "inconclusive",
                    "limitations": ["Synthetic telemetry only; no live vendor or AI model invoked.",
                        "Missing telemetry cannot establish absence of compromise."]}
                if self.reasoner is not None:
                    assessment = await self.reasoner.assess(context, identity, worker, evidence)
                    report["engine"] = ("structured-fixture-v1" if self.reasoner.gateway.is_synthetic
                                        else "structured-model-v1")
                    report["assessment"] = assessment["assessment"]
                    report["findings"] = [{"finding_id":str(uuid5(NAMESPACE_URL, identity + ":" + item["evidence_id"])),
                        "statement":"Observed synthetic telemetry: " + item["quote"],
                        "evidence_ids":[item["evidence_id"]]} for item in assessment["observations"]]
                    report["reasoning"] = self.reasoner.metadata(context, identity)
                    report["limitations"] = ["Synthetic telemetry and model-assisted quotations require analyst review.",
                        "Model output does not establish malicious intent or authorize a response.",
                        "Provider usage and configured prices are not independently verified billing."]
                    if report["reasoning"]["synthetic_fixture"]:
                        report["limitations"].append("The model provider is a deterministic offline fixture; no LLM was invoked.")
                self.store.finish_workflow(context.tenant_id, context.subject, identity, worker, report, "completed")
                return self.store.get(context.tenant_id, identity)
        except asyncio.CancelledError:
            # Runtime task interruption retains a recoverable checkpoint; explicit cancel fences it.
            raise
        except Exception as exc:
            code = exc.code if isinstance(exc, Work4ceError) else (
                "workflow_deadline_exceeded" if isinstance(exc, TimeoutError) else "investigation_failed")
            # Cancellation/lease loss must never be overwritten by a stale worker.
            if code not in {"workflow_lease_lost", "workflow_cancelled", "workflow_terminal"}:
                try:
                    self.store.finish_workflow(context.tenant_id, context.subject, identity, worker,
                        {"id": identity, "synthetic": True, "error": code, "evidence": [], "findings": []}, "failed")
                except Work4ceError as finish_error:
                    if finish_error.code not in {"workflow_lease_lost", "workflow_cancelled", "workflow_terminal"}:
                        raise
                except Exception:
                    raise Work4ceError("workflow_persistence_failed", 503) from None
            if isinstance(exc, Work4ceError):
                raise
            raise Work4ceError(code, 409 if isinstance(exc, TimeoutError) else 503) from None
        finally:
            primary_error = sys.exc_info()[0] is not None
            try:
                self.store.release_workflow(context.tenant_id, context.subject, identity, worker)
            except Exception:
                # Preserve cancellation/primary failure. A crashed worker's lease expires.
                if not primary_error:
                    raise Work4ceError("workflow_persistence_failed", 503) from None

    async def cancel(self, context: ExecutionContext, identity: str) -> dict[str, Any]:
        self._authorize(context)
        self.store.cancel_workflow(context.tenant_id, context.subject, identity)
        return self.store.get(context.tenant_id, identity)
