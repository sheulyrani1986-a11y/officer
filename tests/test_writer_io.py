"""Tests for WriteR document formatting, DOCX, ODT, and PDF export."""

import os
import tempfile
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextDocument
from officer.writer.io.docx_handler import DocxHandler
from officer.writer.io.odt_handler import OdtHandler
from officer.core.io.pdf_exporter import PdfExporter
from officer.writer.unicode_math import to_unicode_math
from officer.writer.window import WriteRWindow



def test_docx_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        docx_path = os.path.join(tmpdir, "sample.docx")

        # 1. Create document
        doc1 = QTextDocument()
        cursor = QTextCursor(doc1)
        cursor.insertText("First paragraph of OfficeR test.\n")
        cursor.insertText("Second line with special content.")

        # 2. Save to .docx
        saved = DocxHandler.save(docx_path, doc1)
        assert saved is True
        assert os.path.exists(docx_path)
        assert os.path.getsize(docx_path) > 0

        # 3. Load into another QTextDocument
        doc2 = QTextDocument()
        loaded = DocxHandler.load(docx_path, doc2)
        assert loaded is True
        text = doc2.toPlainText()
        assert "First paragraph of OfficeR test." in text
        assert "Second line with special content." in text


def test_odt_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        odt_path = os.path.join(tmpdir, "sample.odt")

        doc1 = QTextDocument()
        cursor = QTextCursor(doc1)
        cursor.insertText("OpenDocument test line 1.\n")
        cursor.insertText("OpenDocument test line 2.")

        saved = OdtHandler.save(odt_path, doc1)
        assert saved is True
        assert os.path.exists(odt_path)
        assert os.path.getsize(odt_path) > 0

        doc2 = QTextDocument()
        loaded = OdtHandler.load(odt_path, doc2)
        assert loaded is True
        text = doc2.toPlainText()
        assert "OpenDocument test line 1." in text
        assert "OpenDocument test line 2." in text


def test_pdf_export():
    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "sample.pdf")

        doc = QTextDocument()
        cursor = QTextCursor(doc)
        cursor.insertHtml("<h1>OfficeR Heading</h1><p>This is a high quality PDF test.</p>")

        exported = PdfExporter.export_text_document(doc, pdf_path)
        assert exported is True
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 0


def test_writer_window_interaction():
    win = WriteRWindow()
    win.page.setPlainText("Hello from WriteR!")
    assert "Hello from WriteR!" in win.page.toPlainText()
    win.page.selectAll()
    win.page.set_bold()
    assert win.page.document().isModified() or not win.command_stack.is_clean
    win.close()


# --- paper sizes ------------------------------------------------------------- #

#: The PDF page box is measured in points; 25.4 mm is one inch is 72 pt.
MM_TO_PT = 72.0 / 25.4


@pytest.mark.parametrize("paper", ["Letter", "A4", "A5", "B5 (ISO)", "Tabloid",
                                   "Executive", "Monarch Envelope", "C5 Envelope"])
def test_page_sizes_are_word_sizes_in_millimetres(paper):
    from officer.writer.document_view import PAPER_SIZES_MM
    width, height = PAPER_SIZES_MM[paper]
    assert width < height, f"{paper} should be stored portrait"
    assert 50 < width < 500 and 100 < height < 500


def test_every_paper_size_is_reachable_from_the_size_menu():
    from officer.writer.document_view import PAPER_GROUPS, PAPER_SIZES_MM, paper_size_caption
    win = WriteRWindow()
    size_menu = next(menu for menu in win._ribbon_menus
                     if menu.objectName() == "paper-size")
    captions = [action.text() for action in size_menu.actions() if action.text()]
    assert len(captions) >= 8
    assert len(captions) == len(PAPER_SIZES_MM)
    assert captions == [paper_size_caption(name) for _, names in PAPER_GROUPS
                        for name in names]
    # Choosing one really moves the sheet.
    size_menu.actions()[0].trigger()
    assert win.page.paper_size == "Letter"
    win.close()


@pytest.mark.parametrize("paper", ["A4", "A5", "#10 Envelope"])
def test_pdf_export_uses_the_chosen_paper(paper, tmp_path):
    from officer.writer.document_view import PAPER_SIZES_MM
    from PySide6.QtPdf import QPdfDocument

    win = WriteRWindow()
    win.page.set_paper(paper)
    win.page.setPlainText("Paper size check.")
    expected = PAPER_SIZES_MM[paper]

    pdf = str(tmp_path / f"{paper.replace(' ', '').replace('#', '')}.pdf")
    assert PdfExporter.export_text_document(
        win.page.document(), pdf,
        page_size_mm=win.page.paper_size_mm,
        landscape=win.page.landscape,
    )
    document = QPdfDocument()
    assert document.load(pdf) == QPdfDocument.Error.None_
    size = document.pagePointSize(0)
    assert size.width() == pytest.approx(expected[0] * MM_TO_PT, abs=2)
    assert size.height() == pytest.approx(expected[1] * MM_TO_PT, abs=2)
    win.close()


