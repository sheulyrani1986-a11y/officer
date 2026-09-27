"""What WriteR's paper is dressed with: an ink, or a picture behind the words.

Word's *Page Color* goes under every letter, edge to edge, and carries down each
sheet of a long document. These tests measure the dressed paper itself -- the
colour of the pixels, where they fall on the sheet, and whether the writing
still stands on top of it -- because a fill painted over the words would look
right in a screenshot of an empty page and wrong in every real one.
"""

import pytest
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from officer.writer.page_color import (DEFAULT_OPACITY, DEFAULT_PAGE_COLOUR,
                                       FILL_KINDS, PAGE_COLOURS, cover_box,
                                       clamp_opacity, load_picture)
from officer.writer.page_color_dialog import PageColorDialog
from officer.writer.window import WriteRWindow


@pytest.fixture
def sheet(q_app):
    """A laid-out WriteR window with real writing on it."""
    win = WriteRWindow()
    win.page.setPlainText("A dressed sheet.\n" + "filling words " * 120)
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    return win


@pytest.fixture
def picture(tmp_path):
    """A landscape picture, half red and half blue, twice as wide as it is tall."""
    image = QImage(400, 200, QImage.Format.Format_RGB32)
    image.fill(QColor("#FF0000"))
    painter = QPainter(image)
    painter.fillRect(QRectF(200, 0, 200, 200), QColor("#0000FF"))
    painter.end()
    path = str(tmp_path / "picture.png")
    assert image.save(path)
    return path


# -- measuring the paper ------------------------------------------------------ #

def _ratio(image, hex_colour, within=8, step=4, crop=None):
    """How much of *image* wears *hex_colour*, near enough for Qt's blending."""
    red, green, blue = QColor(hex_colour).getRgb()[:3]
    left, top, right, bottom = crop or (0, 0, image.width(), image.height())
    matched = sampled = 0
    for y in range(top, bottom, step):
        for x in range(left, right, step):
            seen = image.pixel(x, y)
            if (abs(((seen >> 16) & 0xFF) - red) <= within
                    and abs(((seen >> 8) & 0xFF) - green) <= within
                    and abs((seen & 0xFF) - blue) <= within):
                matched += 1
            sampled += 1
    return matched / max(1, sampled)


def _dark(image, step=4, crop=None, below=110):
    """How much of *image* is ink darker than the dress under it."""
    left, top, right, bottom = crop or (0, 0, image.width(), image.height())
    found = sampled = 0
    for y in range(top, bottom, step):
        for x in range(left, right, step):
            seen = QColor(image.pixel(x, y)).getRgb()
            if max(seen[0], seen[1], seen[2]) < below:
                found += 1
            sampled += 1
    return found / max(1, sampled)


