"""Evidence-bound model assistance with durable admission and independent policy.

Models propose one existing read and select exact quotations. They cannot grant
permissions, expand query scope, execute responses or create factual assertions.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import asdict
from typing import Any, Callable

from .contracts import ExecutionContext, Work4ceError, digest
from .models import Assessment, ModelGateway, ModelResult, Plan, PROMPT_VERSION
from .storage import Store

_SECRET = re.compile(r'(?i)(?:\b(?:password|api[_-]?key|secret|access[_-]?token)\s*[:=]\s*\S+|\bbearer\s+[A-Za-z0-9._~+/-]{8,}|\bsk-[A-Za-z0-9_-]{12,})')


def admit_payload(value: Any) -> None:
    """Block recognizable credential patterns; this is not a general DLP engine."""
    if isinstance(value, str) and _SECRET.search(value):
        raise Work4ceError('model_sensitive_input', 422)
    if isinstance(value, dict):
        for item in value.values():
            admit_payload(item)
    elif isinstance(value, list):
        for item in value:
            admit_payload(item)


class Reasoner:
    def __init__(self, gateway: ModelGateway, store: Store, *, max_calls: int = 4,
                 max_tokens: int = 36_000, max_cost_microusd: int = 1_000_000):
        if (type(max_calls) is not int or not 1 <= max_calls <= 8
                or type(max_tokens) is not int or not 1 <= max_tokens <= 262144
                or type(max_cost_microusd) is not int or not 0 <= max_cost_microusd <= 1_000_000_000):
            raise ValueError('Invalid durable model budgets')
        self.gateway, self.store = gateway, store
        self.max_calls, self.max_tokens, self.max_cost_microusd = max_calls, max_tokens, max_cost_microusd
        self.config_hash = digest({'gateway':gateway.fingerprint, 'policy':'exact-evidence-v1',
            'max_calls':max_calls, 'max_tokens':max_tokens, 'max_cost_microusd':max_cost_microusd})

    async def close(self) -> None:
        await self.gateway.close()

    def _cost(self, result: ModelResult) -> int:
        return (result.input_tokens * self.gateway.input_price_microusd_per_million
                + result.output_tokens * self.gateway.output_price_microusd_per_million + 999_999) // 1_000_000

    async def _run(self, context: ExecutionContext, identity: str, worker: str, stage: str,
                   payload: dict[str, Any], validate: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        admit_payload(payload)
        input_hash = digest(payload)
        cached = self.store.get_model_result(context.tenant_id, context.subject, identity, stage,
                                             input_hash, self.config_hash)
        if cached is not None:
            try:
                result = self.gateway.validate_result(ModelResult(**cached), stage)
                validate(result.output)
            except Work4ceError:
                raise
            except Exception:
                raise Work4ceError('model_result_integrity_failure', 500) from None
            return result.output
        active_attempt = None

        def reserve() -> None:
            nonlocal active_attempt
            if active_attempt is not None:
                self.store.fail_model_call(context.tenant_id, context.subject, identity, worker,
                                           active_attempt, 'model_retry')
                active_attempt = None
            active_attempt = self.store.reserve_model_call(context.tenant_id, context.subject, identity,
                worker, stage, input_hash, self.config_hash,
                reserved_tokens=self.gateway.max_input_tokens + self.gateway.max_output_tokens,
                reserved_cost_microusd=self.gateway.estimated_cost_microusd,
                max_calls=self.max_calls, max_tokens=self.max_tokens, max_cost_microusd=self.max_cost_microusd)

        try:
            result = await self.gateway.run(stage, payload, before_attempt=reserve)
            validate(result.output)
            self.store.complete_model_call(context.tenant_id, context.subject, identity, worker,
                active_attempt, asdict(result), actual_input_tokens=result.input_tokens,
                actual_output_tokens=result.output_tokens, actual_cost_microusd=self._cost(result))
            return result.output
        except asyncio.CancelledError:
            # Unknown provider outcomes retain their reservation; no automatic refund.
            raise
        except Exception as error:
            code = error.code if isinstance(error, Work4ceError) else 'model_assistance_failed'
            if active_attempt is not None:
                try:
                    self.store.fail_model_call(context.tenant_id, context.subject, identity, worker,
                                               active_attempt, code)
                except Exception:
                    # Preserve the original error; reserved usage remains conservatively charged.
                    pass
            if isinstance(error, Work4ceError):
                raise
            raise Work4ceError(code, 503) from None

    async def plan(self, context: ExecutionContext, identity: str, worker: str,
                   query: str, limit: int, capabilities: list[dict[str, Any]]) -> dict[str, Any]:
        allowed = [{'capability_id':item['capability_id'], 'version':item['version']}
                   for item in capabilities if item['capability_id'] == 'security.events.search' and item['version'] == '1.0']
        if not allowed:
            raise Work4ceError('no_authorized_connector', 403)

        def validate(output: dict[str, Any]) -> None:
            try:
                plan = Plan.model_validate(output)
                if (plan.arguments.query != query or plan.arguments.limit != limit
                        or {'capability_id':plan.capability_id,'version':plan.version} not in allowed):
                    raise ValueError('Scope expansion')
            except Exception:
                raise Work4ceError('model_plan_rejected', 502) from None

        return await self._run(context, identity, worker, 'plan',
                               {'query':query, 'limit':limit, 'capabilities':allowed}, validate)

    async def assess(self, context: ExecutionContext, identity: str, worker: str,
                     evidence: list[dict[str, Any]]) -> dict[str, Any]:
        sources = {item['evidence_id']:item for item in evidence}
        payload = {'evidence':[{'evidence_id':item['evidence_id'],'summary':item['content']['summary']}
                               for item in evidence]}

        def validate(output: dict[str, Any]) -> None:
            try:
                assessment = Assessment.model_validate(output)
                seen = set()
                for observation in assessment.observations:
                    source = sources.get(observation.evidence_id)
                    if (source is None or source['synthetic'] is not True
                            or source['content_hash'] != digest(source['content'])
                            or observation.quote != source['content']['summary']
                            or observation.evidence_id in seen):
                        raise ValueError('Ungrounded observation')
                    seen.add(observation.evidence_id)
                if ((assessment.assessment == 'needs_analyst_review') != bool(assessment.observations)):
                    raise ValueError('Unsupported assessment')
            except Exception:
                raise Work4ceError('model_evidence_rejected', 502) from None

        return await self._run(context, identity, worker, 'assessment', payload, validate)

    def metadata(self, context: ExecutionContext, identity: str) -> dict[str, Any]:
        return {'provider':self.gateway.provider_name, 'model':self.gateway.model_name,
                'synthetic_fixture':self.gateway.is_synthetic,
                'prompt_version':PROMPT_VERSION, 'config_hash':self.config_hash,
                'cost_basis':'operator_configured_prices_not_verified_billing',
                'usage':self.store.model_usage(context.tenant_id, context.subject, identity)}
