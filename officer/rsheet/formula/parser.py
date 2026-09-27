"""Spreadsheet cell coordinate utilities and formula tokenizer."""

import re
from typing import Tuple, List, Optional


def col_to_letter(col_idx: int) -> str:
    """Convert 0-based column index to Excel column string (0 -> 'A', 27 -> 'AB')."""
    result = ""
    col_idx += 1
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def letter_to_col(letters: str) -> int:
    """Convert Excel column string to 0-based column index ('A' -> 0, 'AB' -> 27)."""
    result = 0
    for char in letters.upper():
        result = result * 26 + (ord(char) - ord('A') + 1)
    return result - 1


def parse_cell_ref(ref_str: str) -> Optional[Tuple[int, int]]:
    """Parse 'B4' into (row, col) = (3, 1)."""
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref_str.strip())
    if not m:
        return None
    col_str, row_str = m.groups()
    col = letter_to_col(col_str)
    row = int(row_str) - 1
    return row, col


def parse_range_ref(range_str: str) -> List[Tuple[int, int]]:
    """Parse 'A1:B3' into list of (row, col) tuples."""
    parts = range_str.split(":")
    if len(parts) != 2:
        cell = parse_cell_ref(range_str)
        return [cell] if cell else []

    c1 = parse_cell_ref(parts[0])
    c2 = parse_cell_ref(parts[1])
    if not c1 or not c2:
        return []

    r_min, r_max = min(c1[0], c2[0]), max(c1[0], c2[0])
    c_min, c_max = min(c1[1], c2[1]), max(c1[1], c2[1])

    cells = []
    for r in range(r_min, r_max + 1):
        for c in range(c_min, c_max + 1):
            cells.append((r, c))
    return cells
