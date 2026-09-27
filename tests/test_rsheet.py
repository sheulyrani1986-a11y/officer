"""Tests for RSheet formula calculation, XLSX, and ODS serialization."""

import os
import tempfile
import pytest
from PySide6.QtCore import Qt, QItemSelection, QItemSelectionModel, QModelIndex
from PySide6.QtWidgets import QApplication
from officer.rsheet.model import (
    Sheet, SpreadsheetModel, format_number, NUMBER_FORMATS
)
from officer.rsheet.formula.parser import col_to_letter, letter_to_col, parse_cell_ref, parse_range_ref
from officer.rsheet.formula.evaluator import FormulaEvaluator
from officer.rsheet.io.xlsx_handler import XlsxHandler
from officer.rsheet.io.ods_handler import OdsHandler
from officer.rsheet.window import RSheetWindow



def test_coordinate_parsing():
    assert col_to_letter(0) == "A"
    assert col_to_letter(25) == "Z"
    assert col_to_letter(26) == "AA"
    assert col_to_letter(27) == "AB"

    assert letter_to_col("A") == 0
    assert letter_to_col("Z") == 25
    assert letter_to_col("AA") == 26
    assert letter_to_col("AB") == 27

    assert parse_cell_ref("B4") == (3, 1)
    assert parse_cell_ref("AA10") == (9, 26)

    cells = parse_range_ref("A1:B2")
    assert len(cells) == 4
    assert (0, 0) in cells and (1, 1) in cells


def test_formula_evaluation():
    sheet = Sheet("TestSheet")
    sheet.set_cell(0, 0, "10")   # A1
    sheet.set_cell(1, 0, "20")   # A2
    sheet.set_cell(2, 0, "30")   # A3

    # Direct math
    assert sheet.evaluator.evaluate("=A1 + A2") == 30
    assert sheet.evaluator.evaluate("=A3 * 2") == 60

    # Functions
    assert sheet.evaluator.evaluate("=SUM(A1:A3)") == 60
    assert sheet.evaluator.evaluate("=AVERAGE(A1:A3)") == 20
    assert sheet.evaluator.evaluate("=MIN(A1:A3)") == 10
    assert sheet.evaluator.evaluate("=MAX(A1:A3)") == 30
    assert sheet.evaluator.evaluate("=COUNT(A1:A3)") == 3

    # Logical IF
    assert sheet.evaluator.evaluate('=IF(A1 > 5, "Yes", "No")') == "Yes"
    assert sheet.evaluator.evaluate('=IF(A1 > 50, "Yes", "No")') == "No"


def test_xlsx_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx_path = os.path.join(tmpdir, "test.xlsx")

        sheet = Sheet("Finances")
        sheet.set_cell(0, 0, "Item")
        sheet.set_cell(0, 1, "Price")
        sheet.set_cell(1, 0, "Keyboard")
        sheet.set_cell(1, 1, "49.99")
        sheet.set_cell(2, 0, "Mouse")
        sheet.set_cell(2, 1, "25.00")

        saved = XlsxHandler.save(xlsx_path, {"Finances": sheet})
        assert saved is True
        assert os.path.exists(xlsx_path)

        loaded = XlsxHandler.load(xlsx_path)
        assert "Finances" in loaded
        loaded_sheet = loaded["Finances"]
        assert loaded_sheet.get_cell_raw(0, 0) == "Item"
        assert loaded_sheet.get_cell_raw(1, 0) == "Keyboard"
        assert float(loaded_sheet.get_cell_raw(1, 1)) == 49.99


def test_ods_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        ods_path = os.path.join(tmpdir, "test.ods")

        sheet = Sheet("Inventory")
        sheet.set_cell(0, 0, "Apples")
        sheet.set_cell(0, 1, "100")
        sheet.set_cell(1, 0, "Oranges")
        sheet.set_cell(1, 1, "250")

        saved = OdsHandler.save(ods_path, {"Inventory": sheet})
        assert saved is True
        assert os.path.exists(ods_path)

        loaded = OdsHandler.load(ods_path)
        assert "Inventory" in loaded
        loaded_sheet = loaded["Inventory"]
        assert loaded_sheet.get_cell_raw(0, 0) == "Apples"
        assert loaded_sheet.get_cell_raw(0, 1) == "100"


