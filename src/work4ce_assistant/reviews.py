"""Human review policy and synthetic response simulation, outside model reasoning.

No endpoint or connector action is executed. The database atomically consumes a
bound approval and records a dry-run result. Live response adapters are absent.
"""
from __future__ import annotations

import re
from typing import Any

from .contracts import ExecutionContext, Work4ceError
from .gateway import Gateway
from .storage import Store


class ReviewService:
    def __init__(self, store: Store, gateway: Gateway):
        if gateway.store is not store:
            raise ValueError('Review and policy must share the same scoped store')
        self.store, self.gateway = store, gateway

    def _authorize(self, context: ExecutionContext, *permissions: str) -> None:
        if context.synthetic is not True or not set(permissions) <= context.permissions:
            self.store.audit(context.tenant_id,context.subject,'review.policy','request','denied')
            raise Work4ceError('permission_denied',403)

    def _source(self, context: ExecutionContext, investigation_id: str, requester: str) -> dict[str, Any]:
        state=self.store.get_workflow(context.tenant_id,requester,investigation_id)
        if state['state']!='completed' or state['checkpoint'] is None:
            raise Work4ceError('investigation_not_collected',409)
        # The actor's present grants remain authoritative; approval cannot restore a
        # disabled connector, changed definition or removed evidence permission.
        self.gateway.authorize_checkpoint(context,state['checkpoint']['resolved'])
        report=self.store.get(context.tenant_id,investigation_id)
        if report['report'].get('synthetic') is not True:
            raise Work4ceError('synthetic_response_only',403)
        return report

    def request_review(self, context: ExecutionContext, investigation_id: str) -> dict[str, Any]:
        self._authorize(context,'investigations:run','investigations:read','events:read')
        self._source(context,investigation_id,context.subject)
        return self.store.request_review(context.tenant_id,context.subject,investigation_id)

    def get_review(self, context: ExecutionContext, investigation_id: str) -> dict[str, Any]:
        self._authorize(context,'investigations:read')
        review=self.store.get_review(context.tenant_id,investigation_id)
        if review['requester']!=context.subject and 'investigations:review' not in context.permissions:
            raise Work4ceError('review_not_found',404)
        return review

    def list_reviews(self, context: ExecutionContext) -> list[dict[str, Any]]:
        self._authorize(context,'investigations:review','investigations:read')
        return self.store.list_reviews(context.tenant_id)

    def decide_review(self, context: ExecutionContext, investigation_id: str, review_id: str,
                      decision: str, comment: str='') -> dict[str, Any]:
        self._authorize(context,'investigations:review','investigations:read','events:read')
        review=self.store.get_review(context.tenant_id,investigation_id)
        self._source(context,investigation_id,review['requester'])
        return self.store.decide_review(context.tenant_id,context.subject,investigation_id,review_id,decision,comment)

    def _response_scope(self, context: ExecutionContext, proposal: dict[str, Any]) -> None:
        report=self._source(context,proposal['investigation_id'],proposal['requester'])
        action,target,parameters=proposal['action'],proposal['target'],proposal['parameters']
        if (action!='endpoint.isolate' or not isinstance(target,str) or not isinstance(parameters,dict)
                or target not in {'demo-host-1','demo-host-2'}
                or set(parameters)!={'duration_minutes'} or type(parameters['duration_minutes']) is not int
                or not 1 <= parameters['duration_minutes'] <= 60):
            raise Work4ceError('synthetic_response_only',403)
        pattern=r'(?<![A-Za-z0-9-])'+re.escape(target)+r'(?![A-Za-z0-9-])'
        if not any(re.search(pattern,e['content']['summary']) for e in report['report']['evidence']):
            raise Work4ceError('response_target_unobserved',403)

    def propose(self, context: ExecutionContext, investigation_id: str, action: str, target: str,
                parameters: dict[str, Any], *, lifetime_seconds: int=300) -> dict[str, Any]:
        self._authorize(context,'responses:propose','investigations:read','events:read')
        proposal={'investigation_id':investigation_id,'requester':context.subject,
                  'action':action,'target':target,'parameters':parameters}
        self._response_scope(context,proposal)
        return self.store.create_response(context.tenant_id,context.subject,investigation_id,
                                          action,target,parameters,lifetime_seconds=lifetime_seconds)

    def get_response(self, context: ExecutionContext, response_id: str) -> dict[str, Any]:
        self._authorize(context,'responses:read')
        proposal=self.store.get_response(context.tenant_id,response_id)
        if proposal['requester']!=context.subject and 'responses:approve' not in context.permissions:
            raise Work4ceError('response_not_found',404)
        return proposal

    def list_responses(self, context: ExecutionContext) -> list[dict[str, Any]]:
        self._authorize(context,'responses:read')
        return self.store.list_responses(context.tenant_id,
            requester=None if 'responses:approve' in context.permissions else context.subject)

    def decide_response(self, context: ExecutionContext, response_id: str,
                        decision: str, comment: str='') -> dict[str, Any]:
        self._authorize(context,'responses:approve','investigations:read','events:read')
        proposal=self.store.get_response(context.tenant_id,response_id)
        self._response_scope(context,proposal)
        return self.store.decide_response(context.tenant_id,context.subject,response_id,decision,comment)

    def revoke(self, context: ExecutionContext, response_id: str) -> dict[str, Any]:
        self._authorize(context,'responses:read')
        proposal=self.store.get_response(context.tenant_id,response_id)
        if proposal['requester']==context.subject:
            self._authorize(context,'responses:propose')
        elif 'responses:approve' not in context.permissions:
            raise Work4ceError('response_not_found',404)
        return self.store.revoke_response(context.tenant_id,response_id,context.subject)

    def simulate(self, context: ExecutionContext, response_id: str, approval_id: str) -> dict[str, Any]:
        self._authorize(context,'responses:simulate','investigations:read','events:read')
        proposal=self.store.get_response(context.tenant_id,response_id)
        if proposal['requester']!=context.subject:
            raise Work4ceError('response_not_found',404)
        self._response_scope(context,proposal)
        # Synchronous policy-to-transaction boundary: consumption rechecks every
        # persisted binding/expiry under row lock, immediately before dry-run commit.
        return self.store.consume_response(context.tenant_id,context.subject,response_id,approval_id)
