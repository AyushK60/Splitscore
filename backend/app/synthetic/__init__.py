"""Seeded synthetic demonstration datasets and their manifest."""

from app.synthetic.generators import DEMO_ORDER, DEMOS, DemoSpec, build_demo
from app.synthetic.manifest import (
    demo_payload,
    get_demo,
    list_demos,
    load_manifest,
    recommended_audit_config,
    recommended_roles,
)

__all__ = [
    "DEMOS",
    "DEMO_ORDER",
    "DemoSpec",
    "build_demo",
    "demo_payload",
    "get_demo",
    "list_demos",
    "load_manifest",
    "recommended_audit_config",
    "recommended_roles",
]
