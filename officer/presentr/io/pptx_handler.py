"""PPTX import and export handler for PresentR using python-pptx."""

import os
from typing import Optional
from pptx import Presentation as PptxPresentation
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.enum.dml import MSO_FILL
from pptx.dml.color import RGBColor
from officer.presentr.slide_deck import Presentation, Slide, TextObject, ShapeObject, ImageObject

#: PresentR's shape keys → the DrawingML preset each one exports as. python-pptx
#: spells "ISOSCELES_TRIANGLE" with its own historical typo, and a name that is
#: missing must not abort a save, hence .get() with a rectangle below.
_MSO_SHAPES = {
    "rect": MSO_SHAPE.RECTANGLE,
    "rounded_rect": MSO_SHAPE.ROUNDED_RECTANGLE,
    "ellipse": MSO_SHAPE.OVAL,
    "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE,
    "right_triangle": MSO_SHAPE.RIGHT_TRIANGLE,
    "diamond": MSO_SHAPE.DIAMOND,
    "pentagon": MSO_SHAPE.REGULAR_PENTAGON,
    "hexagon": MSO_SHAPE.HEXAGON,
    "octagon": MSO_SHAPE.OCTAGON,
    "star": MSO_SHAPE.STAR_5_POINT,
    "star_4": MSO_SHAPE.STAR_4_POINT,
    "arrow": MSO_SHAPE.RIGHT_ARROW,
    "double_arrow": MSO_SHAPE.LEFT_RIGHT_ARROW,
    "down_arrow": MSO_SHAPE.DOWN_ARROW,
    "chevron": MSO_SHAPE.CHEVRON,
    "parallelogram": MSO_SHAPE.PARALLELOGRAM,
    "trapezoid": MSO_SHAPE.TRAPEZOID,
    "plus": MSO_SHAPE.MATH_PLUS,
    "heart": MSO_SHAPE.HEART,
    "donut": MSO_SHAPE.DONUT,
    "pie": MSO_SHAPE.PIE,
    "frame": MSO_SHAPE.FRAME,
    "line": MSO_SHAPE.LINE_INVERSE,
}

#: The same table reversed, for reading a deck back. Every preset PresentR writes
#: is unique, so an auto-shape reopens as the button that created it.
_SHAPE_TYPES = {shape: key for key, shape in _MSO_SHAPES.items()}

#: PresentR's alignment names ↔ python-pptx's paragraph alignment enum.
_ALIGN_TO_PP = {
    "left": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}
_PP_TO_ALIGN = {value: key for key, value in _ALIGN_TO_PP.items()}


def _hex(color: str) -> str:
    """'#RRGGBB' with or without the lead, upper case, as DrawingML wants it."""
    return (color or "").lstrip("#").upper()


def _read_text_format(paragraph) -> dict:
    """The TextObject keyword arguments stored on one PowerPoint paragraph."""
    font = paragraph.font
    attrs = {
        "bold": bool(font.bold),
        "italic": bool(font.italic),
        # python-pptx answers None for "inherited", and MSO_UNDERLINE members
        # for anything set, so only a plain True counts as underlined.
        "underline": font.underline is True,
        "alignment": _PP_TO_ALIGN.get(paragraph.alignment, "left"),
    }
    r_pr = getattr(font, "_rPr", None)
    if r_pr is not None:
        attrs["strike"] = r_pr.get("strike") == "sngStrike"

    if font.size is not None:
        attrs["font_size"] = int(round(font.size.pt))
    if font.name:
        # A theme-inherited run names no face of its own; PresentR's default
        # stands in for those, the same way PowerPoint's does.
        attrs["font_family"] = font.name
    try:
        if font.color and font.color.type is not None:
            attrs["text_color"] = f"#{font.color.rgb}"
    except (AttributeError, TypeError):
        pass  # a theme colour has no rgb; PresentR's default stands

    spacing = paragraph.line_spacing
    if isinstance(spacing, float):
        attrs["line_spacing"] = round(spacing, 2)
    return attrs


def _write_text_format(paragraph, obj: TextObject) -> None:
    """Store *obj*'s formatting on *paragraph*, the inverse of the reader above."""
    font = paragraph.font
    font.name = obj.font_family
    font.size = Pt(obj.font_size)
    font.bold = obj.bold
    font.italic = obj.italic
    font.underline = obj.underline
    # python-pptx has no Font.strike; strikethrough is just an attribute on the
    # run's rPr element.
    font._rPr.set("strike", "sngStrike" if obj.strike else "noStrike")
    paragraph.alignment = _ALIGN_TO_PP.get(obj.alignment, PP_ALIGN.LEFT)
    if obj.line_spacing != 1.0:
        paragraph.line_spacing = obj.line_spacing
    font.color.rgb = RGBColor.from_string(_hex(obj.text_color))


def _auto_shape_type(shape) -> Optional[str]:
    """The PresentR key for an auto-shape, or None if it is not one we draw."""
    try:
        preset = shape.auto_shape_type
    except (AttributeError, ValueError, TypeError):
        # python-pptx raises for a shape with no prstGeom, and for an MSO_FILL
        # value that is not a preset.
        return None
    return _SHAPE_TYPES.get(preset)


