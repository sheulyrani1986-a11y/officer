"""Test OfficeR Core UI components, themes, icons, and base window."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu, QTabBar, QToolButton
from officer.core.themes.theme_manager import ThemeManager
from officer.core.ui.icons import IconProvider
from officer.core.ui.ribbon import OfficeRibbon
from officer.core.ui.quick_access import QuickAccessBar
from officer.core.ui.status_bar import OfficeStatusBar
from officer.core.ui.base_window import OfficeBaseWindow



def test_theme_manager():
    tm = ThemeManager.instance()
    assert tm.is_dark is False
    tm.set_dark_mode(True)
    assert tm.is_dark is True
    tm.set_dark_mode(False)
    assert tm.is_dark is False


def test_icon_provider():
    icon_names = ["new", "open", "save", "undo", "redo", "cut", "copy", "paste",
                  "bold", "italic", "underline", "align-left", "table", "image",
                  "notes", "ellipse", "shape-diamond", "shape-triangle", "shape-star",
                  "shape-arrow", "equation", "ruler", "font-grow", "font-shrink"]
    for name in icon_names:
        icon = IconProvider.get_icon(name, size=24)
        assert icon is not None
        assert not icon.isNull()


def test_named_icons_have_dedicated_glyphs():
    """Unknown names silently fall back to a plain circle, so compare rendered pixels."""
    def render(name: str) -> bytes:
        pixmap = IconProvider.get_icon(name, size=32).pixmap(32, 32)
        return bytes(pixmap.toImage().bits())

    fallback = render("no-such-icon-name")
    for name in ["shape-diamond", "shape-triangle", "shape-star", "shape-arrow",
                 "shape-double-arrow", "notes", "equation", "ruler", "font-grow",
                 "ellipse", "shape-rect", "rounded-rect", "name", "text:Σ",
                 "paintbrush", "bullets", "line-spacing", "select-all", "bring-front",
                 "send-back", "text-box", "fill-color", "clear-format",
                 "view-slide-sorter", "view-normal", "view-page-break"]:
        assert render(name) != fallback, f"'{name}' renders as the unknown-icon fallback"


def test_status_bar_view_modes_use_explicit_keys():
    """Two views whose labels share a first word must not collide.

    Excel's Page Layout and Page Break Preview both begin with "Page", so the
    keys are supplied by the application rather than guessed from the label.
    """
    bar = OfficeStatusBar()
    calls = []
    bar.set_view_modes((
        ("normal", "Normal", "Normal", "view-normal", lambda: calls.append("normal")),
        ("page-layout", "Page Layout", "Page Layout", "view-page-layout",
         lambda: calls.append("page-layout")),
        ("page-break", "Page Break Preview", "Page Break Preview", "view-page-break",
         lambda: calls.append("page-break")),
    ))
    assert list(bar._mode_buttons) == ["normal", "page-layout", "page-break"]
    bar.select_view_mode("page-break")
    assert bar._mode_buttons["page-break"].isChecked()
    assert not bar._mode_buttons["page-layout"].isChecked()
    bar._mode_buttons["normal"].click()
    assert calls == ["normal"]


def test_status_bar_command_entry_is_not_a_view_toggle():
    """PowerPoint's strip ends with a Slide Show button that never stays pressed."""
    bar = OfficeStatusBar()
    clicked = []
    bar.set_view_modes((
        ("normal", "Normal", "Normal", "view-normal", lambda: None),
        ("", "From Beginning (F5)", "Slide Show (F5)", "play", lambda: clicked.append(1)),
    ))
    assert list(bar._mode_buttons) == ["normal"]
    show = bar.view_layout.itemAt(bar.view_layout.count() - 1).widget()
    assert isinstance(show, QToolButton) and not show.isCheckable()
    show.click()
    assert clicked == [1]
    assert bar._mode_buttons["normal"].isChecked()


