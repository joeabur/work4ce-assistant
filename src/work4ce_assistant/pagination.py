"""Bounded, scope-bound keyset markers; cursors never confer authorization.

These markers are deliberately unsigned. Every request must authenticate again
and apply its trusted tenant/owner SQL filters, even for a caller-crafted cursor.
"""
import base64
from datetime import datetime
import json
import re
from uuid import UUID

from .contracts import Work4ceError, canonical, digest

MAX_CURSOR_LENGTH = 512
_TIMESTAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})')


def _scope(tenant: str, subject: str | None) -> str:
    return digest({'tenant':tenant,'subject':subject})


def _anchor(created_at, identity) -> None:
    if (not isinstance(created_at,str) or len(created_at) > 40 or _TIMESTAMP.fullmatch(created_at) is None
            or not isinstance(identity,str) or len(identity) != 36 or str(UUID(identity)) != identity):
        raise ValueError('Invalid position')
    if datetime.fromisoformat(created_at.replace('Z','+00:00')).tzinfo is None:
        raise ValueError('Missing timestamp offset')


def encode_history_cursor(tenant: str, subject: str | None, created_at: str, identity: str) -> str:
    try:
        _anchor(created_at,identity)
        raw = canonical({'v':1,'scope':_scope(tenant,subject),'created_at':created_at,'id':identity}).encode()
        return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
    except (ValueError,TypeError,AttributeError):
        raise Work4ceError('history_position_invalid',500) from None


def _unique_object(pairs):
    value = {}
    for key,item in pairs:
        if key in value:
            raise ValueError('Duplicate field')
        value[key] = item
    return value


def decode_history_cursor(cursor: str, tenant: str, subject: str | None) -> tuple[str,str]:
    try:
        if (not isinstance(cursor,str) or not 1 <= len(cursor) <= MAX_CURSOR_LENGTH
                or re.fullmatch(r'[A-Za-z0-9_-]+',cursor) is None):
            raise ValueError('Invalid encoding')
        raw = base64.b64decode(cursor + '=' * (-len(cursor) % 4),altchars=b'-_',validate=True)
        if base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=') != cursor:
            raise ValueError('Noncanonical encoding')
        value = json.loads(raw.decode('utf-8'),object_pairs_hook=_unique_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid constant')))
        if (not isinstance(value,dict) or set(value) != {'v','scope','created_at','id'}
                or type(value['v']) is not int or value['v'] != 1
                or not isinstance(value['scope'],str) or value['scope'] != _scope(tenant,subject)):
            raise ValueError('Invalid cursor fields or scope')
        _anchor(value['created_at'],value['id'])
        return value['created_at'],value['id']
    except (ValueError,TypeError,AttributeError,RecursionError):
        raise Work4ceError('invalid_history_cursor',422) from None
