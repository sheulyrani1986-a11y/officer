"""Equation Editor Dialog for WriteR.

An equation is text here: what a person types -- LaTeX-style shorthand or plain
``a^2 + b^2`` -- is converted to Unicode maths characters (see
:mod:`officer.writer.unicode_math`), so the inserted equation can be searched,
corrected a symbol at a time and read aloud.

matplotlib can still draw the expression as a picture on request, for the
structures stacked characters cannot express. That is the opt-in button, not the
default one, and it stands down when matplotlib is not installed.
"""

import html
import tempfile
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QDialogButtonBox, QScrollArea, QWidget
)
from PySide6.QtGui import QFont

from officer.core.ui.fonts import math_font
from officer.writer.unicode_math import to_math_runs, to_unicode_math


_COMMON_EQUATIONS = [
    (r"$\sum_{i=1}^{n} x_i$", "Summation"),
    (r"$\int_a^b f(x)\,dx$", "Integral"),
    (r"$\frac{a}{b}$", "Fraction"),
    (r"$\sqrt{x}$", "Square Root"),
    (r"$x^2 + y^2 = z^2$", "Pythagorean"),
    (r"$e^{i\pi} + 1 = 0$", "Euler's Identity"),
    (r"$\lim_{x \to \infty} f(x)$", "Limit"),
    (r"$\alpha, \beta, \gamma, \delta$", "Greek Letters"),
    (r"$\pm, \leq, \geq, \neq$", "Symbols"),
]


def preview_html(equation: str) -> str:
    """The Unicode equation marked up the way the document will hold it.

    A script Unicode could not raise -- there is no superscript pi -- reaches
    the document as a raised run instead, so the preview raises it the same way
    rather than showing the ``^(...)`` the fallback spells it with.
    """
    pieces = []
    for text, script in to_math_runs(equation):
        escaped = html.escape(text).replace("\n", "<br>")
        if script > 0:
            escaped = f"<sup>{escaped}</sup>"
        elif script < 0:
            escaped = f"<sub>{escaped}</sub>"
        pieces.append(escaped)
    return "".join(pieces)


class EquationDialog(QDialog):
    """Modal dialog for inserting mathematical equations into WriteR."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Equation")
        self.setMinimumWidth(520)
        self.setMinimumHeight(380)
        self._equation_text = ""
        self._rendered_path: Optional[str] = None
        self._picture_requested = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 12)

        # Header
        header = QLabel("Insert Mathematical Equation")
        header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(header)

        # Expression input
        input_label = QLabel(
            "LaTeX or plain maths (e.g. <b>$\\sqrt{x^2 + y^2}$</b>, <b>x^2 + 3</b>):"
        )
        input_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(input_label)

        self._latex_input = QLineEdit(r"$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$")
        self._latex_input.setMinimumHeight(32)
        self._latex_input.setFont(QFont("Courier New", 10))
        self._latex_input.textChanged.connect(self._on_input_changed)
        layout.addWidget(self._latex_input)

        # The Unicode text the expression becomes, in the face it is inserted in
        preview_label = QLabel("Unicode equation (inserted as editable text):")
        layout.addWidget(preview_label)
        self._preview = QLabel()
        self._preview.setTextFormat(Qt.TextFormat.RichText)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setFont(math_font(15))
        self._preview.setWordWrap(True)
        self._preview.setMinimumHeight(90)
        self._preview.setStyleSheet(
            "background: #ffffff; border: 1px solid #d1d5db; border-radius: 4px;"
        )
        layout.addWidget(self._preview)

        # Quick-pick common equations
        quick_label = QLabel("Quick insert:")
        layout.addWidget(quick_label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(60)
        quick_widget = QWidget()
        quick_layout = QHBoxLayout(quick_widget)
        quick_layout.setContentsMargins(4, 4, 4, 4)
        quick_layout.setSpacing(6)
        for latex, name in _COMMON_EQUATIONS:
            btn = QPushButton(name)
            btn.setFixedHeight(28)
            btn.setToolTip(latex)
            btn.clicked.connect(lambda checked=False, l=latex: self._set_quick(l))
            quick_layout.addWidget(btn)
        quick_layout.addStretch()
        scroll.setWidget(quick_widget)
        layout.addWidget(scroll)

        # Insert as text / Insert as picture / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Insert Text")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self._picture_button = buttons.addButton(
            "Insert as Picture", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self._picture_button.clicked.connect(self._request_picture)
        if self._picture_available():
            self._picture_button.setToolTip(
                "Draw the expression with matplotlib and insert the picture instead"
            )
        else:
            self._picture_button.setEnabled(False)
            self._picture_button.setToolTip("Requires matplotlib, which is not installed")
        layout.addWidget(buttons)

        self._on_input_changed(self._latex_input.text())

    # ------------------------------------------------------------------ state #

    def _set_quick(self, latex: str) -> None:
        self._latex_input.setText(latex)

    def _on_input_changed(self, text: str) -> None:
        self._equation_text = to_unicode_math(text)
        self._preview.setText(preview_html(self._equation_text))

    def _request_picture(self) -> None:
        self._picture_requested = True

    def _on_accept(self) -> None:
        """Text needs no rendering; only the picture request costs a render."""
        self._rendered_path = None
        if self._picture_requested:
            self._rendered_path = self._render_to_file(self._latex_input.text())
            self._picture_requested = False
        self.accept()

    def equation_text(self) -> str:
        """The equation as Unicode maths characters, ready to insert as text."""
        return self._equation_text

    def rendered_image_path(self) -> Optional[str]:
        """Path of the rendered picture, or None when the text is wanted."""
        return self._rendered_path

    # ------------------------------------------------------------- matplotlib #

    def _picture_available(self) -> bool:
        try:
            import matplotlib  # noqa: F401
        except Exception:
            return False
        return True

    def _render_to_file(self, latex: str) -> Optional[str]:
        """Render *latex* via matplotlib mathtext → temp PNG. Returns path or None."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(4, 1))
            ax.axis("off")
            ax.text(
                0.5, 0.5, latex,
                transform=ax.transAxes,
                fontsize=18,
                ha="center", va="center",
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False,
                                              prefix="officer_eq_")
            fig.savefig(tmp.name, bbox_inches="tight", pad_inches=0.1, dpi=150,
                        transparent=True)
            plt.close(fig)
            return tmp.name
        except Exception:
            return None
