"""Persistence-neutral identity helpers used by application use cases."""

from __future__ import annotations

from hashlib import sha256
from uuid import uuid4


def new_id() -> str:
    return str(uuid4())


def identity_hash(*parts: object) -> str:
    return sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
