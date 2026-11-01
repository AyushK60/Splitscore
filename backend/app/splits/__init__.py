"""Split generation and comparison."""

from app.splits.comparison import compare_splits
from app.splits.strategies import (
    existing_split,
    generate_split,
    random_holdout,
    stratified_holdout,
)

__all__ = [
    "compare_splits",
    "existing_split",
    "generate_split",
    "random_holdout",
    "stratified_holdout",
]
