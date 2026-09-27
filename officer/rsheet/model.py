"""Spreadsheet Data Model and QAbstractTableModel virtualized grid."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, List
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QColor, QFont
from officer.rsheet.formula.parser import col_to_letter
from officer.rsheet.formula.evaluator import FormulaEvaluator


@dataclass
class CellFormat:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font_size: int = 11
    font_family: str = "Calibri"
    text_color: str = "#111827"
    bg_color: Optional[str] = None
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    wrap_text: bool = False
    number_format: str = ""      # "" = General, else an Excel-style format string
    border: str = "none"         # none | all | outside | bottom | top | left | right


#: Excel's Number-group format strings, keyed by the ribbon combo's label.
NUMBER_FORMATS: Dict[str, str] = {
    "General": "",
    "Number": "#,##0.00",
    "Currency": "$#,##0.00",
    "Accounting": "_($* #,##0.00_)",
    "Percentage": "0.00%",
    "Scientific": "0.00E+00",
    "Date": "MM/DD/YYYY",
    "Text": "@",
}


def format_number(raw: str, number_format: str) -> str:
    """Render *raw* with an Excel-style *number_format*; falls back to the input."""
    if not number_format or raw == "":
        return raw
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return raw

    if number_format == "@":
        return raw
    if number_format.endswith("%"):
        decimals = len(re.findall(r"0", number_format.split(".", 1)[1])) if "." in number_format else 0
        return f"{value * 100:.{decimals}f}%"
    if "E+" in number_format:
        return f"{value:.2E}"
    if "YY" in number_format:
        try:
            # Excel's 1900 serial date system.
            return (datetime(1899, 12, 30) + timedelta(days=value)).strftime("%m/%d/%Y")
        except (ValueError, OverflowError):
            return raw

    decimals = len(re.findall(r"0", number_format.split(".", 1)[1])) if "." in number_format else 0
    body = f"{value:,.{decimals}f}" if "," in number_format else f"{value:.{decimals}f}"
    if "_(" in number_format:                      # accounting pads the symbol left
        return f"$ {body}"
    if "$" in number_format:
        return f"${body}"
    return body


@dataclass
class CellData:
    raw_value: str = ""
    format: CellFormat = field(default_factory=CellFormat)


class Sheet:
    """Represents a single spreadsheet tab."""

    def __init__(self, name: str = "Sheet1"):
        self.name = name
        self.cells: Dict[Tuple[int, int], CellData] = {}
        self.evaluator = FormulaEvaluator(self.get_cell_raw)

    def get_cell_raw(self, row: int, col: int) -> str:
        cell = self.cells.get((row, col))
        return cell.raw_value if cell else ""

    def get_cell_display(self, row: int, col: int) -> str:
        raw = self.get_cell_raw(row, col)
        if not raw:
            return ""
        if raw.startswith("="):
            value = self.evaluator.evaluate(raw, (row, col))
            number_format = self.get_format(row, col).number_format
            if number_format and isinstance(value, (int, float)):
                return format_number(str(value), number_format)
            if isinstance(value, float):
                return f"{value:.4g}"
            return str(value)
        return format_number(raw, self.get_format(row, col).number_format)

    def set_cell(self, row: int, col: int, raw_value: str) -> None:
        if (row, col) not in self.cells:
            self.cells[(row, col)] = CellData()
        self.cells[(row, col)].raw_value = str(raw_value)

    def get_format(self, row: int, col: int) -> CellFormat:
        """Read-only view of a cell's format; never allocates (the grid calls this)."""
        cell = self.cells.get((row, col))
        return cell.format if cell else CellFormat()

    def ensure_format(self, row: int, col: int) -> CellFormat:
        """Return the live format object for a cell, creating the cell on first use."""
        cell = self.cells.get((row, col))
        if cell is None:
            cell = CellData()
            self.cells[(row, col)] = cell
        return cell.format

    def clear_cell(self, row: int, col: int) -> None:
        self.cells.pop((row, col), None)

    # -- row / column operations -------------------------------------------- #

    def _shift(self, remap) -> None:
        moved: Dict[Tuple[int, int], CellData] = {}
        for (row, col), cell in self.cells.items():
            moved[remap(row, col)] = cell
        self.cells = moved

    def insert_row(self, row: int) -> None:
        self._shift(lambda r, c: (r + 1 if r >= row else r, c))

    def delete_row(self, row: int) -> None:
        self.cells = {k: v for k, v in self.cells.items() if k[0] != row}
        self._shift(lambda r, c: (r - 1 if r > row else r, c))

    def insert_column(self, col: int) -> None:
        self._shift(lambda r, c: (r, c + 1 if c >= col else c))

    def delete_column(self, col: int) -> None:
        self.cells = {k: v for k, v in self.cells.items() if k[1] != col}
        self._shift(lambda r, c: (r, c - 1 if c > col else c))