def test_landscape_pdf_swaps_the_page(tmp_path):
    from PySide6.QtPdf import QPdfDocument

    win = WriteRWindow()
    win.page.set_paper("A4")
    win.page.set_landscape(True)
    assert win.page.paper_size_mm == (210.0, 297.0), "the sheet is stored portrait"

    pdf = str(tmp_path / "landscape.pdf")
    assert PdfExporter.export_text_document(
        win.page.document(), pdf, page_size_mm=win.page.paper_size_mm,
        landscape=True,
    )
    document = QPdfDocument()
    document.load(pdf)
    size = document.pagePointSize(0)
    assert size.width() > size.height()
    win.close()


# --- fonts ------------------------------------------------------------------- #

def test_printed_type_is_the_size_it_was_written_in(tmp_path):
    """Word's 11 pt has to come out at 11 pt, not at a third of it.

    A document is laid out in 96-to-the-inch units and its layout is computed
    once, on screen; the printer runs at 300. Measuring the height of a printed
    line is the only way to catch the two scales being pulled apart.
    """
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    win = WriteRWindow()
    win.page.setPlainText("filling words " * 400)
    win.resize(1200, 900)
    win.show()
    QApplication.processEvents()
    pdf = str(tmp_path / "type.pdf")
    assert win.export_pdf(pdf) is True

    document = QPdfDocument()
    assert document.load(pdf) == QPdfDocument.Error.None_
    # 150 to the inch: a point is 150/72 of them, and untouched paper is
    # transparent, so any alpha at all is ink.
    image = document.render(0, QSize(1275, 1650))
    rows = [y for y in range(image.height())
            if any(image.pixelColor(x, y).alpha() for x in range(0, 1275, 4))]
    first = rows[0]
    height = 1
    while first + height in rows:
        height += 1
    assert 15 <= height <= 30, \
        f"a line of type stands {height * 72 / 150:.1f} pt tall"
    win.close()


def test_a_long_document_prints_every_sheet_it_fills(tmp_path):
    """The sheet count comes from the laid-out height, so it must not lie."""
    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument

    win = WriteRWindow()
    win.page.setPlainText("filling words " * 400)
    win.resize(1200, 900)
    win.show()
    QApplication.processEvents()
    pdf = str(tmp_path / "long.pdf")
    assert win.export_pdf(pdf) is True
    document = QPdfDocument()
    document.load(pdf)
    assert document.pageCount() == 2
    for page in range(document.pageCount()):
        image = document.render(page, QSize(425, 550))
        ink = sum(1 for y in range(0, 550, 2) for x in range(0, 425, 2)
                  if image.pixelColor(x, y).alpha())
        assert ink > 200, f"sheet {page + 1} printed empty"
    win.close()

def test_font_box_lists_every_installed_family():
    from officer.core.ui.fonts import installed_families
    win = WriteRWindow()
    assert win.font_combo.count() == len(installed_families())
    assert win.font_combo.isEditable()
    win.close()


def test_font_box_draws_each_name_in_its_own_face():
    from PySide6.QtGui import QFont
    from officer.core.ui.fonts import installed_families
    win = WriteRWindow()
    unmarked = [i for i in range(win.font_combo.count())
                if win.font_combo.itemData(i, Qt.ItemDataRole.FontRole) is None]
    assert not unmarked
    sample = win.font_combo.itemData(0, Qt.ItemDataRole.FontRole)
    assert isinstance(sample, QFont)
    assert win.font_combo.itemText(0) == installed_families()[0]
    win.close()


def test_picking_a_font_from_the_box_formats_the_document(q_app):
    win = WriteRWindow()
    win.page.setPlainText("Body text")
    cursor = win.page.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
    win.page.setTextCursor(cursor)
    index = win.font_combo.findText("DejaVu Serif", Qt.MatchFlag.MatchFixedString)
    assert index >= 0
    win.font_combo.textActivated.emit(win.font_combo.itemText(index))
    cursor = win.page.textCursor()
    cursor.clearSelection()
    cursor.setPosition(9)
    assert cursor.charFormat().fontFamilies()[0] == "DejaVu Serif"
    win.close()


