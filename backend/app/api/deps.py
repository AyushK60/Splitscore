"""Application context and FastAPI dependencies.

A single process-wide context holds the settings and the in-memory store. Tests
replace it with :func:`reset_context`, which is the only supported way to get a
clean store.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.store import Store
from app.causal.registry import CausalGraphRegistry
from app.research.studies import StudyRegistry


@dataclass
class AppContext:
    settings: Settings
    store: Store
    studies: StudyRegistry
    causal_graphs: CausalGraphRegistry

    @classmethod
    def create(cls, settings: Settings | None = None) -> AppContext:
        resolved = settings or get_settings()
        return cls(
            settings=resolved,
            store=Store(resolved.store),
            studies=StudyRegistry(),
            causal_graphs=CausalGraphRegistry(),
        )


_context: AppContext | None = None


def get_context() -> AppContext:
    global _context
    if _context is None:
        _context = AppContext.create()
    return _context


def reset_context(settings: Settings | None = None) -> AppContext:
    """Replace the global context. Used by the app factory and by tests."""
    global _context
    _context = AppContext.create(settings)
    return _context


__all__ = ["AppContext", "get_context", "reset_context"]
