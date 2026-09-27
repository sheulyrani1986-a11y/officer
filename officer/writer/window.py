"""WriteR Main Application Window."""

import os
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QFileDialog, QMessageBox, QComboBox, QSpinBox, QDoubleSpinBox, QMenu,
    QColorDialog, QInputDialog, QLabel, QFontDialog, QDockWidget,
    QListWidget, QListWidgetItem
)
from PySide6.QtGui import (
    QFont, QFontInfo, QKeySequence, QShortcut, QTextCursor, QActionGroup, QColor
)
from officer.core.ui.base_window import OfficeBaseWindow
from officer.core.ui.icons import IconProvider, colour_swatch_icon
from officer.core.io.pdf_exporter import PdfExporter
from officer.core.ui.fonts import FontListComboBox, fill_font_list
from officer.writer.document_view import (
    DocumentWorkspace, MARGIN_PRESETS, PAPER_GROUPS, MM_TO_PX, PX_PER_CM,
    paper_size_caption
)
from officer.writer.io.docx_handler import DocxHandler
from officer.writer.io.odt_handler import OdtHandler
from officer.writer.document_templates import template_named
from officer.writer.page_border import PAGE_BORDERS
from officer.writer.page_border_dialog import PageBorderDialog
from officer.writer.page_color import DEFAULT_PAGE_COLOUR, PAGE_COLOURS
from officer.writer.page_color_dialog import PICTURE_FILTER, PageColorDialog
from officer.writer.header_footer import BAND_SIDES
from officer.writer.header_footer_dialog import HeaderFooterDialog
from officer.writer.watermark import MARK_PRESETS, mark_description
from officer.writer.watermark_dialog import WatermarkDialog
from officer.core.ai.ollama_client import OllamaClient


