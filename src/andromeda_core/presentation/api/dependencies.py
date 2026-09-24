"""FastAPI dependencies for settings, sessions and the local role seam."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Coroutine
from enum import StrEnum
from typing import Any, cast

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from andromeda_core.domain.errors import ForbiddenError
from andromeda_core.infrastructure.config import Settings


class Role(StrEnum):
    READER = "READER"
    EDITOR = "EDITOR"
    REVIEWER = "REVIEWER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


ROLE_ORDER = {Role.READER: 10, Role.EDITOR: 20, Role.REVIEWER: 30, Role.ADMIN: 40, Role.SYSTEM: 50}


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


async def get_current_role(
    x_role: str | None = Header(default=None, alias="X-Role"),
) -> Role:
    if not x_role:
        # The local API has no identity provider yet. Reads default to READER;
        # mutating/admin endpoints still require an explicit elevated role.
        # Replace this seam with the host application's authenticated principal
        # resolver when the core is embedded behind Andromeda auth.
        return Role.READER
    try:
        return Role((x_role or "").upper())
    except ValueError as exc:
        raise ForbiddenError("A valid X-Role is required for this environment.") from exc


def require_role(minimum: Role) -> Callable[..., Coroutine[Any, Any, Role]]:
    async def dependency(role: Role = Depends(get_current_role)) -> Role:
        if ROLE_ORDER[role] < ROLE_ORDER[minimum]:
            raise ForbiddenError(f"Role {minimum.value} or higher is required.")
        return role

    return dependency
