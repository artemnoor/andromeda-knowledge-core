from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest_asyncio
from scripts.seed_demo import seed_demo

from andromeda_core.infrastructure.config import Settings
from andromeda_core.infrastructure.db.models import Base
from andromeda_core.infrastructure.db.session import create_engine
from andromeda_core.main import create_app


@pytest_asyncio.fixture
async def seeded_app(tmp_path: Path):
    database_path = tmp_path / "test.db"
    database_url = f"sqlite+aiosqlite:///{database_path.as_posix()}"
    engine = create_engine(Settings(database_url=database_url))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()
    seed = await seed_demo(database_url)
    app = create_app(Settings(database_url=database_url, app_env="test"))
    yield app, seed
    await app.state.engine.dispose()


@pytest_asyncio.fixture
async def client(seeded_app) -> AsyncIterator[httpx.AsyncClient]:
    app, _ = seeded_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client
