"""ODP import and export handler for PresentR using odfpy."""

import os
from typing import List, Optional
from odf.opendocument import OpenDocumentPresentation, load as odf_load
from odf.draw import Page, Frame, TextBox
from odf.presentation import Notes
from odf.text import P
from odf.style import MasterPage, PageLayout
from odf.element import Element
from odf.namespaces import PRESENTATIONNS
from officer.presentr.slide_deck import Presentation, Slide, TextObject


NOTES_TAG = "presentation:notes"


def _inside_notes(element) -> bool:
    """True if *element* sits inside a <presentation:notes> block rather than on the slide."""
    parent = element.parentNode
    while parent is not None:
        if getattr(parent, "tagName", None) == NOTES_TAG:
            return True
        parent = parent.parentNode
    return False


def _slide_text_boxes(page) -> List:
    """Text boxes belonging to the slide itself, excluding the speaker notes frame."""
    return [tb for tb in page.getElementsByType(TextBox) if not _inside_notes(tb)]


def _read_notes(page) -> str:
    """Extract speaker notes text from a draw:page, or '' when the slide has none."""
    lines = []
    for notes_el in page.getElementsByType(Notes):
        for paragraph in notes_el.getElementsByType(P):
            text = ""
            for child in paragraph.childNodes:
                if child.nodeType == Element.TEXT_NODE:
                    text += str(child)
            if text.strip():
                lines.append(text.strip())
    return "\n".join(lines)


def _build_notes_element(notes_text: str) -> Notes:
    """Build the ODF <presentation:notes> block that carries speaker notes."""
    notes = Notes()
    frame = Frame(width="180mm", height="60mm", x="10mm", y="110mm")
    # odfpy's grammar table does not whitelist presentation:class on draw:frame.
    frame.setAttrNS(PRESENTATIONNS, "class", "notes")
    tb = TextBox()
    for line in notes_text.split("\n"):
        tb.addElement(P(text=line))
    frame.addElement(tb)
    notes.addElement(frame)
    return notes


class OdpHandler:
    """Handles importing and exporting .odp OpenDocument Presentation files."""

    @staticmethod
    def load(filepath: str) -> Optional[Presentation]:
        """Load an .odp file into PresentR Presentation object."""
        if not os.path.exists(filepath):
            return None

        try:
            doc = odf_load(filepath)
            presentation = Presentation(title=os.path.basename(filepath))
            presentation.slides.clear()

            pages = doc.getElementsByType(Page)
            for p_idx, page in enumerate(pages):
                slide = Slide(title=f"Slide {p_idx + 1}")
                slide.notes = _read_notes(page)

                text_boxes = _slide_text_boxes(page)
                for t_idx, tb in enumerate(text_boxes):
                    paragraphs = tb.getElementsByType(P)
                    texts = []
                    for p in paragraphs:
                        t = ""
                        for child in p.childNodes:
                            if child.nodeType == Element.TEXT_NODE:
                                t += str(child)
                        if t.strip():
                            texts.append(t.strip())

                    if texts:
                        txt_obj = TextObject(
                            id=f"text_{t_idx}",
                            x=80, y=80 + t_idx * 120, width=800, height=80,
                            text="\n".join(texts),
                            font_size=28 if t_idx == 0 else 18,
                            bold=t_idx == 0
                        )
                        slide.objects.append(txt_obj)

                presentation.slides.append(slide)

            if not presentation.slides:
                presentation._create_default_slide()

            return presentation
        except Exception as e:
            print(f"Error loading odp: {e}")
            return None

    @staticmethod
    def save(filepath: str, presentation: Presentation) -> bool:
        """Export PresentR Presentation to an .odp file."""
        try:
            doc = OpenDocumentPresentation()

            # Master style definition for ODF compliance
            pl = PageLayout(name="PM0")
            doc.automaticstyles.addElement(pl)
            mp = MasterPage(name="Standard", pagelayoutname="PM0")
            doc.masterstyles.addElement(mp)

            for s_idx, slide in enumerate(presentation.slides):
                page = Page(name=f"page{s_idx + 1}", masterpagename="Standard")
                doc.presentation.addElement(page)

                for obj in slide.objects:
                    if isinstance(obj, TextObject):
                        frame = Frame(
                            width=f"{obj.width * 0.264:.2f}mm",
                            height=f"{obj.height * 0.264:.2f}mm",
                            x=f"{obj.x * 0.264:.2f}mm",
                            y=f"{obj.y * 0.264:.2f}mm"
                        )
                        tb = TextBox()
                        for line in obj.text.split("\n"):
                            tb.addElement(P(text=line))
                        frame.addElement(tb)
                        page.addElement(frame)

                if slide.notes and slide.notes.strip():
                    page.addElement(_build_notes_element(slide.notes))

            doc.save(filepath)
            return os.path.exists(filepath)
        except Exception as e:
            print(f"Error saving odp: {e}")
            return False