def test_rsheet_window():
    win = RSheetWindow()
    # Insert data via model
    idx = win.model.index(0, 0)
    win.model.setData(idx, "42", 2)
    assert win.model.sheet.get_cell_display(0, 0) == "42"
    win.close()


# --------------------------------------------------------------------- formats #

def test_number_formats_render_like_excel():
    assert format_number("1234.5", NUMBER_FORMATS["Number"]) == "1,234.50"
    assert format_number("1234.5", NUMBER_FORMATS["Currency"]) == "$1,234.50"
    assert format_number("0.125", NUMBER_FORMATS["Percentage"]) == "12.50%"
    assert format_number("1234567", NUMBER_FORMATS["Scientific"]) == "1.23E+06"
    assert format_number("45200", NUMBER_FORMATS["Date"]) == "10/01/2023"
    assert format_number("1234.5", NUMBER_FORMATS["Accounting"]) == "$ 1,234.50"
    # General and Text pass the value through, and non-numbers never break.
    assert format_number("42", NUMBER_FORMATS["General"]) == "42"
    assert format_number("42", NUMBER_FORMATS["Text"]) == "42"
    assert format_number("hello", NUMBER_FORMATS["Currency"]) == "hello"


def test_number_format_reaches_the_display_role():
    sheet = Sheet("Formats")
    sheet.set_cell(0, 0, "1234.5")
    sheet.ensure_format(0, 0).number_format = NUMBER_FORMATS["Currency"]
    model = SpreadsheetModel(sheet=sheet, rows=100, cols=10)
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == "$1,234.50"


def test_get_format_never_allocates_a_cell():
    sheet = Sheet("Sparse")
    assert sheet.get_format(9, 9).bold is False
    assert (9, 9) not in sheet.cells, "reading a format must not create the cell"

    sheet.ensure_format(9, 9).bold = True
    assert (9, 9) in sheet.cells
    assert sheet.get_format(9, 9).bold is True


# ---------------------------------------------------------------- structure #

def test_sheet_row_and_column_shifts_move_cells_and_formats():
    sheet = Sheet("Shifts")
    sheet.set_cell(1, 1, "here")
    sheet.ensure_format(1, 1).bold = True

    sheet.insert_row(1)
    assert sheet.get_cell_raw(2, 1) == "here"
    assert sheet.get_format(2, 1).bold is True

    sheet.delete_row(1)                               # removes the blank row again
    assert sheet.get_cell_raw(1, 1) == "here"

    sheet.insert_column(1)
    assert sheet.get_cell_raw(1, 2) == "here"
    sheet.delete_column(1)
    assert sheet.get_cell_raw(1, 1) == "here"
    sheet.delete_row(1)
    assert sheet.get_cell_raw(1, 1) == ""


def test_model_structural_ops_keep_row_and_column_count():
    model = SpreadsheetModel(sheet=Sheet("Ops"), rows=120, cols=30)
    model.sheet.set_cell(5, 5, "moved")

    model.insert_row_at(0)
    model.insert_column_at(0)
    assert model.rowCount() == 121 and model.columnCount() == 31
    assert model.sheet.get_cell_raw(6, 6) == "moved"

    model.delete_row_at(0)
    model.delete_column_at(0)
    assert model.rowCount() == 120 and model.columnCount() == 30
    assert model.sheet.get_cell_raw(5, 5) == "moved"

    # Excel refuses to shrink the grid below its default size.
    while model.rowCount() > model.MIN_ROWS:
        model.delete_row_at(0)
    model.delete_row_at(0)
    assert model.rowCount() == model.MIN_ROWS


