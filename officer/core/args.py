"""The document a desktop launcher hands an application on the command line.

Each of the four OfficeR entry points asks for one, so that double-clicking a
.docx in a file manager really opens that file in WriteR rather than an empty
window.
"""

import os
import sys
from typing import List, Optional, Sequence


def file_argument(argv: Optional[Sequence[str]] = None) -> Optional[str]:
    """The first argument naming a file that exists, or nothing."""
    for arg in (sys.argv[1:] if argv is None else argv):
        if arg.startswith("-"):
            continue
        path = os.path.abspath(os.path.expanduser(arg))
        if os.path.isfile(path):
            return path
    return None


def without_flags(argv: Optional[Sequence[str]] = None) -> List[str]:
    """Arguments Qt may act on, with our own `--app name` pair taken out."""
    args = list(sys.argv if argv is None else argv)
    kept, index = [], 0
    while index < len(args):
        if args[index] == "--app" and index + 1 < len(args):
            index += 2
            continue
        kept.append(args[index])
        index += 1
    return kept
