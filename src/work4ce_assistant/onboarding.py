"""Read-only synthetic setup observations; never provision credentials or run a model."""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from .contracts import ExecutionContext, Work4ceError
from .gateway import Gateway
from .storage import HEAD, Store


async def setup_status(store: Store, gateway: Gateway, context: ExecutionContext, *,
                       auth_mode: str, administrator_configured: bool, reasoning_mode: str,
                       review_required: bool, max_tool_calls: int, timeout_seconds: float) -> dict:
    if ('investigations:read' not in context.permissions or not context.synthetic
            or context.tenant_id != 'synthetic-demo'):
        raise Work4ceError('permission_denied',403)

    revision=None
    database_ready=False
    connectors=[]
    try:
        with store._connection() as connection:
            revisions=connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        database_ready=revisions==[HEAD]
        revision=HEAD if database_ready else None
        # Gateway projection rechecks tenant, grants, allowlist and definition integrity.
        connectors=gateway.list_connectors(context)
    except Exception:
        # Diagnostic exceptions may include a DSN or connector route. Return observations only.
        database_ready=False
        revision=None
    if len(connectors)>100:
        raise Work4ceError('registry_budget_exceeded',503)
    rows=[{**item,'health':'unhealthy' if item['enabled'] else 'disabled'} for item in connectors]
    semaphore=asyncio.Semaphore(8)

    async def probe(item):
        if not item['enabled']:
            return
        try:
            async with semaphore,asyncio.timeout(3):
                entry=gateway._entries[item['connector_id']]
                if await entry.connector.health() is True:
                    item['health']='healthy'
        except Exception:
            pass

    try:
        async with asyncio.timeout(6):
            await asyncio.gather(*(probe(item) for item in rows))
    except TimeoutError:
        pass
    can_investigate={'investigations:run','investigations:read','events:read'} <= context.permissions
    return {
        'mode':'demo','synthetic':True,'production_enabled':False,
        'authentication':{'mode':auth_mode,'administrator_configured':administrator_configured},
        'database':{'status':'ready' if database_ready else 'unavailable','schema_revision':revision},
        'reasoning':{'mode':reasoning_mode,'health_checked':False},
        'policy':{'review_required':review_required,'response_mode':'simulation_only',
                  'max_tool_calls':max_tool_calls,'timeout_seconds':timeout_seconds},
        'connectors':rows,'can_investigate':can_investigate,
        'ready_for_investigation':database_ready and can_investigate and any(item['health']=='healthy' for item in rows),
    }
