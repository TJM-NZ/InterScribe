"""Alembic migration chain: runs upgrade head against a dedicated DB and checks ORM coverage."""
import os
import subprocess

import pytest
from sqlalchemy import create_engine, inspect, text

_MIGRATION_DB_URL = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/interscribe_migration_test"
_ADMIN_URL = os.environ["DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"


@pytest.fixture(scope="module")
def migration_engine():
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS interscribe_migration_test"))
        conn.execute(text("CREATE DATABASE interscribe_migration_test"))
    admin.dispose()

    engine = create_engine(_MIGRATION_DB_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": _MIGRATION_DB_URL},
        cwd="/app",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"alembic upgrade head failed:\n{result.stderr}")

    yield engine
    engine.dispose()

    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS interscribe_migration_test"))
    admin.dispose()


def test_alembic_upgrade_head_succeeds(migration_engine):
    """alembic_version table exists, confirming upgrade ran to completion."""
    tables = inspect(migration_engine).get_table_names()
    assert "alembic_version" in tables


def test_migrations_cover_all_orm_tables(migration_engine):
    """Every ORM-declared table exists in the migrated database."""
    import app.models.video   # noqa: F401
    import app.models.phase1  # noqa: F401
    import app.models.phase2  # noqa: F401
    from app.database import Base

    migrated = set(inspect(migration_engine).get_table_names())
    orm_tables = set(Base.metadata.tables.keys())
    missing = orm_tables - migrated
    assert not missing, f"ORM tables missing from migrations: {missing}"
