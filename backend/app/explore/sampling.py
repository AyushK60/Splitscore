"""Reproducible render sampling for the Visual Explorer.

Point-level charts (parallel coordinates, scatters) cannot draw every row of a
10 000-row dataset legibly, so the renderer draws a bounded sample. The sample
must be reproducible — the same dataset and the same cap always produce the
same drawn rows, so a caption can honestly say which rows are on screen.

The method is a **systematic grid sample**: rows keep file order, the stride is
``ceil(n / cap)``, and the first row of every stride is drawn. This is
deterministic without a stored seed, stable under re-request, and easy to
describe in one sentence in a figure caption ("every k-th row"). Random
sampling would need a seed round-trip to stay reproducible and would shuffle
rows that other views (row evidence) address by file position.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_RENDER_ROWS = 5000
DEFAULT_RENDER_ROWS = 1200


@dataclass(frozen=True)
class RenderSample:
    """Which rows a point-level chart draws, and how to describe that."""

    indices: list[int]
    population: int
    stride: int
    method: str = "systematic_grid"

    @property
    def description(self) -> str:
        if self.stride <= 1:
            return "All rows are drawn (the dataset fits the render cap)."
        return (
            f"Systematic grid sample: every {self.stride}th row of {self.population:,} "
            f"in file order; {len(self.indices):,} rows drawn."
        )


def render_sample(population: int, cap: int = DEFAULT_RENDER_ROWS) -> RenderSample:
    """Choose the rows a point-level chart draws.

    ``cap`` is clamped to :data:`MAX_RENDER_ROWS`; a population at or below the
    cap draws everything (stride 1). The first row of every stride is included,
    so the sample always covers the dataset from the first to at least the
    ``stride * (len-1)``-th row.
    """
    if population < 0:
        raise ValueError("population must be non-negative")
    cap = max(1, min(int(cap), MAX_RENDER_ROWS))
    stride = max(1, -(-population // cap))  # ceil division
    indices = list(range(0, population, stride))
    return RenderSample(indices=indices, population=population, stride=stride)


__all__ = ["DEFAULT_RENDER_ROWS", "MAX_RENDER_ROWS", "RenderSample", "render_sample"]
