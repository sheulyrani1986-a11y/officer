"""ODT import and export handler for WriteR using odfpy."""

import os
from odf.opendocument import OpenDocumentText, load as odf_load
from odf.text import P, H, Span
from odf.element import Element
from PySide6.QtGui import QTextDocument, QTextCursor, QFont, QTextCharFormat, QTextBlockFormat
from PySide6.QtCore import Qt


class OdtHandler:
    """Handles importing and exporting .odt OpenDocument files to and from QTextDocument."""

    @staticmethod
    def load(filepath: str, document: QTextDocument) -> bool:
        """Load an .odt file into QTextDocument."""
        if not os.path.exists(filepath):
            return False

        try:
            odt_doc = odf_load(filepath)
            document.clear()
            cursor = QTextCursor(document)

            # Traverse child elements of text body
            paragraphs = odt_doc.getElementsByType(P) + odt_doc.getElementsByType(H)
            for idx, p in enumerate(paragraphs):
                if idx > 0:
                    cursor.insertBlock()

                is_heading = p.tagName == "text:h"
                char_fmt = QTextCharFormat()
                if is_heading:
                    char_fmt.setFontPointSize(18)
                    char_fmt.setFontWeight(QFont.Weight.Bold)

                # Extract plain text content recursively from node
                text_content = ""
                for child in p.childNodes:
                    if child.nodeType == Element.TEXT_NODE:
                        text_content += str(child)
                    elif child.hasChildNodes():
                        for subchild in child.childNodes:
                            if subchild.nodeType == Element.TEXT_NODE:
                                text_content += str(subchild)

                cursor.insertText(text_content, char_fmt)

            return True
        except Exception as e:
            print(f"Error loading odt: {e}")
            return False

    @staticmethod
    def save(filepath: str, document: QTextDocument) -> bool:
        """Export QTextDocument into an .odt file."""
        try:
            odt_doc = OpenDocumentText()
            block = document.begin()

            while block.isValid():
                text = block.text()
                p = P(text=text)
                odt_doc.text.addElement(p)
                block = block.next()

            odt_doc.save(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            print(f"Error saving odt: {e}")
            return False
