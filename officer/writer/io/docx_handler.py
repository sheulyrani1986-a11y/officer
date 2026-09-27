"""DOCX import and export handler for WriteR using python-docx."""

import os
from typing import Optional
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PySide6.QtGui import QTextDocument, QTextCursor, QTextBlock, QTextCharFormat, QTextBlockFormat, QFont
from PySide6.QtCore import Qt


class DocxHandler:
    """Handles importing and exporting .docx files to and from QTextDocument."""

    @staticmethod
    def load(filepath: str, document: QTextDocument) -> bool:
        """Load a .docx file into QTextDocument."""
        if not os.path.exists(filepath):
            return False

        try:
            doc = Document(filepath)
            document.clear()
            cursor = QTextCursor(document)

            for p_idx, p in enumerate(doc.paragraphs):
                if p_idx > 0:
                    cursor.insertBlock()

                # Paragraph format (alignment & style)
                block_fmt = QTextBlockFormat()
                if p.alignment == WD_ALIGN_PARAGRAPH.CENTER:
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
                elif p.alignment == WD_ALIGN_PARAGRAPH.RIGHT:
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignRight)
                elif p.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignJustify)
                else:
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)

                # Heading styles
                style_name = p.style.name.lower() if p.style and p.style.name else ""
                is_heading = "heading" in style_name
                heading_level = 0
                if is_heading:
                    for char in style_name:
                        if char.isdigit():
                            heading_level = int(char)
                            break
                    if heading_level == 0:
                        heading_level = 1

                cursor.setBlockFormat(block_fmt)

                # Process text runs
                if not p.runs:
                    continue

                for run in p.runs:
                    char_fmt = QTextCharFormat()
                    char_fmt.setFontWeight(QFont.Weight.Bold if run.bold else QFont.Weight.Normal)
                    char_fmt.setFontItalic(bool(run.italic))
                    char_fmt.setFontUnderline(bool(run.underline))
                    if run.font.superscript:
                        char_fmt.setVerticalAlignment(
                            QTextCharFormat.VerticalAlignment.AlignSuperScript)
                    elif run.font.subscript:
                        char_fmt.setVerticalAlignment(
                            QTextCharFormat.VerticalAlignment.AlignSubScript)

                    if is_heading:
                        sizes = {1: 22, 2: 18, 3: 16, 4: 14}
                        char_fmt.setFontPointSize(sizes.get(heading_level, 16))
                        char_fmt.setFontWeight(QFont.Weight.Bold)
                    elif run.font.size:
                        char_fmt.setFontPointSize(run.font.size.pt)

                    if run.font.name:
                        char_fmt.setFontFamilies([run.font.name])

                    cursor.insertText(run.text, char_fmt)

            # Process tables if present
            for table in doc.tables:
                cursor.insertBlock()
                num_rows = len(table.rows)
                num_cols = len(table.columns) if num_rows > 0 else 0
                if num_rows > 0 and num_cols > 0:
                    qtable = cursor.insertTable(num_rows, num_cols)
                    for r_idx, row in enumerate(table.rows):
                        for c_idx, cell in enumerate(row.cells):
                            cell_cursor = qtable.cellAt(r_idx, c_idx).firstCursorPosition()
                            cell_cursor.insertText(cell.text.strip())

            return True
        except Exception as e:
            print(f"Error loading docx: {e}")
            return False

    @staticmethod
    def save(filepath: str, document: QTextDocument) -> bool:
        """Export a QTextDocument into a .docx file."""
        try:
            doc = Document()
            block = document.begin()

            while block.isValid():
                text = block.text()
                p = doc.add_paragraph()

                # Paragraph alignment
                alignment = block.blockFormat().alignment()
                if alignment & Qt.AlignmentFlag.AlignCenter:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                elif alignment & Qt.AlignmentFlag.AlignRight:
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                elif alignment & Qt.AlignmentFlag.AlignJustify:
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

                # Extract fragments (runs) within block
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        fmt = frag.charFormat()
                        run = p.add_run(frag.text())
                        run.bold = fmt.fontWeight() >= QFont.Weight.Bold
                        run.italic = fmt.fontItalic()
                        run.underline = fmt.fontUnderline()
                        raised = fmt.verticalAlignment()
                        if raised == QTextCharFormat.VerticalAlignment.AlignSuperScript:
                            run.font.superscript = True
                        elif raised == QTextCharFormat.VerticalAlignment.AlignSubScript:
                            run.font.subscript = True

                        if fmt.fontPointSize() > 0:
                            run.font.size = Pt(fmt.fontPointSize())

                        families = fmt.fontFamilies()
                        if families and len(families) > 0:
                            run.font.name = str(families[0])
                    it += 1

                block = block.next()

            doc.save(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            print(f"Error saving docx: {e}")
            return False
