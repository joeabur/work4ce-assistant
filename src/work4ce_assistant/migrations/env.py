"""Programmatic migrations use an already authenticated SQLAlchemy connection."""
from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use work4ce_assistant.storage.migrate; database URLs are not stored in Alembic config")
context.configure(connection=connection, target_metadata=None)
with context.begin_transaction():
    context.run_migrations()