class SpreadsheetModel(QAbstractTableModel):
    """
    High performance virtualized spreadsheet table model.
    Renders 100,000 rows x 500 columns effortlessly.
    """

    cellStatsChanged = Signal(float, int, float)  # (average, count, sum)

    #: The cell's :class:`CellFormat`, for the grid's delegate to paint borders.
    FormatRole = int(Qt.ItemDataRole.UserRole) + 1

    #: Excel's "Show Formulas" toggle lives on :attr:`show_formulas`; these are
    #: the floors below which rows / columns can no longer be deleted.
    MIN_ROWS, MIN_COLS = 100, 26

    def __init__(
        self,
        sheet: Optional[Sheet] = None,
        rows: int = 10000,
        cols: int = 500,
        parent = None
    ):
        super().__init__(parent)
        self.sheet = sheet or Sheet("Sheet1")
        self._row_count = rows
        self._col_count = cols
        self.show_formulas = False

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self._row_count

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self._col_count

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if self.show_formulas:
                return self.sheet.get_cell_raw(row, col)
            return self.sheet.get_cell_display(row, col)

        elif role == Qt.ItemDataRole.EditRole:
            return self.sheet.get_cell_raw(row, col)

        elif role == self.FormatRole:
            return self.sheet.get_format(row, col)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            fmt = self.sheet.get_format(row, col)
            align = fmt.alignment
            if align == (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter):
                # Excel right-aligns numbers unless the user says otherwise.
                if _is_numeric(self.sheet.get_cell_display(row, col)):
                    align = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            return int(align)

        elif role == Qt.ItemDataRole.FontRole:
            fmt = self.sheet.get_format(row, col)
            font = QFont(fmt.font_family, fmt.font_size)
            font.setBold(fmt.bold)
            font.setItalic(fmt.italic)
            font.setUnderline(fmt.underline)
            return font

        elif role == Qt.ItemDataRole.ForegroundRole:
            fmt = self.sheet.get_format(row, col)
            return QColor(fmt.text_color)

        elif role == Qt.ItemDataRole.BackgroundRole:
            fmt = self.sheet.get_format(row, col)
            return QColor(fmt.bg_color) if fmt.bg_color else None

        elif role == Qt.ItemDataRole.ToolTipRole:
            raw = self.sheet.get_cell_raw(row, col)
            if raw.startswith("="):
                return f"{col_to_letter(col)}{row + 1}  {raw}"
            return None

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False

        row = index.row()
        col = index.column()
        self.sheet.set_cell(row, col, str(value))
        self.dataChanged.emit(index, index, [
            Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.TextAlignmentRole, self.FormatRole,
        ])
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return col_to_letter(section)
            return str(section + 1)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        return None

    # -- structural operations (keep rowCount/columnCount in sync) ---------- #

    def insert_row_at(self, row: int) -> None:
        self.beginInsertRows(QModelIndex(), row, row)
        self._row_count += 1
        self.sheet.insert_row(row)
        self.endInsertRows()
        self.refresh_all()

    def delete_row_at(self, row: int) -> None:
        if self._row_count <= self.MIN_ROWS:
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        self._row_count -= 1
        self.sheet.delete_row(row)
        self.endRemoveRows()
        self.refresh_all()

    def insert_column_at(self, col: int) -> None:
        self.beginInsertColumns(QModelIndex(), col, col)
        self._col_count += 1
        self.sheet.insert_column(col)
        self.endInsertColumns()
        self.refresh_all()

    def delete_column_at(self, col: int) -> None:
        if self._col_count <= self.MIN_COLS:
            return
        self.beginRemoveColumns(QModelIndex(), col, col)
        self._col_count -= 1
        self.sheet.delete_column(col)
        self.endRemoveColumns()
        self.refresh_all()

    # -- bulk operations used by the ribbon --------------------------------- #

    def refresh_all(self) -> None:
        top = self.index(0, 0)
        bottom = self.index(self._row_count - 1, self._col_count - 1)
        self.dataChanged.emit(top, bottom, [
            Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole,
            Qt.ItemDataRole.FontRole, Qt.ItemDataRole.BackgroundRole,
            Qt.ItemDataRole.ForegroundRole, Qt.ItemDataRole.TextAlignmentRole,
            self.FormatRole,
        ])

    def refresh_cells(self, indexes: List[QModelIndex], roles=None) -> None:
        roles = roles or [
            Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.FontRole,
            Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole,
            Qt.ItemDataRole.TextAlignmentRole, self.FormatRole,
        ]
        for idx in indexes:
            self.dataChanged.emit(idx, idx, roles)


def _is_numeric(text: str) -> bool:
    if not text:
        return False
    try:
        float(text.replace(",", "").replace("$", "").replace("%", "").strip())
        return True
    except ValueError:
        return False
