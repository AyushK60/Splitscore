"""Version identifiers used across artifacts, reports and the API."""

from __future__ import annotations

APP_NAME = "SplitScope"
APP_VERSION = "1.0.0"

#: Version of the serialized audit/report contract. Bump when the shape of
#: findings, results or reports changes in a backwards-incompatible way.
AUDIT_SCHEMA_VERSION = "1.0.0"

#: Version of the demo/dataset manifest contract in ``datasets/``.
MANIFEST_SCHEMA_VERSION = "1.0.0"
