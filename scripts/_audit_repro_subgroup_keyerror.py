"""S9C independent audit reproduction: subgroup node outside the adjustment set.

Hypothesis: run_subgroup_estimation parses the subgroup column from
prepared.frame, which only carries adjustment covariate columns. When the
subgroup variable is a baseline variable outside the (valid) adjustment set,
this should raise a raw KeyError instead of a structured ValidationFailure.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from app.audit.dataset import Dataset  # noqa: E402
from app.causal.estimation.contracts import EstimationRequest  # noqa: E402
from app.causal.estimation.subgroups import SubgroupSpec, run_subgroup_estimation  # noqa: E402
from app.causal.registry import CausalGraphRecord  # noqa: E402
from app.causal.schema import CausalGraphSpec  # noqa: E402
from tests.conftest import make_dataset  # noqa: E402

rng = np.random.default_rng(4021)
n = 600
g = rng.choice(["A", "B"], size=n)
x1 = rng.normal(0.0, 1.0, n)
x2 = rng.normal(0.0, 1.0, n)
propensity = 1.0 / (1.0 + np.exp(-(-0.4 + 0.8 * x1 - 0.5 * x2)))
t = rng.binomial(1, propensity)
y = 1.0 * t + 0.9 * x1 - 0.7 * x2 + rng.normal(0.0, 1.0, n)
frame = pd.DataFrame({"x1": x1, "x2": x2, "g": g, "t": t, "y": y})

dataset = make_dataset(frame.to_dict("records"), name="audit-repro.csv")

# g causes the outcome only (no g->t edge), so {x1, x2} is a *valid* backdoor
# set and the subgroup variable g is a baseline variable outside it.
spec = CausalGraphSpec(
    name="Audit repro graph",
    dataset_id=dataset.dataset_id,
    nodes=[
        {"node_id": "x1", "label": "x1", "column": "x1"},
        {"node_id": "x2", "label": "x2", "column": "x2"},
        {"node_id": "g", "label": "g", "column": "g"},
        {"node_id": "t", "label": "t", "column": "t"},
        {"node_id": "y", "label": "y", "column": "y"},
    ],
    edges=[
        {"source": "x1", "target": "t"},
        {"source": "x1", "target": "y"},
        {"source": "x2", "target": "t"},
        {"source": "x2", "target": "y"},
        {"source": "g", "target": "y"},
        {"source": "t", "target": "y"},
    ],
    analysis={"treatment": "t", "outcome": "y"},
)
record = CausalGraphRecord(
    graph_id="cgraph-audit-repro",
    dataset_id=dataset.dataset_id,
    dataset_fingerprint_sha256=dataset.fingerprint_sha256,
    spec=spec,
    revision=1,
)
request = EstimationRequest(
    treatment_node="t",
    outcome_node="y",
    adjustment_nodes=["x1", "x2"],
    treatment_mapping={"treated": "1", "control": "0"},
    cross_fit={"splits": 5},
    uncertainty={"method": "influence_function", "reps": 100, "seed": 4021, "level": 0.95},
    expected_spec_fingerprint_sha256=None,
)

try:
    payload = run_subgroup_estimation(dataset, record, request, SubgroupSpec("g"))
    print("NO ERROR — subgroup outside adjustment set produced a payload.")
except Exception as error:  # noqa: BLE001
    print(f"EXCEPTION TYPE: {type(error).__module__}.{type(error).__name__}")
    print(f"MESSAGE: {error}")