def test_no_ribbon_command_overflows_its_group():
    """Office's ribbon never clips a caption or spills past its group divider."""
    from officer.writer.window import WriteRWindow
    from officer.rsheet.window import RSheetWindow
    from officer.presentr.window import PresentRWindow
    from officer.core.ui.ribbon import RibbonButton, RibbonGroup

    problems = []
    for label, window_class in (("WriteR", WriteRWindow), ("RSheet", RSheetWindow),
                                ("PresentR", PresentRWindow)):
        win = window_class()
        try:
            win.resize(1500, 860)
            win.show()
            QTest.qWait(40)
            tabs = win.ribbon.findChild(QTabBar)
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                QTest.qWait(40)
                tab_name = tabs.tabText(index)
                for group in win.ribbon.findChildren(RibbonGroup):
                    # A group on an inactive tab page has never been laid out;
                    # its stale geometry would look like an overflow.
                    if not group.isVisible():
                        continue
                    body = group.content_widget
                    right = 0
                    for button in group.findChildren(RibbonButton):
                        if not button.isVisible():
                            continue
                        caption = button.text().replace("\n", "\\n")
                        top = button.mapTo(body, QPoint(0, 0)).y()
                        if top < -1 or top + button.height() > body.height() + 1:
                            problems.append((label, tab_name, group.title_label.text(),
                                             caption, "vertical"))
                        right = max(right,
                                    button.mapTo(body, QPoint(0, 0)).x() + button.width())
                        metrics = button.fontMetrics()
                        caption_text = button.text()
                        has_caption = bool(caption_text.strip())
                        widest = max(metrics.horizontalAdvance(line)
                                     for line in (caption_text.splitlines() or [""]))
                        beside = (button.toolButtonStyle()
                                  != Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                        icon_width = 0
                        if beside and not button.icon().isNull():
                            # The gap only exists when a caption sits beside it.
                            icon_width = button.iconSize().width() + (6 if has_caption else 0)
                        # +14: the ribbon button style keeps 7px of padding per side.
                        need = widest + icon_width
                        need += 16 if button.menu() else 0
                        need += 14
                        if button.width() < need:
                            problems.append((label, tab_name, group.title_label.text(),
                                             caption, f"caption {button.width()}<{need}"))
                    if right > body.width() + 1:
                        problems.append((label, tab_name, group.title_label.text(),
                                         "", f"overflow {right}>{body.width()}"))
                tab = win.ribbon._tabs.get(tab_name)
                if tab is not None and tab.layout.sizeHint().width() > win.width():
                    problems.append((label, tab_name, "", "", "tab width"))
        finally:
            win.close()
    assert not problems, f"ribbon commands do not fit: {problems[:6]}"


def test_every_ribbon_icon_draws_a_glyph():
    """No command may fall back to the placeholder circle: catch typo'd icon names."""
    original = IconProvider.get_icon.__func__
    rendered = []

    def spy(cls, name, color="#374151", size=24):
        icon = original(cls, name, color, size)
        rendered.append((name, icon))
        return icon

    IconProvider.get_icon = classmethod(spy)
    try:
        from officer.writer.window import WriteRWindow
        from officer.rsheet.window import RSheetWindow
        from officer.presentr.window import PresentRWindow
        for window_class in (WriteRWindow, RSheetWindow, PresentRWindow):
            window_class()                      # building the ribbon draws its icons

        assert rendered, "no ribbon icons were drawn while building the windows"
        fallback = original(IconProvider, "no-such-icon-name", "#374151", 32)
        fallback_bits = bytes(fallback.pixmap(32, 32).toImage().bits())
        for name, icon in rendered:
            bits = bytes(icon.pixmap(32, 32).toImage().bits())
            assert bits != fallback_bits, f"'{name}' renders the fallback glyph"
    finally:
        IconProvider.get_icon = classmethod(original)


def test_ribbon_structure():
    ribbon = OfficeRibbon()
    home_tab = ribbon.add_tab("Home")
    assert home_tab is not None
    group = home_tab.add_group("Clipboard")
    assert group is not None
    btn = group.add_button("Paste", "paste", large=True)
    assert btn is not None
    assert btn.text() == "Paste"

    # The first group of a tab carries no left separator, later ones do.
    assert group.leading is True
    assert home_tab.add_group("Font").leading is False

    # Split commands keep their drop-down menu alive with the button.
    menu = QMenu()
    menu.addAction("Portrait")
    split = group.add_split_button("Orientation", "orientation", menu, large=False)
    assert split.menu() is menu

    # Test collapse / expand
    ribbon.collapse()
    assert ribbon.height() == OfficeRibbon.COLLAPSED_HEIGHT
    assert ribbon.is_collapsed is True
    ribbon.expand()
    assert ribbon.height() == OfficeRibbon.EXPANDED_HEIGHT
    assert ribbon.is_collapsed is False

    # Tabs switch the command body, not a stack of dummy pages.
    insert_tab = ribbon.add_tab("Insert")
    ribbon.select_tab("Insert")
    assert ribbon.current_tab_name == "Insert"
    assert ribbon.content_stack.currentWidget() is insert_tab


def test_base_window_creation():
    win = OfficeBaseWindow(app_name="writer", app_title="WriteR")
    assert win.app_name == "writer"
    assert win.quick_access is not None
    assert win.ribbon is not None
    assert win.status_bar is not None
    assert win.command_stack is not None
    win.close()


# --- installed fonts ---------------------------------------------------------- #

def test_installed_families_offers_every_face_the_machine_has():
    from PySide6.QtGui import QFontDatabase
    from officer.core.ui.fonts import installed_families, PREFERRED_FIRST
    families = installed_families()
    assert set(families) == set(QFontDatabase.families())
    assert len(families) > 8, "a font box with a handful of names is not a font box"
    pinned = {name for name in PREFERRED_FIRST if name in families}
    rest = [family for family in families if family not in pinned]
    assert rest == sorted(rest, key=str.casefold)


def test_installed_families_keeps_office_faces_at_the_top():
    from officer.core.ui.fonts import installed_families, PREFERRED_FIRST
    families = installed_families()
    leading = [name for name in PREFERRED_FIRST if name in families]
    assert families[:len(leading)] == leading


def test_family_chain_keeps_the_requested_font_and_drops_dead_substitutes():
    from officer.core.ui.fonts import family_chain
    chain = family_chain(["NoSuchFont At All", "Also Missing", "DejaVu Sans"])
    assert chain[0] == "NoSuchFont At All", ("the head is what a saved document "
                                             "records, installed or not")
    assert "Also Missing" not in chain
    assert chain[-1] == "DejaVu Sans"


def test_equation_and_body_fonts_land_on_a_face_that_exists():
    from PySide6.QtGui import QFontDatabase
    from officer.core.ui.fonts import body_font, math_font
    installed = set(QFontDatabase.families())
    for font in (body_font(11), math_font(12)):
        assert font.families()[0], "the requested family must survive the chain"
        assert set(font.families()) & installed, "at least one name must render"


def test_rsheet_font_box_lists_installed_families():
    from officer.core.ui.fonts import installed_families
    from officer.rsheet.window import RSheetWindow
    win = RSheetWindow()
    assert win.font_combo.count() == len(installed_families())
    win.close()


def _font_box(q_app, editable: bool):
    """A font picker holding every family the machine has, kept short on screen."""
    from officer.core.ui.fonts import FontListComboBox, installed_families
    combo = FontListComboBox()
    combo.setEditable(editable)
    combo.addItems(installed_families())
    combo.setMaxVisibleItems(8)
    combo.show()
    q_app.processEvents()
    return combo, installed_families()


@pytest.mark.parametrize("editable", [True, False])
def test_the_font_box_opens_with_the_face_in_use_lit_and_in_sight(q_app, editable):
    """Office walks the list to the font you are wearing; so do we.

    An editable box is the hard case: naming a face in its line edit never moves
    the current index, so the popup would open on nothing at all.
    """
    combo, families = _font_box(q_app, editable)
    far_down = families[-1]
    combo.setCurrentText(far_down)
    combo.showPopup()
    q_app.processEvents()
    try:
        row = combo.findText(far_down, Qt.MatchFlag.MatchFixedString)
        assert row == len(families) - 1
        assert combo.view().currentIndex().row() == row, "the entry is highlighted"
        assert combo.view().visualRect(combo.model().index(row, 0)).isValid(), \
            "and the list has scrolled so you can see it"
    finally:
        combo.hidePopup()
        combo.deleteLater()


def test_a_face_that_is_not_on_the_list_does_not_break_the_box(q_app):
    """A document can ask for Calibri on a machine that has none."""
    combo, families = _font_box(q_app, True)
    combo.setCurrentText("A Face This Machine Has Not")
    combo.showPopup()
    q_app.processEvents()
    try:
        assert combo.view().currentIndex().row() == combo.currentIndex()
    finally:
        combo.hidePopup()
        combo.deleteLater()


def test_both_windows_use_the_font_box_that_lights_the_face_in_use():
    """The fix lives in one shared box; both ribbons have to be holding it."""
    from officer.core.ui.fonts import FontListComboBox
    from officer.rsheet.window import RSheetWindow
    from officer.writer.window import WriteRWindow
    windows = [WriteRWindow(), RSheetWindow()]
    try:
        for win in windows:
            assert isinstance(win.font_combo, FontListComboBox)
    finally:
        for win in windows:
            win.close()
