from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import inspect

from andromeda_core.infrastructure.config import Settings
from andromeda_core.infrastructure.db.session import create_engine


@pytest.mark.asyncio
async def test_head_migration_removes_core_ingestion_table_but_keeps_source_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite+aiosqlite:///{(tmp_path / 'migration.db').as_posix()}"
    environment = {**os.environ, "PYTHONPATH": "src;.", "DATABASE_URL": database_url}
    result = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    engine = create_engine(Settings(database_url=database_url))
    async with engine.begin() as connection:
        tables = await connection.run_sync(lambda sync_connection: set(inspect(sync_connection).get_table_names()))
    await engine.dispose()

    assert "ingestion_pipeline_runs" not in tables
    assert {"sources", "source_documents", "observations"}.issubset(tables)