def _read_shape_colors(shape) -> dict:
    """fill_color / border_color for a solid autoshape; theme fills keep the defaults."""
    attrs = {}
    try:
        if shape.fill.type == MSO_FILL.SOLID:
            attrs["fill_color"] = f"#{shape.fill.fore_color.rgb}"
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        if shape.fill.type == MSO_FILL.GRADIENT:
            stops = shape.fill.gradient_stops
            attrs["fill_color"] = f"#{stops[0].color.rgb}"
            attrs["gradient_color"] = f"#{stops[-1].color.rgb}"
    except (AttributeError, TypeError, ValueError, IndexError):
        pass  # a gradient we cannot read stays a flat shape
    try:
        if shape.line.color and shape.line.color.type is not None:
            attrs["border_color"] = f"#{shape.line.color.rgb}"
    except (AttributeError, TypeError, ValueError):
        pass
    return attrs


def _write_shape_colors(shape, obj: ShapeObject) -> None:
    """Paint *obj*'s fill, gradient and outline onto the PowerPoint shape."""
    try:
        if obj.gradient_color:
            shape.fill.gradient()
            stops = shape.fill.gradient_stops
            stops[0].color.rgb = RGBColor.from_string(_hex(obj.fill_color))
            stops[-1].color.rgb = RGBColor.from_string(_hex(obj.gradient_color))
        else:
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor.from_string(_hex(obj.fill_color))
        shape.line.color.rgb = RGBColor.from_string(_hex(obj.border_color))
    except (AttributeError, TypeError, ValueError):
        pass  # an unreadable colour must not lose the whole deck


class PptxHandler:
    """Handles importing and exporting .pptx presentation files."""

    @staticmethod
    def load(filepath: str) -> Optional[Presentation]:
        """Load a .pptx file into PresentR Presentation object."""
        if not os.path.exists(filepath):
            return None

        try:
            prs = PptxPresentation(filepath)
            presentation = Presentation(title=os.path.basename(filepath))
            presentation.slides.clear()

            # Coordinates factor: 1 inch = 96 px
            for s_idx, slide_data in enumerate(prs.slides):
                slide = Slide(title=f"Slide {s_idx + 1}")

                for shape in slide_data.shapes:
                    x = shape.left.inches * 96 if shape.left else 50
                    y = shape.top.inches * 96 if shape.top else 50
                    w = shape.width.inches * 96 if shape.width else 200
                    h = shape.height.inches * 96 if shape.height else 100

                    if shape.has_text_frame:
                        paragraphs = [p for p in shape.text_frame.paragraphs if p.text]
                        full_text = "\n".join(p.text for p in paragraphs)
                        if full_text.strip():
                            # Formatting lives on the first run; PresentR's model
                            # has one style per box, the way its editor paints one.
                            defaults = {
                                "font_size": 24 if "title" in shape.name.lower() else 18,
                                "bold": "title" in shape.name.lower(),
                            }
                            if paragraphs:
                                defaults.update(_read_text_format(paragraphs[0]))
                            txt_obj = TextObject(
                                id=f"text_{len(slide.objects)}",
                                x=x, y=y, width=w, height=h,
                                text=full_text, **defaults
                            )
                            slide.objects.append(txt_obj)
                            continue

                    preset = _auto_shape_type(shape)
                    if preset is not None:
                        slide.objects.append(ShapeObject(
                            id=f"shape_{len(slide.objects)}",
                            x=x, y=y, width=w, height=h,
                            shape_type=preset,
                            **_read_shape_colors(shape)
                        ))

                if slide_data.has_notes_slide:
                    slide.notes = slide_data.notes_slide.notes_text_frame.text.strip()

                presentation.slides.append(slide)

            if not presentation.slides:
                presentation._create_default_slide()

            return presentation
        except Exception as e:
            print(f"Error loading pptx: {e}")
            return None

    @staticmethod
    def save(filepath: str, presentation: Presentation) -> bool:
        """Export PresentR Presentation to a .pptx file."""
        try:
            prs = PptxPresentation()
            blank_layout = prs.slide_layouts[6]  # Completely blank slide

            for slide in presentation.slides:
                p_slide = prs.slides.add_slide(blank_layout)

                for obj in slide.objects:
                    left = Inches(obj.x / 96.0)
                    top = Inches(obj.y / 96.0)
                    width = Inches(obj.width / 96.0)
                    height = Inches(obj.height / 96.0)

                    if isinstance(obj, TextObject):
                        txBox = p_slide.shapes.add_textbox(left, top, width, height)
                        tf = txBox.text_frame
                        tf.word_wrap = True
                        p = tf.paragraphs[0]
                        p.text = obj.text
                        _write_text_format(p, obj)

                    elif isinstance(obj, ShapeObject):
                        preset = _MSO_SHAPES.get(obj.shape_type, MSO_SHAPE.RECTANGLE)
                        shp = p_slide.shapes.add_shape(preset, left, top, width, height)
                        _write_shape_colors(shp, obj)

                    elif isinstance(obj, ImageObject) and os.path.exists(obj.image_path):
                        p_slide.shapes.add_picture(obj.image_path, left, top, width, height)

                if slide.notes and slide.notes.strip():
                    p_slide.notes_slide.notes_text_frame.text = slide.notes

            prs.save(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            print(f"Error saving pptx: {e}")
            return False
