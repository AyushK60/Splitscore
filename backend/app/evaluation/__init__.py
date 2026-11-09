"""Synthetic evaluation of the audit engine.

This package answers one question on deterministic fixtures: do the implemented
checks detect independently specified conditions, report accurate evidence and
counts, and keep "did not run" separate from "ran and found nothing"?

* :mod:`app.evaluation.oracles` - independent ground-truth computations written
  from each rule's *documented definition*. They import no rule, no engine and
  no shared counting helper, so agreeing with a detector is real evidence and a
  disagreement localises a bug in exactly one of the two.
* :mod:`app.evaluation.cases` - the evaluation suite: small hand-built fixtures
  with hand-written expectations, plus cases over the six committed demo
  datasets whose complete expected outcomes the oracles establish.
* :mod:`app.evaluation.runner` - executes the suite through the public audit
  interface (:func:`app.audit.service.audit_existing_split` and the split
  strategies), compares expected vs actual, verifies that cited evidence rows
  resolve to real fixture records, and reports PASS/FAIL/NOT_EVALUATED per
  case/check.

The command-line entry point is ``scripts/evaluate_synthetic.py``.

This is an engineering evaluation on synthetic fixtures. It is not, and cannot
be, evidence of real-world detection accuracy.
"""

from app.evaluation.cases import CaseResult, build_cases
from app.evaluation.runner import run_suite

__all__ = ["CaseResult", "build_cases", "run_suite"]
