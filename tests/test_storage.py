"""Persistence contract runs on SQLite and an explicitly provided disposable PG DB."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.engine import make_url

from work4ce_assistant.contracts import Work4ceError, canonical, digest
from work4ce_assistant.storage import Store, audit_table, investigations, migrate


class StoreContract:
    def test_tenant_report_and_integrity(self):
        identity = self.store.begin('tenant-a', 'analyst')
        report = {'evidence': [{'id': 'demo-evidence'}], 'synthetic': True}
        self.store.finish('tenant-a', 'analyst', identity, report, 'completed')
        self.assertEqual(self.store.get('tenant-a', identity)['report'], report)
        with self.assertRaisesRegex(Work4ceError, 'investigation_not_found'):
            self.store.get('tenant-b', identity)
        with self.assertRaisesRegex(Work4ceError, 'investigation_not_found'):
            self.store.finish('tenant-b', 'other', identity, {}, 'completed')
        self.assertEqual(self.store.audit_rows('tenant-b'), [])
        with self.store.engine.begin() as connection:
            connection.execute(update(investigations).where(investigations.c.id == identity).values(report='{}'))
        with self.assertRaisesRegex(Work4ceError, 'report_integrity_failure'):
            self.store.get('tenant-a', identity)

    def test_atomic_report_and_audit(self):
        identity = self.store.begin('tenant-a', 'analyst')
        with patch.object(self.store, '_audit', side_effect=RuntimeError('controlled failure')):
            with self.assertRaises(RuntimeError):
                self.store.finish('tenant-a', 'analyst', identity, {'evidence': []}, 'completed')
        self.assertEqual(self.store.get('tenant-a', identity), {'id': identity, 'status': 'running', 'report': None})
        self.assertEqual(len(self.store.audit_rows('tenant-a')), 1)
        with patch.object(self.store, '_audit', side_effect=RuntimeError('controlled failure')):
            with self.assertRaises(RuntimeError):
                self.store.begin('tenant-b', 'analyst')
        with self.store.engine.connect() as connection:
            self.assertEqual(connection.execute(select(investigations.c.id).where(investigations.c.tenant == 'tenant-b')).all(), [])

    def test_idempotent_connector_bootstrap_and_tenant_revocation(self):
        self.store.initialize_connector('tenant-a', 'demo-rest')
        self.store.initialize_connector('tenant-b', 'demo-rest')
        self.store.disable('tenant-a', 'admin', 'demo-rest')
        self.store.initialize_connector('tenant-a', 'demo-rest')
        self.assertFalse(self.store.enabled('tenant-a', 'demo-rest'))
        self.assertTrue(self.store.enabled('tenant-b', 'demo-rest'))
        self.assertFalse(self.store.enabled('tenant-c', 'demo-rest'))
        self.assertEqual(self.store.audit_rows('tenant-a'), [('connector.disable', 'demo-rest', 'disabled')])
        self.assertEqual(self.store.audit_rows('tenant-b'), [])

    def test_sql_parameters_preserve_literal_tenant_and_subject(self):
        tenant = "tenant'; DROP TABLE investigations;--"
        identity = self.store.begin(tenant, "analyst' OR '1'='1")
        self.store.finish(tenant, 'analyst', identity, {'ok': True}, 'completed')
        self.assertEqual(self.store.get(tenant, identity)['report'], {'ok': True})
        with self.assertRaises(Work4ceError):
            self.store.get('tenant-a', identity)
        self.assertEqual(len(self.store.audit_rows(tenant)), 2)


class SQLiteStoreTests(StoreContract, unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp.name) / 'work4ce.db')
        self.store = Store(self.database)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_repeatable_migration_and_restart(self):
        self.store.initialize_connector('tenant-a', 'demo-rest')
        self.store.disable('tenant-a', 'admin', 'demo-rest')
        identity = self.store.begin('tenant-a', 'analyst')
        self.store.finish('tenant-a', 'analyst', identity, {'synthetic': True}, 'completed')
        self.store.close()
        migrate(self.database)
        migrate(self.database)
        self.store = Store(self.database)
        self.assertEqual(self.store.get('tenant-a', identity)['report'], {'synthetic': True})
        self.assertFalse(self.store.enabled('tenant-a', 'demo-rest'))


LEGACY_SCHEMA = '''
CREATE TABLE investigations (id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL,
 status TEXT NOT NULL, report TEXT, report_hash TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE audit (sequence INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL, subject TEXT NOT NULL,
 action TEXT NOT NULL, target TEXT NOT NULL, outcome TEXT NOT NULL, timestamp TEXT NOT NULL);
CREATE TABLE connector_state (tenant TEXT NOT NULL, id TEXT NOT NULL, enabled INTEGER NOT NULL, PRIMARY KEY (tenant,id));
'''


class MigrationTests(unittest.TestCase):
    def test_legacy_sqlite_preserves_reports_audit_and_revocations(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / 'legacy.db')
            report = {'synthetic': True, 'evidence': [{'id': 'retained'}]}
            with sqlite3.connect(database) as connection:
                connection.executescript(LEGACY_SCHEMA)
                connection.execute('INSERT INTO investigations VALUES (?,?,?,?,?,?,?,?)',
                    ('retained-id', 'tenant-a', 'analyst', 'completed', canonical(report), digest(report), 'past', 'past'))
                connection.execute('INSERT INTO audit VALUES (?,?,?,?,?,?,?)',
                    (3, 'tenant-a', 'admin', 'connector.disable', 'demo-rest', 'disabled', 'past'))
                connection.execute('INSERT INTO connector_state VALUES (?,?,?)', ('tenant-a', 'demo-rest', 0))
            migrate(database)
            store = Store(database)
            self.addCleanup(store.close)
            self.assertEqual(store.get('tenant-a', 'retained-id')['report'], report)
            self.assertFalse(store.enabled('tenant-a', 'demo-rest'))
            self.assertEqual(store.audit_rows('tenant-a'), [('connector.disable', 'demo-rest', 'disabled')])
            store.audit('tenant-a', 'analyst', 'new.audit', 'test', 'ok')
            with store.engine.connect() as connection:
                sequence = connection.execute(select(audit_table.c.sequence).order_by(audit_table.c.sequence)).scalars().all()
                self.assertEqual(sequence, [3, 4])

    def test_unknown_or_modified_legacy_schema_fails_without_stamp(self):
        for mutation in ('CREATE TABLE unknown (id INTEGER)', 'ALTER TABLE investigations ADD COLUMN unsafe TEXT',
                         'CREATE TRIGGER unsafe AFTER INSERT ON audit BEGIN DELETE FROM audit; END;',
                         'CREATE UNIQUE INDEX unsafe ON investigations(subject)'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                database = str(Path(directory) / 'unknown.db')
                with sqlite3.connect(database) as connection:
                    connection.executescript(LEGACY_SCHEMA + mutation)
                with self.assertRaisesRegex(Work4ceError, 'unknown_database_schema'):
                    migrate(database)
                with sqlite3.connect(database) as connection:
                    self.assertEqual(connection.execute("SELECT name FROM sqlite_master WHERE name='alembic_version'").fetchall(), [])

    def test_unknown_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / 'unknown.db')
            store = Store(database)
            with store.engine.begin() as connection:
                connection.execute(text("UPDATE alembic_version SET version_num='unknown_revision'"))
            store.close()
            with self.assertRaisesRegex(Work4ceError, 'database_schema_unsupported'):
                Store(database)


@unittest.skipUnless(os.environ.get('WORK4CE_TEST_POSTGRES_URL'), 'WORK4CE_TEST_POSTGRES_URL absent; PostgreSQL integration unrun')
class PostgreSQLStoreTests(StoreContract, unittest.TestCase):
    def setUp(self):
        # Only operate in a unique schema created by this test. Never drop user tables.
        raw_url = make_url(os.environ['WORK4CE_TEST_POSTGRES_URL'])
        if raw_url.drivername in ('postgres', 'postgresql'):
            raw_url = raw_url.set(drivername='postgresql+psycopg')
        self.admin = create_engine(raw_url, hide_parameters=True)
        self.schema = 'work4ce_test_' + uuid4().hex
        with self.admin.begin() as connection:
            connection.execute(text('CREATE SCHEMA ' + self.schema))
        url = raw_url.update_query_dict({'options': '-csearch_path=' + self.schema})
        self.database = url.render_as_string(hide_password=False)
        with self.assertRaisesRegex(Work4ceError, 'database_schema_outdated'):
            Store(self.database)
        migrate(self.database)
        self.store = Store(self.database)

    def tearDown(self):
        self.store.close()
        with self.admin.begin() as connection:
            connection.execute(text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        self.admin.dispose()

    def test_repeatable_explicit_migration_and_restart(self):
        identity = self.store.begin('tenant-a', 'analyst')
        self.store.finish('tenant-a', 'analyst', identity, {'synthetic': True}, 'completed')
        self.store.initialize_connector('tenant-a', 'demo-rest')
        self.store.disable('tenant-a', 'admin', 'demo-rest')
        self.store.close()
        migrate(self.database)
        migrate(self.database)
        self.store = Store(self.database)
        self.assertEqual(self.store.get('tenant-a', identity)['report'], {'synthetic': True})
        self.assertFalse(self.store.enabled('tenant-a', 'demo-rest'))