def _dressed(sheet, colour=DEFAULT_PAGE_COLOUR, kind="solid", image_path="",
             opacity=1.0, pages=1):
    """The page's own dress, painted alone onto *pages* sheets of paper."""
    sheet.page.set_page_colour(kind=kind, colour=colour, opacity=opacity,
                               image_path=image_path or None)
    zoom = sheet.page._zoom_factor
    image = QImage(int(sheet.page._base_width * zoom),
                   int(sheet.page._base_height * zoom) * pages,
                   QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    sheet.page.paint_page_colour(painter)
    painter.end()
    return image


def _shown(sheet):
    """The real widget, painted the way the screen paints it."""
    sheet.page.viewport().update()
    QApplication.instance().processEvents()
    image = sheet.page.grab().toImage().convertToFormat(
        QImage.Format.Format_RGB32)
    margin = int(sheet.page.margin_pixels)
    # The paper's own margin, where no word can stand, and the text column
    # beside it: the first measures the dress, the second the writing over it.
    return image, [(40, 40, margin - 12, min(image.height() - 40, 500)),
                   (margin + 12, 40, image.width() - margin - 12,
                    min(image.height() - 40, 500))]


# -- what the page remembers -------------------------------------------------- #

def test_a_fresh_sheet_is_plain_paper(sheet):
    assert sheet.page.page_colour() == {
        "kind": "none", "colour": DEFAULT_PAGE_COLOUR, "image_path": "",
        "opacity": DEFAULT_OPACITY}


def test_a_picture_needs_a_picture(sheet):
    sheet.page.set_page_colour(kind="solid", colour="#C00000")
    sheet.page.set_page_colour(kind="picture")
    assert sheet.page.page_colour()["kind"] == "solid", \
        "a picture the page has never seen cannot dress it"


def test_a_picture_that_cannot_be_read_leaves_the_sheet_as_it_was(sheet):
    sheet.page.set_page_colour(kind="solid", colour="#C00000")
    sheet.page.set_page_colour(image_path="/no/such/face.png",
                               kind="picture")
    kept = sheet.page.page_colour()
    assert (kept["kind"], kept["colour"], kept["image_path"]) == (
        "solid", "#C00000", "")


def test_a_real_picture_and_its_fade_are_remembered(sheet, picture):
    sheet.page.set_page_colour(image_path=picture, opacity=0.25,
                               kind="picture")
    assert sheet.page.page_colour() == {
        "kind": "picture", "colour": DEFAULT_PAGE_COLOUR,
        "image_path": picture, "opacity": 0.25}


def test_only_what_is_given_changes(sheet, picture):
    """Word's dialog sends the whole set; a caller may change one thing."""
    sheet.page.set_page_colour(image_path=picture, kind="picture")
    sheet.page.set_page_colour(opacity=0.7)
    kept = sheet.page.page_colour()
    assert (kept["kind"], kept["image_path"]) == ("picture", picture)
    assert kept["opacity"] == 0.7


def test_an_unknown_kind_is_not_a_dress(sheet):
    sheet.page.set_page_colour(kind="plaid")
    assert sheet.page.page_colour()["kind"] == "none"


def test_dressing_the_sheet_marks_it_unsaved(sheet):
    sheet.page.document().setModified(False)
    sheet.page.set_page_colour(kind="solid", colour="#FFC000")
    assert sheet.page.document().isModified() is True


def test_the_fade_always_lands_between_a_hint_and_all_of_it():
    assert clamp_opacity(0) == 0.1
    assert clamp_opacity(2) == 1.0
    assert clamp_opacity("nonsense") == DEFAULT_OPACITY
    assert clamp_opacity(0.4) == 0.4


def test_every_ink_on_offer_is_an_ink_or_the_lack_of_one():
    for name, hex_value in PAGE_COLOURS.items():
        assert hex_value == "none" or QColor(hex_value).isValid(), name
    assert list(FILL_KINDS) == ["none", "solid", "picture"]


# -- what the page paints ----------------------------------------------------- #

def test_plain_paper_paints_nothing(sheet):
    image = _dressed(sheet, kind="none")
    assert _ratio(image, "#FFFFFF") == 1.0


def test_a_solid_ink_dresses_the_sheet_edge_to_edge(sheet):
    image = _dressed(sheet, colour="#2E75B6")
    wide, tall = image.width(), image.height()
    for x, y in ((1, 1), (wide - 2, 1), (1, tall - 2), (wide - 2, tall - 2),
                 (wide // 2, tall // 2)):
        assert _ratio(image, "#2E75B6", crop=(x, y, x + 1, y + 1)) == 1.0, \
            f"({x}, {y}) is plain paper"


@pytest.mark.parametrize("hex_colour", ["#FFFFFF", "#111827", "#FFC000",
                                        "#2E75B6"])
def test_each_ink_arrives_as_itself(sheet, hex_colour):
    image = _dressed(sheet, colour=hex_colour)
    assert _ratio(image, hex_colour) == 1.0


def test_the_ink_goes_under_the_writing_not_over_it(sheet):
    """The whole point of a page colour: the words still stand on top of it."""
    sheet.page.set_page_colour(kind="solid", colour="#FFC000")
    image, crops = _shown(sheet)
    assert _ratio(image, "#FFC000", within=6, crop=crops[0]) == 1.0, \
        "the paper's own margin is undressed"
    assert _dark(image, step=2, crop=crops[1]) > 0.001, \
        "the dress has painted the words out"
    assert _ratio(image, "#FFC000", within=6, crop=crops[1]) > 0.7, \
        "barely any of the writing column is dressed"


def test_a_picture_covers_the_sheet_without_white_gaps(sheet, picture):
    """Cover, not fit: a landscape photo still dresses a portrait sheet."""
    image = _dressed(sheet, kind="picture", image_path=picture)
    assert _ratio(image, "#FFFFFF") == 0.0, "paper escaped the picture"


def test_a_picture_fades_by_the_opacity_it_was_given(sheet, picture):
    """Half a red picture over white paper is a quarter-light red."""
    for opacity, red_side, blue_side in ((1.0, "#FF0000", "#0000FF"),
                                         (0.5, "#FF7F7F", "#7F7FFF")):
        image = _dressed(sheet, kind="picture", image_path=picture,
                         opacity=opacity)
        wide = image.width()
        assert _ratio(image, red_side, crop=(0, 0, wide // 4, 40)) == 1.0, \
            f"the red half is not faded to {red_side}"
        assert _ratio(image, blue_side,
                      crop=(wide * 3 // 4, 0, wide, 40)) == 1.0, \
            "the blue half went missing"


def test_a_picture_laid_under_writing_keeps_the_words(sheet, picture):
    sheet.page.set_page_colour(image_path=picture, opacity=0.3,
                              kind="picture")
    image, crops = _shown(sheet)
    assert _ratio(image, "#FFB2B2", within=6, crop=crops[0]) == 1.0, \
        "the picture does not reach the paper's margin"
    assert _dark(image, step=2, crop=crops[1]) > 0.001, \
        "the picture has painted the words out"


# -- every sheet, at any zoom ------------------------------------------------- #

def test_sheets_beyond_the_first_are_dressed_too(sheet):
    """Two sheets on the screen are two sheets of dressed paper."""
    sheet.page.set_zoom(50)
    QApplication.instance().processEvents()
    pages = sheet.page._visible_sheets()
    assert pages >= 2, "the screen does not show two sheets at this size"
    tall = int(sheet.page._base_height * sheet.page._zoom_factor)
    image = _dressed(sheet, colour="#2E75B6", pages=pages)
    for page in range(pages):
        y = page * tall + 4
        assert _ratio(image, "#2E75B6", crop=(4, y, 40, y + 4)) == 1.0, \
            f"sheet {page + 1} is plain paper"


def test_a_sheet_grows_with_the_zoom_it_is_read_at(sheet):
    sheet.page.set_page_colour(kind="solid", colour="#2E75B6")
    one = sheet.page.sheet_box(0)
    sheet.page.set_zoom(150)
    QApplication.instance().processEvents()
    scaled = sheet.page.sheet_box(0)
    assert scaled.width() > one.width()
    assert abs(scaled.width() - one.width() * 1.5) < 2
    assert abs(scaled.height() - one.height() * 1.5) < 2
    image = _dressed(sheet, colour="#2E75B6")
    assert _ratio(image, "#2E75B6", crop=(4, 4, 40, 40)) == 1.0


def test_a_picture_is_covered_onto_the_box_it_is_given(picture):
    image = load_picture(picture)
    box = QRectF(0, 0, 816, 1056)
    laid = cover_box(image, box)
    assert laid.left() <= box.left() and laid.right() >= box.right()
    assert laid.top() <= box.top() and laid.bottom() >= box.bottom()
    assert abs(laid.width() / laid.height() - 2.0) < 0.01, \
        "the photo was stretched out of shape"


def test_load_picture_says_no_to_a_file_that_is_not_one(tmp_path):
    text = tmp_path / "words.txt"
    text.write_text("not a picture")
    assert load_picture(str(text)) is None
    assert load_picture("") is None


# -- the ribbon and the dialog ------------------------------------------------ #

def _colour_menu(win):
    for menu in win._ribbon_menus:
        if menu.objectName() == "page-colour":
            return menu
    raise AssertionError("Layout has no Page Colour menu")


def test_the_ribbon_offers_every_ink_and_a_picture(sheet):
    named = [action.text() for action in _colour_menu(sheet).actions()
             if action.text()]
    for name in PAGE_COLOURS:
        assert name in named
    assert "Picture…" in named and "More Colours…" in named


def test_choosing_an_ink_from_the_ribbon_dresses_the_sheet(sheet):
    menu = _colour_menu(sheet)
    next(a for a in menu.actions() if a.text() == "Red").trigger()
    assert sheet.page.page_colour() == {
        "kind": "solid", "colour": PAGE_COLOURS["Red"], "image_path": "",
        "opacity": DEFAULT_OPACITY}
    next(a for a in menu.actions() if a.text() == "No colour").trigger()
    assert sheet.page.page_colour()["kind"] == "none"


def test_the_inks_wear_their_own_colour_in_the_menu(sheet):
    """A colour menu whose entries are plain text is a menu nobody can read."""
    menu = _colour_menu(sheet)
    for name, hex_value in PAGE_COLOURS.items():
        action = next(a for a in menu.actions() if a.text() == name)
        if hex_value == "none":
            assert action.icon().isNull(), name
            continue
        size = action.icon().availableSizes()[0]
        image = action.icon().pixmap(size).toImage()
        centre = image.pixel(image.width() // 2, image.height() // 2)
        assert (centre & 0x00FFFFFF) == (QColor(hex_value).rgb()
                                         & 0x00FFFFFF), name


def test_the_dialog_answers_with_what_it_was_asked(picture):
    chosen = {"kind": "picture", "colour": "#FFC000", "image_path": picture,
              "opacity": 0.3}
    dialog = PageColorDialog(chosen)
    assert dialog.colour() == chosen
    assert dialog.opacity.isEnabled() is True
    assert dialog.opacity.value() == 30


def test_the_dialogs_swatches_and_slider_answer_for_the_sheet(q_app, picture):
    dialog = PageColorDialog()
    dialog.show()
    q_app.processEvents()
    assert dialog.colour()["kind"] == "none"
    assert dialog.opacity.isEnabled() is False, "there is nothing to fade yet"
    dialog._choose_solid("#C00000")
    assert (dialog.colour()["kind"], dialog.colour()["colour"]) == (
        "solid", "#C00000")
    assert dialog.opacity.isEnabled() is False

    dressed = PageColorDialog({"kind": "picture", "image_path": picture,
                              "opacity": 0.6})
    dressed.show()
    q_app.processEvents()
    assert dressed.opacity.isEnabled() is True
    dressed.opacity.setValue(45)
    assert dressed.colour()["opacity"] == 0.45
    assert dressed.colour()["kind"] == "picture"
    assert dressed.opacity_value.text() == "45%"
    dressed._choose_kind("none")
    assert dressed.colour()["kind"] == "none"
    assert dressed.opacity.isEnabled() is False


def test_the_dialog_dresses_the_page_it_belonged_to(sheet, picture):
    dialog = PageColorDialog({"kind": "picture", "image_path": picture,
                              "opacity": 0.6})
    sheet.page.set_page_colour(**dialog.colour())
    kept = sheet.page.page_colour()
    assert (kept["kind"], kept["opacity"]) == ("picture", 0.6)
    image = _dressed(sheet, kind="picture", image_path=picture, opacity=0.6)
    assert _ratio(image, "#FF6666", crop=(0, 0, 60, 60)) == 1.0


def test_a_broken_picture_from_the_dialog_changes_nothing(sheet):
    sheet.page.set_page_colour(kind="solid", colour="#2E75B6")
    dialog = PageColorDialog({"kind": "picture", "image_path": "/no/such.png",
                              "opacity": 0.5})
    sheet.page.set_page_colour(**dialog.colour())
    assert sheet.page.page_colour()["kind"] == "solid"


# -- what comes out of the printer -------------------------------------------- #

def _printed(win, tmp_path, name="page.pdf", size=QSize(1200, 1554)):
    """The first printed sheet, on the white paper a viewer shows it on.

    Rendered large: at a reading size the printer's own glyphs are a pixel
    wide, and a test that looks for writing in them is a test of the renderer.
    """
    pdf = str(tmp_path / name)
    assert win.export_pdf(pdf) is True
    document = QPdfDocument()
    document.load(pdf)
    assert document.pageCount() >= 1
    rendered = document.render(0, size)
    # Paper the printer never touched comes back transparent, which is not what
    # anyone reads; composite it the way a viewer does.
    image = QImage(rendered.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.drawImage(0, 0, rendered)
    painter.end()
    return image


def _text_column(image):
    """Where the words stand on a printed sheet: inside its own margins."""
    return (int(image.width() * 0.15), int(image.height() * 0.08),
            int(image.width() * 0.85), int(image.height() * 0.75))


def test_a_printed_sheet_wears_the_ink_edge_to_edge(sheet, tmp_path):
    """The dress must cover the paper's own margin, not just the writing area."""
    sheet.page.set_page_colour(kind="solid", colour="#2E75B6")
    image = _printed(sheet, tmp_path)
    wide, tall = image.width(), image.height()
    for x, y in ((2, 2), (wide - 3, 2), (2, tall - 3), (wide - 3, tall - 3)):
        assert _ratio(image, "#2E75B6", crop=(x, y, x + 1, y + 1)) == 1.0, \
            f"the printed page is plain paper at ({x}, {y})"


def test_a_printed_ink_stays_under_the_words(sheet, tmp_path):
    sheet.page.set_page_colour(kind="solid", colour="#FFC000")
    image = _printed(sheet, tmp_path)
    column = _text_column(image)
    assert _ratio(image, "#FFC000", crop=column) > 0.8
    assert _dark(image, step=2, crop=column) > 0.002, \
        "the printed ink painted the words out"


def test_a_printed_picture_fades_and_keeps_the_words(sheet, picture, tmp_path):
    sheet.page.set_page_colour(image_path=picture, opacity=0.5,
                               kind="picture")
    image = _printed(sheet, tmp_path)
    wide, tall = image.width(), image.height()
    assert _ratio(image, "#FF7F7F", crop=(0, 0, wide // 8, tall // 16)) == 1.0
    assert _ratio(image, "#7F7FFF",
                  crop=(wide * 7 // 8, 0, wide, tall // 16)) == 1.0
    assert _dark(image, step=2, crop=_text_column(image)) > 0.002, \
        "the printed picture painted the words out"


def test_plain_paper_prints_no_dress_of_its_own(sheet, tmp_path):
    image = _printed(sheet, tmp_path)
    assert _ratio(image, "#FFFFFF", crop=(0, 0, 8, 8)) == 1.0
    assert _dark(image, step=2, crop=_text_column(image)) > 0.0005, \
        "the plain sheet printed no words either"
