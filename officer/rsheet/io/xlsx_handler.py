"""XLSX import and export handler for RSheet using openpyxl."""

import os
from typing import Dict, List
import openpyxl
from officer.rsheet.model import Sheet


class XlsxHandler:
    """Handles importing and exporting .xlsx files to and from Sheet dictionary."""

    @staticmethod
    def load(filepath: str) -> Dict[str, Sheet]:
        """Load an Excel workbook into a dictionary of Sheet objects."""
        if not os.path.exists(filepath):
            return {}

        try:
            wb = openpyxl.load_workbook(filepath, data_only=False)
            sheets: Dict[str, Sheet] = {}

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                sheet = Sheet(sheet_name)

                for r_idx, row in enumerate(ws.iter_rows(values_only=False)):
                    for c_idx, cell in enumerate(row):
                        if cell.value is not None:
                            val_str = str(cell.value)
                            sheet.set_cell(r_idx, c_idx, val_str)

                sheets[sheet_name] = sheet

            return sheets
        except Exception as e:
            print(f"Error loading xlsx: {e}")
            return {}

    @staticmethod
    def save(filepath: str, sheets: Dict[str, Sheet]) -> bool:
        """Export a dictionary of Sheet objects to an Excel workbook."""
        try:
            wb = openpyxl.Workbook()
            # Remove default active sheet
            wb.remove(wb.active)

            for name, sheet in sheets.items():
                ws = wb.create_sheet(title=name)
                for (row, col), cell_data in sheet.cells.items():
                    val = cell_data.raw_value
                    # Convert to numeric if it's pure number to preserve types in Excel
                    if val.replace(".", "", 1).isdigit() and not val.startswith("="):
                        try:
                            val = float(val) if "." in val else int(val)
                        except ValueError:
                            pass
                    ws.cell(row=row + 1, column=col + 1, value=val)

            wb.save(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            print(f"Error saving xlsx: {e}")
            return False
