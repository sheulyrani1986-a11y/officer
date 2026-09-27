"""Fullscreen Presenter Mode window for slide deck presentation."""

from typing import List, Optional, Tuple
from PySide6.QtCore import (
    Qt, QAbstractAnimation, QEasingCurve, QPropertyAnimation, QPointF, QVariantAnimation
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGraphicsView, QLabel, QGraphicsOpacityEffect
)
from PySide6.QtGui import QKeyEvent, QPainter
from officer.presentr.slide_deck import Presentation, Slide, SlideObject
from officer.presentr.canvas import SlideCanvasScene

#: How long one of PowerPoint's entrance effects runs.
ANIMATION_MS = 400
#: How long the show takes to arrive on a slide that has a transition.
TRANSITION_MS = 320
#: A fly-in starts one whole slide off to the left; a zoom starts this small.
ZOOM_START = 0.55

FORWARD_KEYS = (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Space, Qt.Key.Key_PageDown)
BACK_KEYS = (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Backspace, Qt.Key.Key_PageUp)


class PresenterWindow(QWidget):
    """Clean fullscreen presentation playback window.

    Press N during the show to toggle the speaker notes overlay for the
    current slide. The overlay is hidden by default so the audience view is
    unaffected.

    An object carrying an entrance animation appears one click at a time, and a
    slide's transition plays as the show arrives on it. A click therefore does
    double duty: it finishes the slide's build first and only then moves on.
    """

    def __init__(
        self,
        presentation: Presentation,
        start_index: int = 0,
        show_notes: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent, Qt.WindowType.Window)
        self.presentation = presentation
        self.current_index = max(0, min(start_index, len(presentation.slides) - 1))
        # Objects waiting to be clicked into view, and those already shown.
        self._pending: List[Tuple[object, SlideObject]] = []
        self._revealed: List[Tuple[object, SlideObject]] = []
        # Effects still running, so a fast clicker never leaves a slide half-drawn.
        self._effects: List[QPropertyAnimation] = []

        self.setWindowTitle("PresentR - Slide Show")
        self.setStyleSheet("background-color: #000000;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scene = SlideCanvasScene(self.presentation.width, self.presentation.height, self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.view.setStyleSheet("background-color: #000000; border: none;")
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.view, 1)

        # Speaker notes overlay docked below the slide (hidden until toggled)
        self.notes_label = QLabel(self)
        self.notes_label.setWordWrap(True)
        self.notes_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.notes_label.setStyleSheet(
            "background-color:#111827;color:#F9FAFB;font-size:16px;"
            "padding:12px 16px;border-top:1px solid #374151;"
        )
        self.notes_label.setMaximumHeight(180)
        self.notes_label.setVisible(False)
        layout.addWidget(self.notes_label, 0)

        if show_notes:
            self._set_notes_visible(True)

        self._show_current_slide()
        self.showFullScreen()

    @property
    def current_slide(self) -> Optional[Slide]:
        """The slide currently being shown, or None if the index is out of range."""
        if 0 <= self.current_index < len(self.presentation.slides):
            return self.presentation.slides[self.current_index]
        return None

    def _show_current_slide(self, reveal_all: bool = False, transition: bool = True) -> None:
        self._finish_effects()
        slide = self.current_slide
        if slide is not None:
            self.scene.load_slide(slide)
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._stage_animations(slide, reveal_all=reveal_all)
            if transition:
                self._play_transition(slide)
        self._refresh_notes()

    # -- entrance animations --------------------------------------------------- #

    def _stage_animations(self, slide: Slide, reveal_all: bool = False) -> None:
        """Hold back every animated object on the slide, in the order it was added.

        Objects are matched to their drawing by identity, not by value: two
        placeholders on the same slide can carry the same box, and a slide model
        built from dataclasses cannot be used as a dictionary key at all.
        """
        self._pending = []
        self._revealed = []
        drawn = [(item, item.data(0)) for item in self.scene.items()
                 if item.data(0) is not None]
        for obj in slide.objects:
            item = next((it for it, data in drawn if data is obj), None)
            if item is None or obj.animation == "none":
                continue
            if reveal_all:
                self._revealed.append((item, obj))
                continue
            self._hide(item, obj)
            self._pending.append((item, obj))

    def _hide(self, item, obj: SlideObject) -> None:
        """Put an object back the way it was before its entrance ran."""
        item.setPos(obj.x - self.presentation.width if obj.animation == "fly_in" else obj.x,
                    obj.y)
        item.setScale(ZOOM_START if obj.animation == "zoom" else 1.0)
        item.setOpacity(0.0)

    def _settle(self, item, obj: SlideObject) -> None:
        """The end state of every entrance effect, however it got there."""
        item.setPos(obj.x, obj.y)
        item.setScale(1.0)
        item.setOpacity(1.0)

    def reveal_next(self) -> bool:
        """Bring in the next waiting object. False when the slide is complete."""
        if not self._pending:
            return False
        item, obj = self._pending.pop(0)
        self._revealed.append((item, obj))
        self._animate_in(item, obj)
        return True

    def _animate_in(self, item, obj: SlideObject) -> None:
        """Run one entrance effect, leaving the object in its final place.

        A slide object is drawn by a ``QGraphicsItem``, which is not a ``QObject``
        and so cannot be a property animation's target. The values come off a
        variant animation and go in through the item's own setters instead.
        """
        effect = QVariantAnimation(self)
        effect.setDuration(ANIMATION_MS)
        effect.setEasingCurve(QEasingCurve.Type.OutCubic)
        if obj.animation == "fly_in":
            item.setOpacity(1.0)  # only a fade travels while invisible
            effect.setStartValue(QPointF(obj.x - self.presentation.width, obj.y))
            effect.setEndValue(QPointF(obj.x, obj.y))
            effect.valueChanged.connect(lambda value: item.setPos(value))
        elif obj.animation == "zoom":
            item.setOpacity(1.0)
            # Grow from the middle of the object, as PowerPoint's Zoom does,
            # rather than from its top-left corner.
            item.setTransformOriginPoint(item.boundingRect().center())
            effect.setStartValue(ZOOM_START)
            effect.setEndValue(1.0)
            effect.valueChanged.connect(lambda value: item.setScale(value))
        else:  # fade
            effect.setStartValue(0.0)
            effect.setEndValue(1.0)
            effect.valueChanged.connect(lambda value: item.setOpacity(value))
        effect.finished.connect(lambda: self._settle(item, obj))
        effect.finished.connect(lambda: self._effects.remove(effect)
                                if effect in self._effects else None)
        self._effects.append(effect)
        effect.start()

    def hide_last(self) -> bool:
        """Send the last object back out, the way PowerPoint's Page Up does."""
        if not self._revealed:
            return False
        item, obj = self._revealed.pop()
        self._pending.insert(0, (item, obj))
        self._finish_effects()
        self._hide(item, obj)
        return True

    def _finish_effects(self) -> None:
        """Run every live effect straight to its end state.

        A presenter who holds the arrow key must not end up on a slide with a
        title frozen at half opacity. Stopping an animation that is still running
        fires the same signal its natural end would, so the handlers that put each
        object in its final place still run.
        """
        for effect in list(self._effects):
            if effect.state() == QAbstractAnimation.State.Running:
                effect.stop()

    # -- slide transitions ------------------------------------------------------ #

    def _play_transition(self, slide: Slide) -> None:
        """Play the way the show arrives on *slide*: nothing, a fade, or a push."""
        if slide.transition == "fade":
            self._fade_slide_in()
        elif slide.transition == "push":
            self._push_slide_in()

    def _fade_slide_in(self) -> None:
        """Fade the whole slide up through an effect the view owns and deletes."""
        fade_effect = QGraphicsOpacityEffect(self.view)
        self.view.setGraphicsEffect(fade_effect)
        effect = QPropertyAnimation(fade_effect, b"opacity", self)
        effect.setDuration(TRANSITION_MS)
        effect.setStartValue(0.0)
        effect.setEndValue(1.0)
        effect.setEasingCurve(QEasingCurve.Type.InOutQuad)
        # Handing the view a fresh effect deletes the previous one, so the fade
        # has to be over before it is let go of.
        effect.finished.connect(lambda: self._end_fade(effect))
        self._effects.append(effect)
        effect.start()

    def _end_fade(self, effect: QPropertyAnimation) -> None:
        """Let the view go, which is what deletes the effect it was fading through."""
        self.view.setGraphicsEffect(None)
        if effect in self._effects:
            self._effects.remove(effect)

    def _push_slide_in(self) -> None:
        """Slide the new page in from the right, PowerPoint's push."""
        offset = QVariantAnimation(self)
        offset.setDuration(TRANSITION_MS)
        offset.setStartValue(float(self.presentation.width))
        offset.setEndValue(0.0)
        offset.valueChanged.connect(self._push_slide_to)
        # Cut short mid-push, the page still has to end up square in the viewport.
        offset.finished.connect(lambda: self._push_slide_to(0.0))
        offset.finished.connect(lambda: self._effects.remove(offset)
                                if offset in self._effects else None)
        self._effects.append(offset)
        offset.start()

    def _push_slide_to(self, offset: float) -> None:
        self.view.resetTransform()
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        if offset:
            self.view.translate(offset, 0.0)

    # -- the rest of the show --------------------------------------------------- #

    def step_forward(self) -> bool:
        """The next click: finish this slide's build, or turn to the next one.

        False once the show has run off its end and closed.
        """
        if self.reveal_next():
            return True
        if self.current_index >= len(self.presentation.slides) - 1:
            self.close()  # End of slideshow
            return False
        self.current_index += 1
        self._show_current_slide()
        return True

    def step_back(self) -> bool:
        """Undo the last click: hide an object, or return to the previous slide."""
        if self.hide_last():
            return True
        if self.current_index <= 0:
            return False
        self.current_index -= 1
        # Walking back lands on a slide the audience has already seen finished,
        # so its build is shown complete rather than replayed.
        self._show_current_slide(reveal_all=True, transition=False)
        return True

    def _refresh_notes(self) -> None:
        """Update the notes overlay text from the current slide's model."""
        slide = self.current_slide
        notes = slide.notes.strip() if slide and slide.notes else ""
        self.notes_label.setText(notes if notes else "No notes for this slide.")

    def _set_notes_visible(self, visible: bool) -> None:
        self.notes_label.setVisible(visible)
        self._refresh_notes()

    def toggle_notes(self) -> None:
        """Show or hide the speaker notes overlay (N)."""
        self._set_notes_visible(not self.notes_label.isVisible())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in FORWARD_KEYS:
            self.step_forward()
        elif key in BACK_KEYS:
            self.step_back()
        elif key == Qt.Key.Key_N:
            self.toggle_notes()
        elif key == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)
