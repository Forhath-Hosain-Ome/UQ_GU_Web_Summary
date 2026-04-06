"""
cell_grid.py
------------
Thin wrapper around a pandas DataFrame providing safe zero-based cell access
and label-search helpers used throughout the extraction pipeline.
"""

import re
from typing import Iterable, List, Tuple

import numpy as np
import pandas as pd


def normalize_text(value: str) -> str:
    """
    Lowercase, strip, collapse whitespace, and remove non-alphanumeric chars.

    Used for fuzzy label matching so that e.g.:
      "Factory Name:" == "factory name" == "FACTORY NAME"
    """
    text = value.lower().strip()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class CellGrid:
    """
    Wraps a raw pandas DataFrame (loaded with header=None, dtype=str) and
    exposes safe, boundary-checked cell reads plus label-search utilities.

    Attributes
    ----------
    df    : the underlying DataFrame (NaN replaced with "")
    nrows : row count
    ncols : column count
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df.replace({np.nan: ""})
        self.nrows, self.ncols = self.df.shape

    # ------------------------------------------------------------------
    # Cell access
    # ------------------------------------------------------------------

    def get(self, row: int, col: int) -> str:
        """Return the string value at (row, col), or "" if out of bounds."""
        if row < 0 or col < 0 or row >= self.nrows or col >= self.ncols:
            return ""
        value = self.df.iat[row, col]
        return "" if value is None else str(value).strip()

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_cells(self) -> Iterable[Tuple[int, int, str]]:
        """Yield (row, col, value) for every non-empty cell in reading order."""
        for row in range(self.nrows):
            for col in range(self.ncols):
                value = self.get(row, col)
                if value:
                    yield row, col, value

    # ------------------------------------------------------------------
    # Label searching
    # ------------------------------------------------------------------

    def find_label_positions(self, synonyms: List[str]) -> List[Tuple[int, int, str]]:
        """
        Find all cells whose normalised text exactly matches or starts with
        any of the given synonyms.

        Returns a list of (row, col, raw_cell_value) in discovery order.
        Empty strings in synonyms are silently ignored.
        """
        normalised_synonyms = [normalize_text(s) for s in synonyms if s]

        positions: List[Tuple[int, int, str]] = []

        for row, col, value in self.iter_cells():
            normalised_cell = normalize_text(value)
            for label in normalised_synonyms:
                if not label:
                    continue
                if normalised_cell == label or normalised_cell.startswith(label):
                    positions.append((row, col, value))
                    break

        return positions
