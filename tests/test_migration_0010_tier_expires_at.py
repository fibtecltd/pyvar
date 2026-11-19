"""tests/test_migration_0010_tier_expires_at.py — migration 0010 adds one nullable column and removes it again.

Reasoning:
- CLAUDE.md 3.3: every schema change is an Alembic migration, and a committed one is never edited. This one is
  purely additive (users.tier_expires_at, nullable, no default, no backfill), so what has to be true is that it
  follows 0009 as the single head, that its upgrade is exactly one ADD COLUMN, that its downgrade undoes exactly
  that, and that the ORM model agrees with the column.
- Alembic's offline mode renders the SQL without a connection, so no database is used (CLAUDE.md 5, rule 3);
  the migration was also run up and down against a real throwaway PostgreSQL 16 when it was written.
"""

from __future__ import annotations

import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime

from storage.models import User

ROOT = Path(__file__).resolve().parents[1]
REVISION = "0010_user_tier_expires_at"
PREVIOUS = "0009_api_keys"


def _config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


def _sql(direction: str, span: str) -> str:
    config = _config()
    config.output_buffer = io.StringIO()
    getattr(command, direction)(config, span, sql=True)
    return config.output_buffer.getvalue()


def test_it_is_the_single_head_and_follows_0009() -> None:
    scripts = ScriptDirectory.from_config(_config())
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == PREVIOUS
    assert len(REVISION) <= 32  # alembic_version.version_num is VARCHAR(32)


def test_upgrade_adds_one_nullable_timestamptz_column_and_nothing_else() -> None:
    sql = _sql("upgrade", f"{PREVIOUS}:{REVISION}")
    statements = [line for line in sql.splitlines() if line.strip().upper().startswith("ALTER")]
    assert statements == ["ALTER TABLE users ADD COLUMN tier_expires_at TIMESTAMP WITH TIME ZONE;"]
    assert "NOT NULL" not in sql and "DEFAULT" not in sql.upper().replace("DEFAULT_", "")
    assert "UPDATE users" not in sql  # no backfill
    assert "UPDATE alembic_version SET version_num='0010_user_tier_expires_at'" in sql


def test_downgrade_drops_exactly_that_column() -> None:
    sql = _sql("downgrade", f"{REVISION}:{PREVIOUS}")
    statements = [line for line in sql.splitlines() if line.strip().upper().startswith("ALTER")]
    assert statements == ["ALTER TABLE users DROP COLUMN tier_expires_at;"]
    assert "UPDATE alembic_version SET version_num='0009_api_keys'" in sql


def test_the_model_agrees_with_the_column() -> None:
    column = User.__table__.c.tier_expires_at
    assert column.nullable is True
    assert column.default is None and column.server_default is None
    assert isinstance(column.type, DateTime) and column.type.timezone is True