class WriteRWindow(OfficeBaseWindow):
    """Modern Word Processor Window for OfficeR."""

    has_templates = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(app_name="writer", app_title="WriteR", parent=parent)

        # Set window icon to OfficeR logo
        self.setWindowIcon(IconProvider.get_app_icon())

        # Menus handed to split ribbon buttons must outlive the builder.
        self._ribbon_menus: list = []
        self._line_spacing = 1.0
        #: The gallery's photographs, taken the first time the wall is asked for.
        self._designs: Optional[list] = None

        # Build Document Workspace
        self.workspace = DocumentWorkspace(self)
        self.workspace_layout.addWidget(self.workspace)
        self.page = self.workspace.page

        # Connect status bar & zoom
        self.page.contentStatsChanged.connect(self._on_content_stats_changed)
        self.page.cursorPositionChanged.connect(self._update_page_indicator)
        self.status_bar.zoomChanged.connect(self.page.set_zoom)
        self.status_bar.set_view_modes((
            ("print", "Print Layout", "Print Layout", "view-page-layout",
             lambda: self._set_view_mode("print")),
            ("read", "Read Mode", "Read Mode", "view-read",
             lambda: self._set_view_mode("read")),
            ("web", "Web Layout", "Web Layout", "view-web",
             lambda: self._set_view_mode("web")),
        ))

        # Register shortcuts for font size, ruler, equation
        QShortcut(QKeySequence("Ctrl+["), self, activated=self.page.decrease_font_size)
        QShortcut(QKeySequence("Ctrl+]"), self, activated=self.page.increase_font_size)
        QShortcut(QKeySequence("Ctrl+="), self, activated=self._show_equation_dialog)
        QShortcut(QKeySequence("Ctrl+Shift+R"), self, activated=self._toggle_ruler)
        QShortcut(QKeySequence("Ctrl+L"), self,
                  activated=lambda: self.page.set_alignment(Qt.AlignmentFlag.AlignLeft))
        QShortcut(QKeySequence("Ctrl+E"), self,
                  activated=lambda: self.page.set_alignment(Qt.AlignmentFlag.AlignCenter))
        QShortcut(QKeySequence("Ctrl+R"), self,
                  activated=lambda: self.page.set_alignment(Qt.AlignmentFlag.AlignRight))
        QShortcut(QKeySequence("Ctrl+J"), self,
                  activated=lambda: self.page.set_alignment(Qt.AlignmentFlag.AlignJustify))
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._find_text)
        QShortcut(QKeySequence("Ctrl+H"), self, activated=self._replace_text)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self.page.insert_page_break)
        QShortcut(QKeySequence("Ctrl+Shift+L"), self, activated=self.page.set_bullet_list)
        QShortcut(QKeySequence("Ctrl+Shift+P"), self, activated=self.page.set_numbered_list)

        # Local Ollama AI client
        self.ai_client = OllamaClient(parent=self)

        # Build Ribbon Interface
        self._build_ribbon()

        # Initial Document State
        self._on_content_stats_changed(0, 0)
        self.page.document().modificationChanged.connect(
            lambda mod: self._on_clean_changed(not mod)
        )

    def _build_ribbon(self) -> None:
        """Construct Word's ribbon: Home, Insert, Layout, References, View, AI."""
        self._build_home_tab()
        self._build_insert_tab()
        self._build_layout_tab()
        self._build_references_tab()
        self._build_view_tab()
        self._build_ai_tab()
        self._build_picture_tab()

    # ------------------------------------------------------------------ Home #

    def _populate_font_list(self) -> None:
        """Offer every family fontconfig reports, each name drawn in its own face."""
        fill_font_list(self.font_combo)

    def _sync_font_box(self) -> None:
        """Show the caret's face and size in Home ▸ Font, the way Word does.

        Signals are blocked: reflecting the document is not a formatting command,
        and re-applying it would rewrite the very format it just read.
        """
        size = round(self.page.current_font_point_size())
        if size and self.size_spin.value() != size:
            self.size_spin.blockSignals(True)
            self.size_spin.setValue(size)
            self.size_spin.blockSignals(False)
        family = self.page.current_font_family()
        if family and self.font_combo.findText(family, Qt.MatchFlag.MatchFixedString) < 0:
            # Word's box names the face actually on screen. A document can ask
            # for Calibri on a machine that has none, and showing that dead name
            # would list nothing the reader can pick again.
            family = QFontInfo(self.page.font()).family()
        if family and self.font_combo.currentText() != family:
            self.font_combo.blockSignals(True)
            self.font_combo.setCurrentText(family)
            self.font_combo.blockSignals(False)

    def _build_home_tab(self) -> None:
        tab = self.ribbon.add_tab("Home")

        # 1. Clipboard -------------------------------------------------------- #
        clip_grp = tab.add_group("Clipboard")
        clip_grp.add_button("Paste", "paste", large=True, on_click=self.page.paste,
                            tooltip="Paste (Ctrl+V)")
        clip_col = clip_grp.add_column()
        clip_grp.add_button_to(clip_col, "Cut", "cut", large=False, on_click=self.page.cut)
        clip_grp.add_button_to(clip_col, "Copy", "copy", large=False, on_click=self.page.copy)
        clip_grp.add_button_to(clip_col, "Format\nPainter", "paintbrush", large=False,
                               on_click=self.page.clear_character_format)

        # 2. Font ------------------------------------------------------------- #
        font_grp = tab.add_group("Font")
        font_col = font_grp.add_column()

        row1 = font_grp.add_sub_row(font_col)
        self.font_combo = FontListComboBox(self)
        self.font_combo.setEditable(True)
        self.font_combo.setFixedWidth(160)
        self.font_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_combo.setMaxVisibleItems(18)
        self.font_combo.setToolTip("Font")
        self._populate_font_list()
        # activated (not currentTextChanged): typing a name should apply once,
        # on Enter or on picking from the list, not on every keystroke.
        self.font_combo.textActivated.connect(self.page.set_font_family)
        row1.addWidget(self.font_combo)

        self.size_spin = QSpinBox(self)
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(11)
        self.size_spin.valueChanged.connect(self.page.set_font_size)
        self.size_spin.setFixedWidth(46)
        self.size_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.size_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        row1.addWidget(self.size_spin)
        self.page.cursorPositionChanged.connect(self._sync_font_box)
        self._sync_font_box()

        row2 = font_grp.add_sub_row(font_col)
        # Word draws these as the glyph itself, so the icon carries the command
        # and only a tooltip/accessibility name is added beside it.
        for label, icon, slot in (
            ("Bold", "bold", self.page.set_bold),
            ("Italic", "italic", self.page.set_italic),
            ("Underline", "underline", self.page.set_underline),
            ("Strikethrough", "strikethrough", self.page.set_strikethrough),
            ("Font Color", "font-color", self._choose_font_color),
            ("Text Highlight Color", "text-highlight", self._choose_highlight_color),
            ("Grow Font", "font-grow", self.page.increase_font_size),
            ("Shrink Font", "font-shrink", self.page.decrease_font_size),
        ):
            btn = font_grp.add_button_to(row2, "", icon, large=False, on_click=slot)
            btn.setToolTip(f"{label} (Ctrl+{label[0]})" if label[0] in "BIU" else label)
            btn.setAccessibleName(label)
            btn.setMinimumWidth(28)
        font_grp.set_dialog_launcher(self._show_font_dialog)

        # 3. Paragraph -------------------------------------------------------- #
        para_grp = tab.add_group("Paragraph")
        para_col = para_grp.add_column()

        align_row = para_grp.add_sub_row(para_col)
        for icon, align, label in (
            ("align-left", Qt.AlignmentFlag.AlignLeft, "Align Left (Ctrl+L)"),
            ("align-center", Qt.AlignmentFlag.AlignCenter, "Center (Ctrl+E)"),
            ("align-right", Qt.AlignmentFlag.AlignRight, "Align Right (Ctrl+R)"),
            ("align-justify", Qt.AlignmentFlag.AlignJustify, "Justify (Ctrl+J)"),
        ):
            btn = para_grp.add_button_to(align_row, "", icon, large=False,
                                         on_click=lambda _=False, a=align: self.page.set_alignment(a))
            btn.setToolTip(label)
            btn.setFixedWidth(30)

        list_row = para_grp.add_sub_row(para_col)
        para_grp.add_button_to(list_row, "Bullets", "bullets", large=False,
                               on_click=self.page.set_bullet_list)
        para_grp.add_button_to(list_row, "Numbering", "numbering", large=False,
                               on_click=self.page.set_numbered_list)
        para_grp.add_button_to(list_row, "", "indent-less", large=False,
                               on_click=lambda: self.page.set_indent(-1))
        para_grp.add_button_to(list_row, "", "indent-more", large=False,
                               on_click=lambda: self.page.set_indent(1))
        para_grp.add_button_to(list_row, "", "line-spacing", large=False,
                               on_click=self._cycle_line_spacing)
        para_grp.set_dialog_launcher(self._show_paragraph_dialog)

        # 4. Styles ----------------------------------------------------------- #
        style_grp = tab.add_group("Styles")
        style_col = style_grp.add_column()
        style_top = style_grp.add_sub_row(style_col)
        style_bottom = style_grp.add_sub_row(style_col)
        # Word's gallery previews each style in its own typeface rather than
        # putting an icon next to the name.
        for index, (label, level, preview) in enumerate((
            ("Normal", 0, ("Calibri", 11, False, False)),
            ("Heading 1", 1, ("Calibri Light", 13, True, False)),
            ("Heading 2", 2, ("Calibri Light", 12, True, False)),
            ("Heading 3", 3, ("Calibri Light", 11, True, True)),
            ("Title", 1, ("Calibri Light", 16, False, False)),
            ("Subtitle", 2, ("Calibri Light", 12, False, True)),
            ("Quote", 3, ("Calibri", 11, False, True)),
            ("Intense Quote", 1, ("Calibri Light", 11, True, True)),
        )):
            btn = style_grp.add_button_to(
                style_top if index < 4 else style_bottom, label, None, large=False)
            family, point, bold, italic = preview
            # Only font properties go here; the shared #RibbonCompact rule keeps
            # supplying the padding and hover/pressed colours.
            btn.setStyleSheet(
                "QToolButton {{ font-family:'{0}'; font-size:{1}pt; font-weight:{2};"
                "font-style:{3}; }}".format(
                    family, point, "bold" if bold else "normal",
                    "italic" if italic else "normal"))
            btn.clicked.connect(lambda _=False, l=level: self.page.apply_heading(l))
        style_grp.set_dialog_launcher(self._show_styles_dialog)

        # 5. Editing ---------------------------------------------------------- #
        edit_grp = tab.add_group("Editing")
        edit_grp.add_button("Find", "find", large=True, on_click=self._find_text,
                            tooltip="Find (Ctrl+F)")
        edit_col = edit_grp.add_column()
        edit_grp.add_button_to(edit_col, "Replace", "replace", large=False,
                               on_click=self._replace_text)
        edit_grp.add_button_to(edit_col, "Select All", "select-all", large=False,
                               on_click=self.page.selectAll)

    # ---------------------------------------------------------------- Insert #

    def _build_insert_tab(self) -> None:
        tab = self.ribbon.add_tab("Insert")

        pages_grp = tab.add_group("Pages")
        pages_grp.add_button("Page Break", "page-break", large=True,
                             on_click=self.page.insert_page_break,
                             tooltip="Start a new page (Ctrl+Enter)")

        table_grp = tab.add_group("Tables")
        table_menu = QMenu(table_grp)
        for rows, cols in ((2, 2), (3, 3), (4, 4), (5, 5)):
            table_menu.addAction(f"{rows}x{cols}",
                                 lambda _=False, r=rows, c=cols: self.page.insert_table(r, c))
        table_menu.addSeparator()
        table_menu.addAction("Insert Table...", self._insert_table_dialog)
        self._ribbon_menus.append(table_menu)
        table_grp.add_split_button("Table", "table", table_menu, large=True,
                                   on_click=lambda: self.page.insert_table(2, 2))

        media_grp = tab.add_group("Illustrations")
        media_grp.add_button("Pictures", "image", large=True,
                             on_click=self._insert_image_dialog)

        shapes = QMenu(media_grp)
        for label, shape in (
            ("Rectangle", "rectangle"), ("Rounded Rectangle", "rounded_rectangle"),
            ("Ellipse", "ellipse"), ("Triangle", "triangle"),
            ("Diamond", "diamond"), ("Five-point Star", "star"),
            ("Arrow", "arrow"), ("Double Arrow", "double_arrow"),
            ("Callout", "callout"), ("Line", "line"),
        ):
            shapes.addAction(IconProvider.get_icon(
                {"rectangle": "shape", "rounded_rectangle": "rounded-rect",
                 "ellipse": "ellipse", "triangle": "shape-triangle",
                 "diamond": "shape-diamond", "star": "shape-star",
                 "arrow": "shape-arrow", "double_arrow": "shape-double-arrow",
                 "callout": "text-box", "line": "line-shape"}[shape],
                size=16), label, lambda _=False, s=shape: self._insert_shape(s))
        self._ribbon_menus.append(shapes)
        media_grp.add_split_button("Shapes", "shape", shapes, large=False,
                                   on_click=lambda: self._insert_shape("rectangle"))
        media_grp.set_dialog_launcher(self._insert_image_dialog)

        sym_grp = tab.add_group("Symbols")
        sym_grp.add_button("Symbol", "text:Ω", large=True, on_click=self._insert_symbol_dialog)
        sym_grp.add_button("Equation", "equation", large=True,
                           on_click=self._show_equation_dialog)

        text_grp = tab.add_group("Text")
        text_grp.add_button("Hyperlink", "hyperlink", large=True,
                            on_click=self._insert_hyperlink)
        text_grp.add_button("Word Count", "book", large=True, on_click=self._show_word_count)

        # Word's Header & Footer gallery edits the bands the paper wears, which
        # is a dialog here rather than a mode: the page is one text column, so
        # there is no in-place caret to move into a margin.
        band_grp = tab.add_group("Header & Footer")
        bands = QMenu(band_grp)
        bands.setObjectName("header-footer")
        bands.addAction("Edit Header and Footer…", self._header_footer_dialog)
        bands.addSeparator()
        for kind in ("header", "footer"):
            bands.addAction(f"Remove the {kind}",
                            lambda _=False, k=kind: self._remove_band(k))
        self._ribbon_menus.append(bands)
        band_grp.add_split_button("Header and\nFooter", "header-footer", bands,
                                  large=True, on_click=self._header_footer_dialog)

    # ---------------------------------------------------------------- Layout #

    def _build_layout_tab(self) -> None:
        """Word's Layout tab, where every command is a real split menu."""
        tab = self.ribbon.add_tab("Layout")

        setup_grp = tab.add_group("Page Setup")
        setup_grp.add_button("Templates", "templates", large=True,
                             on_click=self.open_template_gallery,
                             tooltip="Start the document from one of WriteR's designs")
        setup_col = setup_grp.add_column()

        margins = QMenu(setup_grp)
        for name, px in MARGIN_PRESETS.items():
            margins.addAction(name, lambda _=False, m=px: self.page.set_margin_pixels(m))
        self._ribbon_menus.append(margins)
        setup_grp.add_split_button("Margins", "margins", margins, large=False,
                                   on_click=lambda: self._margin_dialog())

        orientation = QMenu(setup_grp)
        orientation.addAction("Portrait", lambda: self.page.set_landscape(False))
        orientation.addAction("Landscape", lambda: self.page.set_landscape(True))
        self._ribbon_menus.append(orientation)
        setup_grp.add_split_button("Orientation", "orientation", orientation, large=False,
                                   on_click=lambda: self.page.set_landscape(
                                       not self.page.landscape))

        size_menu = QMenu(setup_grp)
        size_menu.setObjectName("paper-size")
        for index, (group, names) in enumerate(PAPER_GROUPS):
            if index:
                size_menu.addSeparator()
            for name in names:
                size_menu.addAction(paper_size_caption(name),
                                    lambda _=False, n=name: self.page.set_paper(n))
        self._ribbon_menus.append(size_menu)
        setup_grp.add_split_button("Size", "paper-size", size_menu, large=False,
                                   on_click=lambda: self.page.set_paper("Letter"))

        breaks = QMenu(setup_grp)
        breaks.addAction("Page Break", self.page.insert_page_break)
        breaks.addAction("Column Break", self.page.insert_page_break)
        breaks.addAction("Text Wrapping Break", lambda: self.page.textCursor().insertText(" "))
        self._ribbon_menus.append(breaks)
        setup_grp.add_split_button("Breaks", "page-break", breaks, large=False,
                                   on_click=self.page.insert_page_break)

        borders = QMenu(setup_grp)
        borders.setObjectName("page-border")
        for key in ("none", "box", "shadow", "double", "dashed", "dotted"):
            borders.addAction(PAGE_BORDERS[key][0],
                              lambda _=False, k=key: self.page.set_page_border(
                                  style=k))
        borders.addSeparator()
        borders.addAction("Page Borders and Designs…", self._page_border_dialog)
        self._ribbon_menus.append(borders)
        setup_grp.add_split_button("Page Borders", "page-border", borders,
                                   large=False, on_click=self._page_border_dialog)

        colour_menu = QMenu(setup_grp)
        colour_menu.setObjectName("page-colour")
        for name, hex_value in PAGE_COLOURS.items():
            action = colour_menu.addAction(
                name, lambda _=False, c=hex_value: self._set_page_colour(c))
            if hex_value != "none":
                action.setIcon(colour_swatch_icon(hex_value))
        colour_menu.addSeparator()
        colour_menu.addAction("More Colours…", self._more_page_colours)
        colour_menu.addAction("Picture…", self._page_picture)
        self._ribbon_menus.append(colour_menu)
        setup_grp.add_split_button("Page Colour", "page-colour", colour_menu,
                                   large=False, on_click=self._page_colour_dialog)

        marks = QMenu(setup_grp)
        marks.setObjectName("watermark")
        marks.addAction("Remove Watermark", self._remove_watermark)
        marks.addSeparator()
        for name, words in MARK_PRESETS:
            marks.addAction(name, lambda _=False, t=words:
                            self.page.set_watermark(kind="text", text=t))
        marks.addSeparator()
        marks.addAction("Picture…", self._watermark_picture)
        marks.addAction("Custom Watermark…", self._watermark_dialog)
        self._ribbon_menus.append(marks)
        setup_grp.add_split_button("Watermark", "watermark", marks,
                                   large=False, on_click=self._watermark_dialog)

        para_grp = tab.add_group("Paragraph")
        pcol = para_grp.add_column()
        spacing = QMenu(para_grp)
        for label, multiple in (("1.0", 1.0), ("1.15", 1.15), ("1.5", 1.5), ("2.0", 2.0)):
            spacing.addAction(label, lambda _=False, m=multiple: self.page.set_line_spacing(m))
        self._ribbon_menus.append(spacing)
        para_grp.add_split_button("Line Spacing", "line-spacing", spacing, large=False,
                                  on_click=self._cycle_line_spacing)
        indent = QMenu(para_grp)
        indent.addAction("Increase Indent", lambda: self.page.set_indent(1))
        indent.addAction("Decrease Indent", lambda: self.page.set_indent(-1))
        self._ribbon_menus.append(indent)
        para_grp.add_split_button("Indent", "indent-more", indent, large=False,
                                  on_click=lambda: self.page.set_indent(1))

    # ------------------------------------------------------------ References #

    def _build_references_tab(self) -> None:
        tab = self.ribbon.add_tab("References")

        toc_grp = tab.add_group("Table of Contents")
        toc_grp.add_button("Table of\nContents", "toc", large=True,
                           on_click=self._insert_toc)

        cite_grp = tab.add_group("Captions")
        cite_grp.add_button("Insert\nCaption", "caption", large=True,
                            on_click=self._insert_caption)

        review_grp = tab.add_group("Proofing")
        review_grp.add_button("Word\nCount", "book", large=True,
                              on_click=self._show_word_count)

    # ------------------------------------------------------------------ View #

    def _build_view_tab(self) -> None:
        tab = self.ribbon.add_tab("View")

        view_grp = tab.add_group("Views")
        self._view_buttons = {}
        for label, icon, mode in (
            ("Print Layout", "view-page-layout", "print"),
            ("Read Mode", "view-read", "read"),
            ("Web Layout", "view-web", "web"),
        ):
            btn = view_grp.add_button(label, icon, large=True,
                                      on_click=lambda _=False, m=mode: self._set_view_mode(m))
            btn.setCheckable(True)
            self._view_buttons[mode] = btn
        self._view_buttons["print"].setChecked(True)

        show_grp = tab.add_group("Show")
        self.ruler_btn = show_grp.add_button("Ruler", "ruler", large=False,
                                             on_click=self._toggle_ruler, checkable=True)
        self.ruler_btn.setChecked(True)
        show_grp.add_button_to(show_grp.add_column(), "Outline", "view-outline",
                               large=False, on_click=self._show_outline_pane)

        zoom_grp = tab.add_group("Zoom")
        zoom_grp.add_button("100%", "zoom-fit", large=True,
                            on_click=lambda: self.status_bar.set_zoom(100))
        zcol = zoom_grp.add_column()
        zoom_grp.add_button_to(zcol, "Zoom In", "zoom-in", large=False,
                               on_click=lambda: self.status_bar.set_zoom(
                                   self.status_bar.zoom_percent() + 15))
        zoom_grp.add_button_to(zcol, "Zoom Out", "zoom-out", large=False,
                               on_click=lambda: self.status_bar.set_zoom(
                                   self.status_bar.zoom_percent() - 15))
        zoom_grp.add_button_to(zcol, "One Page", "fit-page", large=False,
                               on_click=self._fit_page)

    def _build_ai_tab(self) -> None:
        tab = self.ribbon.add_tab("AI Assist")

        ai_grp = tab.add_group("Local AI (Ollama)")
        ai_grp.add_button("Proofread", "ai", large=True, on_click=self._ai_proofread)
        ai_grp.add_button("Summarize", "ai", large=True, on_click=self._ai_summarize)
        ai_grp.add_button("Rewrite", "ai", large=True, on_click=self._ai_rewrite)

    # ------------------------------------------------- Picture Format (contextual) #

    PICTURE_WRAPS = {
        "inline": "In Line with Text",
        "top_bottom": "Top and Bottom",
        "left": "Square - Left",
        "right": "Square - Right",
    }

    def _build_picture_tab(self) -> None:
        """Word's Picture Format tab, for whichever picture is being worked on.

        Two kinds answer to it. A picture that is a character in the sentence is
        moved with the align buttons and the wrap menu. A picture that lies on
        the sheet is dragged about the page, placed by the two centimetre boxes,
        put in front of or behind its neighbours, and either lets the words run
        round it or lets them lie under it.
        """
        tab = self.ribbon.add_tab("Picture Format")
        self._applying_picture_size = False

        size_grp = tab.add_group("Size")
        size_col = size_grp.add_column()
        self.pic_height_spin = self._add_picture_box(size_grp, size_col, "Height:")
        self.pic_width_spin = self._add_picture_box(size_grp, size_col, "Width:")
        self.pic_height_spin.valueChanged.connect(self._picture_height_changed)
        self.pic_width_spin.valueChanged.connect(self._picture_width_changed)
        size_row = size_grp.add_sub_row(size_col)
        reset = size_grp.add_button_to(size_row, "Reset Size", None, large=False,
                                       on_click=self._reset_picture_size)
        reset.setToolTip("Return to the picture's own size")
        grow = size_grp.add_button_to(size_row, "Grow", "font-grow", large=False,
                                      on_click=lambda: self._scale_picture(1.1))
        grow.setToolTip("Enlarge by 10%")
        shrink = size_grp.add_button_to(size_row, "Shrink", "font-shrink", large=False,
                                        on_click=lambda: self._scale_picture(1 / 1.1))
        shrink.setToolTip("Reduce by 10%")

        wrap_grp = tab.add_group("Wrap Text")
        wrap_menu = QMenu(wrap_grp)
        wrap_group = QActionGroup(wrap_menu)
        wrap_group.setExclusive(True)
        self._picture_wrap_buttons = {}
        for mode, caption in self.PICTURE_WRAPS.items():
            action = wrap_group.addAction(wrap_menu.addAction(caption))
            action.setCheckable(True)
            action.triggered.connect(lambda _=False, m=mode: self.page.set_picture_wrap(m))
            self._picture_wrap_buttons[mode] = action
        self._ribbon_menus.append(wrap_menu)
        wrap_grp.add_split_button("Wrap Text", "wrap-text", wrap_menu, large=True,
                                  on_click=lambda: self.page.set_picture_wrap("inline"))

        place_grp = tab.add_group("Position")
        place_col = place_grp.add_column()
        place_row = place_grp.add_sub_row(place_col)
        self._picture_align_buttons = []
        for icon, align, caption in (
            ("align-left", Qt.AlignmentFlag.AlignLeft, "Align Left"),
            ("align-center", Qt.AlignmentFlag.AlignCenter, "Center"),
            ("align-right", Qt.AlignmentFlag.AlignRight, "Align Right"),
        ):
            btn = place_grp.add_button_to(place_row, "", icon, large=False,
                                          on_click=lambda _=False, a=align:
                                          self.page.set_picture_alignment(a))
            btn.setToolTip(caption)
            btn.setAccessibleName(caption)
            btn.setFixedWidth(30)
            self._picture_align_buttons.append(btn)

        sheet_grp = tab.add_group("On the page")
        sheet_col = sheet_grp.add_column()
        self.pic_x_spin = self._add_picture_box(sheet_grp, sheet_col, "From left:",
                                                minimum=0.0)
        self.pic_y_spin = self._add_picture_box(sheet_grp, sheet_col, "From top:",
                                                minimum=0.0)
        self.pic_x_spin.valueChanged.connect(
            lambda cm: self._picture_place_changed("x", cm))
        self.pic_y_spin.valueChanged.connect(
            lambda cm: self._picture_place_changed("y", cm))
        sheet_row = sheet_grp.add_sub_row(sheet_col)
        self._picture_wrap_toggle = sheet_grp.add_button_to(
            sheet_row, "Text Round It", "wrap-text", large=False, checkable=True,
            on_click=self._float_wrap_clicked)
        self._picture_wrap_toggle.setToolTip(
            "Let the writing run round this object, or lie under it")
        for caption, icon, step in (("Bring Forward", "bring-front", 1),
                                   ("Send Backward", "send-back", -1)):
            btn = sheet_grp.add_button_to(sheet_row, "", icon, large=False,
                                          on_click=lambda _=False, s=step:
                                          self._move_float_z(s))
            btn.setToolTip(caption)
            btn.setAccessibleName(caption)
            btn.setFixedWidth(30)
        remove = sheet_grp.add_button_to(sheet_row, "", "remove", large=False,
                                         on_click=self._remove_float)
        remove.setToolTip("Take the object off the sheet")
        remove.setAccessibleName("Remove")
        remove.setFixedWidth(30)

        self._picture_tab_shown = False
        self.ribbon.set_tab_visible("Picture Format", False)
        self.page.cursorPositionChanged.connect(self._sync_picture_tab)
        self.page.floatSelectionChanged.connect(self._sync_picture_tab)
        self.page.floatGeometryChanged.connect(self._sync_picture_tab)

    def _add_picture_box(self, group, column, caption: str,
                         minimum: float = 0.20) -> QDoubleSpinBox:
        """One centimetre box with its caption, as Office draws the Size group."""
        row = group.add_sub_row(column)
        label = QLabel(caption, group)
        label.setStyleSheet("color: #6B7280; font-size: 11px;")
        row.addWidget(label)
        box = QDoubleSpinBox(group)
        box.setRange(minimum, 60.00)
        box.setDecimals(2)
        box.setSingleStep(0.10)
        box.setSuffix(" cm")
        box.setFixedWidth(78)
        box.setToolTip(caption.rstrip(":") + " in centimetres")
        row.addWidget(box)
        return box

    def _sync_picture_tab(self) -> None:
        """Put the chosen picture into the tab, and hide it when there is none."""
        placed = self.page.float_info()
        info = self.page.picture_info()
        self.ribbon.set_tab_visible("Picture Format", placed is not None
                                    or info is not None)
        if placed is None and info is None:
            self._picture_tab_shown = False
            return
        edges = placed or info
        self._show_picture_value(self.pic_width_spin, edges["width_cm"])
        self._show_picture_value(self.pic_height_spin, edges["height_cm"])
        # The two models hold the same picture differently: an object on the
        # sheet has a place, a character in the sentence has an alignment.
        for box in (self.pic_x_spin, self.pic_y_spin):
            box.setEnabled(placed is not None)
        for button in self._picture_align_buttons:
            button.setEnabled(placed is None)
        for button in self._picture_wrap_buttons.values():
            button.setEnabled(placed is None)
        self._picture_wrap_toggle.setEnabled(placed is not None)
        if placed is not None:
            self._show_picture_value(self.pic_x_spin, placed["x_cm"])
            self._show_picture_value(self.pic_y_spin, placed["y_cm"])
            self._picture_wrap_toggle.setChecked(placed["wrap"])
        else:
            for mode, button in self._picture_wrap_buttons.items():
                button.setChecked(mode == info["wrap"])
        if not self._picture_tab_shown:
            # Word walks you to the tab the moment a picture becomes the thing
            # you are working on; afterwards you may browse elsewhere.
            self.ribbon.select_tab("Picture Format")
            self._picture_tab_shown = True

    @staticmethod
    def _show_picture_value(box: QDoubleSpinBox, centimetres: float) -> None:
        # Reflecting the document is not an edit, so the box must not fire the
        # command that would re-format the picture it just measured.
        box.blockSignals(True)
        box.setValue(round(centimetres, 2))
        box.blockSignals(False)

    def _picture_width_changed(self, centimetres: float) -> None:
        if self._applying_picture_size:
            return
        self._apply_picture_size("width", centimetres)

    def _picture_height_changed(self, centimetres: float) -> None:
        if self._applying_picture_size:
            return
        self._apply_picture_size("height", centimetres)

    def _apply_picture_size(self, edge: str, centimetres: float) -> None:
        """Resize along one edge; the other follows, so the picture never distorts."""
        self._applying_picture_size = True
        try:
            if self.page.float_info() is not None:
                if edge == "width":
                    self.page.set_float_geometry(width_cm=centimetres)
                else:
                    self.page.set_float_geometry(height_cm=centimetres)
            elif edge == "width":
                self.page.set_picture_size(width_cm=centimetres)
            else:
                self.page.set_picture_size(height_cm=centimetres)
        finally:
            self._applying_picture_size = False
        self._sync_picture_tab()

    def _scale_picture(self, factor: float) -> None:
        """Grow or shrink whichever picture is being worked on."""
        placed = self.page.float_info()
        if placed is not None:
            self.page.set_float_geometry(
                width_cm=placed["width_cm"] * factor,
                height_cm=placed["height_cm"] * factor)
        else:
            self.page.scale_picture(factor)
        self._sync_picture_tab()

    def _reset_picture_size(self) -> None:
        placed = self.page.float_info()
        if placed is not None and placed["natural"] is not None:
            natural = placed["natural"]
            self.page.set_float_geometry(width_cm=natural[0] / PX_PER_CM)
        else:
            self.page.reset_picture_size()
        self._sync_picture_tab()

    def _picture_place_changed(self, edge: str, centimetres: float) -> None:
        if self._applying_picture_size:
            return
        self._applying_picture_size = True
        try:
            self.page.set_float_geometry(**{edge + "_cm": centimetres})
        finally:
            self._applying_picture_size = False
        self._sync_picture_tab()

    def _float_wrap_clicked(self, wraps: bool) -> None:
        if self.page.set_float_wrap(wraps):
            self._sync_picture_tab()

    def _move_float_z(self, step: int) -> None:
        if not self.page.move_float_z(step):
            self.status_bar.showMessage(
                f"There is nothing to move this object {'in front of' if step > 0 else 'behind'}.",
                3000)

    def _remove_float(self) -> None:
        if self.page.remove_float():
            self._sync_picture_tab()

    def _toggle_ruler(self) -> None:
        """Toggle the horizontal document ruler (Ctrl+R)."""
        visible = not self.workspace.ruler.isVisible()
        self.workspace.set_ruler_visible(visible)
        self.ruler_btn.setChecked(visible)

    # --- Font / paragraph dialogs (the group launchers) --------------------- #

    def _choose_font_color(self) -> None:
        color = QColorDialog.getColor(Qt.GlobalColor.black, self, "Font Color")
        if color.isValid():
            self.page.set_text_color(color.name())

    def _choose_highlight_color(self) -> None:
        color = QColorDialog.getColor(QColor("#FFF3A3"), self, "Text Highlight Color")
        if color.isValid():
            self.page.set_highlight_color(color.name())

    def _show_font_dialog(self) -> None:
        family, ok = QFontDialog.getFont(self, "Font")
        if ok:
            self.page.set_font_family(family.family())
            if family.pointSizeF() > 0:
                self.page.set_font_size(family.pointSizeF())

    def _show_paragraph_dialog(self) -> None:
        choices = ["Single", "1.15", "1.5", "Double"]
        value, ok = QInputDialog.getItem(self, "Paragraph", "Line spacing:", choices, 0, False)
        if ok:
            self.page.set_line_spacing({"Single": 1.0, "1.15": 1.15,
                                        "1.5": 1.5, "Double": 2.0}[value])

    def _show_styles_dialog(self) -> None:
        styles = ["Normal", "Heading 1", "Heading 2", "Heading 3"]
        value, ok = QInputDialog.getItem(self, "Styles", "Apply style:", styles, 0, False)
        if ok:
            self.page.apply_heading(styles.index(value))

    def _cycle_line_spacing(self) -> None:
        """Word's line-spacing toggle walks 1.0 -> 1.15 -> 1.5 -> 2.0."""
        steps = [1.0, 1.15, 1.5, 2.0]
        try:
            index = steps.index(self._line_spacing)
        except ValueError:
            index = -1
        self._line_spacing = steps[(index + 1) % len(steps)]
        self.page.set_line_spacing(self._line_spacing)
        self.status_bar.showMessage(f"Line spacing: {self._line_spacing}", 2000)

    # --- Insert commands ---------------------------------------------------- #

    def _insert_table_dialog(self) -> None:
        rows, ok1 = QInputDialog.getInt(self, "Insert Table", "Number of Rows:", 3, 1, 50)
        if not ok1:
            return
        cols, ok2 = QInputDialog.getInt(self, "Insert Table", "Number of Columns:", 3, 1, 20)
        if ok2:
            self.page.insert_table(rows, cols)

    def _insert_image_dialog(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Insert Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.svg)"
        )
        if filepath:
            self.page.insert_float(filepath)

    def _insert_symbol_dialog(self) -> None:
        symbols = list("©®™°±×÷≤≥≠≈∞µΩπ•·—–‘’“”…‹›")
        value, ok = QInputDialog.getItem(self, "Symbol", "Insert character:", symbols, 0, False)
        if ok and value:
            self.page.insertPlainText(value)

    def _insert_hyperlink(self) -> None:
        cursor = self.page.textCursor()
        selected = cursor.selectedText().strip()
        url, ok = QInputDialog.getText(self, "Insert Hyperlink", "Address (URL):",
                                       text=selected or "https://")
        if not ok or not url.strip():
            return
        text = selected or url.strip()
        cursor.insertHtml(f'<a href="{url.strip()}">{text}</a>')
        self.page.setTextCursor(cursor)

    def _show_equation_dialog(self) -> None:
        """Open the equation editor dialog (Ctrl+=)."""
        from officer.writer.equation_dialog import EquationDialog
        dlg = EquationDialog(self)
        if not dlg.exec():
            return
        image_path = dlg.rendered_image_path()
        if image_path:
            self.page.insert_image(image_path)
        elif dlg.equation_text():
            self.page.insert_equation(dlg.equation_text())

    def _insert_shape(self, shape_type: str) -> None:
        """Render *shape_type* as an object lying on the sheet.

        The shape lands at Word's own size for that shape, beside the caret, and
        the writing runs round it. Picture Format then moves, stretches and
        re-stacks it like any other object.
        """
        from officer.writer.shape_insert import SHAPE_SIZES_CM, render_shape_to_temp
        wide_cm, tall_cm = SHAPE_SIZES_CM.get(shape_type, (6.0, 4.0))
        image_path = render_shape_to_temp(shape_type, width_cm=wide_cm,
                                          height_cm=tall_cm,
                                          fill="#5B8CCC", stroke="#1E40AF")
        if image_path:
            self.page.insert_float(image_path, width_cm=wide_cm,
                                   height_cm=tall_cm)

    # --- Layout commands ---------------------------------------------------- #

    def _margin_dialog(self) -> None:
        inches, ok = QInputDialog.getDouble(
            self, "Margins", "Margin (inches):",
            self.page.margin_pixels / 96.0, 0.25, 4.0, 2)
        if ok:
            self.page.set_margin_pixels(inches * 96)

    def _page_border_dialog(self) -> None:
        """Word's Page Borders dialog, put on every sheet of the page."""
        dialog = PageBorderDialog(self.page.page_border(), self)
        if dialog.exec():
            self.page.set_page_border(**dialog.border())

    def _set_page_colour(self, colour: str) -> None:
        """An ink from the gallery; ``none`` puts the paper back as it came."""
        if colour == "none":
            self.page.set_page_colour(kind="none")
        else:
            self.page.set_page_colour(kind="solid", colour=colour)

    def _more_page_colours(self) -> None:
        """Any ink at all, from the colour picker."""
        start = self.page.page_colour()["colour"]
        if start == "none":
            start = DEFAULT_PAGE_COLOUR
        colour = QColorDialog.getColor(QColor(start), self, "Page Color")
        if colour.isValid():
            self.page.set_page_colour(kind="solid", colour=colour.name())

    def _page_picture(self) -> None:
        """Dress the paper with a picture straight from a file.

        A picture the page cannot read falls back to the ink it was asked to
        replace, so the check is on what the page ended up wearing.
        """
        path, _ = QFileDialog.getOpenFileName(self, "Picture for Page", "",
                                             PICTURE_FILTER)
        if not path:
            return
        self.page.set_page_colour(image_path=path, kind="picture")
        if self.page.page_colour()["kind"] != "picture":
            QMessageBox.warning(self, "Picture for Page",
                                f"{path} could not be read as a picture.")

    def _page_colour_dialog(self) -> None:
        """Word's Page Color dialog: an ink, or a picture and its fade."""
        dialog = PageColorDialog(self.page.page_colour(), self)
        if dialog.exec():
            self.page.set_page_colour(**dialog.colour())

    # --- Watermark --------------------------------------------------------- #

    def _watermark_dialog(self) -> None:
        """Word's Printed Watermark dialog: a word across the paper, or a
        picture washed into it."""
        dialog = WatermarkDialog(self.page.watermark(), self)
        if not dialog.exec():
            return
        mark = dialog.mark()
        if self.page.set_watermark(**mark):
            self.status_bar.showMessage(mark_description(mark), 3000)
        else:
            QMessageBox.warning(self, "Printed Watermark",
                                "The sheet kept the mark it wore: the picture "
                                "chosen could not be read.")

    def _remove_watermark(self) -> None:
        self.page.remove_watermark()
        self.status_bar.showMessage("Watermark removed.", 3000)

    def _watermark_picture(self) -> None:
        """Mark the paper with a picture straight from a file."""
        path, _ = QFileDialog.getOpenFileName(self, "Picture for Watermark",
                                              "", PICTURE_FILTER)
        if not path:
            return
        if self.page.set_watermark(image_path=path, kind="picture"):
            self.status_bar.showMessage(
                f"Watermark set to {os.path.basename(path)}.", 3000)
        else:
            QMessageBox.warning(self, "Picture for Watermark",
                                f"{path} could not be read as a picture.")

    # --- Header and footer -------------------------------------------------- #

    def _header_footer_dialog(self) -> None:
        """Write what the top and the bottom of every sheet are to carry."""
        dialog = HeaderFooterDialog(self.page.header_footer(), self)
        if not dialog.exec():
            return
        bands = dialog.bands()
        self.page.set_header_footer(**bands)
        self.status_bar.showMessage(dialog.description(), 4000)

    def _remove_band(self, kind: str) -> None:
        """Empty one band, leaving the other to say what it says."""
        self.page.set_header_footer(
            **{kind: {side: "" for side in BAND_SIDES}})
        self.status_bar.showMessage(f"{kind.capitalize()} removed.", 3000)

    # --- References commands ------------------------------------------------ #

    def _insert_toc(self) -> None:
        """Build a table of contents from the document's headings."""
        document = self.page.document()
        entries = []
        block = document.begin()
        while block.isValid():
            fmt = block.charFormat()
            size = self.page.to_actual(fmt.fontPointSize())
            if size >= 13 and fmt.fontWeight() >= QFont.Weight.Bold:
                level = 1 if size >= 19 else (2 if size >= 15 else 3)
                entries.append((level, block.text().strip()))
            block = block.next()
        if not entries:
            QMessageBox.information(self, "Table of Contents",
                                    "No headings found. Apply Heading 1-3 first.")
            return
        cursor = self.page.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        for level, text in reversed(entries):
            cursor.insertBlock()
            cursor.insertText("   " * (level - 1) + text)
        self.status_bar.showMessage(f"Inserted {len(entries)} heading(s)", 3000)

    def _insert_caption(self) -> None:
        label, ok = QInputDialog.getText(self, "Caption", "Caption text:")
        if ok and label.strip():
            cursor = self.page.textCursor()
            cursor.insertBlock()
            cursor.insertText(label.strip())
            cursor.insertBlock()

    def _show_word_count(self) -> None:
        text = self.page.toPlainText()
        words = len(text.split())
        chars = len(text)
        lines = max(1, text.count("\n") + 1) if text else 0
        paragraphs = len([b for b in text.split("\n") if b.strip()])
        QMessageBox.information(
            self, "Word Count",
            f"Pages: {self.page.page_count()}\nWords: {words}\n"
            f"Characters (no spaces): {len(text.replace(' ', '').replace(chr(10), ''))}\n"
            f"Characters: {chars}\nParagraphs: {paragraphs}\nLines: {lines}",
        )

    # --- View commands ------------------------------------------------------ #

    def _set_view_mode(self, mode: str) -> None:
        """Print Layout / Read Mode / Web Layout, as in Word's View tab."""
        self.workspace.set_read_mode(mode == "read")
        self.workspace.set_web_layout(mode == "web")
        if mode == "print":
            self.workspace.set_ruler_visible(self.ruler_btn.isChecked())
        else:
            self.workspace.set_ruler_visible(False)
        for name, btn in self._view_buttons.items():
            btn.setChecked(name == mode)
        self.status_bar.select_view_mode(mode)

    def _fit_page(self) -> None:
        self.status_bar.set_zoom(self.workspace.fit_page_to_window())

    def _show_outline_pane(self) -> None:
        """Word's Navigation pane: jump between headings."""
        if not hasattr(self, "_nav_dock"):
            dock = QDockWidget("Navigation", self)
            dock.setObjectName("NavigationPane")
            listing = QListWidget(dock)
            dock.setWidget(listing)
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
            self._nav_dock = dock
            self._nav_list = listing
            listing.itemClicked.connect(self._goto_heading)
        headings = []
        block = self.page.document().begin()
        while block.isValid():
            fmt = block.charFormat()
            if (self.page.to_actual(fmt.fontPointSize()) >= 13
                    and fmt.fontWeight() >= QFont.Weight.Bold):
                headings.append((block.position(), block.text().strip()))
            block = block.next()
        self._nav_list.clear()
        for position, text in headings:
            item = QListWidgetItem(text or "(untitled heading)")
            item.setData(Qt.ItemDataRole.UserRole, position)
            self._nav_list.addItem(item)
        if not headings:
            self._nav_list.addItem("(no headings yet)")
        self._nav_dock.show()

    def _goto_heading(self, item) -> None:
        position = item.data(Qt.ItemDataRole.UserRole)
        if position is None:
            return
        cursor = self.page.textCursor()
        cursor.setPosition(int(position))
        self.page.setTextCursor(cursor)
        self.page.ensureCursorVisible()

    # --- Find / replace ----------------------------------------------------- #

    def _find_text(self) -> None:
        text, ok = QInputDialog.getText(self, "Find", "Find what:")
        if not ok or not text:
            return
        if not self.page.find(text):
            cursor = self.page.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.page.setTextCursor(cursor)
            if not self.page.find(text):
                QMessageBox.information(self, "Find", f"Cannot find \"{text}\".")

    def _replace_text(self) -> None:
        find_for, ok = QInputDialog.getText(self, "Replace", "Find what:")
        if not ok or not find_for:
            return
        replace_with, ok = QInputDialog.getText(self, "Replace", "Replace with:")
        if not ok:
            return
        count = 0
        cursor = self.page.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.page.setTextCursor(cursor)
        while self.page.find(find_for) and count <= 5000:
            self.page.textCursor().insertText(replace_with)
            count += 1
        self.status_bar.showMessage(f"Replaced {count} occurrence(s)", 3000)

    # --- Status strip ------------------------------------------------------- #

    def _on_content_stats_changed(self, words: int, chars: int) -> None:
        self._words, self._chars = words, chars
        self._update_page_indicator()

    def _update_page_indicator(self) -> None:
        """Word's status line: "Page 1 of 3 | 128 words, 743 characters"."""
        page = getattr(self, "page", None)
        if page is None:
            return
        total = page.page_count()
        current = min(page.current_page_number(), total)
        words = getattr(self, "_words", 0)
        chars = getattr(self, "_chars", 0)
        self.status_bar.set_info(f"Page {current} of {total}")
        self.status_bar.set_stats(f"{words} words, {chars} characters")

    # --- Document Lifecycle Actions ---

    # -- starting from a design ---------------------------------------------- #

    def template_entries(self) -> list:
        """The document designs, photographed once and kept for the next ask.

        A sheet is painted for its tile the same way it is painted on screen, so
        the wall cannot promise a page the editor will not deliver.
        """
        if self._designs is None:
            from officer.writer.document_templates import DOCUMENT_TEMPLATES
            from officer.writer.templates import build_tiles, gallery_entries
            self._designs = gallery_entries(
                DOCUMENT_TEMPLATES, build_tiles(DOCUMENT_TEMPLATES))
        return self._designs

    def template_held(self) -> bool:
        """Whether the page holds writing or pictures a design would cover."""
        return not self.page.document().isEmpty() or bool(self.page.floats())

    def apply_template(self, key: str) -> None:
        design = template_named(key)
        if design is None:
            return
        design.apply_to(self.page)
        self._sync_font_box()
        self._update_window_title()
        self.page.setFocus()

    def on_new(self) -> None:
        self.page.clear()
        self.page.clear_floats()
        self.page.clear_page_dress()
        self.current_filepath = None
        self.page.document().setModified(False)
        self._update_window_title()

    def on_open(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Document", "", "Documents (*.docx *.odt *.txt);;All Files (*.*)"
        )
        if filepath:
            self.open_path(filepath)

    def open_path(self, filepath: str) -> bool:
        """Read a document from disk into this window, as the shell asks on start."""
        success = False
        ext = os.path.splitext(filepath)[1].lower()

        if ext == ".docx":
            success = DocxHandler.load(filepath, self.page.document())
        elif ext == ".odt":
            success = OdtHandler.load(filepath, self.page.document())
        elif ext == ".txt":
            with open(filepath, "r", encoding="utf-8") as f:
                self.page.setPlainText(f.read())
            success = True

        if success:
            self.page.clear_floats()
            self.page.clear_page_dress()
            self.page.reapply_zoom()
            self.current_filepath = filepath
            self.page.document().setModified(False)
            self._update_window_title()
            self.status_bar.showMessage(f"Opened: {os.path.basename(filepath)}", 3000)
        else:
            QMessageBox.critical(self, "Error", f"Could not open file: {filepath}")
        return success

    def on_save(self) -> None:
        if self.current_filepath:
            self._save_to_path(self.current_filepath)
        else:
            self.on_save_as()

    def on_save_as(self) -> None:
        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Save Document As", "Untitled.docx",
            "Word Document (*.docx);;OpenDocument Text (*.odt);;Plain Text (*.txt)"
        )
        if filepath:
            self._save_to_path(filepath)

    def _save_to_path(self, filepath: str) -> None:
        ext = os.path.splitext(filepath)[1].lower()
        success = False

        if ext == ".docx":
            with self.page.at_actual_size() as document:
                success = DocxHandler.save(filepath, document)
        elif ext == ".odt":
            with self.page.at_actual_size() as document:
                success = OdtHandler.save(filepath, document)
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(self.page.toPlainText())
            success = True

        if success:
            self.current_filepath = filepath
            self.page.document().setModified(False)
            self._update_window_title()
            self.status_bar.showMessage(f"Saved: {os.path.basename(filepath)}", 3000)
        else:
            QMessageBox.critical(self, "Error", f"Failed to save document to {filepath}")

    def export_pdf(self, filepath: str) -> bool:
        """Print the document on the sheet Layout ▸ Size chose, at its real size."""
        with self.page.at_actual_size() as document:
            return PdfExporter.export_text_document(
                document,
                filepath,
                page_size_mm=self.page.paper_size_mm,
                landscape=self.page.landscape,
                margins_mm=self.page.margin_pixels / MM_TO_PX,
                objects=self.page.float_draw_list(),
                border=self.page.page_border(),
                page_colour=self.page.page_colour(),
                watermark=self.page.watermark(),
                header_footer=self.page.header_footer(),
            )

    def on_export_pdf(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", "Document.pdf", "PDF Files (*.pdf)"
        )
        if not filepath:
            return

        if self.export_pdf(filepath):
            self.status_bar.showMessage(f"Exported PDF: {os.path.basename(filepath)}", 3000)
            QMessageBox.information(self, "PDF Export Complete", f"Successfully exported to:\n{filepath}")
        else:
            QMessageBox.critical(self, "Error", "Failed to export PDF.")

    # --- AI Assistance Actions ---

    def _ai_proofread(self) -> None:
        text = self.page.textCursor().selectedText() or self.page.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "AI Assist", "Please select text or write some content first.")
            return

        self.status_bar.showMessage("AI is reviewing text...", 5000)
        prompt = f"Proofread and correct grammar/spelling in the following text, keeping the meaning intact:\n\n{text}"
        self.ai_client.generate_async(
            prompt=prompt,
            system_prompt="You are a professional editor. Return only the corrected text.",
            on_success=lambda res: QMessageBox.information(self, "AI Proofread Suggestions", res),
            on_error=lambda err: QMessageBox.warning(self, "AI Notice", f"Ollama not reachable: {err}")
        )

    def _ai_summarize(self) -> None:
        text = self.page.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "AI Assist", "Document is empty.")
            return

        self.status_bar.showMessage("AI is summarizing...", 5000)
        prompt = f"Summarize the following document in 3 concise bullet points:\n\n{text}"
        self.ai_client.generate_async(
            prompt=prompt,
            on_success=lambda res: QMessageBox.information(self, "Document Summary", res),
            on_error=lambda err: QMessageBox.warning(self, "AI Notice", f"Ollama not reachable: {err}")
        )

    def _ai_rewrite(self) -> None:
        cursor = self.page.textCursor()
        text = cursor.selectedText()
        if not text.strip():
            QMessageBox.information(self, "AI Assist", "Please highlight the text you want to rewrite.")
            return

        self.status_bar.showMessage("AI is rewriting...", 5000)
        prompt = f"Rewrite this sentence to be clearer, more engaging, and professional:\n\n{text}"
        self.ai_client.generate_async(
            prompt=prompt,
            on_success=lambda res: cursor.insertText(res.strip()),
            on_error=lambda err: QMessageBox.warning(self, "AI Notice", f"Ollama not reachable: {err}")
        )
