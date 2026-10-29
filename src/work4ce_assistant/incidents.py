"""Human incident management under the existing case coordination policy."""
from __future__ import annotations

from .cases import CaseService
from .contracts import ExecutionContext
from .incident_storage import IncidentRepository


class IncidentService:
    def __init__(self, policy: CaseService):
        self.policy = policy
        self.repository = IncidentRepository(policy.store)

    def create(self, context: ExecutionContext, investigation_id: str,
               title: str, description: str, severity: str) -> dict:
        self.policy._authorize(context,'cases:coordinate')
        return self.repository.create(context.tenant_id,context.subject,investigation_id,
            title,description,severity,manage='cases:manage' in context.permissions)

    def get(self, context: ExecutionContext, identity: str) -> dict:
        self.policy._authorize(context)
        return self.repository.get(context.tenant_id,context.subject,identity,
            all_cases=self.policy._all_cases(context))

    def for_investigation(self, context: ExecutionContext, investigation_id: str) -> dict:
        self.policy._authorize(context)
        return self.repository.for_investigation(context.tenant_id,context.subject,investigation_id,
            all_cases=self.policy._all_cases(context))

    def list(self, context: ExecutionContext, *, limit: int=50) -> list[dict]:
        self.policy._authorize(context)
        return self.repository.list(context.tenant_id,context.subject,
            all_cases=self.policy._all_cases(context),limit=limit)

    def activity(self, context: ExecutionContext, identity: str) -> list[dict]:
        self.policy._authorize(context)
        return self.repository.activity(context.tenant_id,context.subject,identity,
            all_cases=self.policy._all_cases(context))

    def transition(self, context: ExecutionContext, identity: str, revision: int,
                   status: str, comment: str='') -> dict:
        self.policy._authorize(context,'cases:coordinate')
        return self.repository.transition(context.tenant_id,context.subject,identity,revision,status,comment,
            manage='cases:manage' in context.permissions)

    def add_note(self, context: ExecutionContext, identity: str, revision: int,
                 body: str, evidence_ids: list[str]) -> dict:
        self.policy._authorize(context,'cases:coordinate')
        return self.repository.add_note(context.tenant_id,context.subject,identity,revision,body,evidence_ids,
            manage='cases:manage' in context.permissions)
