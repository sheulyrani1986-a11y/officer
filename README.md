# OfficeR

A modern, beginner-friendly, Linux-native office suite inspired by Microsoft Office, built with **Python 3.13** and **Qt 6 (PySide6)**.

---

## Overview

OfficeR provides a cohesive, polished, and intuitive office experience for Linux desktop users, designed to overcome the feature limitations of ONLYOFFICE while being more beginner-friendly and modern than LibreOffice.

The suite comprises three major applications sharing a unified **OfficeR Core**:

* 📘 **WriteR** — Modern word processor (.docx, .odt, vector PDF export)
* 📊 **RSheet** — High-performance spreadsheet (.xlsx, .ods, formulas, virtualized 1,000,000-row grid, vector PDF export)
* 📽️ **PresentR** — Presentation software (.pptx, .odp, 16:9 canvas, shapes, text, fullscreen presenter mode, vector PDF export)
* 🚀 **OfficeR Hub** — Unified welcome center and document manager

---

## Key Features

### 1. OfficeR Core
* **Microsoft Office-Style Ribbon**: Collapsible ribbon toolbar with organized tabs (Home, Insert, Layout, View, AI Assist) and quick access toolbar.
* **Undo/Redo Engine**: Full Command Pattern with compound macro transactions and dirty state tracking.
* **Modern Theme Engine**: Dynamic light and dark mode with system theme integration and crisp vector icons.
* **Local AI Copilot (Ollama)**: Non-blocking background assistant hook for grammar correction, summarization, formula creation, and slide generation.

### 2. WriteR (Word Processor)
* **Paginated WYSIWYG View**: Page-by-page document rendering with margins and drop shadow.
* **Rich-Text Formatting**: Headings (H1–H3, Title, Normal), font families, sizes, bold, italic, underline, strikethrough, font colors, and alignment.
* **Insertable Objects**: Tables with customizable rows/columns, and pictures and shapes that float on the page with text wrapping around them.
* **Dressed Paper**: Page colour as a solid or as a picture with an opacity control, page borders, and text or picture watermarks.
* **Headers, Footers and Templates**: Running headers and footers with page counts, and fourteen document designs reached from *New from Template*.
* **File Interoperability**: Direct import/export for `.docx` (Microsoft Word) and `.odt` (OpenDocument Text), plus high-resolution vector PDF export.
* **Printing**: *File ▸ Print* (or `Ctrl+P`) sends the document through CUPS to any queue the system offers — network, USB, shared or print-to-file. The printer's own paper wins over the document's while the document keeps its margins, a page range prints only the sheets named, and the sheet's border, colour, watermark and header bands go out with the writing.

### 3. RSheet (Spreadsheet)
* **High-Performance Grid**: Virtualized `QTableView` rendering over 1,000,000 rows with instantaneous 60fps scrolling and minimal memory usage.
* **Formula Calculation Engine**: Expression evaluation with dependency resolution and built-in functions:
  * Math & Aggregation: `SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`, `COUNTA`
  * Logical & Text: `IF`, `CONCAT`
* **Interactive Formula Bar**: Real-time cell coordinate tracking (e.g. `B4`), function editor (`fx`), and selection statistics (Average, Count, Sum).
* **Multi-Sheet Support**: Add, switch, and manage multiple workbook sheets with bottom tabs.
* **File Interoperability**: Direct import/export for `.xlsx` (Excel), `.ods` (OpenDocument Calc), `.csv`, and PDF export.

### 4. PresentR (Presentations)
* **Interactive Slide Canvas**: Hardware-accelerated 2D scene (`QGraphicsScene`) with 16:9 widescreen layout.
* **Slide Objects**: Movable, resizable rich-text boxes, twenty vector shapes with gradients, and images.
* **Deck Designs**: Eleven full presentations — cover, agenda, cards, figures, bar charts, timelines, quotes and tables — reached from *New from Template*.
* **Slide Sorter Sidebar**: Add, duplicate, delete, and switch between slides with real-time thumbnail updates.
* **Fullscreen Presenter Mode**: Presentation playback (F5 / Shift+F5) with keyboard navigation (Arrows, Space, PageDown, Esc), plus speaker notes.
* **File Interoperability**: Import/export for `.pptx` (PowerPoint), `.odp` (OpenDocument Impress), and multi-page vector PDF export.

