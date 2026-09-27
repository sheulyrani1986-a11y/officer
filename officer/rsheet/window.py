"""RSheet Main Application Window."""

import csv
import os
from dataclasses import fields
from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import Qt, QModelIndex, QMarginsF, QPointF, QRectF, QSizeF
from PySide6.QtGui import (
    QColor, QKeySequence, QPainter, QPageLayout, QPageSize, QPen, QPdfWriter,
    QShortcut
)
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QMenu,
    QMessageBox, QSpinBox, QTabBar, QToolButton, QVBoxLayout, QWidget
)
from officer.core.ai.ollama_client import OllamaClient
from officer.core.ui.base_window import OfficeBaseWindow
from officer.core.ui.icons import IconProvider
from officer.core.ui.fonts import FontListComboBox, installed_families
from officer.rsheet.formula.parser import col_to_letter, parse_cell_ref
from officer.rsheet.grid_view import SpreadsheetWidget
from officer.rsheet.io.xlsx_handler import XlsxHandler
from officer.rsheet.io.ods_handler import OdsHandler
from officer.rsheet.model import CellFormat, NUMBER_FORMATS, Sheet, SpreadsheetModel


class RSheetWindow(OfficeBaseWindow):
    """Excel-style spreadsheet window: ribbon, formula bar, worksheet grid, sheet tabs."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(app_name="rsheet", app_title="RSheet", parent=parent)

        # Set window icon to OfficeR logo
        self.setWindowIcon(IconProvider.get_app_icon())

        # Multi-sheet storage
        self.sheets: Dict[str, Sheet] = {"Sheet1": Sheet("Sheet1")}
        self.active_sheet_name = "Sheet1"

        # Model & widget (formula bar + grid)
        self.model = SpreadsheetModel(sheet=self.sheets["Sheet1"], rows=1000, cols=60, parent=self)
        self.sheet_widget = SpreadsheetWidget(self.model, self)
        self.workspace_layout.addWidget(self.sheet_widget, 1)

        # Workbook state Excel keeps on the page-layout / formula side
        self.paper_size = "A4"
        self.landscape = True
        self.page_margin_mm = 12.7
        self._page_breaks: List[int] = []
        self._title_rows: Optional[int] = None
        self._named_ranges: Dict[str, str] = {}
        self._show_formulas = False
        self._filter_active = False
        self._chart_windows: List["ChartCanvas"] = []
        self._apply_page_geometry()

        # Bottom worksheet tab strip
        self._build_sheet_tab_bar()

        # Status strip: selection stats, cell position, workbook views, zoom
        self.sheet_widget.grid.selectionStatsChanged.connect(self._on_selection_stats_changed)
        self.sheet_widget.grid.currentCellChanged.connect(lambda *_: self._update_status_position())
        self._setup_status_strip()

        # Keyboard shortcuts for the commands Excel exposes as chords
        QShortcut(QKeySequence("Ctrl+Shift+$"), self, activated=lambda: self._apply_format_key("Currency"))
        QShortcut(QKeySequence("Ctrl+Shift+%"), self, activated=lambda: self._apply_format_key("Percentage"))
        QShortcut(QKeySequence("Ctrl+Shift+#"), self, activated=lambda: self._apply_format_key("Date"))
        QShortcut(QKeySequence("Ctrl+B"), self, activated=lambda: self._toggle_font("bold"))
        QShortcut(QKeySequence("Ctrl+I"), self, activated=lambda: self._toggle_font("italic"))
        QShortcut(QKeySequence("Ctrl+U"), self, activated=lambda: self._toggle_font("underline"))
        QShortcut(QKeySequence("Ctrl+D"), self, activated=self._fill_down)
        QShortcut(QKeySequence("Shift+F11"), self, activated=self._on_add_sheet)

        # Ollama AI client
        self.ai_client = OllamaClient(parent=self)

        # The ribbon is built last so its controls can read the live model
        self._build_ribbon()

    # ------------------------------------------------------------------ chrome #

    def _build_sheet_tab_bar(self) -> None:
        container = QWidget(self)
        container.setObjectName("SheetTabStrip")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        container.setFixedHeight(28)
        strip_layout = QHBoxLayout(container)
        strip_layout.setContentsMargins(4, 0, 6, 0)
        strip_layout.setSpacing(3)

        self.add_sheet_btn = QToolButton(container)
        self.add_sheet_btn.setObjectName("SheetAddButton")
        self.add_sheet_btn.setText("+")
        self.add_sheet_btn.setFixedSize(20, 20)
        self.add_sheet_btn.setToolTip("New Sheet (Shift+F11)")
        self.add_sheet_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_sheet_btn.clicked.connect(self._on_add_sheet)
        strip_layout.addWidget(self.add_sheet_btn)

        self.tab_bar = QTabBar(container)
        self.tab_bar.setObjectName("SheetTabBar")
        self.tab_bar.setShape(QTabBar.Shape.RoundedSouth)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setMovable(True)
        self.tab_bar.tabBarDoubleClicked.connect(self._on_rename_sheet)
        self.tab_bar.currentChanged.connect(self._on_sheet_tab_switched)
        self.tab_bar.addTab("Sheet1")
        strip_layout.addWidget(self.tab_bar)

        strip_layout.addStretch(1)
        self.workspace_layout.addWidget(container)

    def _setup_status_strip(self) -> None:
        self.status_bar.set_view_modes((
            ("normal", "Normal", "Normal", "view-normal",
             lambda: self._set_view_mode("normal")),
            ("page-layout", "Page Layout", "Page Layout", "view-page-layout",
             lambda: self._set_view_mode("page-layout")),
            ("page-break", "Page Break Preview", "Page Break Preview", "view-page-break",
             lambda: self._set_view_mode("page-break")),
        ))
        self.status_bar.set_zoom_range(40, 400, 100)
        self.status_bar.zoomChanged.connect(self.sheet_widget.grid.set_zoom)
        self.status_bar.set_info("Ready")

    # ----------------------------------------------------------------- ribbon #

    def _build_ribbon(self) -> None:
        self._build_home_tab()
        self._build_insert_tab()
        self._build_page_layout_tab()
        self._build_formulas_tab()
        self._build_data_tab()
        self._build_view_tab()
        self._build_ai_tab()

    def _build_home_tab(self) -> None:
        tab = self.ribbon.add_tab("Home")

        # 1. Clipboard -------------------------------------------------------- #
        clip = tab.add_group("Clipboard")
        clip.add_button("Paste", "paste", large=True, on_click=self._paste,
                        tooltip="Paste (Ctrl+V)")
        clip_col = clip.add_column()
        clip.add_button_to(clip_col, "Cut", "cut", on_click=self._cut)
        clip.add_button_to(clip_col, "Copy", "copy", on_click=self._copy)
        clip.add_button_to(clip_col, "Format\nPainter", "paintbrush", on_click=self._copy_format)

        # 2. Font ------------------------------------------------------------- #
        font = tab.add_group("Font")
        font.set_dialog_launcher(self._show_format_cells_dialog)
        font_col = font.add_column()

        row1 = font.add_sub_row(font_col)
        self.font_combo = FontListComboBox(self)
        self.font_combo.addItems(installed_families())
        self.font_combo.setFixedWidth(132)
        self.font_combo.setToolTip("Font")
        self.font_combo.setMaxVisibleItems(18)
        self.font_combo.activated.connect(lambda _=0: self._set_font_family())
        row1.addWidget(self.font_combo)

        self.size_spin = QSpinBox(self)
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(11)
        self.size_spin.setFixedWidth(44)
        self.size_spin.setToolTip("Font Size")
        self.size_spin.valueChanged.connect(lambda _=0: self._set_font_size())
        row1.addWidget(self.size_spin)

        row2 = font.add_sub_row(font_col)
        for label, icon, handler in (
            ("Bold", "bold", lambda: self._toggle_font("bold")),
            ("Italic", "italic", lambda: self._toggle_font("italic")),
            ("Underline", "underline", lambda: self._toggle_font("underline")),
        ):
            btn = font.add_button_to(row2, "", icon, on_click=handler)
            btn.setToolTip(f"{label} (Ctrl+{label[0]})")
        border_menu = QMenu(self)
        for kind in ("all", "outside", "bottom", "top", "left", "right", "none"):
            border_menu.addAction(kind.capitalize(), lambda checked=False, k=kind: self._apply_border(k))
        font.add_button_to(row2, "Borders", "border-all", menu=border_menu)
        font.add_button_to(row2, "", "fill-color", on_click=self._choose_fill_color)
        font.add_button_to(row2, "", "font-color", on_click=self._choose_text_color)

        # 3. Alignment -------------------------------------------------------- #
        align = tab.add_group("Alignment")
        align_col = align.add_column()
        a_row1 = align.add_sub_row(align_col)
        for label, icon in (("Align Left", "align-left"), ("Center", "align-center"),
                            ("Align Right", "align-right")):
            btn = align.add_button_to(a_row1, "", icon,
                                      on_click=lambda checked=False, k=label: self._set_alignment(k))
            btn.setToolTip(label)
        a_row2 = align.add_sub_row(align_col)
        for key, icon in (("top", "align-top"), ("middle", "align-middle"),
                          ("bottom", "align-bottom")):
            btn = align.add_button_to(a_row2, "", icon,
                                      on_click=lambda checked=False, k=key: self._set_alignment(k))
            btn.setToolTip(f"{key.capitalize()} Align")
        align.add_button_to(a_row2, "Wrap Text", "wrap-text", on_click=self._toggle_wrap_text)

        # 4. Number ----------------------------------------------------------- #
        number = tab.add_group("Number")
        number.set_dialog_launcher(self._show_format_cells_dialog)
        num_col = number.add_column()

        # Excel's Number group: the format combo sits over the $ % , shortcuts,
        # with Increase/Decrease Decimal stacked as a column on their right.
        num_row = number.add_sub_row(num_col)
        num_left = QVBoxLayout()
        num_left.setContentsMargins(0, 0, 0, 0)
        num_left.setSpacing(2)
        num_row.addLayout(num_left)

        self.format_combo = QComboBox(self)
        self.format_combo.addItems(list(NUMBER_FORMATS.keys()))
        self.format_combo.setFixedWidth(118)
        self.format_combo.setToolTip("Number Format")
        self.format_combo.activated.connect(
            lambda _=0: self._apply_format_key(self.format_combo.currentText()))
        num_left.addWidget(self.format_combo)

        num_styles = QHBoxLayout()
        num_styles.setContentsMargins(0, 0, 0, 0)
        num_styles.setSpacing(1)
        num_left.addLayout(num_styles)
        for tooltip, icon, handler in (
            ("Format as Currency", "currency", lambda: self._apply_format_key("Currency")),
            ("Format as Percentage", "percent", lambda: self._apply_format_key("Percentage")),
            ("Comma Style", "text:,", lambda: self._apply_format_key("Number")),
        ):
            btn = number.add_button_to(num_styles, "", icon, on_click=handler)
            btn.setToolTip(tooltip)

        num_decimals = QVBoxLayout()
        num_decimals.setContentsMargins(0, 0, 0, 0)
        num_decimals.setSpacing(2)
        num_row.addLayout(num_decimals)
        bigger = number.add_button_to(num_decimals, "", "text:.00",
                                      on_click=lambda: self._step_decimals(1))
        bigger.setToolTip("Increase Decimal")
        smaller = number.add_button_to(num_decimals, "", "text:.0",
                                       on_click=lambda: self._step_decimals(-1))
        smaller.setToolTip("Decrease Decimal")

        # 5. Styles ----------------------------------------------------------- #
        styles = tab.add_group("Styles")
        styles.add_button("Format as\nTable", "table", large=True, on_click=self._format_as_table)
        style_menu = QMenu(self)
        for key, label in (("heading", "Heading"), ("good", "Good"), ("bad", "Bad"),
                           ("neutral", "Neutral"), ("total", "Total")):
            style_menu.addAction(label, lambda checked=False, k=key: self._apply_cell_style(k))
        styles.add_split_button("Cell\nStyles", "styles", style_menu, large=True,
                                on_click=lambda: self._apply_cell_style("heading"))

        # 6. Cells ------------------------------------------------------------ #
        cells = tab.add_group("Cells")
        cells.set_dialog_launcher(self._show_format_cells_dialog)
        insert_menu = QMenu(self)
        insert_menu.addAction("Rows Above", self._insert_row)
        insert_menu.addAction("Columns to the Left", self._insert_column)
        insert_menu.addAction("New Sheet", self._on_add_sheet)
        delete_menu = QMenu(self)
        delete_menu.addAction("Rows", self._delete_row)
        delete_menu.addAction("Columns", self._delete_column)
        delete_menu.addAction("Sheet", self._delete_current_sheet)
        cells.add_split_button("Insert", "new", insert_menu, large=True,
                               on_click=self._insert_row)
        cells_col = cells.add_column()
        cells.add_button_to(cells_col, "Delete", "remove", menu=delete_menu)
        cells.add_button_to(cells_col, "Format", "text:☰", on_click=self._show_format_cells_dialog)

        # 7. Editing ---------------------------------------------------------- #
        editing = tab.add_group("Editing")
        editing.add_button("AutoSum", "text:Σ", large=True, on_click=self._insert_autosum,
                           tooltip="Sum the numbers above (Alt+=)")
        sort_menu = QMenu(self)
        sort_menu.addAction("Sort A to Z", lambda: self._sort_column(True))
        sort_menu.addAction("Sort Z to A", lambda: self._sort_column(False))
        edit_col = editing.add_column()
        editing.add_button_to(edit_col, "Fill Down", "text:↓", on_click=self._fill_down)
        editing.add_button_to(edit_col, "Clear", "clear", on_click=self._clear_selected_cells)
        editing.add_button_to(edit_col, "Sort", "sort-az", menu=sort_menu,
                              on_click=lambda: self._sort_column(True))

    def _build_insert_tab(self) -> None:
        tab = self.ribbon.add_tab("Insert")

        tables = tab.add_group("Tables")
        table_menu = QMenu(self)
        for size in (2, 3, 4, 5):
            table_menu.addAction(f"{size} x {size}", lambda checked=False, s=size: self._insert_table(s, s))
        tables.add_split_button("Table", "table", table_menu, large=True,
                                on_click=lambda: self._insert_table(3, 3))

        charts = tab.add_group("Charts")
        chart_menu = QMenu(self)
        for kind in ("Bar", "Line", "Pie"):
            chart_menu.addAction(f"{kind} Chart", lambda checked=False, k=kind: self._insert_chart(k))
        charts.add_split_button("Chart", "chart-bar", chart_menu, large=True,
                                on_click=lambda: self._insert_chart("Bar"))

        sheets_grp = tab.add_group("Sheets")
        sheets_grp.add_button("New Sheet", "new", large=True, on_click=self._on_add_sheet,
                              tooltip="Insert a worksheet (Shift+F11)")

    def _build_page_layout_tab(self) -> None:
        tab = self.ribbon.add_tab("Page Layout")

        setup = tab.add_group("Page Setup")
        setup.set_dialog_launcher(self._show_page_setup_dialog)
        margin_menu = QMenu(self)
        for label, millimetres in (("Narrow", 6.4), ("Normal", 12.7), ("Wide", 19.1)):
            margin_menu.addAction(label, lambda checked=False, m=millimetres: self._set_margin(m))
        orientation_menu = QMenu(self)
        orientation_menu.addAction("Portrait", lambda checked=False: self._set_orientation(False))
        orientation_menu.addAction("Landscape", lambda checked=False: self._set_orientation(True))
        size_menu = QMenu(self)
        for label in ("A4", "Letter", "Legal"):
            size_menu.addAction(label, lambda checked=False, l=label: self._set_paper_size(l))
        break_menu = QMenu(self)
        break_menu.addAction("Insert Row Break", self._insert_page_break)
        break_menu.addAction("Clear All Breaks", self._clear_page_breaks)

        setup_col = setup.add_column()
        setup.add_button_to(setup_col, "Margins", "margins", menu=margin_menu)
        setup.add_button_to(setup_col, "Orientation", "orientation", menu=orientation_menu)
        setup_row = setup.add_sub_row(setup_col)
        setup.add_button_to(setup_row, "Size", "paper-size", on_click=self._show_page_setup_dialog)
        setup.add_button_to(setup_row, "Breaks", "page-break", on_click=self._insert_page_break)

        options = tab.add_group("Sheet Options")
        options.add_button("Gridline\nDisplay", "gridlines", large=True, on_click=self._toggle_gridlines)
        options_col = options.add_column()
        options.add_button_to(options_col, "View", "view-normal",
                              on_click=lambda: self._set_view_mode("normal"))
        options.add_button_to(options_col, "Print Title\nRows", "text:1", on_click=self._set_title_rows)

    def _build_formulas_tab(self) -> None:
        tab = self.ribbon.add_tab("Formulas")

        library = tab.add_group("Function Library")
        function_menu = QMenu(self)
        for name, signature in (
            ("SUM", "SUM(number1, [number2], ...)"),
            ("AVERAGE", "AVERAGE(number1, [number2], ...)"),
            ("COUNT", "COUNT(value1, [value2], ...)"),
            ("MIN", "MIN(number1, [number2], ...)"),
            ("MAX", "MAX(number1, [number2], ...)"),
            ("IF", "IF(logical_test, value_if_true, value_if_false)"),
            ("CONCAT", "CONCAT(text1, [text2], ...)"),
        ):
            function_menu.addAction(signature, lambda checked=False, f=name: self._insert_function(f))
        library.add_split_button("Insert\nFunction", "function", function_menu, large=True,
                                 on_click=self._show_function_dialog)
        library_col = library.add_column()
        library.add_button_to(library_col, "AutoSum", "text:Σ", on_click=self._insert_autosum)

        names = tab.add_group("Defined Names")
        names.add_button("Define\nName", "name", large=True, on_click=self._name_selection)
        names_col = names.add_column()
        names.add_button_to(names_col, "Go to\nName", "search", on_click=self._goto_name)

        audit = tab.add_group("Formula Auditing")
        audit.add_button("Explain\nFormula", "text:fx", large=True, on_click=self._ai_explain_formula)
        audit_col = audit.add_column()
        audit.add_button_to(audit_col, "Show\nFormulas", "text:=f", on_click=self._toggle_show_formulas)
        audit.add_button_to(audit_col, "Watch\nSelection", "search", on_click=self._describe_selection)

    def _build_data_tab(self) -> None:
        tab = self.ribbon.add_tab("Data")

        sort_filter = tab.add_group("Sort & Filter")
        sort_filter.add_button("Sort A to Z", "sort-az", large=True,
                               on_click=lambda: self._sort_column(True))
        sf_col = sort_filter.add_column()
        sort_filter.add_button_to(sf_col, "Sort Z to A", "sort-za",
                                  on_click=lambda: self._sort_column(False))
        sort_filter.add_button_to(sf_col, "Filter", "filter", on_click=self._toggle_filter)

        tools = tab.add_group("Data Tools")
        tools.add_button("Text to\nColumns", "text:abc", large=True, on_click=self._text_to_columns)
        tools_col = tools.add_column()
        tools.add_button_to(tools_col, "Remove\nDuplicates", "remove", on_click=self._remove_duplicates)
        tools.add_button_to(tools_col, "Fill Down", "text:↓", on_click=self._fill_down)

    def _build_view_tab(self) -> None:
        tab = self.ribbon.add_tab("View")

        views = tab.add_group("Workbook Views")
        views.add_button("Page Break\nPreview", "view-page-break", large=True,
                         on_click=lambda: self._set_view_mode("page-break"))
        views_col = views.add_column()
        views.add_button_to(views_col, "Normal", "view-normal",
                            on_click=lambda: self._set_view_mode("normal"))
        views.add_button_to(views_col, "Page Layout", "view-page-layout",
                            on_click=lambda: self._set_view_mode("page-layout"))

        show = tab.add_group("Show")
        self.gridlines_btn = show.add_button("Gridlines", "gridlines", large=True,
                                             on_click=self._toggle_gridlines)
        self.gridlines_btn.setCheckable(True)
        self.gridlines_btn.setChecked(True)
        show_col = show.add_column()
        self.formula_bar_btn = show.add_button_to(show_col, "Formula Bar", "text:fx",
                                                  on_click=self._toggle_formula_bar)
        self.formula_bar_btn.setCheckable(True)
        self.formula_bar_btn.setChecked(True)

        zoom = tab.add_group("Zoom")
        zoom.add_button("100%", "zoom", large=True, on_click=self._reset_zoom)
        zoom_col = zoom.add_column()
        zoom.add_button_to(zoom_col, "Zoom In", "zoom-in", on_click=lambda: self._step_zoom(10))
        zoom.add_button_to(zoom_col, "Zoom Out", "zoom-out", on_click=lambda: self._step_zoom(-10))

    def _build_ai_tab(self) -> None:
        tab = self.ribbon.add_tab("AI Assist")
        copilot = tab.add_group("Formula Copilot")
        copilot.add_button("Formula\nGenerator", "ai", large=True, on_click=self._ai_generate_formula)
        copilot_col = copilot.add_column()
        copilot.add_button_to(copilot_col, "Explain\nFormula", "text:fx",
                              on_click=self._ai_explain_formula)

    # ------------------------------------------------------- worksheet tabs #

    def _on_add_sheet(self) -> None:
        num = len(self.sheets) + 1
        while f"Sheet{num}" in self.sheets:
            num += 1
        name = f"Sheet{num}"
        self.sheets[name] = Sheet(name)
        self.tab_bar.addTab(name)
        self.tab_bar.setCurrentIndex(self.tab_bar.count() - 1)

    def _on_sheet_tab_switched(self, index: int) -> None:
        name = self.tab_bar.tabText(index)
        if name not in self.sheets:
            return
        # Resetting the model drops the active cell, so carry it across like Excel.
        previous = self._current()
        anchor = (previous.row(), previous.column()) if previous.isValid() else (0, 0)
        self.active_sheet_name = name
        self.model.beginResetModel()
        self.model.sheet = self.sheets[name]
        self.model.endResetModel()
        self.sheet_widget.grid.setCurrentIndex(self.model.index(*anchor))
        if hasattr(self, "font_combo"):
            self._sync_ribbon_to_cell()
        self._update_status_position()

    def _on_rename_sheet(self, index: int) -> None:
        if index < 0:
            return
        old = self.tab_bar.tabText(index)
        name, ok = QInputDialog.getText(self, "Rename Sheet", "Sheet name:", text=old)
        name = name.strip()[:31]
        if not ok or not name or name == old or name in self.sheets:
            return
        sheet = self.sheets.pop(old)
        sheet.name = name
        self.sheets[name] = sheet
        if self.active_sheet_name == old:
            self.active_sheet_name = name
        self.tab_bar.blockSignals(True)
        self.tab_bar.setTabText(index, name)
        self.tab_bar.blockSignals(False)
        self._update_status_position()

    def _delete_current_sheet(self) -> None:
        if len(self.sheets) <= 1:
            QMessageBox.information(self, "Delete Sheet", "A workbook must keep one visible sheet.")
            return
        name = self.active_sheet_name
        reply = QMessageBox.question(self, "Delete Sheet", f"Delete “{name}” and all of its data?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
        index = self.tab_bar.currentIndex()
        self.sheets.pop(name, None)
        self.tab_bar.blockSignals(True)
        self.tab_bar.removeTab(index)
        self.tab_bar.blockSignals(False)
        self.tab_bar.setCurrentIndex(max(0, index - 1))
        self._on_sheet_tab_switched(self.tab_bar.currentIndex())

    # ---------------------------------------------------------- cell access #

    def _selected_indexes(self) -> List[QModelIndex]:
        return self.sheet_widget.grid.selectedIndexes()

    def _current(self) -> QModelIndex:
        return self.sheet_widget.grid.currentIndex()

    def _format_of_current(self) -> CellFormat:
        idx = self._current()
        if idx.isValid():
            return self.model.sheet.get_format(idx.row(), idx.column())
        return CellFormat()

    def _apply_to_selection(self, mutate, roles: Optional[Sequence[int]] = None) -> int:
        """Run *mutate* over every selected cell's live format, then refresh."""
        indexes = self._selected_indexes()
        for idx in indexes:
            mutate(self.model.sheet.ensure_format(idx.row(), idx.column()))
        self.model.refresh_cells(indexes, roles)
        return len(indexes)

    def _sync_ribbon_to_cell(self) -> None:
        """Show the active cell's formatting in the ribbon's controls."""
        fmt = self._format_of_current()
        for widget, value in ((self.font_combo, fmt.font_family),
                              (self.format_combo, self._format_label(fmt.number_format))):
            widget.blockSignals(True)
            widget.setCurrentText(value)
            widget.blockSignals(False)
        self.size_spin.blockSignals(True)
        self.size_spin.setValue(fmt.font_size)
        self.size_spin.blockSignals(False)

    @staticmethod
    def _format_label(format_string: str) -> str:
        for label, value in NUMBER_FORMATS.items():
            if value == format_string:
                return label
        return "General"

    # ------------------------------------------------------------------- font #

    def _set_font_family(self) -> None:
        family = self.font_combo.currentText()
        self._apply_to_selection(lambda fmt: setattr(fmt, "font_family", family))

    def _set_font_size(self) -> None:
        size = self.size_spin.value()
        self._apply_to_selection(lambda fmt: setattr(fmt, "font_size", size))

    def _toggle_font(self, key: str) -> None:
        if self._apply_to_selection(lambda fmt: setattr(fmt, key, not getattr(fmt, key))):
            self._sync_ribbon_to_cell()

    def _choose_text_color(self) -> None:
        color = QColorDialog.getColor(Qt.GlobalColor.black, self, "Font Color")
        if color.isValid():
            self._apply_to_selection(lambda fmt: setattr(fmt, "text_color", color.name()))

    def _choose_fill_color(self) -> None:
        color = QColorDialog.getColor(Qt.GlobalColor.white, self, "Fill Color")
        if color.isValid():
            self._apply_to_selection(lambda fmt: setattr(fmt, "bg_color", color.name()))

    def _copy_format(self) -> None:
        """Format Painter: copy the active cell's format over the rest of the range."""
        source = self._current()
        if not source.isValid():
            return
        template = self.model.sheet.get_format(source.row(), source.column())
        names = [f.name for f in fields(CellFormat)]
        count = 0
        for idx in self._selected_indexes():
            if (idx.row(), idx.column()) == (source.row(), source.column()):
                continue
            target = self.model.sheet.ensure_format(idx.row(), idx.column())
            for name in names:
                setattr(target, name, getattr(template, name))
            count += 1
        self.model.refresh_cells(self._selected_indexes())
        if count:
            self.status_bar.showMessage(
                f"Format Painter copied {col_to_letter(source.column())}{source.row() + 1} "
                f"formatting to {count} cells.", 5000)
        else:
            self.status_bar.showMessage("Select the cells to paint, then click Format Painter.", 5000)

    def _show_format_cells_dialog(self) -> None:
        fmt = self._format_of_current()
        choices = [f"{label} format" for label in NUMBER_FORMATS] + [
            "Bold", "Italic", "Underline", "Wrap Text", "No Fill", "No Borders", "Reset"]
        item, ok = QInputDialog.getItem(
            self, "Format Cells", f"Category (current: {self._format_label(fmt.number_format)}):",
            choices, 0, False)
        if not ok or not item:
            return
        label = item.replace(" format", "")
        if label in NUMBER_FORMATS:
            self._apply_format_key(label)
        elif label == "No Fill":
            self._apply_to_selection(lambda f: setattr(f, "bg_color", None))
        elif label == "No Borders":
            self._apply_to_selection(lambda f: setattr(f, "border", "none"))
        elif label == "Reset":
            defaults = CellFormat()
            names = [f.name for f in fields(CellFormat)]
            self._apply_to_selection(lambda f: [setattr(f, n, getattr(defaults, n)) for n in names])
        else:
            key = {"Bold": "bold", "Italic": "italic", "Underline": "underline",
                   "Wrap Text": "wrap_text"}[label]
            self._apply_to_selection(lambda f: setattr(f, key, not getattr(f, key)))

    # -------------------------------------------------------------- alignment #

    HORIZONTAL = {"align left": Qt.AlignmentFlag.AlignLeft,
                  "center": Qt.AlignmentFlag.AlignHCenter,
                  "align right": Qt.AlignmentFlag.AlignRight,
                  "left": Qt.AlignmentFlag.AlignLeft,
                  "right": Qt.AlignmentFlag.AlignRight}
    VERTICAL = {"top": Qt.AlignmentFlag.AlignTop,
                "middle": Qt.AlignmentFlag.AlignVCenter,
                "bottom": Qt.AlignmentFlag.AlignBottom}

    def _set_alignment(self, kind: str) -> None:
        flag = self.HORIZONTAL.get(kind) or self.VERTICAL.get(kind)
        if flag is None:
            return
        mask = (Qt.AlignmentFlag.AlignHorizontal_Mask if flag in self.HORIZONTAL.values()
                else Qt.AlignmentFlag.AlignVertical_Mask)

        def apply(fmt: CellFormat) -> None:
            fmt.alignment = (fmt.alignment & ~mask) | flag

        self._apply_to_selection(apply, [Qt.ItemDataRole.TextAlignmentRole])

    def _toggle_wrap_text(self) -> None:
        count = self._apply_to_selection(lambda fmt: setattr(fmt, "wrap_text", not fmt.wrap_text))
        self.status_bar.showMessage(f"Text wraps in {count} cells." if count
                                    else "Select cells to wrap their text.", 4000)

    # ----------------------------------------------------------- number formats #

    def _apply_format_key(self, label: str) -> None:
        self._set_number_format(NUMBER_FORMATS.get(label, ""))
        self.status_bar.showMessage(f"Number format: {label}", 3000)

    def _set_number_format(self, format_string: str) -> None:
        self._apply_to_selection(lambda fmt: setattr(fmt, "number_format", format_string),
                                 [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.TextAlignmentRole])

    def _apply_number_format(self, fmt_key: str) -> None:
        """Compatibility shim: takes a legacy key ("currency") or an Excel label."""
        for label in NUMBER_FORMATS:
            if label.lower() == fmt_key.lower():
                self._apply_format_key(label)
                return
        self._set_number_format(fmt_key)

    def _step_decimals(self, delta: int) -> None:
        current = self._format_of_current().number_format or "#,##0.00"
        head, _, tail = current.partition(".")
        decimals = len(tail) if tail[:1].isdigit() else 2
        decimals = max(0, min(6, decimals + delta))
        pattern = head if decimals == 0 else f"{head}.{'0' * decimals}"
        if "%" in current:
            pattern += "%"
        self._set_number_format(pattern)
        self.format_combo.blockSignals(True)
        self.format_combo.setCurrentText(self._format_label(pattern))
        self.format_combo.blockSignals(False)

    # ----------------------------------------------------------------- styles #

    CELL_STYLES = {
        "heading": ("#4472C4", "#FFFFFF", True),
        "good": ("#C6EFCE", "#006100", False),
        "bad": ("#FFC7CE", "#9C0006", False),
        "neutral": ("#FFEB9C", "#9C6500", False),
        "total": ("#F2F2F2", "#000000", True),
        "accent": ("#9DC3E6", "#1F4E78", False),
    }

    def _apply_cell_style(self, style_key: str) -> None:
        style = self.CELL_STYLES.get(style_key)
        if not style:
            return
        background, foreground, bold = style

        def apply(fmt: CellFormat) -> None:
            fmt.bg_color, fmt.text_color, fmt.bold = background, foreground, bold

        self._apply_to_selection(apply)

    def _apply_border(self, border_type: str) -> None:
        """Store the choice on the cell format; the delegate paints the lines."""
        count = self._apply_to_selection(lambda fmt: setattr(fmt, "border", border_type),
                                        [self.model.FormatRole])
        self.status_bar.showMessage(f"{border_type.capitalize()} borders on {count} cells."
                                    if count else "Select cells to border.", 4000)

    def _format_as_table(self) -> None:
        indexes = self._selected_indexes()
        if not indexes:
            self.status_bar.showMessage("Select a range to format as a table.", 4000)
            return
        top = min(i.row() for i in indexes)
        left = min(i.column() for i in indexes)
        for idx in indexes:
            fmt = self.model.sheet.ensure_format(idx.row(), idx.column())
            fmt.border = "all"
            if idx.row() == top:
                fmt.bold = True
                fmt.bg_color, fmt.text_color = "#1F4E78", "#FFFFFF"
            elif (idx.column() - left) % 2 == 0:
                fmt.bg_color = "#DCE6F1"
            else:
                fmt.bg_color = "#FFFFFF"
        self.model.refresh_cells(indexes)
        rows = len({i.row() for i in indexes})
        cols = len({i.column() for i in indexes})
        self.status_bar.showMessage(f"Formatted the selection as a table: {rows} x {cols} cells.", 5000)

    # ------------------------------------------------- rows, columns and cells #

    def _insert_object(self) -> None:
        item, ok = QInputDialog.getItem(self, "Insert", "Insert:",
                                        ["Rows Above", "Columns to the Left", "New Sheet"],
                                        0, False)
        if not ok:
            return
        {"Rows Above": self._insert_row,
         "Columns to the Left": self._insert_column,
         "New Sheet": self._on_add_sheet}[item]()

    def _insert_row(self) -> None:
        idx = self._current()
        if idx.isValid():
            self.model.insert_row_at(idx.row())
            self.status_bar.showMessage(f"Inserted a row above row {idx.row() + 1}.", 3000)

    def _delete_row(self) -> None:
        idx = self._current()
        if idx.isValid():
            self.model.delete_row_at(idx.row())

    def _insert_column(self) -> None:
        idx = self._current()
        if idx.isValid():
            self.model.insert_column_at(idx.column())

    def _delete_column(self) -> None:
        idx = self._current()
        if idx.isValid():
            self.model.delete_column_at(idx.column())

    def _clear_selected_cells(self) -> None:
        indexes = self._selected_indexes()
        for idx in indexes:
            self.model.sheet.clear_cell(idx.row(), idx.column())
        self.model.refresh_cells(indexes)
        self.status_bar.showMessage(f"Cleared {len(indexes)} cells.", 3000)

    def _fill_down(self) -> None:
        """Ctrl+D: copy the top row of the selection over the rows below it."""
        indexes = self._selected_indexes()
        if len(indexes) < 2:
            self.status_bar.showMessage("Select the source row and the rows below it.", 4000)
            return
        sheet = self.model.sheet
        rows = sorted({i.row() for i in indexes})
        columns = sorted({i.column() for i in indexes})
        for col in columns:
            raw = sheet.get_cell_raw(rows[0], col)
            fmt = sheet.get_format(rows[0], col)
            for row in rows[1:]:
                sheet.set_cell(row, col, raw)
                target = sheet.ensure_format(row, col)
                target.number_format = fmt.number_format
                target.border = fmt.border
                target.bg_color = fmt.bg_color
        self.model.refresh_cells(indexes)
        self.status_bar.showMessage(f"Filled {len(rows) - 1} rows down.", 4000)

    def _insert_table(self, rows: int, cols: int) -> None:
        """Drop a bordered, bold-headed rows x cols block at the active cell."""
        idx = self._current()
        if not idx.isValid():
            self.status_bar.showMessage("Pick the table's top-left cell first.", 4000)
            return
        sheet = self.model.sheet
        for dr in range(rows):
            for dc in range(cols):
                fmt = sheet.ensure_format(idx.row() + dr, idx.column() + dc)
                fmt.border = "all"
                if dr == 0:
                    fmt.bold = True
                    fmt.bg_color = "#1F4E78"
        self.model.refresh_all()
        self.status_bar.showMessage(f"Inserted a {rows} x {cols} table at "
                                    f"{col_to_letter(idx.column())}{idx.row() + 1}.", 4000)

    # -------------------------------------------------------- clipboard, sort #

    def _paste(self) -> None:
        written = self.sheet_widget.grid.paste_clipboard()
        self.status_bar.showMessage(f"Pasted {written} cells." if written
                                    else "The clipboard has no text to paste.", 4000)

    def _copy(self) -> None:
        text = self.sheet_widget.grid.copy_selection()
        self.status_bar.showMessage(f"Copied {len(text.splitlines())} row(s) to the clipboard."
                                    if text else "Select cells to copy.", 4000)

    def _cut(self) -> None:
        text = self.sheet_widget.grid.copy_selection(cut=True)
        self.status_bar.showMessage(f"Cut {len(text.splitlines())} row(s)." if text
                                    else "Select cells to cut.", 4000)

    def _sort_column(self, ascending: bool) -> None:
        """Sort the selected rows on their left-most selected column."""
        indexes = self._selected_indexes()
        if not indexes:
            self.status_bar.showMessage("Select the cells to sort.", 4000)
            return
        sheet = self.model.sheet
        left = min(i.column() for i in indexes)
        right = max(i.column() for i in indexes)
        rows = sorted({i.row() for i in indexes})
        blocks = {r: [sheet.get_cell_raw(r, c) for c in range(left, right + 1)] for r in rows}
        ordered = sorted(rows, key=lambda r: self._sort_key(blocks[r][0]), reverse=not ascending)
        for destination, row in zip(rows, ordered):
            for offset, raw in enumerate(blocks[row]):
                sheet.set_cell(destination, left + offset, raw)
        self.model.refresh_cells([self.model.index(r, c) for r in rows
                                  for c in range(left, right + 1)])
        direction = "A to Z" if ascending else "Z to A"
        self.status_bar.showMessage(f"Sorted {len(rows)} rows {direction} by "
                                    f"column {col_to_letter(left)}.", 5000)

    @staticmethod
    def _sort_key(raw: str):
        try:
            return (0, float(str(raw).replace(",", "").replace("$", "").rstrip("%")))
        except (TypeError, ValueError):
            return (1, str(raw).lower())

    def _toggle_filter(self) -> None:
        self._filter_active = not self._filter_active
        self.model.refresh_all()
        self.status_bar.showMessage("Filter buttons shown on the header row." if self._filter_active
                                    else "Filter removed.", 4000)

    def _text_to_columns(self) -> None:
        """Split the active cell's text across the row on a chosen delimiter."""
        idx = self._current()
        if not idx.isValid():
            return
        raw = self.model.sheet.get_cell_raw(idx.row(), idx.column())
        if not raw:
            self.status_bar.showMessage("Select a cell containing delimited text.", 4000)
            return
        delimiter, ok = QInputDialog.getItem(self, "Convert Text to Columns", "Delimiter:",
                                             [",", ";", "\t", " "], 0, False)
        if not ok:
            return
        parts = [p.strip() for p in raw.split(delimiter)]
        for offset, part in enumerate(parts):
            self.model.sheet.set_cell(idx.row(), idx.column() + offset, part)
        self.model.refresh_all()
        self.status_bar.showMessage(f"Split the cell into {len(parts)} columns.", 4000)

    def _remove_duplicates(self) -> None:
        indexes = self._selected_indexes()
        if not indexes:
            self.status_bar.showMessage("Select the rows to deduplicate.", 4000)
            return
        sheet = self.model.sheet
        col = min(i.column() for i in indexes)
        seen: set = set()
        removed = 0
        for row in sorted({i.row() for i in indexes}, reverse=True):
            value = sheet.get_cell_raw(row, col)
            if value and value in seen:
                self.model.delete_row_at(row)
                removed += 1
            else:
                seen.add(value)
        self.status_bar.showMessage(f"Removed {removed} duplicate rows.", 5000)

    # --------------------------------------------------------------------------- #

    def _insert_autosum(self) -> None:
        idx = self._current()
        if not idx.isValid():
            return
        letter = col_to_letter(idx.column())
        if idx.row() > 0:
            formula = f"=SUM({letter}1:{letter}{idx.row()})"
        else:
            columns = sorted({i.column() for i in self._selected_indexes()}) or [idx.column()]
            formula = f"=SUM({letter}1:{col_to_letter(columns[-1])}1)"
        self.model.setData(idx, formula, Qt.ItemDataRole.EditRole)
        self.sheet_widget.formula_bar.set_cell(idx.row(), idx.column(), formula)

    def _insert_function(self, name: str) -> None:
        idx = self._current()
        if not idx.isValid():
            return
        self.model.setData(idx, f"={name}()", Qt.ItemDataRole.EditRole)
        self.sheet_widget.formula_bar.formula_input.setFocus()
        self.status_bar.showMessage(f"Inserted ={name}() — type the range between the brackets.", 5000)

    def _show_function_dialog(self) -> None:
        functions = ["SUM", "AVERAGE", "COUNT", "MIN", "MAX", "IF", "CONCAT"]
        item, ok = QInputDialog.getItem(self, "Insert Function", "Select function:", functions, 0, False)
        if ok and item:
            self._insert_function(item)

    def _toggle_show_formulas(self) -> None:
        self._show_formulas = not self._show_formulas
        self.model.show_formulas = self._show_formulas
        self.model.refresh_all()
        self.status_bar.showMessage("Cells now show their formulas." if self._show_formulas
                                    else "Cells show their results.", 4000)

    def _name_selection(self) -> None:
        ref = self._selection_reference()
        if not ref:
            self.status_bar.showMessage("Select the cells to name.", 4000)
            return
        name, ok = QInputDialog.getText(self, "Define Name", f"Name for {ref}:")
        name = name.strip().replace(" ", "_")
        if ok and name:
            self._named_ranges[name] = ref
            self.status_bar.showMessage(f"Defined {name} = {ref}", 5000)

    def _goto_name(self) -> None:
        if not self._named_ranges:
            self.status_bar.showMessage("No named ranges yet — use Define Name first.", 4000)
            return
        name, ok = QInputDialog.getItem(self, "Go To", "Named range:",
                                        list(self._named_ranges), 0, False)
        if not ok:
            return
        parsed = parse_cell_ref(self._named_ranges[name].split(":")[0])
        if parsed:
            row, col = parsed
            self.sheet_widget.grid.setCurrentIndex(self.model.index(row, col))

    def _describe_selection(self) -> None:
        ref = self._selection_reference()
        if not ref:
            self.status_bar.showMessage("Select cells to see their reference.", 4000)
            return
        self.status_bar.showMessage(f"{ref}  ·  {len(self._selected_indexes())} cells selected", 6000)

    def _selection_reference(self) -> str:
        indexes = self._selected_indexes()
        if not indexes:
            return ""
        top, left = min(i.row() for i in indexes), min(i.column() for i in indexes)
        bottom, right = max(i.row() for i in indexes), max(i.column() for i in indexes)
        start = f"{col_to_letter(left)}{top + 1}"
        return start if (top, left) == (bottom, right) else f"{start}:{col_to_letter(right)}{bottom + 1}"

    # --------------------------------------------------- page layout and print #

    def _set_margin(self, millimetres: float) -> None:
        self.page_margin_mm = millimetres
        self.sheet_widget.grid.set_page_margins(millimetres)
        self._apply_page_geometry()
        self.status_bar.showMessage(f"Page margins set to {millimetres:g} mm.", 4000)

    def _set_orientation(self, landscape: bool) -> None:
        self.landscape = landscape
        self._apply_page_geometry()
        self.status_bar.showMessage("Pages are landscape." if landscape else "Pages are portrait.", 4000)

    def _set_paper_size(self, size: str) -> None:
        self.paper_size = size
        self._apply_page_geometry()
        self.status_bar.showMessage(f"Paper size set to {size}.", 4000)

    #: Sheet size in millimetres, portrait.
    PAPER_SIZES_MM = {"A3": (297, 420), "A4": (210, 297), "A5": (148, 210),
                      "Letter": (216, 279), "Legal": (216, 356)}

    #: Dots per inch a written-out PDF is drawn at. A printer gets
    #: printing.PRINT_DPI instead, because it asks for the detail.
    PDF_DPI = 150

    def _apply_page_geometry(self) -> None:
        """Hand the paper and margins to the grid's Page Layout / Break views."""
        width, height = self.PAPER_SIZES_MM.get(self.paper_size, self.PAPER_SIZES_MM["A4"])
        if self.landscape:
            width, height = height, width
        self.sheet_widget.grid.set_page_size(width, height)

    def _insert_page_break(self) -> None:
        idx = self._current()
        if not idx.isValid() or idx.row() in self._page_breaks:
            return
        self._page_breaks.append(idx.row())
        self.sheet_widget.grid.set_page_breaks(self._page_breaks)
        self._set_view_mode("page-break")
        self.status_bar.showMessage(f"Manual page break above row {idx.row() + 1}.", 4000)

    def _clear_page_breaks(self) -> None:
        self._page_breaks.clear()
        self.sheet_widget.grid.set_page_breaks(self._page_breaks)
        self.status_bar.showMessage("Manual page breaks cleared.", 4000)

    def _set_title_rows(self) -> None:
        idx = self._current()
        if not idx.isValid():
            return
        self._title_rows = idx.row()
        self.status_bar.showMessage(f"Row {idx.row() + 1} repeats at the top of every page.", 5000)

    def _show_page_setup_dialog(self) -> None:
        info = (f"Paper: {self.paper_size}\n"
                f"Orientation: {'Landscape' if self.landscape else 'Portrait'}\n"
                f"Margins: {self.page_margin_mm:g} mm\n"
                f"Manual page breaks: {len(self._page_breaks)}\n"
                f"Print title row: {'none' if self._title_rows is None else self._title_rows + 1}")
        QMessageBox.information(self, "Page Setup", info)

    # -------------------------------------------------------------------- view #

    def _set_view_mode(self, mode: str) -> None:
        self.sheet_widget.grid.set_view_mode(mode)
        self.status_bar.select_view_mode(mode)
        labels = {"normal": "Normal", "page-layout": "Page Layout",
                  "page-break": "Page Break Preview"}
        self.status_bar.showMessage(f"{labels.get(mode, 'Normal')} view.", 3000)

    def _toggle_gridlines(self) -> None:
        grid = self.sheet_widget.grid
        grid.setShowGrid(not grid.showGrid())
        self.gridlines_btn.setChecked(grid.showGrid())
        grid.viewport().update()

    def _toggle_formula_bar(self) -> None:
        bar = self.sheet_widget.formula_bar
        bar.setVisible(not bar.isVisible())
        self.formula_bar_btn.setChecked(bar.isVisible())

    def _step_zoom(self, delta: int) -> None:
        self.status_bar.set_zoom(self.status_bar.zoom_percent() + delta)

    def _reset_zoom(self) -> None:
        self.status_bar.set_zoom(100)

    # ------------------------------------------------------------------ charts #

    def _numeric_selection(self) -> List[float]:
        """The numbers behind the current selection, computed cells included."""
        return self._selection_values()

    def _insert_chart(self, kind: str) -> None:
        """Plot the selected numbers in a chart window."""
        values = self._numeric_selection()
        if len(values) < 2:
            self.status_bar.showMessage("Select at least two numeric cells to chart.", 4000)
            return
        canvas = ChartCanvas(kind, values, self)
        canvas.setWindowTitle(f"{kind} Chart of {self.active_sheet_name}")
        canvas.resize(560, 360)
        self._chart_windows.append(canvas)
        canvas.show()
        self.status_bar.showMessage(f"Plotted {len(values)} values as a {kind.lower()} chart.", 5000)

    # ------------------------------------------------------------------ status #

    def _on_selection_stats_changed(self, avg: float, count: int, total: float) -> None:
        if count > 1:
            values = self._selection_values()
            self.status_bar.set_stats(
                f"Average: {avg:,.2f}    Count: {count}    Sum: {total:,.2f}    "
                f"Min: {min(values):,.2f}    Max: {max(values):,.2f}")
        elif count == 1:
            self.status_bar.set_stats(f"Sum: {total:,.2f}    Count: 1")
        else:
            self.status_bar.set_stats("")

    def _selection_values(self) -> List[float]:
        out: List[float] = []
        for idx in self._selected_indexes():
            raw = self.model.sheet.get_cell_display(idx.row(), idx.column())
            try:
                out.append(float(str(raw).replace(",", "").replace("$", "").rstrip("%")))
            except (TypeError, ValueError):
                continue
        return out

    def _update_status_position(self) -> None:
        idx = self._current()
        if not idx.isValid():
            idx = self.model.index(0, 0)
        self.status_bar.set_info(
            f"{col_to_letter(idx.column())}{idx.row() + 1} on {self.active_sheet_name}")
        if hasattr(self, "font_combo"):
            self._sync_ribbon_to_cell()

    # ------------------------------------------------------------- documents #

    def on_new(self) -> None:
        self.sheets = {"Sheet1": Sheet("Sheet1")}
        self.tab_bar.blockSignals(True)
        while self.tab_bar.count() > 0:
            self.tab_bar.removeTab(0)
        self.tab_bar.addTab("Sheet1")
        self.tab_bar.blockSignals(False)
        self._on_sheet_tab_switched(0)
        self.current_filepath = None
        self._update_window_title()

    def on_open(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Spreadsheet", "", "Spreadsheets (*.xlsx *.ods *.csv);;All Files (*.*)"
        )
        if filepath:
            self.open_path(filepath)

    def open_path(self, filepath: str) -> bool:
        """Read a workbook from disk into this window, as the shell asks on start."""
        ext = os.path.splitext(filepath)[1].lower()
        loaded_sheets: Dict[str, Sheet] = {}

        if ext == ".xlsx":
            loaded_sheets = XlsxHandler.load(filepath)
        elif ext == ".ods":
            loaded_sheets = OdsHandler.load(filepath)
        elif ext == ".csv":
            sheet = Sheet("Sheet1")
            with open(filepath, "r", encoding="utf-8", errors="replace") as handle:
                for r_idx, row in enumerate(csv.reader(handle)):
                    for c_idx, val in enumerate(row):
                        sheet.set_cell(r_idx, c_idx, val)
            loaded_sheets = {"Sheet1": sheet}

        if not loaded_sheets:
            QMessageBox.critical(self, "Error", f"Failed to open spreadsheet: {filepath}")
            return False

        self.sheets = loaded_sheets
        self.tab_bar.blockSignals(True)
        while self.tab_bar.count() > 0:
            self.tab_bar.removeTab(0)
        for name in self.sheets:
            self.tab_bar.addTab(name)
        self.tab_bar.blockSignals(False)
        self._on_sheet_tab_switched(0)
        self.current_filepath = filepath
        self._update_window_title()
        self.status_bar.showMessage(f"Opened: {os.path.basename(filepath)}", 3000)
        return True

    def on_save(self) -> None:
        if self.current_filepath:
            self._save_to_path(self.current_filepath)
        else:
            self.on_save_as()

    def on_save_as(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Spreadsheet As", "Workbook.xlsx",
            "Excel Workbook (*.xlsx);;OpenDocument Spreadsheet (*.ods);;CSV (*.csv)"
        )
        if filepath:
            self._save_to_path(filepath)

    def _save_to_path(self, filepath: str) -> None:
        ext = os.path.splitext(filepath)[1].lower()
        success = False

        if ext == ".xlsx":
            success = XlsxHandler.save(filepath, self.sheets)
        elif ext == ".ods":
            success = OdsHandler.save(filepath, self.sheets)
        elif ext == ".csv":
            active_sheet = self.sheets.get(self.active_sheet_name)
            if active_sheet and active_sheet.cells:
                max_r = max(r for r, _ in active_sheet.cells.keys())
                max_c = max(c for _, c in active_sheet.cells.keys())
                with open(filepath, "w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    for r in range(max_r + 1):
                        writer.writerow([active_sheet.get_cell_display(r, c)
                                         for c in range(max_c + 1)])
            else:
                with open(filepath, "w", encoding="utf-8"):
                    pass
            success = True

        if success:
            self.current_filepath = filepath
            self._update_window_title()
            self.status_bar.showMessage(f"Saved: {os.path.basename(filepath)}", 3000)
        else:
            QMessageBox.critical(self, "Error", f"Failed to save spreadsheet to {filepath}")

    def _sheet_layout(self) -> QPageLayout:
        """The paper this sheet was set to, with its margins.

        Naming the sizes one by one left every sheet but A4, Letter and Legal
        arriving on an A4 page, so the sheet's own millimetres are used.
        """
        width, height = self.PAPER_SIZES_MM.get(self.paper_size,
                                                self.PAPER_SIZES_MM["A4"])
        return QPageLayout(
            QPageSize(QSizeF(width, height), QPageSize.Unit.Millimeter),
            QPageLayout.Orientation.Landscape if self.landscape
            else QPageLayout.Orientation.Portrait,
            QMarginsF(self.page_margin_mm, self.page_margin_mm,
                      self.page_margin_mm, self.page_margin_mm),
            QPageLayout.Unit.Millimeter)

    def _paint_pages(self, device, painter: QPainter) -> None:
        """Lay the grid over *device*'s paper, opening a sheet as it runs out."""
        self.sheet_widget.grid.print_to(
            painter, device.pageLayout().paintRectPixels(device.resolution()),
            device.newPage)

    def export_pdf(self, filepath: str) -> bool:
        """Write the grid to *filepath* on the paper the sheet was set to."""
        writer = QPdfWriter(filepath)
        writer.setPageLayout(self._sheet_layout())
        writer.setResolution(self.PDF_DPI)
        painter = QPainter(writer)
        if not painter.isActive():
            return False
        self._paint_pages(writer, painter)
        painter.end()
        return os.path.exists(filepath) and os.path.getsize(filepath) > 0

    def on_export_pdf(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Sheet to PDF", "Spreadsheet.pdf", "PDF Files (*.pdf)"
        )
        if not filepath:
            return

        if self.export_pdf(filepath):
            self.status_bar.showMessage(f"Exported PDF: {os.path.basename(filepath)}", 3000)
            QMessageBox.information(self, "PDF Export Complete", f"Successfully exported to:\n{filepath}")
        else:
            QMessageBox.critical(self, "Error", "Failed to export PDF.")

    # -------------------------------------------------------------- AI copilot #

    def _ai_generate_formula(self) -> None:
        prompt, ok = QInputDialog.getText(
            self, "AI Formula Generator", "Describe what you want to calculate:"
        )
        if not ok or not prompt.strip():
            return

        self.status_bar.showMessage("AI is generating formula...", 5000)
        system_p = "You are an expert spreadsheet formula creator. Return ONLY the Excel formula starting with =."
        self.ai_client.generate_async(
            prompt=prompt,
            system_prompt=system_p,
            on_success=self._on_ai_formula_generated,
            on_error=lambda err: QMessageBox.warning(self, "AI Notice", f"Ollama not reachable: {err}")
        )

    def _on_ai_formula_generated(self, formula: str) -> None:
        idx = self._current()
        if idx.isValid():
            self.model.setData(idx, formula.strip(), Qt.ItemDataRole.EditRole)
            QMessageBox.information(self, "Formula Inserted", f"Inserted formula: {formula.strip()}")

    def _ai_explain_formula(self) -> None:
        idx = self._current()
        if not idx.isValid():
            return
        raw = str(self.model.data(idx, Qt.ItemDataRole.EditRole) or "")
        if not raw.startswith("="):
            QMessageBox.information(self, "AI Assist", "Select a cell containing a formula first.")
            return

        self.status_bar.showMessage("AI is analyzing formula...", 5000)
        prompt = f"Explain what this spreadsheet formula does step by step:\n\n{raw}"
        self.ai_client.generate_async(
            prompt=prompt,
            on_success=lambda res: QMessageBox.information(self, f"Formula Explanation ({raw})", res),
            on_error=lambda err: QMessageBox.warning(self, "AI Notice", f"Ollama not reachable: {err}")
        )


class ChartCanvas(QWidget):
    """A hand-drawn bar / line / pie chart of a selected range of numbers."""

    PALETTE = ("#217346", "#4472C4", "#C43E1C", "#FFC000", "#7030A0",
               "#00B0F0", "#808080", "#70AD47", "#ED7D31", "#264478")

    def __init__(self, kind: str, values: Sequence[float], parent: Optional[QWidget] = None):
        super().__init__(parent, Qt.WindowType.Window)
        self.kind = kind
        self.values = list(values)
        self.setStyleSheet("background-color: #FFFFFF;")

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width, height = self.width(), self.height()
        top, footer, left, right = 20, 34, 48, width - 16
        plot = max(20, height - top - footer)
        span = max(max(self.values), 1.0)
        gap = (right - left) / len(self.values)

        painter.setPen(QPen(QColor("#D1D5DB"), 1))
        painter.drawLine(left, top, left, top + plot)
        painter.drawLine(left, top + plot, right, top + plot)
        for step in range(5):
            y = top + int(plot * step / 4)
            painter.setPen(QPen(QColor("#E5E7EB"), 1, Qt.PenStyle.DotLine))
            painter.drawLine(left, y, right, y)
            painter.setPen(QColor("#6B7280"))
            painter.drawText(4, y + 4, f"{span * (4 - step) / 4:g}")

        if self.kind == "Pie":
            total = sum(abs(v) for v in self.values) or 1.0
            side = min(plot, right - left) - 20
            area = QRectF(left, top, side, side)
            start_angle = 0
            for index, value in enumerate(self.values):
                sweep = int(round(360 * 16 * abs(value) / total))
                painter.setBrush(QColor(self.PALETTE[index % len(self.PALETTE)]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPie(area, start_angle, sweep)
                start_angle += sweep
        elif self.kind == "Line":
            painter.setPen(QPen(QColor(self.PALETTE[0]), 2))
            points = [QPointF(left + gap * (i + 0.5), top + plot * (1 - v / span))
                      for i, v in enumerate(self.values)]
            for a, b in zip(points, points[1:]):
                painter.drawLine(a, b)
            painter.setBrush(QColor(self.PALETTE[0]))
            painter.setPen(Qt.PenStyle.NoPen)
            for point in points:
                painter.drawEllipse(point, 3.5, 3.5)
        else:
            bar = gap * 0.62
            for index, value in enumerate(self.values):
                column = plot * value / span
                painter.setBrush(QColor(self.PALETTE[index % len(self.PALETTE)]))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(QRectF(left + gap * index + (gap - bar) / 2,
                                        top + plot - column, bar, column))

        painter.setPen(QColor("#6B7280"))
        for index in range(len(self.values)):
            painter.drawText(int(left + gap * index), height - 12, str(index + 1))
        painter.end()
