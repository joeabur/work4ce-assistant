"""Tenant-scoped SQLAlchemy persistence with versioned, explicit migrations.

SQLite demo databases bootstrap on open. PostgreSQL requires migrate() first.
Methods are synchronous; deployments need worker isolation before scaling.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Column, Integer, MetaData, Table, Text, create_engine, event, inspect, select, text, update
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool

from .contracts import Work4ceError, canonical, digest

HEAD = "0001_foundation"
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
        command.stamp(_config(connection), HEAD)
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

    def close(self) -> None:
        with self._lock:
            self.engine.dispose()