def test_formula_result_and_show_formulas_toggle():
    sheet = Sheet("Calc")
    sheet.set_cell(0, 0, "2")
    sheet.set_cell(1, 0, "3")
    sheet.set_cell(2, 0, "=SUM(A1:A2)")
    model = SpreadsheetModel(sheet=sheet, rows=50, cols=10)
    index = model.index(2, 0)
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "5"
    assert model.data(index, Qt.ItemDataRole.EditRole) == "=SUM(A1:A2)"

    model.show_formulas = True
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "=SUM(A1:A2)"
    model.show_formulas = False
    assert model.data(index, Qt.ItemDataRole.DisplayRole) == "5"


# ------------------------------------------------------------------ grid view #

def _grid_window():
    win = RSheetWindow()
    return win, win.sheet_widget.grid, win.model


def test_grid_clipboard_round_trip():
    win, grid, model = _grid_window()
    try:
        for row in range(2):
            for col in range(2):
                model.setData(model.index(row, col), f"r{row}c{col}", Qt.ItemDataRole.EditRole)
        grid.setCurrentIndex(model.index(0, 0))
        grid.selectionModel().select(
            QItemSelection(model.index(0, 0), model.index(1, 1)),
            QItemSelectionModel.SelectionFlag.Select)
        assert grid.copy_selection() == "r0c0\tr0c1\nr1c0\tr1c1"

        grid.setCurrentIndex(model.index(4, 4))
        assert grid.paste_clipboard() == 4
        assert model.sheet.get_cell_raw(5, 5) == "r1c1"

        # Cut clears the source range after putting it on the clipboard.
        grid.setCurrentIndex(model.index(0, 0))
        grid.selectionModel().select(
            QItemSelection(model.index(0, 0), model.index(0, 1)),
            QItemSelectionModel.SelectionFlag.Select)
        grid.copy_selection(cut=True)
        assert model.sheet.get_cell_raw(0, 0) == ""
    finally:
        win.close()


def test_grid_zoom_scales_explicit_and_default_sections():
    win, grid, model = _grid_window()
    try:
        grid.setColumnWidth(0, 120)
        base_row = grid.rowHeight(0)
        grid.set_zoom(200)
        assert grid.zoom_factor() == 2.0
        assert grid.rowHeight(0) == base_row * 2
        assert grid.columnWidth(0) == 240, "a hand-sized column must zoom too"
        grid.set_zoom(100)
        assert grid.columnWidth(0) == 120
        assert grid.zoom() == 100
    finally:
        win.close()


def test_grid_view_modes_and_page_geometry():
    win, grid, model = _grid_window()
    try:
        assert grid.view_mode() == "normal"
        assert grid.showGrid() is True

        grid.set_view_mode("page-layout")
        assert grid.showGrid() is False, "Page Layout view prints without gridlines"
        grid.set_view_mode("normal")
        assert grid.showGrid() is True

        wide = grid._page_area_px()
        grid.set_page_size(210, 297)                   # A4 portrait
        assert grid._page_area_px() < wide
        assert grid._page_height_px() > grid._page_area_px()

        grid.set_page_margins(25.4)
        assert grid._page_area_px() == int((210 - 2 * 25.4) / 25.4 * 96)

        grid.set_page_breaks([3, 1, 3])
        assert grid._page_breaks == [1, 3], "breaks are stored sorted and de-duplicated"
    finally:
        win.close()


def test_range_edges_outline_only_the_outer_sides():
    win, grid, model = _grid_window()
    try:
        grid.setCurrentIndex(model.index(1, 1))
        grid.selectionModel().select(
            QItemSelection(model.index(1, 1), model.index(2, 2)),
            QItemSelectionModel.SelectionFlag.Select)
        edges = grid.range_edges(model.index(1, 1))
        assert "top" in edges and "left" in edges
        assert "bottom" not in edges and "right" not in edges
        inner = grid.range_edges(model.index(2, 2))
        assert "bottom" in inner and "right" in inner
        corner = grid.range_edges(model.index(1, 2))
        assert set(corner) == {"top", "right"}
        assert grid.range_edges(QModelIndex()) == []
    finally:
        win.close()


