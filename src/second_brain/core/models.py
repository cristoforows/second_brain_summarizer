from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Message:
    """A single parsed message from the dump file."""

    id: str
    content: str


@dataclass(frozen=True)
class Category:
    """A category definition (from seed config or AI-created)."""

    name: str
    description: str
