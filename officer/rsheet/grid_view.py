"""Spreadsheet grid, Excel-style cell delegate and formula bar for RSheet."""

from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import Qt, QRect, QSize, Signal, QModelIndex, QItemSelection
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTableView,
    QHeaderView, QAbstractItemView, QApplication, QStyledItemDelegate, QStyle
)
from officer.core.themes.theme_manager import ThemeManager
from officer.rsheet.model import SpreadsheetModel, Sheet, CellFormat
from officer.rsheet.formula.parser import col_to_letter


class CellDelegate(QStyledItemDelegate):
    """
    Paints a cell the way Excel does: fill colour, borders, the light-green
    range tint, the 2px accent outline on the active range and the fill handle.
    """

    HANDLE = 7

    def __init__(self, view: "SpreadsheetGrid", parent=None):
        super().__init__(parent or view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), self.view.row_height())

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: C901
        colors = ThemeManager.instance().colors("rsheet")
        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        fmt = index.data(SpreadsheetModel.FormatRole) or CellFormat()

        # 1. Fill: the cell's own colour, then Excel's range tint on top.
        background = index.data(Qt.ItemDataRole.BackgroundRole)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.surface))
        painter.drawRect(rect)
        if background is not None:
            painter.setBrush(QColor(background))
            painter.drawRect(rect)
        if selected:
            tint = QColor(colors.grid_selection)
            tint.setAlphaF(0.55)
            painter.setBrush(tint)
            painter.drawRect(rect)

        # 2. Text (scaled by the workbook's zoom, wrapped when the cell says so)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if text:
            font = index.data(Qt.ItemDataRole.FontRole) or option.font
            scale = self.view.zoom_factor()
            if scale != 1.0 and font.pointSizeF() > 0:
                font.setPointSizeF(max(5.0, font.pointSizeF() * scale))
            painter.setFont(font)
            color = index.data(Qt.ItemDataRole.ForegroundRole)
            painter.setPen(QColor(color) if color else QColor(colors.text))
            align = Qt.AlignmentFlag(index.data(Qt.ItemDataRole.TextAlignmentRole)
                                     or int(option.displayAlignment))
            if getattr(fmt, "wrap_text", False):
                painter.drawText(rect.adjusted(3, 1, -3, -1),
                                 align | Qt.TextFlag.TextWordWrap, text)
            else:
                painter.drawText(rect.adjusted(3, 0, -3, 0), align, text)

        # 3. Cell borders (Excel's Border gallery)
        self._paint_borders(painter, rect, fmt, colors)

        # 4. The active-range outline: only the edges that face outward.
        if self.view.is_range_edge(index):
            pen = QPen(QColor(colors.grid_selection_border), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            edges = self.view.range_edges(index)
            half = 1.0
            if "top" in edges:
                painter.drawLine(rect.left(), rect.top() + 0, rect.right(), rect.top() + 0)
            if "bottom" in edges:
                painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
            if "left" in edges:
                painter.drawLine(rect.left() + 0, rect.top(), rect.left() + 0, rect.bottom())
            if "right" in edges:
                painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())

        # 5. Fill handle: the small solid square on the active cell's corner.
        if index == self.view.currentIndex() and self.view.currentIndex().isValid():
            painter.setPen(QPen(QColor(colors.grid_selection_border), 1))
            painter.setBrush(QColor(colors.grid_selection_border))
            size = self.HANDLE
            painter.drawRect(QRect(rect.right() - size + 1, rect.bottom() - size + 1,
                                   size, size))
        painter.restore()

    @staticmethod
    def _paint_borders(painter: QPainter, rect: QRect, fmt: CellFormat, colors) -> None:
        if fmt.border == "none":
            return
        pen = QPen(QColor(colors.text), 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        edges = {
            "all": ("top", "bottom", "left", "right"),
            "outside": ("top", "bottom", "left", "right"),
            "bottom": ("bottom",),
            "top": ("top",),
            "left": ("left",),
            "right": ("right",),
        }.get(fmt.border, ())
        for edge in edges:
            if edge == "top":
                painter.drawLine(rect.topLeft(), rect.topRight())
            elif edge == "bottom":
                painter.drawLine(rect.bottomLeft(), rect.bottomRight())
            elif edge == "left":
                painter.drawLine(rect.topLeft(), rect.bottomLeft())
            else:
                painter.drawLine(rect.topRight(), rect.bottomRight())


class SpreadsheetGrid(QTableView):
    """
    The worksheet grid: Excel's header ramp, a themed gridline colour, and the
    range-edge bookkeeping the delegate needs for its outline and fill handle.
    """

    selectionStatsChanged = Signal(float, int, float)  # avg, count, sum
    currentCellChanged = Signal(int, int, str)         # row, col, raw value

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SpreadsheetGrid")
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setShowGrid(True)
        self.setGridStyle(Qt.PenStyle.SolidLine)
        self.setCornerButtonEnabled(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.horizontalHeader().setDefaultSectionSize(95)
        self.verticalHeader().setDefaultSectionSize(22)
        self.horizontalHeader().setMinimumSectionSize(30)
        self.verticalHeader().setMinimumSectionSize(18)
        self.horizontalHeader().setHighlightSections(False)
        self.verticalHeader().setHighlightSections(False)
        self.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setItemDelegate(CellDelegate(self, self))
        self._edges_cache: dict = {}
        self._view_mode = "normal"
        self._zoom = 100
        self._page_breaks: List[int] = []
        self.page_margin_mm = self.DEFAULT_PAGE_MARGIN_MM
        self.page_size_mm = self.PAGE_SIZE_MM
        self._cut_range: Optional[Tuple[int, int, int, int]] = None
        self._custom_cols: Dict[int, int] = {}
        self._custom_rows: Dict[int, int] = {}

    # -- Excel's zoom ------------------------------------------------------- #

    BASE_COL_WIDTH = 95
    BASE_ROW_HEIGHT = 22

    def zoom_factor(self) -> float:
        return self._zoom / 100

    def row_height(self) -> int:
        return max(14, int(self.BASE_ROW_HEIGHT * self.zoom_factor()))

    def set_zoom(self, percent: int) -> None:
        """Scale column widths, row heights and cell fonts, like Excel's zoom."""
        self._zoom = max(40, min(400, int(percent)))
        factor = self.zoom_factor()
        self.horizontalHeader().setDefaultSectionSize(max(24, int(self.BASE_COL_WIDTH * factor)))
        self.verticalHeader().setDefaultSectionSize(self.row_height())
        for column, base in self._custom_cols.items():
            super().setColumnWidth(column, max(1, int(base * factor)))
        for row, base in self._custom_rows.items():
            super().setRowHeight(row, max(1, int(base * factor)))
        self.viewport().update()

    def setColumnWidth(self, column: int, width: int) -> None:
        """Remember the *unscaled* width so a later zoom keeps the proportion."""
        self._custom_cols[column] = max(1, int(width / self.zoom_factor()))
        super().setColumnWidth(column, max(1, int(self._custom_cols[column] * self.zoom_factor())))

    def setRowHeight(self, row: int, height: int) -> None:
        self._custom_rows[row] = max(1, int(height / self.zoom_factor()))
        super().setRowHeight(row, max(1, int(self._custom_rows[row] * self.zoom_factor())))

    def zoom(self) -> int:
        return self._zoom

    # -- Excel's workbook views -------------------------------------------- #

    PAGE_SIZE_MM = (297, 210)   # A4 landscape
    DEFAULT_PAGE_MARGIN_MM = 12.7
    PAGE_GAP_PX = 14            # Excel's grey gutter between two printed pages

    def view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode: str) -> None:
        """Normal / Page Layout (print look) / Page Break Preview."""
        self._view_mode = mode
        self.setShowGrid(mode != "page-layout")
        self.viewport().update()

    def set_page_size(self, width_mm: float, height_mm: float) -> None:
        """The paper the Page Layout / Page Break views are measured against."""
        self.page_size_mm = (width_mm, height_mm)
        self.viewport().update()

    def _page_area_px(self) -> int:
        """Printable width of one page, in device-independent px."""
        width_mm = self.page_size_mm[0] - 2 * self.page_margin_mm
        return max(64, int(width_mm / 25.4 * 96))

    def _page_height_px(self) -> int:
        """Printable height of one page, in device-independent px."""
        height_mm = self.page_size_mm[1] - 2 * self.page_margin_mm
        return max(64, int(height_mm / 25.4 * 96))

    def set_page_breaks(self, rows: List[int]) -> None:
        """Manual page breaks the user inserted; shown in Page Break Preview."""
        self._page_breaks = sorted(set(rows))
        self.viewport().update()

    def set_page_margins(self, millimetres: float) -> None:
        """Excel's page margins, which shrink the printable area per page."""
        self.page_margin_mm = millimetres
        self.viewport().update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self._view_mode == "normal" or self.model() is None:
            return
        colors = ThemeManager.instance().colors("rsheet")
        painter = QPainter(self.viewport())

        # Where each printed page starts, in viewport coordinates.
        h_scroll = self.horizontalScrollBar().value()
        v_scroll = self.verticalScrollBar().value()
        page_w, page_h = self._page_area_px(), self._page_height_px()
        width, height = self.viewport().width(), self.viewport().height()

        if self._view_mode == "page-layout":
            # Excel's Page Layout view: white sheets separated by grey gutters.
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(colors.window))
            x = page_w - self.PAGE_GAP_PX // 2 - h_scroll
            while x < width:
                if x + self.PAGE_GAP_PX > 0:
                    painter.drawRect(int(x), 0, self.PAGE_GAP_PX, height)
                x += page_w
            y = page_h - self.PAGE_GAP_PX // 2 - v_scroll
            while y < height:
                if y + self.PAGE_GAP_PX > 0:
                    painter.drawRect(0, int(y), width, self.PAGE_GAP_PX)
                y += page_h
            painter.end()
            return

        pen = QPen(QColor(colors.accent), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)

        col_w = self.horizontalHeader().defaultSectionSize()
        per_page_cols = max(1, page_w // max(1, col_w))
        for col in range(per_page_cols, self.model().columnCount(), per_page_cols):
            x = self.columnViewportPosition(col)
            if 0 < x < width:
                painter.drawLine(x, 0, x, height)

        row_h = self.verticalHeader().defaultSectionSize()
        per_page_rows = max(1, page_h // max(1, row_h))
        boundaries = set(range(per_page_rows, self.model().rowCount(), per_page_rows))
        boundaries.update(self._page_breaks)
        painter.setPen(QPen(QColor(colors.grid_selection_border), 1, Qt.PenStyle.DashLine))
        for row in sorted(boundaries):
            y = self.rowViewportPosition(row)
            if 0 < y < height:
                painter.drawLine(0, y, width, y)
        painter.end()

    # -- printing ----------------------------------------------------------- #

    def _print_col_width(self, column: int) -> float:
        """A column's width in layout pixels, untouched by the view's zoom."""
        return self._custom_cols.get(column, self.BASE_COL_WIDTH)

    def _print_row_height(self, row: int) -> float:
        return self._custom_rows.get(row, self.BASE_ROW_HEIGHT)

    def used_range(self) -> Tuple[int, int]:
        """(bottom row, right column) of the sheet, or (-1, -1) when empty.

        The model claims thousands of empty rows; a sheet prints what has been
        typed or styled, which is what the sparse cell map knows.
        """
        model = self.model()
        sheet = getattr(model, "sheet", None) if model is not None else None
        if sheet is None:
            return -1, -1
        bottom = right = -1
        for (row, col), cell in sheet.cells.items():
            if not str(cell.raw_value or "").strip() and cell.format == CellFormat():
                continue
            bottom, right = max(bottom, row), max(right, col)
        return bottom, right

    def _print_column_bands(self, right: int, usable_px: float) -> List[tuple]:
        """Column ranges that each fit across one page, with the shrink factor.

        A column wider than the paper is scaled down rather than cut off.
        """
        bands: List[tuple] = []
        first = 0
        while first <= right:
            width, last = 0.0, first
            for col in range(first, right + 1):
                w = self._print_col_width(col)
                if width + w > usable_px and col > first:
                    break
                width, last = width + w, col
            bands.append((first, last, min(1.0, usable_px / max(1.0, width))))
            first = last + 1
        return bands

    def _print_row_bands(self, bottom: int, usable_px: float) -> List[Tuple[int, int]]:
        """Row ranges for one page down, cut by the paper and manual breaks."""
        breaks = set(self._page_breaks)
        bands: List[Tuple[int, int]] = []
        first = 0
        while first <= bottom:
            height, last = 0.0, first
            for row in range(first, bottom + 1):
                h = self._print_row_height(row)
                if height + h > usable_px and row > first:
                    break
                height, last = height + h, row
                if last in breaks and last < bottom:
                    break
            bands.append((first, last))
            first = last + 1
        return bands

    def print_to(self, painter: QPainter, area: QRect, new_page) -> int:
        """Draw the sheet onto a paged paint device, one page per sheet.

        *area* is one page's printable rectangle in the device's own pixels and
        *new_page* moves to the next one. Columns that no longer fit across the
        paper start a band to the right, rows past the bottom start a new page,
        and the manual breaks the user inserted are honoured.
        """
        bottom, right = self.used_range()
        if bottom < 0:
            return 1                          # a blank sheet still gets its page
        px = area.width() / max(1, self._page_area_px())
        pages = 0
        for band in self._print_column_bands(right, self._page_area_px()):
            for rows in self._print_row_bands(bottom, self._page_height_px() / band[2]):
                if pages:
                    new_page()
                self._print_page(painter, area, band, rows, px)
                pages += 1
        return pages

    def _print_page(self, painter: QPainter, area: QRect, band: tuple,
                    rows: Tuple[int, int], px: float) -> None:
        first_col, last_col, scale = band
        y = area.top()
        for row in range(rows[0], rows[1] + 1):
            height = max(1, round(self._print_row_height(row) * scale * px))
            x = area.left()
            for col in range(first_col, last_col + 1):
                width = max(1, round(self._print_col_width(col) * scale * px))
                self._print_cell(painter, QRect(x, y, width, height), row, col, scale)
                x += width
            y += height

    def _print_cell(self, painter: QPainter, rect: QRect, row: int, col: int,
                    scale: float) -> None:
        model = self.model()
        colors = ThemeManager.instance().colors("rsheet")
        index = model.index(row, col)
        fmt = model.data(index, SpreadsheetModel.FormatRole) or CellFormat()
        background = model.data(index, Qt.ItemDataRole.BackgroundRole)

        painter.setPen(QPen(QColor(colors.gridline), 1))
        painter.setBrush(QColor(background) if background is not None
                         else Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        text = str(model.data(index, Qt.ItemDataRole.DisplayRole) or "")
        if text:
            font = QFont(model.data(index, Qt.ItemDataRole.FontRole) or self.font())
            if font.pointSizeF() > 0 and scale != 1.0:
                font.setPointSizeF(max(4.0, font.pointSizeF() * scale))
            painter.setFont(font)
            color = model.data(index, Qt.ItemDataRole.ForegroundRole)
            painter.setPen(QColor(color) if color else QColor(colors.text))
            align = Qt.AlignmentFlag(model.data(index, Qt.ItemDataRole.TextAlignmentRole)
                                     or int(fmt.alignment))
            pad = max(1, round(3 * scale))
            if fmt.wrap_text:
                painter.drawText(rect.adjusted(pad, 1, -pad, -1),
                                 align | Qt.TextFlag.TextWordWrap, text)
            else:
                painter.drawText(rect.adjusted(pad, 0, -pad, 0), align, text)
        CellDelegate._paint_borders(painter, rect, fmt, colors)

    # -- theming hooks ------------------------------------------------------ #

    def refresh_theme(self) -> None:
        """Re-pull the palette's gridline colour (called on theme switches)."""
        colors = ThemeManager.instance().colors("rsheet")
        self.setStyleSheet(f"""
            QTableView#SpreadsheetGrid {{
                background-color: {colors.surface};
                gridline-color: {colors.gridline};
                border: none;
                selection-background-color: {colors.grid_selection};
                selection-color: {colors.text};
            }}
            QTableView#SpreadsheetGrid QHeaderView::section {{
                background-color: {colors.header};
                color: {colors.text_secondary};
                border: 1px solid {colors.gridline};
                border-right: 1px solid {colors.border_strong};
                border-bottom: 1px solid {colors.border_strong};
                padding: 1px 4px;
                font-size: 11px;
            }}
            QTableView#SpreadsheetGrid QHeaderView::section:horizontal {{
                min-height: 20px;
            }}
            QTableView#SpreadsheetGrid QHeaderView::section:vertical {{
                min-width: 38px;
            }}
        """)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.refresh_theme()

    # -- range geometry for the delegate ------------------------------------ #

    def _selection_rects(self) -> List[QRect]:
        sm = self.selectionModel()
        if sm is None:
            return []
        rects = []
        for range_ in sm.selection():
            rects.append(QRect(range_.topLeft().row(), range_.topLeft().column(),
                               range_.bottomRight().row() - range_.topLeft().row() + 1,
                               range_.bottomRight().column() - range_.topLeft().column() + 1))
        return rects

    def is_range_edge(self, index: QModelIndex) -> bool:
        return bool(self.range_edges(index))

    def range_edges(self, index: QModelIndex) -> List[str]:
        """Which sides of *index* sit on the boundary of a selected range."""
        if not index.isValid():
            return []
        row, col = index.row(), index.column()
        edges: List[str] = []
        for rect in self._selection_rects():
            if not rect.contains(row, col):
                continue
            if row == rect.top():
                edges.append("top")
            if row == rect.bottom():
                edges.append("bottom")
            if col == rect.left():
                edges.append("left")
            if col == rect.right():
                edges.append("right")
            break
        if not edges and index == self.currentIndex():
            edges = ["top", "bottom", "left", "right"]
        return edges

    # -- clipboard: Excel's tab-separated round trip ------------------------ #

    def selection_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """(top, left, bottom, right) of the selection, or None when empty."""
        indexes = self.selectedIndexes()
        if not indexes:
            return None
        rows = [i.row() for i in indexes]
        cols = [i.column() for i in indexes]
        return min(rows), min(cols), max(rows), max(cols)

    def copy_selection(self, cut: bool = False) -> str:
        """Put the selection on the clipboard as TSV; returns the text."""
        bounds = self.selection_bounds()
        if bounds is None or self.model() is None:
            return ""
        top, left, bottom, right = bounds
        lines = []
        for row in range(top, bottom + 1):
            cells = []
            for col in range(left, right + 1):
                value = self.model().data(self.model().index(row, col), Qt.ItemDataRole.EditRole)
                cells.append("" if value is None else str(value))
            lines.append("\t".join(cells))
        text = "\n".join(lines)
        QApplication.clipboard().setText(text)
        self._cut_range = (top, left, bottom, right) if cut else None
        if cut:
            for row in range(top, bottom + 1):
                for col in range(left, right + 1):
                    self.model().setData(self.model().index(row, col), "", Qt.ItemDataRole.EditRole)
        return text

    def paste_clipboard(self) -> int:
        """Paste clipboard text at the active cell; returns the cells written."""
        text = QApplication.clipboard().text()
        curr = self.currentIndex()
        if not text or not curr.isValid() or self.model() is None:
            return 0
        separator = "\t" if "\t" in text else ","
        written = 0
        for dr, line in enumerate(text.splitlines()):
            for dc, value in enumerate(line.split(separator)):
                target = self.model().index(curr.row() + dr, curr.column() + dc)
                if target.isValid() and self.model().setData(target, value.strip(),
                                                             Qt.ItemDataRole.EditRole):
                    written += 1
        return written

    # -- signals ------------------------------------------------------------ #

    def selectionChanged(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        super().selectionChanged(selected, deselected)
        self._calculate_selection_metrics()
        self.viewport().update()

    def currentChanged(self, current: QModelIndex, previous: QModelIndex) -> None:  # noqa: N802
        super().currentChanged(current, previous)
        if current.isValid() and self.model():
            raw = self.model().data(current, Qt.ItemDataRole.EditRole) or ""
            self.currentCellChanged.emit(current.row(), current.column(), str(raw))
        self.viewport().update()

    def _calculate_selection_metrics(self) -> None:
        indexes = self.selectedIndexes()
        if not indexes or not self.model():
            self.selectionStatsChanged.emit(0.0, 0, 0.0)
            return

        nums: List[float] = []
        for idx in indexes:
            val = self.model().data(idx, Qt.ItemDataRole.DisplayRole)
            if val is not None and str(val).strip():
                try:
                    nums.append(float(str(val).replace(",", "").replace("$", "").rstrip("%")))
                except ValueError:
                    pass

        count = len(nums)
        total = sum(nums)
        avg = total / count if count else 0.0
        self.selectionStatsChanged.emit(avg, count, total)


class FormulaBar(QWidget):
    """Excel's formula bar: name box, the italic *fx* marker and the edit field."""

    formulaSubmitted = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("FormulaBar")
        self.setFixedHeight(26)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        self.cell_coord_label = QLabel("A1", self)
        self.cell_coord_label.setObjectName("NameBox")
        self.cell_coord_label.setFixedWidth(64)
        self.cell_coord_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.cell_coord_label)

        self.fx_label = QLabel("fx", self)
        self.fx_label.setObjectName("FunctionMarker")
        self.fx_label.setFixedWidth(22)
        self.fx_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.fx_label)

        self.formula_input = QLineEdit(self)
        self.formula_input.setObjectName("FormulaInput")
        self.formula_input.setPlaceholderText("Enter a value or a formula starting with =")
        self.formula_input.setFrame(False)
        self.formula_input.returnPressed.connect(self._on_return)
        layout.addWidget(self.formula_input, 1)

    def set_cell(self, row: int, col: int, raw_value: str) -> None:
        self.cell_coord_label.setText(f"{col_to_letter(col)}{row + 1}")
        self.formula_input.setText(raw_value)

    def _on_return(self) -> None:
        self.formulaSubmitted.emit(self.formula_input.text())


class SpreadsheetWidget(QWidget):
    """Container combining the FormulaBar and the worksheet grid."""

    def __init__(self, model: SpreadsheetModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model = model

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.formula_bar = FormulaBar(self)
        layout.addWidget(self.formula_bar)

        self.grid = SpreadsheetGrid(self)
        self.grid.setModel(self.model)
        layout.addWidget(self.grid, 1)

        self.grid.selectionModel().currentChanged.connect(self._on_current_cell_changed)
        self.grid.currentCellChanged.connect(
            lambda r, c, raw: self.formula_bar.set_cell(r, c, raw))
        self.formula_bar.formulaSubmitted.connect(self._on_formula_submitted)

    def _on_current_cell_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            raw = self.model.data(current, Qt.ItemDataRole.EditRole) or ""
            self.formula_bar.set_cell(current.row(), current.column(), str(raw))

    def _on_formula_submitted(self, text: str) -> None:
        curr = self.grid.currentIndex()
        if curr.isValid():
            self.model.setData(curr, text, Qt.ItemDataRole.EditRole)
            self._on_current_cell_changed(curr, curr)

    def refresh_theme(self) -> None:
        self.grid.refresh_theme()
        self.grid.viewport().update()
