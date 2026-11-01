"""Runtime limits and defaults.

Every bound that could reject, skip or sample user input lives here so that it
is visible in one place, is echoed into audit settings/reports, and can be
overridden by environment variables without editing code.

These are *explicit* limits: SplitScope never silently truncates input. An
upload that exceeds a limit is rejected with a reason, and an analysis that
cannot fit in a bound is either skipped or sampled with disclosure.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from None


#: Bytes in a mebibyte. Limits are stated in MiB so the API, the UI and the
#: documentation all use the same unit.
MIB = 1024 * 1024


@dataclass(frozen=True)
class UploadLimits:
    """Hard limits applied to a single uploaded CSV.

    Three independent bounds, deliberately not conflated:

    * ``max_bytes`` — the raw upload, checked on the server while reading the
      request body. The browser is never trusted for this.
    * ``max_parsed_bytes`` — the estimated in-memory size of the *parsed* frame.
      A CSV expands substantially when it becomes Python objects (roughly 3-5x
      for text), so a file that passes the byte cap can still be rejected here
      with a message naming the parsed-memory limit instead of exhausting RAM.
    * ``max_rows`` / ``max_columns`` — shape limits, unrelated to file size.
      Raising the byte cap does not raise them.
    """

    max_bytes: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_MAX_UPLOAD_BYTES", 25 * MIB)
    )
    max_rows: int = field(default_factory=lambda: _env_int("SPLITSCOPE_MAX_ROWS", 10_000))
    max_columns: int = field(default_factory=lambda: _env_int("SPLITSCOPE_MAX_COLUMNS", 100))
    #: Admission limit on the parsed DataFrame, not on the uploaded bytes.
    max_parsed_bytes: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_MAX_PARSED_BYTES", 256 * MIB)
    )
    #: A dataset smaller than this cannot support a meaningful train/test audit.
    min_rows: int = field(default_factory=lambda: _env_int("SPLITSCOPE_MIN_ROWS", 20))
    min_columns: int = field(default_factory=lambda: _env_int("SPLITSCOPE_MIN_COLUMNS", 2))

    def as_dict(self) -> dict[str, int]:
        return {
            "max_upload_bytes": self.max_bytes,
            "max_upload_mb": round(self.max_bytes / MIB, 3),
            "max_parsed_bytes": self.max_parsed_bytes,
            "max_rows": self.max_rows,
            "max_columns": self.max_columns,
            "min_rows": self.min_rows,
            "min_columns": self.min_columns,
        }


@dataclass(frozen=True)
class StoreLimits:
    """Bounds for the in-memory dataset/result store.

    ``max_total_bytes`` accounts for the *parsed* size of each dataset, because
    that is what the process actually holds. A single dataset larger than this
    budget is rejected at admission rather than silently evicting everything
    else and still not fitting.
    """

    max_datasets: int = field(default_factory=lambda: _env_int("SPLITSCOPE_MAX_STORED_DATASETS", 8))
    max_runs: int = field(default_factory=lambda: _env_int("SPLITSCOPE_MAX_STORED_RUNS", 16))
    max_total_bytes: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_MAX_STORE_BYTES", 384 * MIB)
    )
    ttl_seconds: int = field(default_factory=lambda: _env_int("SPLITSCOPE_STORE_TTL_SECONDS", 3600))

    def as_dict(self) -> dict[str, int]:
        return {
            "max_datasets": self.max_datasets,
            "max_runs": self.max_runs,
            "max_total_bytes": self.max_total_bytes,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass(frozen=True)
class NearDuplicateLimits:
    """Bounds for the expensive near-duplicate candidate analysis."""

    #: Maximum combined (train + test) rows entering the distance computation.
    max_combined_rows: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_NEAR_DUP_MAX_ROWS", 500)
    )
    #: Maximum number of distance pairs retained as evidence.
    max_reported_pairs: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_NEAR_DUP_MAX_PAIRS", 200)
    )

    def as_dict(self) -> dict[str, int]:
        return {
            "near_duplicate_max_combined_rows": self.max_combined_rows,
            "near_duplicate_max_reported_pairs": self.max_reported_pairs,
        }


@dataclass(frozen=True)
class DiagnosticsLimits:
    """Bounds for supporting (non-finding) distribution diagnostics."""

    #: A target with at most this many distinct values is treated as categorical.
    categorical_max_unique: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_CATEGORICAL_MAX_UNIQUE", 20)
    )
    #: Categories shown before the rest are aggregated into "(other categories)".
    max_categories_shown: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_MAX_CATEGORIES_SHOWN", 12)
    )
    histogram_bins: int = field(default_factory=lambda: _env_int("SPLITSCOPE_HISTOGRAM_BINS", 10))
    #: Columns with the widest missingness gap shown individually.
    max_missingness_columns: int = field(
        default_factory=lambda: _env_int("SPLITSCOPE_MAX_MISSINGNESS_COLUMNS", 15)
    )

    def as_dict(self) -> dict[str, int]:
        return {
            "categorical_max_unique": self.categorical_max_unique,
            "max_categories_shown": self.max_categories_shown,
            "histogram_bins": self.histogram_bins,
            "max_missingness_columns": self.max_missingness_columns,
        }


@dataclass(frozen=True)
class ApiSettings:
    """HTTP-facing settings."""

    #: Development origins allowed by CORS. Narrow on purpose.
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.environ.get(
                "SPLITSCOPE_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,"
                "http://localhost:4173,http://127.0.0.1:4173",
            ).split(",")
            if o.strip()
        )
    )
    host: str = field(default_factory=lambda: os.environ.get("SPLITSCOPE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _env_int("SPLITSCOPE_PORT", 8000))
    preview_rows: int = field(default_factory=lambda: _env_int("SPLITSCOPE_PREVIEW_ROWS", 100))
    log_level: str = field(default_factory=lambda: os.environ.get("SPLITSCOPE_LOG_LEVEL", "INFO"))


@dataclass(frozen=True)
class Settings:
    upload: UploadLimits = field(default_factory=UploadLimits)
    store: StoreLimits = field(default_factory=StoreLimits)
    near_duplicate: NearDuplicateLimits = field(default_factory=NearDuplicateLimits)
    diagnostics: DiagnosticsLimits = field(default_factory=DiagnosticsLimits)
    api: ApiSettings = field(default_factory=ApiSettings)

    def limits_payload(self) -> dict[str, object]:
        """Machine-readable limits for ``GET /api/health`` and the UI."""
        return {
            **self.upload.as_dict(),
            **self.store.as_dict(),
            **self.near_duplicate.as_dict(),
            **self.diagnostics.as_dict(),
        }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Test helper: force re-reading of environment variables."""
    global _settings
    _settings = None
