"""Data model for PresentR slides and objects."""

from dataclasses import dataclass, field
from typing import List, Optional

#: The face a slide's text is drawn in when nobody has chosen one. PowerPoint's
#: own theme font, and the one PresentR's canvas has always used.
DEFAULT_FONT_FAMILY = "Segoe UI"


@dataclass
class SlideObject:
    """Base class for visual objects on a slide."""
    id: str
    x: float
    y: float
    width: float
    height: float
    z_order: int = 0
    #: How the object arrives during the show: none, fade, fly_in or zoom.
    animation: str = "none"


@dataclass
class TextObject(SlideObject):
    text: str = ""
    #: The face PowerPoint's Latin theme font resolves to on this machine, and
    #: the face a box is drawn in until the ribbon is pointed at another.
    font_family: str = DEFAULT_FONT_FAMILY
    font_size: int = 24
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    text_color: str = "#111827"
    alignment: str = "left"
    line_spacing: float = 1.0  # 1.0 / 1.5 / 2.0, as PowerPoint's Paragraph picker


@dataclass
class ShapeObject(SlideObject):
    shape_type: str = "rect"  # see canvas.shape_path and the PPTX writer's table
    fill_color: str = "#3B82F6"
    #: The second stop of a gradient fill. ``None`` keeps the shape one flat
    #: colour, which is what PowerPoint hands out until asked otherwise.
    gradient_color: Optional[str] = None
    border_color: str = "#1D4ED8"
    border_width: int = 2
    #: Degrees, clockwise, about the shape's own centre.
    rotation: float = 0.0


@dataclass
class ImageObject(SlideObject):
    image_path: str = ""


#: (role, x, y, width, height, font size, bold, alignment) for each layout's
#: placeholders. Both :meth:`Presentation.add_slide` and
#: :meth:`Slide.apply_layout` read this, so a new slide and a layout change can
#: never disagree about where PowerPoint's boxes sit.
LAYOUT_PLACEHOLDERS = {
    "title": (
        ("title", 100, 160, 760, 80, 40, True, "center"),
        ("subtitle", 150, 260, 660, 60, 20, False, "center"),
    ),
    "title_content": (
        ("title", 60, 40, 840, 60, 32, True, "left"),
        ("content", 60, 120, 840, 360, 20, False, "left"),
    ),
    "two_content": (
        ("title", 60, 40, 840, 60, 32, True, "left"),
        ("left", 60, 120, 405, 360, 18, False, "left"),
        ("right", 495, 120, 405, 360, 18, False, "left"),
    ),
    "blank": (),
}

#: The text a placeholder carries before the presenter types over it.
PLACEHOLDER_PROMPTS = {
    "title": "Slide Title",
    "subtitle": "Click to add subtitle",
    "content": "• First bullet point\n• Second bullet point\n• Third bullet point",
    "left": "• Left column",
    "right": "• Right column",
}


def make_placeholder(role: str, x: float, y: float, width: float, height: float,
                     font_size: int, bold: bool, alignment: str) -> TextObject:
    """Build one empty placeholder box for *role*."""
    return TextObject(
        id=role, x=x, y=y, width=width, height=height,
        text=PLACEHOLDER_PROMPTS.get(role, ""), font_size=font_size,
        bold=bold, alignment=alignment
    )


@dataclass
class Slide:
    title: str = "Untitled Slide"
    layout: str = "title_content"  # see LAYOUT_PLACEHOLDERS
    background_color: str = "#FFFFFF"
    objects: List[SlideObject] = field(default_factory=list)
    notes: str = ""  # Speaker notes shown in the notes panel and presenter view
    #: How the show arrives at this slide: none, fade or push.
    transition: str = "none"

    def apply_layout(self, layout: str) -> None:
        """Reflow this slide's text into *layout*'s placeholder rectangles.

        Existing content keeps its text and moves to the new box; a placeholder
        the slide lacks is added. Blank deliberately leaves everything on the
        slide rather than deleting what the presenter has typed.
        """
        placeholders = LAYOUT_PLACEHOLDERS.get(layout)
        if placeholders is None:
            return
        self.layout = layout
        boxes = {obj.id: obj for obj in self.objects if isinstance(obj, TextObject)}
        for spec in placeholders:
            role, x, y, w, h, size, bold, align = spec
            box = boxes.get(role)
            if box is None:
                self.objects.append(make_placeholder(*spec))
                continue
            box.x, box.y, box.width, box.height = x, y, w, h
            box.font_size, box.bold, box.alignment = size, bold, align
            if not box.text.strip():
                box.text = PLACEHOLDER_PROMPTS.get(role, "")


class Presentation:
    """Presentation deck containing multiple slides."""

    def __init__(self, title: str = "Presentation"):
        self.title = title
        # 16:9 widescreen canvas standard coordinates: 960 x 540
        self.width = 960
        self.height = 540
        self.slides: List[Slide] = []
        self._create_default_slide()

    def _create_default_slide(self) -> None:
        title_slide = Slide(title="Title Slide", layout="title")
        for spec in LAYOUT_PLACEHOLDERS["title"]:
            title_slide.objects.append(make_placeholder(*spec))
        self.slides.append(title_slide)

    def add_slide(self, layout: str = "title_content") -> Slide:
        slide = Slide(title=f"Slide {len(self.slides) + 1}", layout=layout)
        for spec in LAYOUT_PLACEHOLDERS.get(layout, ()):
            slide.objects.append(make_placeholder(*spec))
        self.slides.append(slide)
        return slide