def test_font_box_follows_the_caret_without_rewriting_it(q_app):
    win = WriteRWindow()
    win.page.setPlainText("plain")
    cursor = win.page.textCursor()
    fmt = QTextCharFormat()
    fmt.setFontFamilies(["DejaVu Sans"])
    fmt.setFontPointSize(14)
    cursor.insertText("X", fmt)
    win.page.setTextCursor(cursor)
    assert win.font_combo.currentText() == "DejaVu Sans"
    assert win.size_spin.value() == round(win.page.current_font_point_size())
    # Reflecting the caret must not be a formatting command.
    before = win.page.toPlainText()
    win._sync_font_box()
    assert win.page.toPlainText() == before
    win.close()


# --- unicode equations -------------------------------------------------------- #

@pytest.mark.parametrize("typed,expected", [
    (r"$x^2 + y^2 = z^2$", "x² + y² = z²"),
    (r"$\sqrt{x}$", "√x"),
    (r"$\frac{1}{2}$", "½"),
    (r"$\sum_{i=1}^{n} x_i$", "∑ᵢ₌₁ⁿ xᵢ"),
    (r"$\alpha, \beta, \gamma, \delta$", "α, β, γ, δ"),
    (r"$\pm, \leq, \geq, \neq$", "±, ≤, ≥, ≠"),
    (r"$\int_a^b f(x)\,dx$", "∫ₐᵇ f(x) dx"),
    (r"\vec{F} = m\vec{a}", "F⃗ = ma⃗"),
    (r"\{a,b\} \subset \mathbb{Z}", "{a,b} ⊂ ℤ"),
    (r"\forall \epsilon > 0 \exists \delta > 0", "∀ ε > 0 ∃ δ > 0"),
    ("a <= b >= c != d -> e", "a ≤ b ≥ c ≠ d → e"),
    (r"\sin^{2}\theta + \cos^{2}\theta = 1", "sin²θ + cos²θ = 1"),
])
def test_equations_convert_to_unicode_characters(typed, expected):
    from officer.writer.unicode_math import to_unicode_math
    assert to_unicode_math(typed) == expected


@pytest.mark.parametrize("typed,keeps", [
    (r"\wibblecommand x^2", "wibblecommand"),
    (r"\sqrt{b^2 - 4ac}", "4ac"),
    (r"$e^{i\pi} + 1 = 0$", "π"),
    (r"\begin{pmatrix} a & b \\ c \end{pmatrix}", "b"),
])
def test_conversion_never_loses_what_was_typed(typed, keeps):
    """Nothing a reader could still want is dropped for want of a mapping."""
    from officer.writer.unicode_math import to_unicode_math
    assert keeps in to_unicode_math(typed)


def test_unmappable_stays_spelled_the_way_it_was():
    from officer.writer.unicode_math import to_unicode_math
    assert to_unicode_math(r"\weirdthing") == r"\weirdthing"
    assert to_unicode_math(r"e^{i\pi}") == "e^(iπ)"


@pytest.mark.parametrize("typed,expected", [
    (r"e^i\pi", "e^(iπ)"),
    (r"e^i \pi", "eⁱ π"),
    (r"x^2y", "x²ʸ"),
    (r"x^2 y", "x² y"),
    (r"\sin^2\theta", "sin^(2θ)"),
    (r"a_i b", "aᵢ b"),
])
def test_a_script_takes_everything_glued_to_it(typed, expected):
    """Only whitespace divides a script from what follows it, as in LaTeX."""
    from officer.writer.unicode_math import to_unicode_math
    assert to_unicode_math(typed) == expected


@pytest.mark.parametrize("converted,runs", [
    ("e^(iπ)", [("e", 0), ("iπ", 1)]),
    ("x² + y²", [("x² + y²", 0)]),
    ("x^*", [("x", 0), ("*", 1)]),
    ("a_(ij)", [("a", 0), ("ij", -1)]),
])
def test_the_runs_a_document_needs_for_a_script(converted, runs):
    """A group a reader could raise falls to the run's own vertical alignment."""
    from officer.writer.unicode_math import to_math_runs
    assert to_math_runs(converted) == runs


def test_a_script_unicode_cannot_raise_is_raised_by_the_run(q_app):
    """There is no superscript pi, so the document lifts the run instead."""
    from PySide6.QtGui import QTextCharFormat
    win = WriteRWindow()
    win.page.insert_equation(to_unicode_math(r"e^i\pi + 1 = 0"))
    assert win.page.toPlainText() == "eiπ + 1 = 0"

    raised = {}
    block = win.page.document().begin()
    cursor = QTextCursor(block)
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                alignment = fragment.charFormat().verticalAlignment()
                raised[fragment.text()] = alignment
            iterator += 1
        block = block.next()
    assert raised["iπ"] == QTextCharFormat.VerticalAlignment.AlignSuperScript
    assert raised["e"] == QTextCharFormat.VerticalAlignment.AlignNormal
    assert raised[" + 1 = 0"] == QTextCharFormat.VerticalAlignment.AlignNormal


