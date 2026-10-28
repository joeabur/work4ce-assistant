"""Tenant-scoped SQLAlchemy persistence with versioned, explicit migrations.

SQLite demo databases bootstrap on open. PostgreSQL requires migrate() first.
Methods are synchronous; deployments need worker isolation before scaling.
"""
from __future__ import annotations

import json
import threading
import math
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Column, Float, ForeignKey, Integer, MetaData, Table, Text, and_, create_engine, event, func, inspect, or_, select, text, update
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from .contracts import Work4ceError, canonical, digest

HEAD = "0002_workflows"
metadata = MetaData()
investigations = Table("investigations", metadata,
    Column("id", Text, primary_key=True), Column("tenant", Text, nullable=False),
    Column("subject", Text, nullable=False), Column("status", Text, nullable=False),
    Column("report", Text), Column("report_hash", Text),
    Column("created_at", Text, nullable=False), Column("updated_at", Text, nullable=False))
audit_table = Table("audit", metadata,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("tenant", Text, nullable=False), Column("subject", Text, nullable=False),
    Column("action", Text, nullable=False), Column("target", Text, nullable=False),
    Column("outcome", Text, nullable=False), Column("timestamp", Text, nullable=False))
connector_state = Table("connector_state", metadata,
    Column("tenant", Text, primary_key=True), Column("id", Text, primary_key=True),
    Column("enabled", Integer, nullable=False))

workflow_owner_locks = Table("workflow_owner_locks", metadata,
    Column("tenant", Text, primary_key=True), Column("subject", Text, primary_key=True))
workflow_state = Table("workflow_state", metadata,
    Column("id", Text, ForeignKey("investigations.id"), primary_key=True),
    Column("tenant", Text, nullable=False), Column("subject", Text, nullable=False),
    Column("idempotency_key", Text, nullable=False), Column("request_hash", Text, nullable=False),
    Column("query", Text, nullable=False), Column("limit", Integer, nullable=False),
    Column("max_tool_calls", Integer, nullable=False), Column("tool_calls", Integer, nullable=False),
    Column("deadline", Float, nullable=False), Column("checkpoint", Text), Column("checkpoint_hash", Text),
    Column("state", Text, nullable=False), Column("lease_owner", Text), Column("lease_until", Float),
    Column("revision", Integer, nullable=False))
TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