---

## Installation & Running

### Installing a package
Pick whichever suits the machine; each carries its own Python and Qt, so nothing
else has to be installed first.

* **Debian / Ubuntu — `.deb`**

  ```bash
  sudo apt install ./officer_0.1.0_amd64.deb
  ```

  WriteR, RSheet and PresentR appear in the applications menu, `officer` opens
  the hub, and `.docx`, `.odt`, `.xlsx`, `.ods`, `.pptx` and `.odp` files open in
  the right application from the file manager.

* **Any Linux — `.tar.gz`**

  ```bash
  tar xzf OfficeR-0.1.0-linux-x86_64.tar.gz
  cd OfficeR-0.1.0-linux-x86_64
  ./bin/officer-writer            # run it from here, or:
  sudo ./install.sh               # put it in the menu (/opt/officer)
  ```

* **Any Linux — `.AppImage`**

  ```bash
  chmod +x OfficeR-0.1.0-x86_64.AppImage
  ./OfficeR-0.1.0-x86_64.AppImage
  OFFICER_APP=presentr ./OfficeR-0.1.0-x86_64.AppImage   # straight to one app
  ```

Packages are built for x86_64; a machine on another architecture needs the
source route below or its own build.

### Running from source
Requirements: Python 3.10+, and the packages listed in `pyproject.toml`
(`pip install -e .` picks them up).

To launch the unified OfficeR Hub:
```bash
python3 -m officer.app
```

To launch individual applications directly:
```bash
# WriteR (Word Processor)
python3 -m officer.writer.app

# RSheet (Spreadsheet)
python3 -m officer.rsheet.app

# PresentR (Presentations)
python3 -m officer.presentr.app
```

Any of them takes a document to open, as the desktop entries do:
```bash
python3 -m officer.writer.app notes.docx
```

---

## Building the Linux packages

```bash
python3 -m venv ~/.officer-build/venv
~/.officer-build/venv/bin/pip install pyinstaller PySide6 python-docx \
    openpyxl python-pptx odfpy Pillow
packaging/build_dist.sh                 # writes into ~/Apps
```

The script freezes the suite into one binary with `packaging/officer.spec`, then
wraps that same tree as the `.deb`, the tarball and the AppImage described
above. `OUT=/tmp/packages packaging/build_dist.sh` sends the results elsewhere.

---

## Automated Test Suite
OfficeR has comprehensive automated tests covering the command stack, formula engine, and roundtrip file import/export for all formats:
```bash
python3 -m pytest tests/
```

---

## Architecture Diagram

```
                             ┌───────────────────────────────────┐
                             │       OfficeR Hub / Launcher      │
                             │  (Recent files, Templates, Apps)  │
                             └─────────────────┬─────────────────┘
                                               │
               ┌───────────────────────────────┼───────────────────────────────┐
               ▼                               ▼                               ▼
       ┌───────────────┐               ┌───────────────┐               ┌───────────────┐
       │    WriteR     │               │    RSheet     │               │   PresentR    │
       │(Word Processor│               │ (Spreadsheet) │               │(Presentations)│
       └───────┬───────┘               └───────┬───────┘               └───────┬───────┘
               │                               │                               │
               └───────────────────────┬───────┴───────────────────────────────┘
                                       ▼
       ┌───────────────────────────────────────────────────────────────────────────────┐
       │                                 OfficeR Core                                  │
       ├───────────────────────────────────────────────────────────────────────────────┤
       │ • Modern Office Ribbon UI & Quick Access Toolbar                              │
       │ • Command & Undo/Redo Engine (Transaction batching, action history)           │
       │ • Unified Styling & Typography (Fonts, colors, paragraph & cell formats)      │
       │ • File I/O Interoperability (.docx/.odt, .xlsx/.ods, .pptx/.odp, Vector PDF)   │
       │ • Multi-format Clipboard & Drag-and-Drop                                      │
       │ • (Extensible) Ollama AI Sidecar Hook (Rewriting, formulas, slide generation) │
       └───────────────────────────────────────────────────────────────────────────────┘
```
