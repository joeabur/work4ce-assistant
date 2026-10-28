# Development database and migrations

The synchronous SQLAlchemy store supports a SQLite path, supported SQLite URL, or `postgresql://` / `postgresql+psycopg://` URL supplied as `WORK4CE_DB`. SQLite is the default. PostgreSQL 17.11 was exercised through a real isolated container. This is integration evidence, not production deployment validation.

## SQLite

The default `.local/work4ce.db` is created and migrated automatically when opened. Existing databases from the original demo are adopted only when they exactly match its known three-table schema; reports, audit records and connector disablement are preserved. Unknown schemas fail closed.

Before upgrading a database with data you need, stop application writers and make a verified SQLite backup with the SQLite backup API or supported SQLite tooling. Protect the backup and verify it can be opened independently. Do not delete or recreate an existing database to bypass a migration error. Backup/restore drills and migration rollback are not established.

## PostgreSQL

The included Compose service is a development database only. Set a unique `WORK4CE_POSTGRES_PASSWORD` securely, then start it:

```sh
docker compose up -d postgres
```

The service binds to `127.0.0.1:55432`, creates user `work4ce` and database `work4ce_db`, and retains data in its named volume. The PostgreSQL image is pinned by digest in `docker-compose.yml`. Password rotation for an existing volume requires PostgreSQL administration; changing the startup environment alone does not rotate the stored password.

Supply a correctly URL-encoded connection URL through secure `WORK4CE_DB` configuration. Do not print it or commit it. Run the explicit migration before API startup:

```sh
python -m work4ce_assistant database migrate
python -m work4ce_assistant serve
```

The bundled Alembic head is `0002_workflows`. PostgreSQL startup requires the expected schema revision and does not silently initialize an unversioned production database. Database configuration, connection and migration errors are redacted. Engine pools are bounded to four connections. The development service does not establish TLS, least-privilege runtime/migration separation, row-level tenant isolation, encrypted storage or recovery readiness.

## Isolated integration suite

With the development environment activated and Docker available:

```sh
python scripts/test_postgres.py
```

This runner generates an ephemeral database credential, starts its own uniquely named digest-pinned container, runs the full suite against it, and removes only its own container and temporary data on exit. It does not reuse or delete the Compose volume. Tests should never target a database containing useful data.

Persistent reports after API restart are tested. Owner-scoped manual resume now reuses validated checkpoints after lease release/expiry. Automatic scheduling, general multi-step recovery and backup/restore drills remain incomplete. Synchronous store methods can block the API event loop; worker isolation or an asynchronous persistence design is required before scaling.