class _IdempotencyRace(Exception):
    """Roll back the losing transaction before loading the committed winner."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _engine(database: str) -> Engine:
    try:
        if "://" not in database:
            if database != ":memory:":
                Path(database).parent.mkdir(parents=True, exist_ok=True)
            url = make_url("sqlite+pysqlite:///:memory:") if database == ":memory:" else make_url("sqlite+pysqlite://").set(database=str(Path(database).resolve()))
        else:
            url = make_url(database)
        if url.drivername in ("postgres", "postgresql"):
            url = url.set(drivername="postgresql+psycopg")
        if url.drivername not in ("sqlite", "sqlite+pysqlite", "postgresql+psycopg"):
            raise Work4ceError("unsupported_database", 500)
        options: dict[str, Any] = {"pool_pre_ping": True, "hide_parameters": True, "echo": False}
        if url.get_backend_name() == "sqlite":
            options["connect_args"] = {"check_same_thread": False, "timeout": 10}
            if url.database in (None, "", ":memory:"):
                options["poolclass"] = StaticPool
            else:
                options.update(pool_size=4, max_overflow=0, pool_timeout=10)
        else:
            options.update(pool_size=4, max_overflow=0, pool_timeout=10, connect_args={"connect_timeout": 10})
        engine = create_engine(url, **options)
        if url.get_backend_name() == "sqlite":
            @event.listens_for(engine, "connect")
            def sqlite_pragmas(connection, record):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
        return engine
    except Work4ceError:
        raise
    except (SQLAlchemyError, ValueError, OSError):
        raise Work4ceError("database_configuration_invalid", 500) from None


def _config(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.attributes["connection"] = connection
    return config


def _validate_legacy(connection: Connection) -> None:
    """Adopt only the exact three-table schema emitted by the original demo."""
    inspector = inspect(connection)
    if connection.dialect.name != "sqlite" or set(inspector.get_table_names()) != {"investigations", "audit", "connector_state"} or inspector.get_view_names():
        raise Work4ceError("unknown_database_schema", 500)
    expected = {
        "investigations": [("id", "TEXT", True, 1), ("tenant", "TEXT", False, 0), ("subject", "TEXT", False, 0),
            ("status", "TEXT", False, 0), ("report", "TEXT", True, 0), ("report_hash", "TEXT", True, 0),
            ("created_at", "TEXT", False, 0), ("updated_at", "TEXT", False, 0)],
        "audit": [("sequence", "INTEGER", True, 1), ("tenant", "TEXT", False, 0), ("subject", "TEXT", False, 0),
            ("action", "TEXT", False, 0), ("target", "TEXT", False, 0), ("outcome", "TEXT", False, 0), ("timestamp", "TEXT", False, 0)],
        "connector_state": [("tenant", "TEXT", False, 1), ("id", "TEXT", False, 2), ("enabled", "INTEGER", False, 0)],
    }
    for table, columns in expected.items():
        actual = [(c["name"], str(c["type"]), c["nullable"], c["primary_key"]) for c in inspector.get_columns(table)]
        if actual != columns or inspector.get_foreign_keys(table) or inspector.get_indexes(table) or inspector.get_unique_constraints(table) or inspector.get_check_constraints(table):
            raise Work4ceError("unknown_database_schema", 500)
    if connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger'")).first():
        raise Work4ceError("unknown_database_schema", 500)
    audit_sql = connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='audit'")).scalar_one()
    if "AUTOINCREMENT" not in audit_sql.upper():
        raise Work4ceError("unknown_database_schema", 500)


def _migrate_connection(connection: Connection) -> None:
    inspector = inspect(connection)
    tables = inspector.get_table_names()
    if "alembic_version" not in tables and (tables or inspector.get_view_names()):
        _validate_legacy(connection)
        # Existing schema is exactly the first revision, so preserve rows intact.
        command.stamp(_config(connection), "0001_foundation")
    context = MigrationContext.configure(connection)
    revisions = context.get_current_heads()
    known_revisions = {revision.revision for revision in ScriptDirectory.from_config(_config(connection)).walk_revisions()}
    if len(revisions) > 1 or any(revision not in known_revisions for revision in revisions):
        raise Work4ceError("database_schema_unsupported", 500)
    if not revisions and "alembic_version" in tables and (set(tables) != {"alembic_version"} or inspector.get_view_names()):
        raise Work4ceError("unknown_database_schema", 500)
    command.upgrade(_config(connection), "head")


def migrate(database: str) -> None:
    """Explicitly upgrade a configured database; never logs URLs or credentials."""
    engine = _engine(database)
    try:
        with engine.begin() as connection:
            _migrate_connection(connection)
    except Work4ceError:
        raise
    except Exception:
        raise Work4ceError("database_migration_failed", 500) from None
    finally:
        engine.dispose()


class Store:
    def __init__(self, path_or_url: str):
        self._lock = threading.RLock()
        self.engine = _engine(path_or_url)
        try:
            with self.engine.begin() as connection:
                if self.engine.dialect.name == "sqlite":
                    _migrate_connection(connection)
                elif MigrationContext.configure(connection).get_current_heads() != (HEAD,):
                    raise Work4ceError("database_schema_outdated", 500)
        except Work4ceError:
            self.engine.dispose()
            raise
        except Exception:
            self.engine.dispose()
            raise Work4ceError("database_unavailable", 503) from None

    @contextmanager
    def _connection(self, *, write: bool = False):
        try:
            with self._lock:
                with self.engine.begin() if write else self.engine.connect() as connection:
                    yield connection
        except SQLAlchemyError:
            raise Work4ceError("database_unavailable", 503) from None

    def _audit(self, connection: Connection, tenant: str, subject: str, action: str, target: str, outcome: str) -> None:
        connection.execute(audit_table.insert().values(tenant=tenant, subject=subject, action=action, target=target, outcome=outcome, timestamp=now()))

    def audit(self, tenant: str, subject: str, action: str, target: str, outcome: str) -> None:
        with self._connection(write=True) as connection:
            self._audit(connection, tenant, subject, action, target, outcome)

    def begin(self, tenant: str, subject: str) -> str:
        identity = str(uuid4())
        with self._connection(write=True) as connection:
            connection.execute(investigations.insert().values(id=identity, tenant=tenant, subject=subject, status="running", created_at=now(), updated_at=now()))
            self._audit(connection, tenant, subject, "investigation.start", identity, "running")
        return identity

    def finish(self, tenant: str, subject: str, identity: str, report: dict[str, Any], status: str) -> None:
        with self._connection(write=True) as connection:
            # Compatibility API is only for pre-workflow records; managed workflows
            # must pass the lease/cancellation fences in finish_workflow().
            managed = connection.execute(select(workflow_state.c.id).where(
                workflow_state.c.id == identity, workflow_state.c.tenant == tenant)).first()
            if managed is not None:
                raise Work4ceError("workflow_lease_required", 409)
            cursor = connection.execute(update(investigations).where(investigations.c.id == identity, investigations.c.tenant == tenant).values(status=status, report=canonical(report), report_hash=digest(report), updated_at=now()))
            if cursor.rowcount != 1:
                raise Work4ceError("investigation_not_found", 404)
            self._audit(connection, tenant, subject, "investigation.finish", identity, status)

    def get(self, tenant: str, identity: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(select(investigations.c.status, investigations.c.report, investigations.c.report_hash).where(investigations.c.tenant == tenant, investigations.c.id == identity)).first()
        if row is None:
            raise Work4ceError("investigation_not_found", 404)
        try:
            report = json.loads(row.report) if row.report else None
            if report is not None and digest(report) != row.report_hash:
                raise ValueError("hash mismatch")
        except (ValueError, TypeError):
            raise Work4ceError("report_integrity_failure", 500) from None
        return {"id": identity, "status": row.status, "report": report}

    def enabled(self, tenant: str, connector_id: str) -> bool:
        with self._connection() as connection:
            value = connection.execute(select(connector_state.c.enabled).where(connector_state.c.tenant == tenant, connector_state.c.id == connector_id)).scalar()
        return value == 1

    def initialize_connector(self, tenant: str, connector_id: str) -> None:
        # Database-specific conflict handling keeps concurrent bootstrap idempotent.
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        with self._connection(write=True) as connection:
            connection.execute(insert(connector_state).values(tenant=tenant, id=connector_id, enabled=1).on_conflict_do_nothing(index_elements=["tenant", "id"]))

    def disable(self, tenant: str, subject: str, connector_id: str) -> None:
        with self._connection(write=True) as connection:
            connection.execute(update(connector_state).where(connector_state.c.tenant == tenant, connector_state.c.id == connector_id).values(enabled=0))
            self._audit(connection, tenant, subject, "connector.disable", connector_id, "disabled")

    def audit_rows(self, tenant: str) -> list[tuple]:
        with self._connection() as connection:
            return [tuple(row) for row in connection.execute(select(audit_table.c.action, audit_table.c.target, audit_table.c.outcome).where(audit_table.c.tenant == tenant).order_by(audit_table.c.sequence))]

    @staticmethod
    def _workflow_scope(tenant: str, subject: str, identity: str):
        return and_(workflow_state.c.tenant == tenant, workflow_state.c.subject == subject,
                    workflow_state.c.id == identity)

    @staticmethod
    def _workflow_data(row) -> dict[str, Any]:
        data = dict(row._mapping)
        raw, expected = data["checkpoint"], data["checkpoint_hash"]
        if raw is None:
            if expected is not None:
                raise Work4ceError("checkpoint_integrity_failure", 500)
            data["checkpoint"] = None
        else:
            try:
                checkpoint = json.loads(raw)
                if not isinstance(checkpoint, dict) or len(raw.encode()) > 262144 or digest(checkpoint) != expected:
                    raise ValueError("invalid checkpoint")
                data["checkpoint"] = checkpoint
            except (ValueError, TypeError):
                raise Work4ceError("checkpoint_integrity_failure", 500) from None
        return data

    def _load_workflow(self, connection: Connection, tenant: str, subject: str, identity: str, *, lock: bool = False) -> dict[str, Any]:
        statement = select(workflow_state).where(self._workflow_scope(tenant, subject, identity))
        if lock:
            statement = statement.with_for_update()
        row = connection.execute(statement).first()
        if row is None:
            raise Work4ceError("workflow_not_found", 404)
        return self._workflow_data(row)

    def get_workflow(self, tenant: str, subject: str, identity: str) -> dict[str, Any]:
        with self._connection() as connection:
            return self._load_workflow(connection, tenant, subject, identity)

    def create_workflow(self, tenant: str, subject: str, query: str, limit: int, idempotency_key: str,
                        *, max_tool_calls: int = 2, duration_seconds: float = 120) -> dict[str, Any]:
        if (not all(isinstance(value, str) and 1 <= len(value) <= 200 for value in (tenant, query))
                or not isinstance(subject, str) or not 1 <= len(subject) <= 256
                or not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128
                or not idempotency_key.isascii() or not idempotency_key.isprintable() or not idempotency_key.strip()
                or type(limit) is not int or not 1 <= limit <= 100
                or type(max_tool_calls) is not int or not 1 <= max_tool_calls <= 8
                or type(duration_seconds) not in (int, float) or not math.isfinite(duration_seconds)
                or not 0 < duration_seconds <= 600):
            raise Work4ceError("invalid_workflow_request", 422)
        request_hash = digest({"query": query, "limit": limit, "max_tool_calls": max_tool_calls,
                               "duration_seconds": float(duration_seconds)})
        identity = str(uuid4())
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        insert = sqlite_insert if self.engine.dialect.name == "sqlite" else pg_insert
        try:
            with self._connection(write=True) as connection:
                # The owner row serializes this quota and idempotency decision on
                # PostgreSQL. The INSERT also starts SQLite's serialized write
                # transaction, including when the existing lock row is unchanged.
                connection.execute(insert(workflow_owner_locks).values(tenant=tenant, subject=subject)
                    .on_conflict_do_nothing(index_elements=["tenant", "subject"]))
                connection.execute(select(workflow_owner_locks).where(workflow_owner_locks.c.tenant == tenant,
                    workflow_owner_locks.c.subject == subject).with_for_update()).one()
                existing_row = connection.execute(select(workflow_state).where(workflow_state.c.tenant == tenant,
                    workflow_state.c.subject == subject, workflow_state.c.idempotency_key == idempotency_key)).first()
                if existing_row is not None:
                    existing = self._workflow_data(existing_row)
                    if existing["request_hash"] != request_hash:
                        raise Work4ceError("idempotency_conflict", 409)
                    return existing
                pending = connection.execute(select(func.count()).select_from(workflow_state).where(
                    workflow_state.c.tenant == tenant, workflow_state.c.subject == subject,
                    workflow_state.c.state.in_(["queued", "running", "collected"]))).scalar_one()
                if pending >= 100:
                    raise Work4ceError("workflow_queue_full", 429)
                # A uniqueness conflict still rolls back this parent INSERT before
                # loading the winner, so no orphan investigation can survive.
                connection.execute(investigations.insert().values(id=identity, tenant=tenant, subject=subject,
                    status="running", created_at=now(), updated_at=now()))
                created = connection.execute(insert(workflow_state).values(id=identity, tenant=tenant,
                    subject=subject, idempotency_key=idempotency_key, request_hash=request_hash, query=query,
                    limit=limit, max_tool_calls=max_tool_calls, tool_calls=0, deadline=time.time() + duration_seconds,
                    state="queued", revision=0).on_conflict_do_nothing(
                        index_elements=["tenant", "subject", "idempotency_key"]).returning(workflow_state.c.id)).scalar()
                if created is None:
                    raise _IdempotencyRace()
                self._audit(connection, tenant, subject, "workflow.create", identity, "queued")
                result = self._load_workflow(connection, tenant, subject, identity)
            return result
        except _IdempotencyRace:
            with self._connection() as connection:
                row = connection.execute(select(workflow_state).where(workflow_state.c.tenant == tenant,
                    workflow_state.c.subject == subject, workflow_state.c.idempotency_key == idempotency_key)).first()
                if row is None:
                    raise Work4ceError("workflow_conflict", 409) from None
                existing = self._workflow_data(row)
            if existing["request_hash"] != request_hash:
                raise Work4ceError("idempotency_conflict", 409) from None
            return existing

    def _cas_workflow(self, connection: Connection, row: dict[str, Any], *,
                      require_worker: str | None = None, allow_expired_deadline: bool = False, **values) -> None:
        values["revision"] = row["revision"] + 1
        conditions = [self._workflow_scope(row["tenant"], row["subject"], row["id"]),
                      workflow_state.c.revision == row["revision"]]
        if require_worker is not None:
            instant = time.time()
            conditions.extend([workflow_state.c.lease_owner == require_worker,
                               workflow_state.c.lease_until > instant])
            if not allow_expired_deadline:
                conditions.append(workflow_state.c.deadline > instant)
        changed = connection.execute(update(workflow_state).where(*conditions).values(**values))
        if changed.rowcount != 1:
            code = "workflow_lease_lost" if require_worker is not None else "workflow_busy"
            raise Work4ceError(code, 409)

    @staticmethod
    def _require_live_lease(row: dict[str, Any], worker: str, *, allow_expired_deadline: bool = False) -> None:
        instant = time.time()
        if row["state"] in TERMINAL_STATES:
            raise Work4ceError("workflow_terminal", 409)
        if row["lease_owner"] != worker or row["lease_until"] is None or row["lease_until"] <= instant:
            raise Work4ceError("workflow_lease_lost", 409)
        if not allow_expired_deadline and row["deadline"] <= instant:
            raise Work4ceError("workflow_deadline_exceeded", 409)

    def _write_workflow_report(self, connection: Connection, row: dict[str, Any], report: dict[str, Any], status: str) -> None:
        changed = connection.execute(update(investigations).where(investigations.c.id == row["id"],
            investigations.c.tenant == row["tenant"], investigations.c.subject == row["subject"]).values(
                status=status, report=canonical(report), report_hash=digest(report), updated_at=now()))
        if changed.rowcount != 1:
            raise Work4ceError("investigation_not_found", 404)
        self._audit(connection, row["tenant"], row["subject"], "workflow.finish", row["id"], status)

    def claim_workflow(self, tenant: str, subject: str, identity: str, worker: str,
                       *, lease_seconds: float = 30) -> dict[str, Any]:
        if (not isinstance(worker, str) or not 1 <= len(worker) <= 128
                or type(lease_seconds) not in (int, float) or not math.isfinite(lease_seconds)
                or not 0 < lease_seconds <= 30):
            raise Work4ceError("invalid_workflow_lease", 422)
        expired = False
        with self._connection(write=True) as connection:
            row = self._load_workflow(connection, tenant, subject, identity, lock=True)
            instant = time.time()
            if row["state"] in TERMINAL_STATES:
                raise Work4ceError("workflow_terminal", 409)
            if row["deadline"] <= instant:
                self._cas_workflow(connection, row, state="failed", lease_owner=None, lease_until=None)
                report = {"id": identity, "synthetic": True, "error": "workflow_deadline_exceeded", "evidence": [], "findings": []}
                self._write_workflow_report(connection, row, report, "failed")
                expired = True
            elif row["lease_until"] is not None and row["lease_until"] > instant:
                raise Work4ceError("workflow_busy", 409)
            else:
                state = "collected" if row["state"] == "collected" else "running"
                self._cas_workflow(connection, row, state=state, lease_owner=worker, lease_until=instant + lease_seconds)
                self._audit(connection, tenant, subject, "workflow.claim", identity, state)
            result = self._load_workflow(connection, tenant, subject, identity)
        if expired:
            raise Work4ceError("workflow_deadline_exceeded", 409)
        return result

    def reserve_tool_call(self, tenant: str, subject: str, identity: str, worker: str) -> dict[str, Any]:
        with self._connection(write=True) as connection:
            row = self._load_workflow(connection, tenant, subject, identity, lock=True)
            self._require_live_lease(row, worker)
            if row["state"] not in {"queued", "running"}:
                raise Work4ceError("workflow_checkpoint_exists", 409)
            if row["tool_calls"] >= row["max_tool_calls"]:
                raise Work4ceError("workflow_budget_exhausted", 409)
            self._cas_workflow(connection, row, require_worker=worker, state="running", tool_calls=row["tool_calls"] + 1)
            self._audit(connection, tenant, subject, "workflow.tool.reserve", identity, "reserved")
            return self._load_workflow(connection, tenant, subject, identity)

    def checkpoint_workflow(self, tenant: str, subject: str, identity: str, worker: str, checkpoint: dict[str, Any]) -> None:
        try:
            if not isinstance(checkpoint, dict) or len(canonical(checkpoint).encode()) > 262144:
                raise ValueError("invalid checkpoint")
            raw, checksum = canonical(checkpoint), digest(checkpoint)
        except (ValueError, TypeError, RecursionError):
            raise Work4ceError("invalid_workflow_checkpoint", 422) from None
        with self._connection(write=True) as connection:
            row = self._load_workflow(connection, tenant, subject, identity, lock=True)
            self._require_live_lease(row, worker)
            if row["state"] != "running" or row["tool_calls"] < 1:
                raise Work4ceError("invalid_workflow_transition", 409)
            self._cas_workflow(connection, row, require_worker=worker, state="collected", checkpoint=raw, checkpoint_hash=checksum)
            self._audit(connection, tenant, subject, "workflow.checkpoint", identity, "collected")

    def finish_workflow(self, tenant: str, subject: str, identity: str, worker: str,
                        report: dict[str, Any], status: str) -> None:
        if status not in {"completed", "failed"}:
            raise Work4ceError("invalid_workflow_transition", 409)
        with self._connection(write=True) as connection:
            row = self._load_workflow(connection, tenant, subject, identity, lock=True)
            self._require_live_lease(row, worker, allow_expired_deadline=(status == "failed"))
            if status == "completed" and row["state"] != "collected":
                raise Work4ceError("workflow_checkpoint_required", 409)
            self._cas_workflow(connection, row, require_worker=worker, allow_expired_deadline=(status == "failed"),
                               state=status, lease_owner=None, lease_until=None)
            self._write_workflow_report(connection, row, report, status)

    def cancel_workflow(self, tenant: str, subject: str, identity: str) -> dict[str, Any]:
        with self._connection(write=True) as connection:
            row = self._load_workflow(connection, tenant, subject, identity, lock=True)
            if row["state"] in TERMINAL_STATES:
                return row
            self._cas_workflow(connection, row, state="cancelled", lease_owner=None, lease_until=None)
            report = {"id": identity, "synthetic": True, "error": "workflow_cancelled", "evidence": [], "findings": []}
            self._write_workflow_report(connection, row, report, "cancelled")
            return self._load_workflow(connection, tenant, subject, identity)

    def release_workflow(self, tenant: str, subject: str, identity: str, worker: str) -> None:
        with self._connection(write=True) as connection:
            row = self._load_workflow(connection, tenant, subject, identity, lock=True)
            if row["state"] in TERMINAL_STATES or row["lease_owner"] != worker:
                return
            self._cas_workflow(connection, row, lease_owner=None, lease_until=None)
            self._audit(connection, tenant, subject, "workflow.release", identity, row["state"])

    def close(self) -> None:
        with self._lock:
            self.engine.dispose()
