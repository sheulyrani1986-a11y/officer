"""ODS import and export handler for RSheet using odfpy."""

import os
from typing import Dict
from odf.opendocument import OpenDocumentSpreadsheet, load as odf_load
from odf.table import Table, TableRow, TableCell
from odf.text import P
from odf.element import Element
from officer.rsheet.model import Sheet


class OdsHandler:
    """Handles importing and exporting .ods files to and from Sheet dictionary."""

    @staticmethod
    def load(filepath: str) -> Dict[str, Sheet]:
        """Load an OpenDocument Spreadsheet file into Sheet objects."""
        if not os.path.exists(filepath):
            return {}

        try:
            doc = odf_load(filepath)
            sheets: Dict[str, Sheet] = {}

            tables = doc.getElementsByType(Table)
            for tbl in tables:
                sheet_name = tbl.getAttribute("name") or "Sheet1"
                sheet = Sheet(sheet_name)

                rows = tbl.getElementsByType(TableRow)
                for r_idx, r in enumerate(rows):
                    cells = r.getElementsByType(TableCell)
                    c_idx = 0
                    for cell in cells:
                        # Check repeated columns
                        repeat = int(cell.getAttribute("numbercolumnsrepeated") or 1)
                        paragraphs = cell.getElementsByType(P)
                        text_val = ""
                        for p in paragraphs:
                            for child in p.childNodes:
                                if child.nodeType == Element.TEXT_NODE:
                                    text_val += str(child)

                        formula = cell.getAttribute("formula")
                        val_to_set = formula if formula else text_val.strip()

                        if val_to_set:
                            sheet.set_cell(r_idx, c_idx, val_to_set)

                        c_idx += repeat
                        # Cap at 500 columns for sanity during import
                        if c_idx > 500:
                            break

                sheets[sheet_name] = sheet

            return sheets
        except Exception as e:
            print(f"Error loading ods: {e}")
            return {}

    @staticmethod
    def save(filepath: str, sheets: Dict[str, Sheet]) -> bool:
        """Export a dictionary of Sheet objects to an .ods file."""
        try:
            doc = OpenDocumentSpreadsheet()

            for name, sheet in sheets.items():
                tbl = Table(name=name)
                doc.spreadsheet.addElement(tbl)

                if not sheet.cells:
                    continue

                max_r = max(r for r, c in sheet.cells.keys())
                max_c = max(c for r, c in sheet.cells.keys())

                for r in range(max_r + 1):
                    row_el = TableRow()
                    tbl.addElement(row_el)
                    for c in range(max_c + 1):
                        cell_el = TableCell()
                        val = sheet.get_cell_raw(r, c)
                        if val.startswith("="):
                            cell_el.setAttribute("formula", f"of:{val}")
                        p = P(text=sheet.get_cell_display(r, c))
                        cell_el.addElement(p)
                        row_el.addElement(cell_el)

            doc.save(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            print(f"Error saving ods: {e}")
            return False