def test_selection_metrics_ignore_text_cells():
    win, grid, model = _grid_window()
    seen = []
    grid.selectionStatsChanged.connect(lambda avg, count, total: seen.append((avg, count, total)))
    try:
        model.setData(model.index(0, 0), "10", Qt.ItemDataRole.EditRole)
        model.setData(model.index(1, 0), "20", Qt.ItemDataRole.EditRole)
        model.setData(model.index(2, 0), "text", Qt.ItemDataRole.EditRole)
        grid.setCurrentIndex(model.index(0, 0))
        grid.selectionModel().select(
            QItemSelection(model.index(0, 0), model.index(2, 0)),
            QItemSelectionModel.SelectionFlag.Select)
        avg, count, total = seen[-1]
        assert (count, total, avg) == (2, 30.0, 15.0)
    finally:
        win.close()


# ------------------------------------------------------------------- commands #

def test_ribbon_commands_operate_on_the_selection():
    win, grid, model = _grid_window()
    try:
        for row, (label, value) in enumerate((("a", "5"), ("b", "7"), ("c", "9"))):
            model.setData(model.index(row, 0), label, Qt.ItemDataRole.EditRole)
            model.setData(model.index(row, 1), value, Qt.ItemDataRole.EditRole)
        grid.setCurrentIndex(model.index(0, 1))
        grid.selectionModel().select(
            QItemSelection(model.index(0, 1), model.index(2, 1)),
            QItemSelectionModel.SelectionFlag.Select)

        win._apply_format_key("Currency")
        assert model.data(model.index(0, 1), Qt.ItemDataRole.DisplayRole) == "$5.00"

        win._toggle_font("bold")
        assert model.sheet.get_format(0, 1).bold is True

        win._apply_cell_style("heading")
        assert model.sheet.get_format(1, 1).bg_color == "#4472C4"

        win._sort_column(ascending=False)
        assert model.sheet.get_cell_raw(0, 1) == "9"
        assert model.sheet.get_cell_raw(2, 1) == "5"

        grid.setCurrentIndex(model.index(3, 1))
        win._insert_autosum()
        assert model.sheet.get_cell_raw(3, 1) == "=SUM(B1:B3)"
        assert model.data(model.index(3, 1), Qt.ItemDataRole.DisplayRole) == "21"

        # Ctrl+D copies the top row of the selection over the rows below it.
        grid.selectionModel().select(
            QItemSelection(model.index(3, 1), model.index(4, 1)),
            QItemSelectionModel.SelectionFlag.Select)
        win._fill_down()
        assert model.sheet.get_cell_raw(4, 1) == "=SUM(B1:B3)"
        assert model.data(model.index(4, 1), Qt.ItemDataRole.DisplayRole) == "21"
    finally:
        win.close()


def test_workbook_sheets_and_status(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *args, **kwargs: ("Sales2", True)))
    win, grid, model = _grid_window()
    try:
        grid.setCurrentIndex(model.index(0, 0))
        win._on_add_sheet()
        assert len(win.sheets) == 2
        assert win.active_sheet_name == "Sheet2"

        model.setData(model.index(0, 0), "kept on Sheet2", Qt.ItemDataRole.EditRole)
        win.tab_bar.setCurrentIndex(0)
        assert model.sheet.get_cell_raw(0, 0) == ""
        win.tab_bar.setCurrentIndex(1)
        assert model.sheet.get_cell_raw(0, 0) == "kept on Sheet2"

        win._on_rename_sheet(1)
        assert "Sales2" in win.sheets
        assert win.status_bar.info_label.text().endswith("on Sales2")

        win._update_status_position()
        assert win.status_bar.info_label.text().startswith("A1")
    finally:
        win.close()