def test_a_spaced_script_stays_a_single_raised_letter(q_app):
    from PySide6.QtGui import QTextCharFormat
    win = WriteRWindow()
    win.page.insert_equation(to_unicode_math(r"e^i \pi"))
    assert win.page.toPlainText() == "eⁱ π"
    cursor = QTextCursor(win.page.document())
    cursor.setPosition(1)
    cursor.movePosition(cursor.MoveOperation.NextCharacter,
                        cursor.MoveMode.KeepAnchor)
    assert cursor.charFormat().verticalAlignment() == (
        QTextCharFormat.VerticalAlignment.AlignNormal)


def test_a_raised_script_survives_a_docx_round_trip(tmp_path):
    from PySide6.QtGui import QTextCharFormat
    win = WriteRWindow()
    win.page.insert_equation(to_unicode_math(r"e^i\pi = 0"))
    path = str(tmp_path / "script.docx")
    assert DocxHandler.save(path, win.page.document())
    reloaded = QTextDocument()
    assert DocxHandler.load(path, reloaded)
    assert reloaded.toPlainText() == "eiπ = 0"
    formats = []
    block = reloaded.begin()
    while block.isValid():
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                formats.append((fragment.text(),
                                fragment.charFormat().verticalAlignment()))
            iterator += 1
        block = block.next()
    assert ("iπ", QTextCharFormat.VerticalAlignment.AlignSuperScript) in formats


def test_equation_is_inserted_as_editable_text_in_the_math_face(q_app):
    from officer.core.ui.fonts import MATH_CHAIN
    win = WriteRWindow()
    win.page.insert_equation("∑ᵢ₌₁ⁿ xᵢ = ½")
    assert win.page.toPlainText() == "∑ᵢ₌₁ⁿ xᵢ = ½"
    cursor = win.page.textCursor()
    cursor.movePosition(cursor.MoveOperation.Start)
    cursor.movePosition(cursor.MoveOperation.End, cursor.MoveMode.KeepAnchor)
    families = cursor.charFormat().fontFamilies()
    assert families[0] == MATH_CHAIN[0]
    assert "<img" not in win.page.document().toHtml()


def test_variables_are_italic_and_function_words_are_not(q_app):
    win = WriteRWindow()
    win.page.insert_equation("sin x")
    italic = {}
    cursor = win.page.textCursor()
    cursor.movePosition(cursor.MoveOperation.Start)
    while not cursor.atEnd():
        cursor.movePosition(cursor.MoveOperation.NextCharacter,
                            cursor.MoveMode.KeepAnchor)
        for char in cursor.selectedText():
            italic[char] = cursor.charFormat().fontItalic()
        cursor.movePosition(cursor.MoveOperation.NextCharacter)
    assert italic["x"] is True
    assert italic["s"] is False and italic["i"] is False and italic["n"] is False


def test_equation_command_inserts_unicode_text_not_a_picture(q_app, monkeypatch):
    from officer.writer import equation_dialog as module
    monkeypatch.setattr(module.EquationDialog, "exec", lambda self: 1)
    win = WriteRWindow()
    win._show_equation_dialog()
    assert "√" in win.page.toPlainText()
    assert "±" in win.page.toPlainText()


def test_equation_dialog_previews_the_unicode_text(q_app):
    from officer.writer.equation_dialog import EquationDialog
    dlg = EquationDialog()
    assert dlg.equation_text() == "x = (-b ± √(b² - 4ac))/(2a)"
    assert dlg._preview.text() == dlg.equation_text()
    assert dlg.rendered_image_path() is None
    dlg._latex_input.setText(r"$\sqrt{x}$")
    assert dlg.equation_text() == "√x"
    dlg._latex_input.setText(r"$e^i\pi$")
    assert dlg._preview.text() == "e<sup>iπ</sup>"
    dlg._request_picture()
    dlg._on_accept()
    assert dlg.rendered_image_path()
    dlg.close()


def test_equation_survives_a_docx_round_trip(tmp_path):
    """An equation is text, so it saves and reloads like the words around it."""
    win = WriteRWindow()
    win.page.setPlainText("Quadratic: ")
    win.page.insert_equation(to_unicode_math(r"$x = \frac{-b \pm \sqrt{b^2}}{2a}$"))
    equation = win.page.toPlainText()

    path = str(tmp_path / "equation.docx")
    assert DocxHandler.save(path, win.page.document())
    reloaded = QTextDocument()
    assert DocxHandler.load(path, reloaded)
    assert "√" in reloaded.toPlainText()
    assert "±" in reloaded.toPlainText()
    assert equation in reloaded.toPlainText()
    win.close()
