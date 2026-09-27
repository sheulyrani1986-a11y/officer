"""PresentR Main Application Window."""

import os
from typing import Optional
from PySide6.QtCore import Qt, QMarginsF, QSize, QSizeF, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel, QTextEdit,
    QFileDialog, QMessageBox, QInputDialog, QColorDialog, QSplitter, QDoubleSpinBox,
    QGraphicsDropShadowEffect, QGraphicsItem, QGraphicsTextItem, QStackedWidget,
    QMenu, QComboBox
)
from PySide6.QtGui import (
    QBrush, QFont, QFontInfo, QPainter, QPageLayout, QPageSize, QPdfWriter,
    QShortcut, QKeySequence, QColor
)
from officer.core.ui.base_window import OfficeBaseWindow
from officer.core.ui.fonts import FontListComboBox, fill_font_list
from officer.core.ui.icons import IconProvider
from officer.presentr.slide_deck import (
    DEFAULT_FONT_FAMILY, Presentation, Slide, TextObject, ShapeObject,
    ImageObject, LAYOUT_PLACEHOLDERS
)
from officer.presentr.canvas import (
    SlideCanvasScene, SlideCanvasView, apply_text_style, set_text_alignment,
    PX_PER_CM, SHAPE_KEYS, shape_box
)
from officer.presentr.thumbnails import (
    ThumbnailPane, SlideSorterView, layout_preview_icon, theme_swatch_icon,
    shape_gallery_icon, shape_style_icon, animation_gallery_icon,
    transition_gallery_icon
)
from officer.presentr.presenter_mode import PresenterWindow
from officer.presentr.io.pptx_handler import PptxHandler
from officer.presentr.io.odp_handler import OdpHandler
from officer.presentr.deck_templates import deck_named
from officer.core.ai.ollama_client import OllamaClient


