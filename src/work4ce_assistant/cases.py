"""Case coordination policy, independent of execution and report approvals."""
from __future__ import annotations

from .contracts import ExecutionContext, Work4ceError
from .storage import Store


class CaseService:
    def __init__(self, store: Store, tenant: str, assignees: frozenset[str]):
        if (not isinstance(tenant,str) or not tenant or len(assignees)>100
                or any(not isinstance(subject,str) or not 1<=len(subject)<=256 for subject in assignees)):
            raise ValueError('Case directory must use trusted configured subjects')
        self.store, self.tenant, self.assignees = store, tenant, frozenset(assignees)

    def _authorize(self, context: ExecutionContext, *permissions: str) -> None:
        required={'cases:read','investigations:read',*permissions}
        if (context.synthetic is not True or context.tenant_id!=self.tenant
                or not required<=context.permissions):
            self.store.audit(context.tenant_id,context.subject,'case.policy','request','denied')
            raise Work4ceError('permission_denied',403)

    @staticmethod
    def _all_cases(context: ExecutionContext) -> bool:
        return bool({'cases:manage','investigations:review'} & context.permissions)

    def directory(self, context: ExecutionContext) -> list[dict[str,str]]:
        self._authorize(context,'cases:coordinate')
        return [{'subject':subject} for subject in sorted(self.assignees)]

    def get(self, context: ExecutionContext, identity: str) -> dict:
        self._authorize(context)
        return self.store.get_case(context.tenant_id,context.subject,identity,
                                   all_cases=self._all_cases(context))

    def list(self, context: ExecutionContext, *, limit: int=50) -> list[dict]:
        self._authorize(context)
        return self.store.list_cases(context.tenant_id,context.subject,
                                     all_cases=self._all_cases(context),limit=limit)

    def assign(self, context: ExecutionContext, identity: str, revision: int, assignee: str | None) -> dict:
        self._authorize(context,'cases:coordinate')
        if assignee is not None and (not isinstance(assignee,str) or assignee not in self.assignees):
            raise Work4ceError('invalid_case_assignee',422)
        return self.store.mutate_case(context.tenant_id,context.subject,identity,revision,'assign',
            assignee=assignee,manage='cases:manage' in context.permissions)

    def escalate(self, context: ExecutionContext, identity: str, revision: int, reason: str) -> dict:
        self._authorize(context,'cases:coordinate')
        return self.store.mutate_case(context.tenant_id,context.subject,identity,revision,'escalate',
            reason=reason,manage='cases:manage' in context.permissions)

    def acknowledge(self, context: ExecutionContext, identity: str, revision: int) -> dict:
        self._authorize(context,'cases:coordinate','cases:manage')
        return self.store.mutate_case(context.tenant_id,context.subject,identity,revision,'acknowledge',manage=True)
