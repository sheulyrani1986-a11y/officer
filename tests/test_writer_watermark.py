"""What WriteR's paper is marked with: a word across it, or a picture in it.

Word's *Watermark* goes under every letter on every sheet, faded enough to read
through. These tests measure the mark itself -- where its ink falls on the
sheet, how far it climbs, whether the writing still stands over it, and what
comes out of the printer -- because a mark painted over the words, or one that
only appears on the first sheet, looks right in a screenshot of an empty page
and wrong in every real one.
"""

import pytest
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from officer.writer.page_color import load_picture
from officer.writer.watermark import (DEFAULT_WATERMARK, MARK_COLOURS,
                                      MARK_KINDS, MARK_LAYOUTS, MARK_PRESETS,
                                      clamp_scale, fit_font, mark_angle,
                                      mark_description, paint_watermark,
                                      watermark_mark)
from officer.writer.watermark_dialog import WatermarkDialog
from officer.writer.window import WriteRWindow

#: A light grey mark at full strength, so a test can name the pixels it wants.
MARK_GREY = "#BFBFBF"


@pytest.fixture
def sheet(q_app):
    """A laid-out WriteR window with real writing on it."""
    win = WriteRWindow()
    win.page.setPlainText("A marked sheet.\n" + "filling words " * 120)
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


# -- measuring the mark ------------------------------------------------------- #

def _ratio(image, hex_colour, within=8, step=4, crop=None):
    """How much of *image* wears *hex_colour*, near enough for Qt's blending."""
    red, green, blue = QColor(hex_colour).getRgb()[:3]
    left, top, right, bottom = crop or (0, 0, image.width(), image.height())
    matched = sampled = 0
    for y in range(int(top), int(bottom), step):
        for x in range(int(left), int(right), step):
            seen = image.pixel(x, y)
            if (abs(((seen >> 16) & 0xFF) - red) <= within
                    and abs(((seen >> 8) & 0xFF) - green) <= within
                    and abs((seen & 0xFF) - blue) <= within):
                matched += 1
            sampled += 1
    return matched / max(1, sampled)


def _dark(image, step=4, crop=None, below=110):
    """How much of *image* is ink darker than the mark under it."""
    left, top, right, bottom = crop or (0, 0, image.width(), image.height())
    found = sampled = 0
    for y in range(int(top), int(bottom), step):
        for x in range(int(left), int(right), step):
            seen = QColor(image.pixel(x, y)).getRgb()
            if max(seen[0], seen[1], seen[2]) < below:
                found += 1
            sampled += 1
    return found / max(1, sampled)


def _band(wide, tall, x_from, x_to, y_from, y_to):
    """A rectangle between two fractions of a sheet."""
    return (wide * x_from, tall * y_from, wide * x_to, tall * y_to)