class PresentRWindow(OfficeBaseWindow):
    """Modern Presentation Software Window for OfficeR."""

    has_templates = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(app_name="presentr", app_title="PresentR", parent=parent)

        # Set window icon to OfficeR logo
        self.setWindowIcon(IconProvider.get_app_icon())

        self.presentation = Presentation("Untitled Presentation")
        self.current_slide_idx = 0
        # Menus handed to split ribbon buttons must outlive the builder.
        self._ribbon_menus: list = []
        #: The gallery's photographs, taken the first time the wall is asked for.
        self._designs: Optional[list] = None

        # Build Main Workspace with Splitter (Slide List on left, Canvas on right)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.workspace_layout.addWidget(self.splitter, 1)

        # 1. Left slide strip: PowerPoint renders each slide as a card with its
        # number in a gutter, rather than listing titles.
        self.slide_list = ThumbnailPane("presentr",
                                        (self.presentation.width, self.presentation.height),
                                        self.splitter)
        self.slide_list.currentRowChanged.connect(self._on_slide_selected)
        self.splitter.addWidget(self.slide_list)

        # 2. Central Canvas + Speaker Notes pane (vertical splitter)
        self.notes_splitter = QSplitter(Qt.Orientation.Vertical, self.splitter)

        self.scene = SlideCanvasScene(self.presentation.width, self.presentation.height, self)
        self.canvas_view = SlideCanvasView(self.scene, self.notes_splitter)
        self.notes_splitter.addWidget(self.canvas_view)

        notes_panel = QWidget(self.notes_splitter)
        notes_panel.setObjectName("NotesPanel")
        notes_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        notes_layout = QVBoxLayout(notes_panel)
        notes_layout.setContentsMargins(0, 0, 0, 0)
        notes_layout.setSpacing(0)

        notes_header = QLabel("Speaker Notes", notes_panel)
        notes_header.setObjectName("NotesHeader")
        notes_header.setFixedHeight(24)
        notes_layout.addWidget(notes_header)

        self.notes_edit = QTextEdit(notes_panel)
        self.notes_edit.setObjectName("NotesEditor")
        self.notes_edit.setPlaceholderText("Click here to add speaker notes for this slide...")
        self.notes_edit.setAcceptRichText(False)
        self.notes_edit.setMinimumHeight(96)
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        notes_layout.addWidget(self.notes_edit)

        self.notes_panel = notes_panel
        # The splitter may shrink this pane, so state the floor the test and the
        # ribbon toggle both rely on; setChildrenCollapsible alone is not enough.
        self.notes_panel.setMinimumHeight(120)
        self.notes_splitter.addWidget(notes_panel)
        # Keep the pane draggable but never let a drag collapse it out of reach;
        # the ribbon Notes button is the affordance for hiding it.
        self.notes_splitter.setChildrenCollapsible(False)
        self.notes_splitter.setStretchFactor(0, 3)
        self.notes_splitter.setStretchFactor(1, 1)
        self.notes_splitter.setSizes([500, 120])

        # PowerPoint floats the slide on the grey desk with a soft shadow.
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 66))
        self.scene.bg_item.setGraphicsEffect(shadow)

        # 3. Slide Sorter: the same cards tiled, reached from the status strip.
        self.sorter_view = SlideSorterView("presentr",
                                           (self.presentation.width, self.presentation.height),
                                           self.splitter, on_reorder=self._move_slide)
        self.sorter_view.itemDoubleClicked.connect(self._on_sorter_activated)
        self.editor_stack = QStackedWidget(self.splitter)
        self.editor_stack.addWidget(self.notes_splitter)
        self.editor_stack.addWidget(self.sorter_view)
        self.splitter.addWidget(self.editor_stack)
        self.splitter.setStretchFactor(1, 4)

        # Thumbnails track what happens on the canvas.
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(240)
        self._thumb_timer.timeout.connect(self._refresh_current_thumbnail)
        self.scene.changed.connect(lambda _=None: self._thumb_timer.start())

        self._setup_status_strip()

        # Ollama AI client
        self.ai_client = OllamaClient(parent=self)

        # Build Ribbon Interface
        self._build_ribbon()

        # Keyboard shortcuts for Slide Show
        QShortcut(QKeySequence("F5"), self, self.start_slideshow_beginning)
        QShortcut(QKeySequence("Shift+F5"), self, self.start_slideshow_current)
        QShortcut(QKeySequence("Ctrl+M"), self, lambda: self.add_new_slide())
        QShortcut(QKeySequence("Ctrl+Shift+N"), self, lambda: self._toggle_notes_panel())
        # Office's own text keys, so the Font group's tooltips are honest.
        for key, attr in (("Ctrl+B", "bold"), ("Ctrl+I", "italic"), ("Ctrl+U", "underline")):
            QShortcut(QKeySequence(key), self,
                      activated=lambda a=attr: self._toggle_text_attribute(a))

        # The ribbon's toggles mirror the marquee, as they do in Office.
        self.scene.selectionChangedSignal.connect(self._sync_text_buttons)

        # Initial Population
        self._refresh_slide_list()
        self.status_bar.zoomChanged.connect(self._on_zoom_changed)

    def _build_ribbon(self) -> None:
        self._build_home_tab()
        self._build_insert_tab()
        self._build_design_tab()
        # PowerPoint's own order: the page, then how it changes, then how what
        # sits on it arrives.
        self._build_transitions_tab()
        self._build_animations_tab()
        self._build_slideshow_tab()
        self._build_ai_tab()
        # Last, so a contextual tab never shifts the index of a permanent one.
        self._build_format_tab()

    def _build_home_tab(self) -> None:
        tab = self.ribbon.add_tab("Home")

        # 1. Slides ---------------------------------------------------------- #
        slide_grp = tab.add_group("Slides")
        new_menu = QMenu(self)
        for kind, caption in self._LAYOUTS:
            new_menu.addAction(caption,
                               lambda checked=False, k=kind: self.add_new_slide(k))
        self._ribbon_menus.append(new_menu)
        slide_grp.add_split_button("New Slide", "slide", new_menu, large=True,
                                   on_click=lambda checked=False: self.add_new_slide())
        slides_col = slide_grp.add_column()
        layout_menu = QMenu(self)
        self._ribbon_menus.append(layout_menu)
        for kind, caption in self._LAYOUTS:
            layout_menu.addAction(caption,
                                  lambda checked=False, k=kind: self._change_layout(k))
        slide_grp.add_button_to(slides_col, "Layout", "slide", menu=layout_menu)
        slide_grp.add_button_to(slides_col, "Delete\nSlide", "cut",
                                on_click=self.delete_current_slide)

        # 2. Font ------------------------------------------------------------ #
        # PowerPoint addresses the selection; a shape here carries one style for
        # its whole text, so each command re-renders the selected text boxes.
        font_grp = tab.add_group("Font")
        font_col = font_grp.add_column()
        row1 = font_grp.add_sub_row(font_col)
        self.font_combo = FontListComboBox(self)
        self.font_combo.setEditable(True)
        self.font_combo.setFixedWidth(150)
        self.font_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_combo.setMaxVisibleItems(18)
        self.font_combo.setToolTip("Font")
        self._populate_font_list()
        # activated (not currentTextChanged): typing a name applies once, on
        # Enter or on picking from the list, not on every keystroke.
        self.font_combo.textActivated.connect(self._set_font_family)
        row1.addWidget(self.font_combo)
        self._text_attr_buttons = {}
        self._text_align_buttons = {}
        for label, icon, attr in (
            ("Bold", "bold", "bold"),
            ("Italic", "italic", "italic"),
            ("Underline", "underline", "underline"),
            ("Strikethrough", "strikethrough", "strike"),
        ):
            btn = font_grp.add_button_to(row1, "", icon, checkable=True,
                                         on_click=lambda checked=False, a=attr: self._toggle_text_attribute(a))
            btn.setToolTip(f"{label} (Ctrl+{label[0]})" if label[0] in "BIU" else label)
            btn.setAccessibleName(label)
            btn.setMinimumWidth(28)
            self._text_attr_buttons[attr] = btn
        row2 = font_grp.add_sub_row(font_col)
        font_grp.add_button_to(row2, "", "font-grow",
                               on_click=lambda: self._step_font_size(2), ).setToolTip("Increase Font Size")
        font_grp.add_button_to(row2, "", "font-shrink",
                               on_click=lambda: self._step_font_size(-2)).setToolTip("Decrease Font Size")
        font_grp.add_button_to(row2, "", "font-color",
                               on_click=self._choose_text_color).setToolTip("Font Color")
        font_grp.add_button_to(row2, "", "clear-format",
                               on_click=self._clear_text_format).setToolTip("Clear All Formatting")

        # 3. Paragraph ------------------------------------------------------- #
        para_grp = tab.add_group("Paragraph")
        para_col = para_grp.add_column()
        para_row = para_grp.add_sub_row(para_col)
        para_grp.add_button_to(para_row, "", "bullets",
                               on_click=self._toggle_bullets).setToolTip("Bullets")
        for label, icon, name in (
            ("Align Left", "align-left", "left"),
            ("Center", "align-center", "center"),
            ("Align Right", "align-right", "right"),
        ):
            btn = para_grp.add_button_to(para_row, "", icon, checkable=True,
                                         on_click=lambda checked=False, n=name: self._set_text_align(n))
            btn.setToolTip(label)
            btn.setAccessibleName(label)
            btn.setMinimumWidth(28)
            self._text_align_buttons[name] = btn
        indent_row = para_grp.add_sub_row(para_col)
        spacing_menu = QMenu(self)
        self._ribbon_menus.append(spacing_menu)
        for value in (1.0, 1.5, 2.0):
            spacing_menu.addAction(f"{value:g} lines",
                                   lambda checked=False, v=value: self._set_line_spacing(v))
        spacing = para_grp.add_button_to(indent_row, "Line Spacing", "line-spacing",
                                         menu=spacing_menu)
        spacing.setToolTip("Choose the line spacing for the selected text box")

        # 4. Drawing --------------------------------------------------------- #
        draw_grp = tab.add_group("Drawing")
        draw_grp.add_button("Text Box", "text-box", large=True, on_click=self.insert_textbox)
        draw_col = draw_grp.add_column()
        draw_grp.add_button_to(draw_col, "Rectangle", "shape-rect",
                               on_click=lambda: self.insert_shape("rect"))
        draw_grp.add_button_to(draw_col, "Ellipse", "ellipse",
                               on_click=lambda: self.insert_shape("ellipse"))
        draw_grp.add_button_to(draw_col, "Fill Color", "fill-color",
                               on_click=self._change_selected_fill)

        # 5. Arrange --------------------------------------------------------- #
        zorder_grp = tab.add_group("Arrange")
        zorder_grp.add_button("Bring\nForward", "bring-front", large=True,
                              on_click=self._bring_to_front)
        zorder_col = zorder_grp.add_column()
        zorder_grp.add_button_to(zorder_col, "Send\nBackward", "send-back",
                                 on_click=self._send_to_back)
        align_menu = QMenu(self)
        self._ribbon_menus.append(align_menu)
        for label, name in (("Align Left", "left"), ("Align Center", "center"),
                            ("Align Right", "right")):
            align_menu.addAction(label, lambda checked=False, n=name: self._align_objects(n))
        zorder_grp.add_button_to(zorder_col, "Align", "align-center", menu=align_menu,
                                 on_click=lambda: self._align_objects("center"))

        # 6. Editing --------------------------------------------------------- #
        edit_grp = tab.add_group("Editing")
        edit_grp.add_button("Select\nAll", "select-all", large=True,
                            on_click=self.select_all_objects)
        edit_col = edit_grp.add_column()
        edit_grp.add_button_to(edit_col, "Delete", "cut",
                               on_click=self.delete_selected_objects)
        self.notes_button = edit_grp.add_button_to(edit_col, "Notes", "notes",
                                                   on_click=lambda checked=False: self._toggle_notes_panel(checked))
        self.notes_button.setCheckable(True)
        self.notes_button.setChecked(True)
        self.notes_button.setToolTip("Show or hide the speaker notes pane (Ctrl+Shift+N)")

    _LAYOUTS = (
        ("title", "Title Slide"),
        ("title_content", "Title and Content"),
        ("two_content", "Two Content"),
        ("blank", "Blank"),
    )

    #: PowerPoint's Shapes gallery, in the order it lays them out: rectangles,
    #: basic shapes, arrows, then stars and banners. Each button draws the shape
    #: itself, so the gallery needs no captions to be readable.
    _SHAPE_GALLERY = (
        ("rect", "Rectangle"), ("rounded_rect", "Rounded Rectangle"),
        ("ellipse", "Oval"), ("triangle", "Isosceles Triangle"),
        ("right_triangle", "Right Triangle"), ("diamond", "Diamond"),
        ("pentagon", "Pentagon"), ("hexagon", "Hexagon"), ("octagon", "Octagon"),
        ("parallelogram", "Parallelogram"), ("trapezoid", "Trapezoid"),
        ("plus", "Plus"), ("heart", "Heart"), ("donut", "Donut"),
        ("pie", "Pie"), ("frame", "Frame"), ("star", "5-Point Star"),
        ("star_4", "4-Point Star"), ("arrow", "Right Arrow"),
        ("double_arrow", "Left-Right Arrow"), ("down_arrow", "Down Arrow"),
        ("chevron", "Chevron"), ("line", "Line"),
    )
    _RIBBON_SHAPES = tuple(kind for kind, _ in _SHAPE_GALLERY)

    def _build_insert_tab(self) -> None:
        tab = self.ribbon.add_tab("Insert")

        images_grp = tab.add_group("Images")
        images_grp.add_button("Picture", "image", large=True, on_click=self.insert_picture_dialog)

        # PowerPoint's Shapes gallery is a grid of the shapes themselves: six
        # columns of four, since twenty-three captions would only fit as icons.
        shapes_grp = tab.add_group("Shapes")
        self._shape_buttons = {}
        column = None
        for index, (kind, caption) in enumerate(self._SHAPE_GALLERY):
            if index % 4 == 0:
                column = shapes_grp.add_column()
            btn = shapes_grp.add_button_to(column, "", None,
                                           on_click=lambda checked=False, k=kind: self.insert_shape(k))
            btn.setIcon(shape_gallery_icon(kind, (16, 16)))
            btn.setIconSize(QSize(16, 16))
            btn.setFixedWidth(34)
            btn.setToolTip(f"Insert a {caption.lower()} on this slide")
            btn.setAccessibleName(caption)
            self._shape_buttons[kind] = btn

        text_grp = tab.add_group("Text")
        text_grp.add_button("Text Box", "text-box", large=True,
                            on_click=lambda checked=False: self.insert_textbox())

    def _build_design_tab(self) -> None:
        tab = self.ribbon.add_tab("Design")

        # A whole deck from one choice: PowerPoint's Themes gallery, but for the
        # run of sheets rather than for their colours.
        deck_grp = tab.add_group("Deck")
        deck_grp.add_button("Templates", "templates", large=True,
                            on_click=self.open_template_gallery,
                            tooltip="Start the presentation from one of PresentR's designs")

        # PowerPoint's galleries show the thing itself: a slide in that theme, a
        # card with that layout's placeholders — never a shared generic glyph.
        themes_grp = tab.add_group("Themes")
        for name, key in self._THEME_LABELS:
            btn = themes_grp.add_button(name, None, large=True,
                                        on_click=lambda checked=False, k=key: self._apply_theme(k))
            btn.setIcon(theme_swatch_icon(*self._THEMES[key]))
            # A slide is 16:9, so keep the card's own proportions inside the button.
            btn.setIconSize(QSize(36, 22))
            btn.setToolTip(f"Apply the {name} theme to every slide")

        layout_grp = tab.add_group("Slide Layout")
        for kind, caption in self._LAYOUTS:
            btn = layout_grp.add_button(caption, None, large=True,
                                        on_click=lambda checked=False, k=kind: self._change_layout(k))
            btn.setIcon(layout_preview_icon(kind))
            btn.setIconSize(QSize(36, 22))
            btn.setToolTip(f"Reflow this slide into the {caption} layout")

        customize = tab.add_group("Customize")
        customize.add_button("Background", "fill-color", large=True,
                             on_click=self._choose_background)
        customize_col = customize.add_column()
        customize.add_button_to(customize_col, "Reset\nSlide", "clear-format",
                                on_click=self._reset_current_slide)

    def _build_slideshow_tab(self) -> None:
        tab = self.ribbon.add_tab("Slide Show")

        start_grp = tab.add_group("Start Slide Show")
        beginning = start_grp.add_button("From\nBeginning", "play", large=True,
                                         on_click=self.start_slideshow_beginning)
        beginning.setToolTip("Start the show at the first slide (F5)")
        start_col = start_grp.add_column()
        current = start_grp.add_button_to(start_col, "From Current", "play-from",
                                          on_click=self.start_slideshow_current)
        current.setToolTip("Start the show at this slide (Shift+F5)")
        # PowerPoint's Presenter View is the show with the notes panel attached;
        # here that is the same fullscreen window opened with its N overlay on.
        presenter = start_grp.add_button_to(start_col, "Presenter\nView", "notes",
                                            on_click=self.start_presenter_view)
        presenter.setToolTip("Show fullscreen with this slide's speaker notes (N toggles them)")

        preview = tab.add_group("Preview")
        preview.add_button("Reading\nView", "view-read", large=True,
                           on_click=lambda checked=False: self._set_view_mode("reading"))
        preview_col = preview.add_column()
        preview.add_button_to(preview_col, "Fit Slide", "zoom-fit",
                              on_click=self._fit_slide_to_window)
        preview.add_button_to(preview_col, "Actual\nSize", "zoom",
                              on_click=lambda checked=False: self.status_bar.set_zoom(100))

    # ------------------------------------------------- Transitions & Animations #

    #: How the show arrives at a slide, as PowerPoint's Transitions gallery names them.
    _TRANSITIONS = (("none", "None"), ("fade", "Fade"), ("push", "Push"))
    #: How an object arrives during the show, as PowerPoint's Animation gallery names them.
    _EFFECTS = (("none", "None"), ("fade", "Fade"), ("fly_in", "Fly In"), ("zoom", "Zoom"))
    _TRANSITION_LABELS = dict(_TRANSITIONS)

    def _build_transitions_tab(self) -> None:
        """PowerPoint's Transitions tab: one effect per slide, applied to this one."""
        tab = self.ribbon.add_tab("Transitions")
        grp = tab.add_group("Transition to This Slide")
        self._transition_buttons = {}
        for key, caption in self._TRANSITIONS:
            btn = grp.add_button(caption, None, large=True, checkable=True,
                                 on_click=lambda checked=False, k=key: self._set_slide_transition(k))
            btn.setIcon(transition_gallery_icon(key, (36, 22)))
            btn.setIconSize(QSize(36, 22))
            btn.setToolTip(f"Play the {caption.lower()} transition coming into this slide")
            self._transition_buttons[key] = btn
        apply_grp = tab.add_group("Apply")
        apply_grp.add_button("Apply To\nAll Slides", "slide", large=True,
                             on_click=self._apply_transition_to_all)
        self._sync_transition_buttons()

    def _build_animations_tab(self) -> None:
        """PowerPoint's Animations tab: an entrance effect for what is selected."""
        tab = self.ribbon.add_tab("Animations")
        grp = tab.add_group("Animation Style")
        self._animation_buttons = {}
        for key, caption in self._EFFECTS:
            btn = grp.add_button(caption, None, large=True, checkable=True,
                                 on_click=lambda checked=False, k=key: self._set_selection_animation(k))
            btn.setIcon(animation_gallery_icon(key, (36, 22)))
            btn.setIconSize(QSize(36, 22))
            btn.setToolTip(f"Make the selected objects arrive with the {caption.lower()} effect")
            self._animation_buttons[key] = btn
        order_grp = tab.add_group("Watching")
        self._play_from_here = order_grp.add_button(
            "Play From\nHere", "play-from", large=True,
            on_click=self.start_slideshow_current)
        self._play_from_here.setToolTip(
            "Run the show from this slide, effects and all (Shift+F5)")

    def _set_slide_transition(self, name: str) -> None:
        """Remember how the show should arrive on this slide."""
        slide = self._current_slide()
        if slide is not None:
            slide.transition = name
        self._sync_transition_buttons()

    def _apply_transition_to_all(self) -> None:
        """Give every slide the transition this one carries."""
        slide = self._current_slide()
        if slide is None:
            return
        for other in self.presentation.slides:
            other.transition = slide.transition
        self.status_bar.showMessage(
            f"{self._TRANSITION_LABELS[slide.transition]} transition applied to "
            f"{len(self.presentation.slides)} slides", 3000)

    def _sync_transition_buttons(self) -> None:
        """Show which transition this slide carries, once the ribbon exists."""
        slide = self._current_slide()
        name = slide.transition if slide else "none"
        for key, btn in self._transition_buttons.items():
            btn.setChecked(key == name)

    def _set_selection_animation(self, name: str) -> None:
        """Give the selected objects *name* as their entrance effect."""
        if self.scene.set_selection_animation(name):
            self._sync_animation_buttons()

    def _sync_animation_buttons(self) -> None:
        """Show the effect the one selected object arrives with."""
        info = self.scene.selection_info()
        name = info["animation"] if info else None
        for key, btn in self._animation_buttons.items():
            btn.setChecked(key == name)

    def _build_ai_tab(self) -> None:
        tab = self.ribbon.add_tab("AI Assist")
        ai_grp = tab.add_group("Slide Creator")
        ai_grp.add_button("Slide Outline", "ai", large=True, on_click=self._ai_generate_outline)
        ai_grp.add_button("Bullet Enhancer", "ai", large=True, on_click=self._ai_enhance_bullets)

    # ------------------------------------------------ Shape Format (contextual) #

    #: PowerPoint's Gradient gallery, reduced to stops PresentR can also draw:
    #: every pair is a linear ramp from the shape's own colour to the second.
    _GRADIENTS = (
        ("Blue to White", "#3B82F6", "#DBEAFE"),
        ("Ink to Grey", "#1F2937", "#9CA3AF"),
        ("Sunset", "#F59E0B", "#EF4444"),
        ("Forest", "#065F46", "#34D399"),
        ("Royal", "#4338CA", "#C4B5FD"),
    )
    _LINE_WEIGHTS = (1, 2, 3, 5, 8)

    #: PowerPoint's Shape Styles gallery: name, near colour, far colour (``None``
    #: for a flat one), outline and its weight. One click paints all four.
    _SHAPE_STYLES = (
        ("Blue", "#3B82F6", None, "#1D4ED8", 2),
        ("Sky", "#DBEAFE", None, "#3B82F6", 1),
        ("Blue to Sky", "#3B82F6", "#DBEAFE", "#1D4ED8", 1),
        ("Ink", "#1F2937", None, "#111827", 1),
        ("Ink to Grey", "#1F2937", "#9CA3AF", "#111827", 1),
        ("Gold", "#F59E0B", None, "#B45309", 2),
        ("Forest", "#065F46", "#34D399", "#064E3B", 1),
        ("Rose", "#E11D48", None, "#9F1239", 2),
    )

    def _build_format_tab(self) -> None:
        """PowerPoint's Shape Format tab, which only exists over a shape or picture.

        Every box here writes the slide model, and the canvas draws from that
        model, so the numbers on the ribbon and the shape on the slide cannot
        disagree.
        """
        tab = self.ribbon.add_tab("Shape Format")

        size_grp = tab.add_group("Size")
        size_col = size_grp.add_column()
        self.shape_height_spin = self._add_length_box(size_grp, size_col, "Height:")
        self.shape_width_spin = self._add_length_box(size_grp, size_col, "Width:")
        self.shape_rotate_spin = self._add_length_box(size_grp, size_col, "Rotate:",
                                                      maximum=359.99, suffix="°")
        self.shape_height_spin.valueChanged.connect(
            lambda v: self._apply_shape_size("height", v))
        self.shape_width_spin.valueChanged.connect(
            lambda v: self._apply_shape_size("width", v))
        self.shape_rotate_spin.valueChanged.connect(self._apply_shape_rotation)

        place_grp = tab.add_group("Position")
        place_col = place_grp.add_column()
        self.shape_pos_x_spin = self._add_length_box(place_grp, place_col, "Position X:")
        self.shape_pos_y_spin = self._add_length_box(place_grp, place_col, "Position Y:")
        self.shape_pos_x_spin.valueChanged.connect(
            lambda v: self._apply_shape_place("x", v))
        self.shape_pos_y_spin.valueChanged.connect(
            lambda v: self._apply_shape_place("y", v))
        place_row = place_grp.add_sub_row(place_col)
        place_grp.add_button_to(place_row, "Reset Size", None,
                                on_click=self._reset_shape_size)

        style_grp = tab.add_group("Shape Style")
        self._format_style_group = style_grp
        style_col = style_grp.add_column()
        style_grp.add_button("Shape Fill", "fill-color", large=True,
                             on_click=self._pick_shape_fill)
        gradient_menu = QMenu(self)
        for name, start, stop in self._GRADIENTS:
            gradient_menu.addAction(
                name, lambda checked=False, a=start, b=stop:
                self._apply_shape_gradient(a, b))
        gradient_menu.addSeparator()
        gradient_menu.addAction("More colours…", self._pick_shape_gradient)
        gradient_menu.addAction("No Gradient",
                                lambda checked=False: self._apply_shape_gradient(None, None))
        self._ribbon_menus.append(gradient_menu)
        style_grp.add_button_to(style_col, "Gradient", "fill-color",
                                menu=gradient_menu,
                                on_click=lambda checked=False: self._apply_shape_gradient(
                                    *self._GRADIENTS[0][1:]))
        outline_menu = QMenu(self)
        for weight in self._LINE_WEIGHTS:
            outline_menu.addAction(
                f"{weight} pt", lambda checked=False, w=weight:
                self._set_shape_line_weight(w))
        outline_menu.addSeparator()
        outline_menu.addAction("Colour…", self._pick_shape_outline)
        self._ribbon_menus.append(outline_menu)
        style_grp.add_button_to(style_col, "Outline", "line-shape", menu=outline_menu,
                                on_click=self._pick_shape_outline)

        # PowerPoint's Shape Styles row: one click sets fill, gradient and outline
        # together, and the card is painted in the style it applies.
        styles_grp = tab.add_group("Shape Styles")
        self._style_buttons = {}
        column = None
        for index, preset in enumerate(self._SHAPE_STYLES):
            if index % 3 == 0:
                column = styles_grp.add_column()
            name, fill, gradient, border, weight = preset
            btn = styles_grp.add_button_to(column, "", None, checkable=True,
                                           on_click=lambda checked=False, p=preset: self._apply_shape_style(p))
            btn.setIcon(shape_style_icon(preset, (20, 14)))
            btn.setIconSize(QSize(20, 14))
            btn.setFixedWidth(34)
            btn.setToolTip(f"Paint the shape in the {name} style")
            btn.setAccessibleName(f"{name} style")
            self._style_buttons[preset] = btn
        self._format_styles_group = styles_grp

        self._shape_tab_shown = False
        self.ribbon.set_tab_visible("Shape Format", False)
        self.scene.selectionChangedSignal.connect(self._sync_shape_tab)
        self.scene.selectionChangedSignal.connect(self._sync_selection_commands)

    def _add_length_box(self, group, column, caption: str, maximum: float = 60.0,
                        suffix: str = " cm") -> QDoubleSpinBox:
        """One measurement box with its caption, as Office draws its Size pane."""
        row = group.add_sub_row(column)
        label = QLabel(caption, group)
        label.setStyleSheet("color: #6B7280; font-size: 11px;")
        row.addWidget(label)
        box = QDoubleSpinBox(group)
        box.setRange(0.0, maximum)
        box.setDecimals(2 if suffix == "°" else 1)
        box.setSingleStep(0.1 if suffix == "°" else 0.5)
        box.setSuffix(suffix)
        box.setFixedWidth(78)
        box.setToolTip(caption.rstrip(":") + " in " + suffix.strip())
        row.addWidget(box)
        return box

    def _sync_selection_commands(self) -> None:
        """Light the Animations gallery for whatever the presenter picked up."""
        self._sync_animation_buttons()

    def _sync_shape_tab(self) -> None:
        """Show the tab over a shape or picture, and put its numbers in the boxes."""
        info = self.scene.selection_info()
        editable = info is not None and info["kind"] in ("shape", "picture")
        self.ribbon.set_tab_visible("Shape Format", editable)
        if not editable:
            self._shape_tab_shown = False
            return
        # PowerPoint keeps its paint commands over a shape but not over a photo,
        # whose own colours are the point of it.
        self._format_style_group.setVisible(info["kind"] == "shape")
        self._format_styles_group.setVisible(info["kind"] == "shape")
        self._format_styles_group.setVisible(info["kind"] == "shape")
        for box, key in ((self.shape_height_spin, "height_cm"),
                         (self.shape_width_spin, "width_cm"),
                         (self.shape_pos_x_spin, "x_cm"),
                         (self.shape_pos_y_spin, "y_cm"),
                         (self.shape_rotate_spin, "rotation")):
            box.blockSignals(True)
            box.setValue(round(info[key], 2))
            box.blockSignals(False)
        # Office keeps the gallery entry lit for the style the shape already wears.
        for preset, btn in self._style_buttons.items():
            btn.setChecked(self._wears_style(info, preset))
        if not self._shape_tab_shown:
            # PowerPoint walks to the tab the moment an object is picked up,
            # then leaves the presenter free to browse elsewhere.
            self.ribbon.select_tab("Shape Format")
            self._shape_tab_shown = True

    def _after_shape_edit(self) -> None:
        """Keep the model, the thumbnail strip and the ribbon in step."""
        self.scene.sync_to_slide()
        self._thumb_timer.start()
        self._sync_shape_tab()

    def _apply_shape_size(self, edge: str, centimetres: float) -> None:
        if getattr(self, "_applying_shape", False) or centimetres <= 0:
            return
        self._applying_shape = True
        try:
            pixels = centimetres * PX_PER_CM
            self.scene.set_selection_box(**{edge: pixels})
            self._after_shape_edit()
        finally:
            self._applying_shape = False

    def _apply_shape_place(self, edge: str, centimetres: float) -> None:
        if getattr(self, "_applying_shape", False):
            return
        self._applying_shape = True
        try:
            self.scene.set_selection_box(**{edge: centimetres * PX_PER_CM})
            self._after_shape_edit()
        finally:
            self._applying_shape = False

    def _reset_shape_size(self) -> None:
        if self.scene.reset_selection_size():
            self._after_shape_edit()

    def _apply_shape_rotation(self, degrees: float) -> None:
        if getattr(self, "_applying_shape", False):
            return
        if self.scene.set_selection_rotation(degrees):
            self._after_shape_edit()

    def _set_shape_line_weight(self, weight: int) -> None:
        if self.scene.set_selection_paint(border_width=weight):
            self._after_shape_edit()

    def _wears_style(self, info: dict, preset: tuple) -> bool:
        """Whether the selected shape is already painted with *preset*."""
        if info["kind"] != "shape":
            return False
        _name, fill, gradient, border, weight = preset
        return (info["fill_color"].upper() == fill.upper()
                and (info["gradient_color"] or "").upper() == (gradient or "").upper()
                and info["border_color"].upper() == border.upper()
                and int(info["border_width"]) == weight)

    def _apply_shape_style(self, preset: tuple) -> None:
        """Paint the selected shape with one of PowerPoint's style presets."""
        _name, fill, gradient, border, weight = preset
        if self.scene.set_selection_paint(fill=fill, gradient=gradient,
                                          border=border, border_width=weight):
            self._after_shape_edit()

    def _pick_shape_fill(self) -> None:
        info = self.scene.selection_info()
        start = QColor(info["fill_color"]) if info and info.get("fill_color") else QColor("#3B82F6")
        color = QColorDialog.getColor(start, self, "Shape Fill")
        if color.isValid():
            self._apply_gradient_pair(color.name(), None)

    def _pick_shape_gradient(self) -> None:
        """Ask for the gradient's far stop and keep the shape's own colour as the near one."""
        info = self.scene.selection_info()
        start = (info or {}).get("fill_color") or "#3B82F6"
        color = QColorDialog.getColor(QColor(start), self, "Gradient Second Colour")
        if color.isValid():
            self._apply_gradient_pair(start, color.name())

    def _pick_shape_outline(self) -> None:
        info = self.scene.selection_info()
        start = QColor(info["border_color"]) if info and info.get("border_color") else QColor("#1D4ED8")
        color = QColorDialog.getColor(start, self, "Shape Outline")
        if color.isValid() and self.scene.set_selection_paint(border=color.name()):
            self._after_shape_edit()

    def _apply_shape_gradient(self, start: Optional[str], stop: Optional[str]) -> None:
        if start is None:
            self._apply_gradient_pair(None, None)
            return
        self._apply_gradient_pair(start, stop)

    def _apply_gradient_pair(self, fill: Optional[str], gradient: Optional[str]) -> None:
        if self.scene.set_selection_paint(fill=fill, gradient=gradient):
            self._after_shape_edit()

    # --- Slide Navigation & Operations ---

    def _setup_status_strip(self) -> None:
        """PowerPoint's strip: slide counter on the left, three views, a show button, zoom."""
        self.status_bar.set_view_modes((
            ("normal", "Normal", "Normal", "view-normal",
             lambda: self._set_view_mode("normal")),
            ("sorter", "Slide Sorter", "Slide Sorter", "view-slide-sorter",
             lambda: self._set_view_mode("sorter")),
            ("reading", "Reading View", "Reading View", "view-read",
             lambda: self._set_view_mode("reading")),
            ("", "From Beginning (F5)", "Slide Show (F5)", "play",
             self.start_slideshow_beginning),
        ))
        self.status_bar.set_zoom_range(40, 400, 100)
        self.status_bar.zoomChanged.connect(self._on_zoom_changed)

    def _set_view_mode(self, mode: str) -> None:
        """Switch between the editor, the sorter and PowerPoint's reading view."""
        if mode == "sorter":
            self.editor_stack.setCurrentWidget(self.sorter_view)
            self.sorter_view.refresh(self.presentation.slides, self.current_slide_idx)
        else:
            self.editor_stack.setCurrentWidget(self.notes_splitter)
        # Reading view keeps only the slide: no thumbnail strip, no notes pane.
        reading = mode == "reading"
        self.slide_list.setVisible(not reading)
        self.notes_panel.setVisible(not reading and self.notes_button.isChecked())
        self.canvas_view.set_fit_to_view(True)
        self.canvas_view.fit_slide_to_view()
        self.status_bar.select_view_mode(mode)
        labels = {"normal": "Normal", "sorter": "Slide Sorter", "reading": "Reading View"}
        self.status_bar.showMessage(f"{labels.get(mode, 'Normal')} view.", 2500)

    def _on_sorter_activated(self, item: QListWidgetItem) -> None:
        """Double-clicking a card in the sorter opens that slide, as PowerPoint does."""
        row = self.sorter_view.row(item)
        self._set_view_mode("normal")
        self.slide_list.setCurrentRow(row)

    def _refresh_slide_list(self) -> None:
        self.slide_list.refresh(self.presentation.slides, self.current_slide_idx)
        self.sorter_view.refresh(self.presentation.slides, self.current_slide_idx)

        if 0 <= self.current_slide_idx < len(self.presentation.slides):
            self._load_slide_into_scene(self.current_slide_idx)
        self._update_stats()

    def _refresh_current_thumbnail(self) -> None:
        """Re-render the card for the slide being edited, so it mirrors the canvas."""
        if not 0 <= self.current_slide_idx < len(self.presentation.slides):
            return
        self.scene.sync_to_slide()
        slide = self.presentation.slides[self.current_slide_idx]
        self.slide_list.update_thumbnail(self.current_slide_idx, slide)
        self.sorter_view.refresh(self.presentation.slides, self.current_slide_idx)

    def _load_slide_into_scene(self, idx: int) -> None:
        if 0 <= idx < len(self.presentation.slides):
            self.current_slide_idx = idx
            slide = self.presentation.slides[idx]
            self.scene.load_slide(slide)
            # Loading a slide re-fits the canvas, as before; the zoom slider only
            # holds for the current slide.
            self.canvas_view.set_fit_to_view(True)
            self.canvas_view.fit_slide_to_view()
            self._load_notes_for_slide(slide)
            self._sync_transition_buttons()

    def _load_notes_for_slide(self, slide: Slide) -> None:
        """Display *slide*'s notes, blocking signals so the model is not echoed back."""
        self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(slide.notes)
        self.notes_edit.blockSignals(False)

    def _toggle_notes_panel(self, checked: Optional[bool] = None) -> None:
        """Show or hide the speaker notes pane (ribbon Notes button / Ctrl+Shift+N)."""
        visible = (not self.notes_panel.isVisible()) if checked is None else bool(checked)
        self.notes_panel.setVisible(visible)
        if self.notes_button.isChecked() != visible:
            self.notes_button.setChecked(visible)
        if visible:
            self.notes_splitter.setSizes([500, 120])
            self.notes_edit.setFocus()
        self.status_bar.showMessage(f"Speaker notes {'shown' if visible else 'hidden'}", 2000)

    def _on_slide_selected(self, row: int) -> None:
        if row >= 0:
            self.scene.sync_to_slide()
            self._load_slide_into_scene(row)
            self._update_stats()

    def _update_stats(self) -> None:
        """PowerPoint prints the slide counter at the left end of the strip."""
        total = len(self.presentation.slides)
        curr = self.current_slide_idx + 1
        self.status_bar.set_info(f"Slide {curr} of {total}")

    def add_new_slide(self, layout: str = "title_content") -> None:
        """Append a slide carrying *layout*'s empty placeholders."""
        self.scene.sync_to_slide()
        self.presentation.add_slide(layout=layout)
        self.current_slide_idx = len(self.presentation.slides) - 1
        self._refresh_slide_list()

    def _move_slide(self, source: int, target: int) -> None:
        """Reorder the deck after a card is dropped in the slide sorter."""
        self.scene.sync_to_slide()
        slide = self.presentation.slides.pop(source)
        self.presentation.slides.insert(target, slide)
        self.current_slide_idx = target
        self._refresh_slide_list()
        self.status_bar.showMessage(f"Slide moved to position {target + 1}.", 2500)

    def delete_current_slide(self) -> None:
        if len(self.presentation.slides) <= 1:
            QMessageBox.information(self, "Notice", "Presentation must contain at least one slide.")
            return
        self.presentation.slides.pop(self.current_slide_idx)
        self.current_slide_idx = max(0, self.current_slide_idx - 1)
        self._refresh_slide_list()

    # --- Canvas Object Insertion ---

    def insert_textbox(self) -> None:
        txt = TextObject(
            id=f"text_{len(self.scene.items())}",
            x=200, y=200, width=400, height=80,
            text="Double click to edit text", font_size=24
        )
        self.scene._add_text_item(txt)

    def insert_shape(self, shape_type: str = "rect") -> None:
        """Drop a shape in the middle of the slide, at its own natural box."""
        wide, tall = shape_box(shape_type)
        shp = ShapeObject(
            id=f"shape_{len(self.scene.items())}",
            x=(self.scene.slide_width - wide) / 2,
            y=(self.scene.slide_height - tall) / 2,
            width=wide, height=tall,
            shape_type=shape_type,
            fill_color="#3B82F6",
            border_color="#1D4ED8"
        )
        item = self.scene._add_shape_item(shp)
        self.scene.clearSelection()
        item.setSelected(True)
        self.scene.sync_to_slide()

    def insert_picture_dialog(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Insert Picture", "", "Images (*.png *.jpg *.jpeg *.bmp *.svg)"
        )
        if not filepath:
            return
        from PySide6.QtGui import QImage
        natural = QImage(filepath)
        if natural.isNull():
            self.status_bar.set_info("That file is not a picture PresentR can read")
            return
        wide, tall = float(natural.width()), float(natural.height())
        # PowerPoint drops a picture at its own pixels, then shrinks it to the
        # slide rather than hanging it over the edge.
        fit = min(1.0, self.scene.slide_width / wide, self.scene.slide_height / tall)
        wide, tall = wide * fit, tall * fit
        img = ImageObject(
            id=f"img_{len(self.scene.items())}",
            x=(self.scene.slide_width - wide) / 2,
            y=(self.scene.slide_height - tall) / 2,
            width=wide, height=tall,
            image_path=filepath
        )
        item = self.scene._add_image_item(img)
        if item is not None:
            self.scene.clearSelection()
            item.setSelected(True)
            self.scene.sync_to_slide()

    def _change_selected_fill(self) -> None:
        """Recolour the selected shapes, and the model behind them."""
        color = QColorDialog.getColor(QColor("#3B82F6"), self, "Fill Color")
        if not color.isValid():
            return
        self.scene.set_selection_paint(fill=color.name())
        self._thumb_timer.start()

    def _on_zoom_changed(self, percent: int) -> None:
        scale = percent / 100.0
        self.canvas_view.set_fit_to_view(False)
        self.canvas_view.resetTransform()
        self.canvas_view.scale(scale, scale)

    def _on_notes_changed(self) -> None:
        """Mirror the notes editor into the current slide's model."""
        if 0 <= self.current_slide_idx < len(self.presentation.slides):
            slide = self.presentation.slides[self.current_slide_idx]
            slide.notes = self.notes_edit.toPlainText()

    # --- Text formatting ---------------------------------------------------- #
    # PowerPoint formats the current selection; a text box here carries one
    # style for its whole body, so each command updates every selected box.

    def _selected_text_boxes(self):
        """(item, TextObject) pairs for the text boxes the marquee holds.

        The scene is synced first: while a placeholder is being typed in, the
        QGraphicsTextItem holds the live text and the model still has the old
        one, so a command that read the model would overwrite what the
        presenter just wrote.
        """
        self.scene.sync_to_slide()
        pairs = []
        for item in self.scene.selectedItems():
            obj = item.data(0) if isinstance(item, QGraphicsTextItem) else None
            if isinstance(obj, TextObject):
                pairs.append((item, obj))
        return pairs

    def _edit_text(self, mutate, describe: str) -> None:
        pairs = self._selected_text_boxes()
        if not pairs:
            # Nothing selected: the toggles must not stay lit from a stale click.
            self._sync_text_buttons()
            self.status_bar.showMessage("Select a text box first.", 2500)
            return
        for item, obj in pairs:
            mutate(obj)
            item.setPlainText(obj.text)
            apply_text_style(item, obj)
        self.scene.sync_to_slide()
        self._sync_text_buttons()
        self._thumb_timer.start()
        self.status_bar.showMessage(describe, 2000)

    def _toggle_text_attribute(self, attr: str) -> None:
        pairs = self._selected_text_boxes()
        if not pairs:
            self._edit_text(lambda obj: None, "")
            return
        enable = not all(getattr(obj, attr) for _, obj in pairs)
        self._edit_text(lambda obj: setattr(obj, attr, enable),
                        f"{attr.title()} {'on' if enable else 'off'}")

    def _step_font_size(self, delta: int) -> None:
        self._edit_text(
            lambda obj: setattr(obj, "font_size", max(8, obj.font_size + delta)),
            f"Font size {'increased' if delta > 0 else 'decreased'}.")

    def _set_font_family(self, family: str) -> None:
        """Home ▸ Font: put the chosen face on every selected text box."""
        self._edit_text(lambda obj: setattr(obj, "font_family", family),
                        f"Font {family}.")

    def _populate_font_list(self) -> None:
        """Every family fontconfig reports, each name drawn in its own face."""
        fill_font_list(self.font_combo)

    def _set_text_align(self, name: str) -> None:
        self._edit_text(lambda obj: setattr(obj, "alignment", name),
                        f"Aligned {name}.")

    def _set_line_spacing(self, value: float) -> None:
        self._edit_text(lambda obj: setattr(obj, "line_spacing", value),
                        f"Line spacing {value:g}.")

    def _choose_text_color(self) -> None:
        pairs = self._selected_text_boxes()
        start = QColor(pairs[0][1].text_color) if pairs else QColor("#111827")
        color = QColorDialog.getColor(start, self, "Font Color")
        if color.isValid():
            self._edit_text(lambda obj: setattr(obj, "text_color", color.name()),
                            f"Font colour {color.name()}.")

    def _clear_text_format(self) -> None:
        """PowerPoint's Clear All Formatting: back to plain body text."""
        def plain(obj: TextObject) -> None:
            obj.bold = obj.italic = obj.underline = obj.strike = False
            obj.font_family = DEFAULT_FONT_FAMILY
            obj.text_color = "#111827"
            obj.line_spacing = 1.0
        self._edit_text(plain, "Formatting cleared.")

    def _toggle_bullets(self) -> None:
        """Prefix or strip the bullet the content placeholder already uses."""
        pairs = self._selected_text_boxes()
        if not pairs:
            self._edit_text(lambda obj: None, "")
            return
        lines = [ln for ln in pairs[0][1].text.splitlines() if ln.strip()]
        add = not all(ln.lstrip().startswith("•") for ln in lines)

        def rebullets(obj: TextObject) -> None:
            out = []
            for line in obj.text.splitlines() or [""]:
                body = line.lstrip("• ").strip() if line.lstrip().startswith("•") else line.lstrip()
                out.append(f"• {body}" if add and body else body)
            obj.text = "\n".join(out)
        self._edit_text(rebullets, "Bullets added." if add else "Bullets removed.")

    def _sync_text_buttons(self) -> None:
        """Light up the ribbon toggles for whatever is selected, as Office does."""
        pairs = self._selected_text_boxes()
        for attr, btn in getattr(self, "_text_attr_buttons", {}).items():
            btn.setChecked(bool(pairs) and all(getattr(obj, attr) for _, obj in pairs))
        for name, btn in getattr(self, "_text_align_buttons", {}).items():
            btn.setChecked(bool(pairs) and all(obj.alignment == name for _, obj in pairs))
        self._sync_font_box(pairs)

    def _sync_font_box(self, pairs) -> None:
        """Name the face the selected boxes are drawn in, the way PowerPoint does.

        Signals are blocked: reflecting the slide is not a formatting command, and
        re-applying it would rewrite the very face it just read.
        """
        family = pairs[0][1].font_family if pairs else DEFAULT_FONT_FAMILY
        if self.font_combo.findText(family, Qt.MatchFlag.MatchFixedString) < 0:
            # A deck can ask for a face this machine has not got, and a box
            # naming it could never be picked again: show what is really there.
            family = QFontInfo(QFont(family)).family() or family
        if self.font_combo.currentText() != family:
            self.font_combo.blockSignals(True)
            self.font_combo.setCurrentText(family)
            self.font_combo.blockSignals(False)

    # --- Slide structure ---------------------------------------------------- #

    def select_all_objects(self) -> None:
        self.scene.clearSelection()
        for item in self.scene.items():
            if item is not self.scene.bg_item and item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
                item.setSelected(True)

    def delete_selected_objects(self) -> None:
        selected = [item for item in self.scene.selectedItems() if item is not self.scene.bg_item]
        if not selected:
            self.status_bar.showMessage("Nothing selected to delete.", 2500)
            return
        for item in selected:
            self.scene.removeItem(item)
        self.scene.sync_to_slide()
        self._thumb_timer.start()
        self.status_bar.showMessage(f"{len(selected)} object(s) deleted.", 2500)

    # --- Themes ---

    _THEMES = {
        "slate_sapphire":    ("#1E293B", "#FFFFFF", "#3B82F6"),   # bg, text, accent
        "emerald_executive": ("#064E3B", "#FFFFFF", "#10B981"),
        "crimson_modern":    ("#7F1D1D", "#FFFFFF", "#EF4444"),
        "sunset_gold":       ("#92400E", "#FFFBEB", "#F59E0B"),
        "midnight_minimalist": ("#0F172A", "#E2E8F0", "#818CF8"),
    }

    _THEME_LABELS = (
        ("Slate Sapphire", "slate_sapphire"),
        ("Emerald", "emerald_executive"),
        ("Crimson", "crimson_modern"),
        ("Sunset Gold", "sunset_gold"),
        ("Midnight", "midnight_minimalist"),
    )

    def _apply_theme(self, theme_key: str) -> None:
        """Recolour the deck the way PowerPoint's gallery does: ground, text, shapes."""
        theme = self._THEMES.get(theme_key)
        if not theme:
            return
        self.scene.sync_to_slide()
        bg_color, text_color, accent = theme
        for slide in self.presentation.slides:
            slide.background_color = bg_color
            for obj in slide.objects:
                if isinstance(obj, TextObject):
                    obj.text_color = text_color
                elif isinstance(obj, ShapeObject):
                    obj.fill_color = accent
        self._refresh_slide_list()
        label = dict((k, l) for l, k in self._THEME_LABELS).get(theme_key, theme_key)
        self.status_bar.showMessage(f"Theme applied: {label}", 2500)

    def _choose_background(self) -> None:
        """PowerPoint's Format Background, reduced to the solid fill it defaults to."""
        slide = self._current_slide()
        if slide is None:
            return
        color = QColorDialog.getColor(QColor(slide.background_color), self,
                                      "Slide Background Color")
        if not color.isValid():
            return
        slide.background_color = color.name()
        self.scene.bg_item.setBrush(QBrush(color))
        self._thumb_timer.start()
        self.status_bar.showMessage(f"Background set to {color.name()}.", 2500)

    def _reset_current_slide(self) -> None:
        """Restore the placeholder boxes' formatting; typed text is kept, as Office."""
        slide = self._current_slide()
        if slide is None:
            return
        self.scene.sync_to_slide()
        specs = {spec[0]: spec for spec in LAYOUT_PLACEHOLDERS.get(slide.layout, ())}
        for obj in slide.objects:
            spec = specs.get(obj.id)
            if spec is None or not isinstance(obj, TextObject):
                continue
            _, x, y, w, h, size, bold, align = spec
            obj.x, obj.y, obj.width, obj.height = x, y, w, h
            obj.font_size, obj.bold, obj.alignment = size, bold, align
            obj.italic = obj.underline = obj.strike = False
            obj.line_spacing = 1.0
        self.scene.load_slide(slide)
        self._thumb_timer.start()
        self.status_bar.showMessage("Slide placeholders reset.", 2500)

    def _change_layout(self, layout_key: str) -> None:
        """Reflow the current slide into *layout_key*'s placeholders."""
        slide = self._current_slide()
        if slide is None or layout_key not in LAYOUT_PLACEHOLDERS:
            return
        self.scene.sync_to_slide()
        slide.apply_layout(layout_key)
        self.scene.load_slide(slide)
        self._refresh_current_thumbnail()
        caption = dict(self._LAYOUTS).get(layout_key, layout_key)
        self.status_bar.showMessage(f"Layout changed to: {caption}", 2500)

    def _current_slide(self) -> Optional[Slide]:
        if 0 <= self.current_slide_idx < len(self.presentation.slides):
            return self.presentation.slides[self.current_slide_idx]
        return None

    # --- Z-Order & Alignment ---

    def _bring_to_front(self) -> None:
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue() + 1)

    def _send_to_back(self) -> None:
        for item in self.scene.selectedItems():
            item.setZValue(item.zValue() - 1)

    def _align_objects(self, align: str) -> None:
        items = self.scene.selectedItems()
        if not items:
            return
        if align == "left":
            min_x = min(item.x() for item in items)
            for item in items:
                item.setX(min_x)
        elif align == "right":
            max_x = max(item.x() + item.boundingRect().width() for item in items)
            for item in items:
                item.setX(max_x - item.boundingRect().width())
        elif align == "center":
            avg_x = sum(item.x() + item.boundingRect().width() / 2 for item in items) / len(items)
            for item in items:
                item.setX(avg_x - item.boundingRect().width() / 2)

    # --- Slide Show ---

    def start_slideshow_beginning(self) -> None:
        self.scene.sync_to_slide()
        self.presenter = PresenterWindow(self.presentation, start_index=0)
        self.presenter.show()

    def start_slideshow_current(self) -> None:
        self.scene.sync_to_slide()
        self.presenter = PresenterWindow(self.presentation, start_index=self.current_slide_idx)
        self.presenter.show()

    def start_presenter_view(self) -> None:
        """The same fullscreen show, opened with its speaker-notes overlay on."""
        self.scene.sync_to_slide()
        self.presenter = PresenterWindow(self.presentation,
                                         start_index=self.current_slide_idx,
                                         show_notes=True)
        self.presenter.show()

    def _fit_slide_to_window(self) -> None:
        """PowerPoint's "Fit Slide to Window": back to the automatic scale."""
        self.canvas_view.set_fit_to_view(True)
        self.canvas_view.fit_slide_to_view()
        self.status_bar.showMessage("Slide fitted to the window.", 2000)

    # --- Document Lifecycle ---

    def on_new(self) -> None:
        self.presentation = Presentation("Untitled Presentation")
        self.current_slide_idx = 0
        self.current_filepath = None
        self._refresh_slide_list()
        self._update_window_title()

    # -- starting from a design ---------------------------------------------- #

    def template_entries(self) -> list:
        """The deck designs, each shown as the sheet its deck opens on."""
        if self._designs is None:
            from officer.presentr.deck_templates import (DECK_TEMPLATES,
                                                         build_deck_tiles,
                                                         gallery_entries)
            self._designs = gallery_entries(DECK_TEMPLATES,
                                            build_deck_tiles())
        return self._designs

    def template_held(self) -> bool:
        """Whether the deck holds more than the blank sheet it starts with."""
        slides = self.presentation.slides
        return len(slides) > 1 or bool(slides and slides[0].objects)

    def apply_template(self, key: str) -> None:
        design = deck_named(key)
        if design is None:
            return
        design.apply_to(self.presentation)
        self.current_slide_idx = 0
        self._refresh_slide_list()
        self._update_window_title()

    def on_open(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Presentation", "", "Presentations (*.pptx *.odp);;All Files (*.*)"
        )
        if filepath:
            self.open_path(filepath)

    def open_path(self, filepath: str) -> bool:
        """Read a deck from disk into this window, as the shell asks on start."""
        ext = os.path.splitext(filepath)[1].lower()
        loaded_prs = None

        if ext == ".pptx":
            loaded_prs = PptxHandler.load(filepath)
        elif ext == ".odp":
            loaded_prs = OdpHandler.load(filepath)

        if loaded_prs:
            self.presentation = loaded_prs
            self.current_slide_idx = 0
            self.current_filepath = filepath
            self._refresh_slide_list()
            self._update_window_title()
            self.status_bar.showMessage(f"Opened: {os.path.basename(filepath)}", 3000)
            return True
        QMessageBox.critical(self, "Error", f"Failed to open presentation: {filepath}")
        return False

    def on_save(self) -> None:
        if self.current_filepath:
            self._save_to_path(self.current_filepath)
        else:
            self.on_save_as()

    def on_save_as(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Presentation As", "Presentation.pptx",
            "PowerPoint Presentation (*.pptx);;OpenDocument Presentation (*.odp)"
        )
        if filepath:
            self._save_to_path(filepath)

    def _save_to_path(self, filepath: str) -> None:
        self.scene.sync_to_slide()
        ext = os.path.splitext(filepath)[1].lower()
        success = False

        if ext == ".pptx":
            success = PptxHandler.save(filepath, self.presentation)
        elif ext == ".odp":
            success = OdpHandler.save(filepath, self.presentation)

        if success:
            self.current_filepath = filepath
            self._update_window_title()
            self.status_bar.showMessage(f"Saved: {os.path.basename(filepath)}", 3000)
        else:
            QMessageBox.critical(self, "Error", f"Failed to save presentation to {filepath}")

    def export_pdf(self, filepath: str) -> bool:
        """Write every slide to *filepath*, one sheet per slide, at the slide's size.

        The deck is its own paper: a 16:9 show printed on A4 arrives with bars of
        blank sheet down the sides, and the scene's pixels are 96 to the inch, so
        the sheet is cut from the slide's own measurements.
        """
        self.scene.sync_to_slide()
        wide = self.presentation.width * 10 / PX_PER_CM
        tall = self.presentation.height * 10 / PX_PER_CM
        writer = QPdfWriter(filepath)
        # The slide's measurements already say which way it lies, so the layout
        # takes them unrotated; asking for Landscape on top turns a 16:9 sheet
        # back into a portrait page.
        writer.setPageLayout(QPageLayout(
            QPageSize(QSizeF(wide, tall), QPageSize.Unit.Millimeter),
            QPageLayout.Orientation.Portrait,
            QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter))
        writer.setResolution(150)

        painter = QPainter(writer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = writer.pageLayout().paintRectPixels(writer.resolution())
        scale = area.width() / self.presentation.width
        temp_scene = SlideCanvasScene(self.presentation.width, self.presentation.height)

        for s_idx, slide in enumerate(self.presentation.slides):
            if s_idx > 0:
                writer.newPage()
            painter.resetTransform()
            painter.translate(area.topLeft())
            painter.scale(scale, scale)
            temp_scene.load_slide(slide)
            temp_scene.render(painter)

        painter.end()
        return os.path.exists(filepath) and os.path.getsize(filepath) > 0

    def on_export_pdf(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Presentation to PDF", "Presentation.pdf", "PDF Files (*.pdf)"
        )
        if not filepath:
            return

        if self.export_pdf(filepath):
            self.status_bar.showMessage(f"Exported PDF: {os.path.basename(filepath)}", 3000)
            QMessageBox.information(self, "PDF Export Complete", f"Successfully exported to:\n{filepath}")
        else:
            QMessageBox.critical(self, "Error", "Failed to export presentation to PDF.")

    # --- AI Slide Creator ---

    def _ai_generate_outline(self) -> None:
        topic, ok = QInputDialog.getText(
            self, "AI Presentation Generator", "Enter presentation topic:"
        )
        if not ok or not topic.strip():
            return

        self.status_bar.showMessage("AI is generating slide deck outline...", 5000)
        prompt = f"Create a 4-slide presentation outline for topic: '{topic}'. Format as Slide Title followed by 3 concise bullet points."
        self.ai_client.generate_async(
            prompt=prompt,
            on_success=self._on_ai_outline_received,
            on_error=lambda err: QMessageBox.warning(self, "AI Notice", f"Ollama not reachable: {err}")
        )

    def _on_ai_outline_received(self, text: str) -> None:
        QMessageBox.information(self, "Generated Presentation Outline", text)

    def _ai_enhance_bullets(self) -> None:
        for item in self.scene.selectedItems():
            if hasattr(item, "toPlainText"):
                raw = item.toPlainText()
                self.status_bar.showMessage("AI is polishing bullet points...", 5000)
                prompt = f"Make these presentation bullet points punchy and professional:\n\n{raw}"
                self.ai_client.generate_async(
                    prompt=prompt,
                    on_success=lambda res: item.setPlainText(res.strip()),
                    on_error=lambda err: QMessageBox.warning(self, "AI Notice", f"Ollama not reachable: {err}")
                )
                return
        QMessageBox.information(self, "AI Assist", "Please select a text box on the slide first.")
