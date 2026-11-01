"""Bounded, expiring in-memory store.

SplitScope is a local single-user tool, so datasets live in process memory rather
than in a database. That choice has consequences which are stated here and in the
API payload, because a user who assumed persistence would be misled:

* **Restart behaviour.** Everything is lost when the process exits. Nothing is
  written to disk except reports the user explicitly downloads.
* **Expiry.** Entries untouched for longer than ``ttl_seconds`` are dropped, and
  every operation prunes expired entries first.
* **Eviction.** When a bound is reached, the least-recently-used entry of that kind
  is evicted, and the eviction is logged.
* **Distinguishable errors.** A lookup that misses raises
  :class:`~app.core.errors.ExpiredError` (HTTP 410), never a generic "not found":
  "your dataset expired" and "that id never existed" call for different actions.

All ages are measured with :func:`time.monotonic`, so a wall-clock change cannot
make entries look arbitrarily old or young.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from app.audit.dataset import Dataset
from app.audit.types import SplitAssignment
from app.core.config import StoreLimits
from app.core.errors import ExpiredError, LimitExceededError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

RunKind = Literal["audit", "comparison"]

ASSIGNMENT_LIMIT_MULTIPLIER = 8


@dataclass
class StoredRun:
    run_id: str
    kind: RunKind
    dataset_id: str
    payload: dict[str, Any]
    created_at: float
    last_access: float
    label: str = ""


@dataclass
class StoreStats:
    datasets: int
    runs: int
    assignments: int
    total_bytes: int
    limits: dict[str, int]
    evictions: int
    expirations: int
    dataset_ids: list[str] = field(default_factory=list)


class _Entry:
    __slots__ = ("last_access", "value")

    def __init__(self, value: Any) -> None:
        self.value = value
        self.last_access = time.monotonic()

    def touch(self) -> None:
        self.last_access = time.monotonic()


class Store:
    """Thread-safe, bounded, expiring in-memory store."""

    def __init__(self, limits: StoreLimits) -> None:
        self._limits = limits
        self._datasets: dict[str, _Entry] = {}
        self._dataset_bytes: dict[str, int] = {}
        self._runs: dict[str, _Entry] = {}
        self._assignments: dict[str, _Entry] = {}
        self._lock = threading.RLock()
        self._evictions = 0
        self._expirations = 0

    # -- maintenance ------------------------------------------------------- #

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._limits.ttl_seconds
        for entries in (self._datasets, self._runs, self._assignments):
            stale = [key for key, entry in entries.items() if entry.last_access < cutoff]
            for key in stale:
                del entries[key]
                self._dataset_bytes.pop(key, None)
                self._expirations += 1

    def _enforce(self, entries: dict[str, _Entry], limit: int) -> None:
        while len(entries) > limit:
            oldest = min(entries, key=lambda key: entries[key].last_access)
            del entries[oldest]
            self._dataset_bytes.pop(oldest, None)
            self._evictions += 1
            logger.info("Store evicted least-recently-used entry %s", oldest)

    def _prune_orphaned_runs(self) -> None:
        live = set(self._datasets)
        for key in [k for k, entry in self._runs.items() if entry.value.dataset_id not in live]:
            del self._runs[key]

    # -- datasets ---------------------------------------------------------- #

    def put_dataset(self, dataset: Dataset, *, size_bytes: int | None = None) -> Dataset:
        """Store a dataset, accounting for its parsed in-memory size.

        ``size_bytes`` is the estimated memory the parsed frame occupies; it
        defaults to the raw file size for the committed demos, which are tiny.
        A dataset whose own footprint exceeds the whole store budget can never
        fit, so it is rejected with a typed error instead of evicting every
        other entry and being admitted anyway.
        """
        with self._lock:
            self._prune()
            if dataset.dataset_id in ("", "pending"):
                dataset.dataset_id = f"ds-{uuid.uuid4().hex[:12]}"
            footprint = size_bytes if size_bytes is not None else dataset.size_bytes
            if footprint > self._limits.max_total_bytes:
                raise LimitExceededError(
                    "The parsed dataset needs "
                    f"{footprint / (1024 * 1024):.1f} MB in memory, above the "
                    f"{self._limits.max_total_bytes / (1024 * 1024):.0f} MB store budget for this "
                    "server, so it was not admitted.",
                    details={
                        "parsed_bytes": footprint,
                        "store_budget_bytes": self._limits.max_total_bytes,
                        "hint": "Split the file into smaller pieces, or raise "
                        "SPLITSCOPE_MAX_STORE_BYTES and SPLITSCOPE_MAX_PARSED_BYTES when starting "
                        "the server.",
                    },
                )
            self._datasets[dataset.dataset_id] = _Entry(dataset)
            self._dataset_bytes[dataset.dataset_id] = footprint
            self._enforce(self._datasets, self._limits.max_datasets)
            while len(self._datasets) > 1 and self._total_bytes() > self._limits.max_total_bytes:
                oldest = min(self._datasets, key=lambda key: self._datasets[key].last_access)
                del self._datasets[oldest]
                self._dataset_bytes.pop(oldest, None)
                self._evictions += 1
            self._prune_orphaned_runs()
            return dataset

    def get_dataset(self, dataset_id: str) -> Dataset:
        with self._lock:
            self._prune()
            entry = self._datasets.get(dataset_id)
            if entry is None:
                raise ExpiredError(
                    "That dataset is no longer in memory. It may have expired, been evicted, or the "
                    "server may have restarted since the upload.",
                    details={
                        "dataset_id": dataset_id,
                        "known_dataset_ids": sorted(self._datasets)[:20],
                        "ttl_seconds": self._limits.ttl_seconds,
                        "fix": "Re-upload the file or reload the demo, then run the audit again.",
                    },
                )
            entry.touch()
            return entry.value

    # -- runs -------------------------------------------------------------- #

    def put_run(
        self, *, kind: RunKind, dataset_id: str, payload: dict[str, Any], label: str = ""
    ) -> str:
        with self._lock:
            self._prune()
            run_id = f"run-{uuid.uuid4().hex[:12]}"
            now = time.monotonic()
            self._runs[run_id] = _Entry(
                StoredRun(
                    run_id=run_id,
                    kind=kind,
                    dataset_id=dataset_id,
                    payload=payload,
                    created_at=now,
                    last_access=now,
                    label=label,
                )
            )
            self._enforce(self._runs, self._limits.max_runs)
            return run_id

    def get_run(self, run_id: str) -> StoredRun:
        with self._lock:
            self._prune()
            entry = self._runs.get(run_id)
            if entry is None:
                raise ExpiredError(
                    "That audit run is no longer in memory, so its report cannot be regenerated. "
                    "Re-run the audit to produce a new report.",
                    details={
                        "run_id": run_id,
                        "known_run_ids": sorted(self._runs)[:20],
                        "ttl_seconds": self._limits.ttl_seconds,
                    },
                )
            run: StoredRun = entry.value
            if run.dataset_id not in self._datasets:
                raise ExpiredError(
                    "The dataset behind that audit run is no longer in memory, so the stored results "
                    "cannot be exported together with their input identity.",
                    details={"run_id": run_id, "dataset_id": run.dataset_id},
                )
            entry.touch()
            return run

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune()
            now = time.monotonic()
            return [
                {
                    "run_id": entry.value.run_id,
                    "kind": entry.value.kind,
                    "dataset_id": entry.value.dataset_id,
                    "label": entry.value.label,
                    "created_seconds_ago": round(now - entry.value.created_at, 1),
                }
                for entry in sorted(
                    self._runs.values(), key=lambda item: -item.value.created_at
                )
            ]

    # -- assignments ------------------------------------------------------- #

    def put_assignment(self, assignment: SplitAssignment) -> str:
        with self._lock:
            self._prune()
            self._assignments[assignment.assignment_id] = _Entry(assignment)
            self._enforce(
                self._assignments, self._limits.max_runs * ASSIGNMENT_LIMIT_MULTIPLIER
            )
            return assignment.assignment_id

    def get_assignment(self, assignment_id: str) -> SplitAssignment:
        with self._lock:
            self._prune()
            entry = self._assignments.get(assignment_id)
            if entry is None:
                raise ExpiredError(
                    "That split assignment is no longer in memory, so its CSV cannot be downloaded. "
                    "Re-run the split comparison to regenerate it.",
                    details={"assignment_id": assignment_id},
                )
            entry.touch()
            return entry.value

    # -- introspection ----------------------------------------------------- #

    def _total_bytes(self) -> int:
        return sum(self._dataset_bytes.values())

    def stats(self) -> StoreStats:
        with self._lock:
            self._prune()
            return StoreStats(
                datasets=len(self._datasets),
                runs=len(self._runs),
                assignments=len(self._assignments),
                total_bytes=self._total_bytes(),
                limits=self._limits.as_dict(),
                evictions=self._evictions,
                expirations=self._expirations,
                dataset_ids=sorted(self._datasets),
            )

    def clear(self) -> None:
        with self._lock:
            self._datasets.clear()
            self._dataset_bytes.clear()
            self._runs.clear()
            self._assignments.clear()


__all__ = ["RunKind", "Store", "StoreStats", "StoredRun"]
