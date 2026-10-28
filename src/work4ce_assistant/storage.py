"""Tenant-scoped SQLite demo persistence, with atomic reports and audit events."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import Work4ceError, canonical, digest


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL,
                status TEXT NOT NULL, report TEXT, report_hash TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
                subject TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL,
                outcome TEXT NOT NULL, timestamp TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS connector_state (
                tenant TEXT NOT NULL, id TEXT NOT NULL, enabled INTEGER NOT NULL,
                PRIMARY KEY (tenant,id));
        ''')

    def audit(self, tenant: str, subject: str, action: str, target: str, outcome: str) -> None:
        with self._lock, self.db:
            self._audit(tenant, subject, action, target, outcome)

    def _audit(self, tenant: str, subject: str, action: str, target: str, outcome: str) -> None:
        self.db.execute("INSERT INTO audit(tenant,subject,action,target,outcome,timestamp) VALUES (?,?,?,?,?,?)",
                        (tenant, subject, action, target, outcome, now()))

    def begin(self, tenant: str, subject: str) -> str:
        identity = str(uuid4())
        with self._lock, self.db:
            self.db.execute("INSERT INTO investigations VALUES (?,?,?,?,?,?,?,?)",
                            (identity, tenant, subject, "running", None, None, now(), now()))
            self._audit(tenant, subject, "investigation.start", identity, "running")
        return identity

    def finish(self, tenant: str, subject: str, identity: str, report: dict[str, Any], status: str) -> None:
        with self._lock, self.db:
            cursor = self.db.execute(
                "UPDATE investigations SET status=?,report=?,report_hash=?,updated_at=? WHERE id=? AND tenant=?",
                (status, canonical(report), digest(report), now(), identity, tenant))
            if cursor.rowcount != 1:
                raise Work4ceError("investigation_not_found", 404)
            self._audit(tenant, subject, "investigation.finish", identity, status)

    def get(self, tenant: str, identity: str) -> dict[str, Any]:
        with self._lock:
            row = self.db.execute(
                "SELECT status,report,report_hash FROM investigations WHERE tenant=? AND id=?",
                (tenant, identity)).fetchone()
        if not row:
            raise Work4ceError("investigation_not_found", 404)
        report = json.loads(row[1]) if row[1] else None
        if report is not None and digest(report) != row[2]:
            raise Work4ceError("report_integrity_failure", 500)
        return {"id": identity, "status": row[0], "report": report}

    def enabled(self, tenant: str, connector_id: str) -> bool:
        with self._lock:
            row = self.db.execute("SELECT enabled FROM connector_state WHERE tenant=? AND id=?",
                                  (tenant, connector_id)).fetchone()
        return bool(row and row[0])

    def initialize_connector(self, tenant: str, connector_id: str) -> None:
        # Called only for built-in connectors explicitly approved by bootstrap.
        with self._lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO connector_state VALUES (?,?,1)", (tenant, connector_id))

    def disable(self, tenant: str, subject: str, connector_id: str) -> None:
        with self._lock, self.db:
            self.db.execute("UPDATE connector_state SET enabled=0 WHERE tenant=? AND id=?", (tenant, connector_id))
            self._audit(tenant, subject, "connector.disable", connector_id, "disabled")

    def audit_rows(self, tenant: str) -> list[tuple]:
        with self._lock:
            return self.db.execute("SELECT action,target,outcome FROM audit WHERE tenant=? ORDER BY sequence", (tenant,)).fetchall()

    def close(self) -> None:
        self.db.close()
