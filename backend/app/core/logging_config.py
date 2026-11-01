"""Standard-library logging setup.

Deliberately small: SplitScope is a local single-user tool, so ``logging`` with
a concise formatter is sufficient.

Privacy rule enforced by convention at every call site: log records never
contain dataframe contents or CSV cell values. Only shapes, identifiers,
fingerprints, durations and error codes are logged.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, writing to stderr."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