def _marked(sheet, pages=1, **given):
    """The page's own mark, painted alone onto *pages* sheets of paper."""
    sheet.page.set_watermark(**given)
    zoom = sheet.page._zoom_factor
    image = QImage(int(sheet.page._base_width * zoom),
                   int(sheet.page._base_height * zoom) * pages,
                   QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    sheet.page.paint_page_watermark(painter)
    painter.end()
    return image


def _shown(sheet):
    """The real widget, painted the way the screen paints it, with its sheet."""
    sheet.page.viewport().update()
    QApplication.instance().processEvents()
    image = sheet.page.grab().toImage().convertToFormat(
        QImage.Format.Format_RGB32)
    box = sheet.page.sheet_box(0)
    crop = (int(box.left()), int(box.top()), int(box.right()),
            int(min(box.bottom(), image.height())))
    return image, crop


# -- what the page remembers -------------------------------------------------- #

def test_a_fresh_sheet_wears_no_mark(sheet):
    assert sheet.page.watermark() == DEFAULT_WATERMARK


def test_a_picture_mark_needs_a_picture_it_can_see(sheet):
    sheet.page.set_watermark(kind="text", text="DRAFT")
    assert sheet.page.set_watermark(kind="picture") is False
    assert sheet.page.watermark()["kind"] == "text", \
        "a picture the page has never seen cannot mark it"


def test_a_picture_that_cannot_be_read_is_refused(sheet):
    sheet.page.set_watermark(kind="text", text="SAMPLE")
    assert sheet.page.set_watermark(kind="picture",
                                    image_path="/no/such/face.png") is False
    kept = sheet.page.watermark()
    assert (kept["kind"], kept["text"]) == ("text", "SAMPLE")


def test_a_mark_of_no_words_wears_nothing(sheet):
    assert sheet.page.set_watermark(kind="text", text="   ") is True
    assert sheet.page.watermark()["kind"] == "none"


def test_only_what_is_given_changes(sheet, picture):
    """Word's dialog sends the whole mark; a ribbon preset sends one word."""
    sheet.page.set_watermark(image_path=picture, kind="picture", scale=40)
    sheet.page.set_watermark(scale=75)
    kept = sheet.page.watermark()
    assert (kept["kind"], kept["image_path"], kept["scale"]) == (
        "picture", picture, 75)


def test_the_dialogs_answer_is_accepted_whole(sheet):
    """The dialog sends an empty picture path along with a text mark: that is a
    mark, not a picture that failed to read."""
    chosen = WatermarkDialog({"kind": "text", "text": "CONFIDENTIAL",
                              "size_pt": 40, "colour": "#C00000"}).mark()
    assert chosen["image_path"] == ""
    assert sheet.page.set_watermark(**chosen) is True
    kept = sheet.page.watermark()
    assert (kept["kind"], kept["text"], kept["size_pt"],
            kept["colour"]) == ("text", "CONFIDENTIAL", 40.0, "#C00000")


def test_removing_a_mark_leaves_the_rest_of_the_dress_alone(sheet, picture):
    sheet.page.set_page_colour(kind="solid", colour="#FFC000")
    sheet.page.set_watermark(image_path=picture, kind="picture")
    sheet.page.remove_watermark()
    assert sheet.page.watermark()["kind"] == "none"
    assert sheet.page.page_colour()["kind"] == "solid"


def test_marking_the_sheet_marks_it_unsaved(sheet):
    sheet.page.document().setModified(False)
    sheet.page.set_watermark(kind="text", text="DRAFT")
    assert sheet.page.document().isModified() is True


@pytest.mark.parametrize("value,expected", [(0, 5), (500, 100),
                                            ("nonsense", 60), (35, 35)])
def test_a_pictures_share_of_the_sheet_stays_within_reason(value, expected):
    assert clamp_scale(value) == expected


def test_a_mark_is_kept_whole_however_it_arrives():
    odd = watermark_mark({"kind": "plaid", "layout": "sideways",
                          "size_pt": "not a number", "opacity": 9,
                          "scale": -4})
    assert odd["kind"] == "none"
    assert odd["layout"] == "diagonal"
    assert odd["size_pt"] == DEFAULT_WATERMARK["size_pt"]
    assert odd["opacity"] == 1.0
    assert odd["scale"] == 5


def test_every_ink_on_offer_is_an_ink():
    for hex_value in MARK_COLOURS:
        assert QColor(hex_value).isValid(), hex_value
    assert list(MARK_KINDS) == ["none", "text", "picture"]
    assert list(MARK_LAYOUTS) == ["diagonal", "horizontal"]
    assert [words for name, words in MARK_PRESETS] == ["CONFIDENTIAL", "DRAFT",
                                                       "SAMPLE"]


@pytest.mark.parametrize("layout,angle", [("diagonal", -45.0),
                                          ("horizontal", 0.0),
                                          ("anything else", -45.0)])
def test_a_diagonal_mark_climbs_and_a_horizontal_one_runs_flat(layout, angle):
    assert mark_angle(layout) == angle


def test_a_mark_is_described_in_the_words_the_status_line_shows():
    assert mark_description({"kind": "none"}) == "No mark on the page."
    assert mark_description({"kind": "text", "layout": "diagonal",
                             "text": "DRAFT"}) == "A diagonal “DRAFT”."
    assert mark_description({"kind": "text", "text": "  "}) == \
        "A mark with no words in it."
    assert mark_description({"kind": "picture", "scale": 70,
                             "image_path": "/a/b/logo.png"}) == \
        "A picture, 70% wide: logo.png"


# -- what the page paints ----------------------------------------------------- #

def test_no_mark_paints_plain_paper(sheet):
    image = _marked(sheet, kind="none")
    assert _ratio(image, "#FFFFFF") == 1.0


def test_a_text_mark_lies_across_the_middle_of_the_sheet(sheet):
    image = _marked(sheet, kind="text", text="DRAFT", colour=MARK_GREY,
                    opacity=1.0, size_pt=54)
    wide, tall = image.width(), image.height()
    assert _ratio(image, MARK_GREY, crop=_band(wide, tall, 0.32, 0.68,
                                               0.40, 0.60)) > 0.02, \
        "no mark across the middle of the sheet"
    assert _ratio(image, "#FFFFFF", crop=(0, 0, wide, 40)) == 1.0, \
        "the mark has run off the paper's top edge"


def test_a_diagonal_mark_runs_from_corner_to_corner(sheet):
    image = _marked(sheet, kind="text", text="CONFIDENTIAL", colour=MARK_GREY,
                    opacity=1.0, layout="diagonal")
    cx, cy = image.width() / 2, image.height() / 2
    step = image.width() * 0.22

    def around(x, y):
        return (x - 35, y - 35, x + 35, y + 35)

    climbed = _ratio(image, MARK_GREY, crop=around(cx + step, cy - step))
    fell = _ratio(image, MARK_GREY, crop=around(cx + step, cy + step))
    assert climbed > 0.02, "the mark does not climb the sheet it is set on"
    assert fell == 0.0, "a diagonal mark laid itself across the other diagonal"


def test_a_horizontal_mark_runs_the_whole_width_of_the_sheet(sheet):
    image = _marked(sheet, kind="text", text="CONFIDENTIAL", colour=MARK_GREY,
                    opacity=1.0, layout="horizontal")
    wide, tall = image.width(), image.height()
    across = _ratio(image, MARK_GREY, crop=_band(wide, tall, 0.10, 0.90,
                                                 0.44, 0.56))
    left = _ratio(image, MARK_GREY, crop=_band(wide, tall, 0.18, 0.30,
                                               0.44, 0.56))
    right = _ratio(image, MARK_GREY, crop=_band(wide, tall, 0.70, 0.82,
                                                0.44, 0.56))
    assert across > 0.02, "a horizontal mark is not lying across the sheet"
    assert left > 0.0 and right > 0.0, \
        "the mark stops short of the paper's own sides"


def test_a_mark_is_set_into_the_paper_not_over_the_writing(sheet):
    """The whole point of a watermark: the words still stand on top of it."""
    sheet.page.set_watermark(kind="text", text="CONFIDENTIAL",
                             colour=MARK_GREY, opacity=1.0)
    image, crop = _shown(sheet)
    left, top, right, bottom = crop
    wide, tall = right - left, bottom - top
    band = _band(wide, tall, 0.30, 0.70, 0.40, 0.60)
    band = (left + band[0], top + band[1], left + band[2], top + band[3])
    assert _ratio(image, MARK_GREY, crop=band) > 0.01, \
        "the mark is not on the screen at all"
    assert _dark(image, step=2, crop=band) > 0.002, \
        "the mark has painted the words out"


def test_a_mark_fades_by_the_strength_it_was_given(sheet):
    strong = _marked(sheet, kind="text", text="DRAFT", colour="#C00000",
                     opacity=1.0)
    faint = _marked(sheet, kind="text", text="DRAFT", colour="#C00000",
                    opacity=0.2)
    wide, tall = strong.width(), strong.height()
    band = _band(wide, tall, 0.25, 0.75, 0.38, 0.62)
    assert _ratio(strong, "#C00000", crop=band) > 0.02
    assert _ratio(faint, "#C00000", crop=band) == 0.0, \
        "a faded mark still stands at full strength"
    # Two-tenths of #C00000 over white paper is #F2CCCC, and that is what a
    # reader sees through the words.
    assert _ratio(faint, "#F2CCCC", within=10, crop=band) > 0.02, \
        "a faded mark drew nothing at all"


def _picture_box(wide, tall, scale):
    """Where a picture mark of *scale* per cent lies on a sheet, and its shape."""
    laid_wide = wide * scale / 100.0
    laid_tall = laid_wide * 200 / 400
    return (wide / 2 - laid_wide / 2, tall / 2 - laid_tall / 2,
            laid_wide, laid_tall)


def test_a_picture_mark_sits_centred_at_its_own_share_of_the_width(sheet,
                                                                  picture):
    image = _marked(sheet, kind="picture", image_path=picture, opacity=1.0,
                    scale=50)
    wide, tall = image.width(), image.height()
    left, top, laid_wide, laid_tall = _picture_box(wide, tall, 50)

    def spot(x_ratio, y_ratio):
        x, y = left + laid_wide * x_ratio, top + laid_tall * y_ratio
        return (x - 1, y - 1, x + 2, y + 2)

    assert _ratio(image, "#FF0000", crop=spot(0.25, 0.5)) == 1.0
    assert _ratio(image, "#0000FF", crop=spot(0.75, 0.5)) == 1.0
    assert _ratio(image, "#FFFFFF", crop=(0, top, left - 2, top + laid_tall)) \
        == 1.0, "the picture is wider than the share it was given"
    assert _ratio(image, "#FFFFFF", crop=(0, 0, wide, top - 2)) == 1.0, \
        "the picture is taller than its own shape"


def test_a_picture_mark_fades_into_the_paper_too(sheet, picture):
    image = _marked(sheet, kind="picture", image_path=picture, opacity=0.5,
                    scale=50)
    wide, tall = image.width(), image.height()
    left, top, laid_wide, laid_tall = _picture_box(wide, tall, 50)
    red = (left + laid_wide * 0.2, top + laid_tall * 0.4,
           left + laid_wide * 0.2 + 8, top + laid_tall * 0.4 + 8)
    assert _ratio(image, "#FF7F7F", crop=red) == 1.0, \
        "half a red picture over white paper is not a quarter-light red"


def test_a_long_word_is_shrunk_onto_the_sheet_rather_than_cut():
    font = fit_font("SUPERCALIFRAGILISTIC", "", 120, 400)
    assert font.pixelSize() < 120
    assert QFontMetricsF(font).horizontalAdvance(
        "SUPERCALIFRAGILISTIC") <= 400
    assert fit_font("DRAFT", "", 40, 4000).pixelSize() == 40, \
        "a mark that already fits was shrunk for nothing"


def test_a_mark_with_nothing_to_say_draws_nothing():
    image = QImage(10, 10, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    box = QRectF(0, 0, 816, 1056)
    assert paint_watermark(painter, {"kind": "none"}, box) is False
    assert paint_watermark(painter, {"kind": "text", "text": "  "}, box,
                           size_px=40) is False
    assert paint_watermark(painter, {"kind": "picture", "opacity": 1}, box,
                           image=None) is False
    assert paint_watermark(painter, {"kind": "text", "text": "DRAFT"},
                           QRectF(0, 0, 0, 0), size_px=40) is False
    painter.end()
    assert _ratio(image, "#FFFFFF") == 1.0


# -- every sheet, at any zoom ------------------------------------------------- #

def test_sheets_beyond_the_first_are_marked_too(sheet):
    """Two sheets on the screen are two sheets of marked paper."""
    sheet.page.set_zoom(50)
    QApplication.instance().processEvents()
    pages = sheet.page._visible_sheets()
    assert pages >= 2, "the screen does not show two sheets at this size"
    image = _marked(sheet, pages=pages, kind="text", text="DRAFT",
                    colour=MARK_GREY, opacity=1.0)
    tall = int(sheet.page._base_height * sheet.page._zoom_factor)
    for page in range(pages):
        band = _band(image.width(), tall, 0.30, 0.70, 0.40, 0.60)
        band = (band[0], page * tall + band[1], band[2], page * tall + band[3])
        assert _ratio(image, MARK_GREY, crop=band) > 0.02, \
            f"sheet {page + 1} is plain paper"


def test_the_mark_grows_with_the_zoom_it_is_read_at(sheet):
    one = _marked(sheet, kind="text", text="DRAFT", colour=MARK_GREY,
                  opacity=1.0)
    sheet.page.set_zoom(200)
    QApplication.instance().processEvents()
    scaled = _marked(sheet, kind="text", text="DRAFT", colour=MARK_GREY,
                     opacity=1.0)
    assert scaled.width() == one.width() * 2
    wide, tall = scaled.width(), scaled.height()
    assert _ratio(scaled, MARK_GREY,
                  crop=_band(wide, tall, 0.30, 0.70, 0.40, 0.60)) > 0.02


# -- the ribbon and the dialog ------------------------------------------------ #

def _mark_menu(win):
    for menu in win._ribbon_menus:
        if menu.objectName() == "watermark":
            return menu
    raise AssertionError("Layout has no Watermark menu")


def test_the_ribbon_offers_the_marks_and_a_way_out(sheet):
    named = [action.text() for action in _mark_menu(sheet).actions()
             if action.text()]
    for name, words in MARK_PRESETS:
        assert name in named
    assert "Remove Watermark" in named
    assert "Picture…" in named and "Custom Watermark…" in named


def test_choosing_a_preset_from_the_ribbon_marks_the_sheet(sheet):
    menu = _mark_menu(sheet)
    next(a for a in menu.actions() if a.text() == "CONFIDENTIAL").trigger()
    assert sheet.page.watermark()["kind"] == "text"
    assert sheet.page.watermark()["text"] == "CONFIDENTIAL"
    next(a for a in menu.actions() if a.text() == "Remove Watermark").trigger()
    assert sheet.page.watermark()["kind"] == "none"


def test_a_preset_keeps_the_marks_own_dress(sheet):
    sheet.page.set_watermark(kind="text", text="DRAFT", colour="#2E7D32",
                             size_pt=88, layout="horizontal")
    next(a for a in _mark_menu(sheet).actions() if a.text() == "SAMPLE").trigger()
    kept = sheet.page.watermark()
    assert (kept["text"], kept["colour"], kept["size_pt"],
            kept["layout"]) == ("SAMPLE", "#2E7D32", 88.0, "horizontal")


def test_the_dialog_answers_with_the_mark_it_was_asked_about(sheet):
    sheet.page.set_watermark(kind="text", text="SAMPLE", size_pt=72,
                             colour="#7030A0", layout="horizontal",
                             opacity=0.3)
    dialog = WatermarkDialog(sheet.page.watermark(), parent=sheet)
    assert dialog.mark() == sheet.page.watermark()
    assert dialog.kinds["text"].isChecked()
    assert dialog.layouts["horizontal"].isChecked()
    assert dialog.text_group.isEnabled() is True
    assert dialog.picture_group.isEnabled() is False
    assert dialog.size_box.value() == 72
    assert dialog.opacity.value() == 30
    assert dialog.summary.text() == "A horizontal “SAMPLE”."


def test_a_bare_sheet_gains_a_word_as_soon_as_one_is_written(q_app):
    dialog = WatermarkDialog()
    dialog.show()
    q_app.processEvents()
    assert dialog.mark()["kind"] == "none"
    assert dialog.text_group.isEnabled() is False
    dialog.text_edit.setEditText("SAMPLE")
    assert dialog.mark()["kind"] == "text"
    assert dialog.text_group.isEnabled() is True
    assert dialog.summary.text() == "A diagonal “SAMPLE”."


def test_a_sheet_already_wearing_a_picture_keeps_it(q_app, picture):
    dialog = WatermarkDialog({"kind": "picture", "image_path": picture})
    dialog.show()
    q_app.processEvents()
    dialog.text_edit.setEditText("SAMPLE")
    assert dialog.mark()["kind"] == "picture", \
        "typing in a disabled box took the picture off the paper"
    assert dialog.picture_group.isEnabled() is True
    assert dialog.text_group.isEnabled() is False


def test_the_marks_controls_answer_for_the_sheet(q_app):
    dialog = WatermarkDialog({"kind": "text", "text": "DRAFT"})
    dialog.show()
    q_app.processEvents()
    dialog.size_box.setValue(120)
    dialog.layouts["horizontal"].click()
    dialog.opacity.setValue(15)
    for tile in dialog._swatches.values():
        if tile.toolTip() == "#C00000":
            tile.click()
    mark = dialog.mark()
    assert (mark["size_pt"], mark["layout"], mark["opacity"],
            mark["colour"]) == (120.0, "horizontal", 0.15, "#C00000")
    assert dialog.opacity_value.text() == "15%"
    dialog.kinds["none"].click()
    assert dialog.mark()["kind"] == "none"
    assert dialog.opacity.isEnabled() is False


def test_the_picture_radio_asks_for_a_picture_before_it_takes(sheet):
    dialog = WatermarkDialog({"kind": "text", "text": "DRAFT"}, parent=sheet)
    asked = []
    dialog._choose_picture = lambda: asked.append(True)
    dialog.kinds["picture"].click()
    assert asked == [True], "the dialog did not go looking for a picture"
    assert dialog.mark()["kind"] == "text", \
        "a picture mark was chosen with no picture to show"


def test_a_chosen_picture_marks_the_sheet_at_once(sheet, picture):
    dialog = WatermarkDialog(parent=sheet)
    dialog._image = load_picture(picture)
    dialog._mark["image_path"] = picture
    dialog.kinds["picture"].click()
    mark = dialog.mark()
    assert (mark["kind"], mark["scale"]) == ("picture", 60)
    assert sheet.page.set_watermark(**mark) is True
    assert sheet.page.watermark()["image_path"] == picture
    image, crop = _shown(sheet)
    # The picture's own middle, where the sheet's centre is: the red half lies
    # to the left of it and the blue to the right.
    box = sheet.page.sheet_box(0)
    cx, cy = box.center().x(), box.center().y()
    share = box.width() * mark["scale"] / 100.0
    assert cy < crop[3], "the sheet's centre is not on the screen to check"
    spot = (cx - share / 4 - 4, cy - 4, cx - share / 4 + 4, cy + 4)
    assert _ratio(image, "#FF7F7F", crop=spot) == 1.0, \
        "the chosen picture is on the sheet at the wrong strength"


def test_a_new_document_sheds_the_mark(sheet, picture):
    sheet.page.set_watermark(image_path=picture, kind="picture")
    sheet.page.set_page_colour(kind="solid", colour="#2E75B6")
    sheet.on_new()
    assert sheet.page.watermark() == DEFAULT_WATERMARK
    assert sheet.page.page_colour()["kind"] == "none"


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


def test_a_printed_sheet_carries_the_mark(sheet, tmp_path):
    sheet.page.set_watermark(kind="text", text="CONFIDENTIAL",
                             colour=MARK_GREY, opacity=1.0)
    image = _printed(sheet, tmp_path)
    wide, tall = image.width(), image.height()
    assert _ratio(image, MARK_GREY,
                  crop=_band(wide, tall, 0.28, 0.72, 0.38, 0.62)) > 0.02, \
        "the printed sheet has no mark on it"


def test_a_printed_mark_stays_under_the_words(sheet, tmp_path):
    """A sheet the writing has filled, marked through the middle of it."""
    sheet.page.setPlainText("A marked sheet.\n" + "filling words " * 400)
    sheet.page.set_watermark(kind="text", text="CONFIDENTIAL",
                             colour=MARK_GREY, opacity=1.0)
    image = _printed(sheet, tmp_path)
    wide, tall = image.width(), image.height()
    band = _band(wide, tall, 0.28, 0.72, 0.38, 0.62)
    assert _ratio(image, MARK_GREY, crop=band) > 0.02, \
        "the printed mark is not on the sheet at all"
    assert _dark(image, step=2, crop=band) > 0.002, \
        "the printed mark painted the words out"


def test_a_printed_picture_fades_and_keeps_its_shape(sheet, picture, tmp_path):
    """A nearly blank sheet, so the paper round the picture is its own."""
    sheet.page.setPlainText("A marked sheet.")
    sheet.page.set_watermark(image_path=picture, kind="picture", scale=50,
                             opacity=0.5)
    image = _printed(sheet, tmp_path)
    wide, tall = image.width(), image.height()
    left, top, laid_wide, laid_tall = _picture_box(wide, tall, 50)
    assert _ratio(image, "#FF7F7F",
                  crop=(left + laid_wide * 0.15, top + laid_tall * 0.4,
                        left + laid_wide * 0.35, top + laid_tall * 0.6)) == 1.0
    assert _ratio(image, "#7F7FFF",
                  crop=(left + laid_wide * 0.65, top + laid_tall * 0.4,
                        left + laid_wide * 0.85, top + laid_tall * 0.6)) == 1.0
    assert _ratio(image, "#FFFFFF",
                  crop=(0, int(top), int(left) - 4, int(top + laid_tall))) \
        == 1.0, "the printed picture ran past its share of the sheet"
    assert _ratio(image, "#FFFFFF", crop=(0, 260, wide, int(top) - 4)) == 1.0, \
        "the printed picture is taller than its own shape"


def test_a_plain_sheet_prints_no_mark_of_its_own(sheet, tmp_path):
    image = _printed(sheet, tmp_path)
    wide, tall = image.width(), image.height()
    assert _ratio(image, "#FFFFFF", crop=(0, 0, 10, 10)) == 1.0
    assert _ratio(image, MARK_GREY,
                  crop=_band(wide, tall, 0.28, 0.72, 0.38, 0.62)) == 0.0
