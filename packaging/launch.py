"""The one binary behind every packaged OfficeR launcher.

A packaged build ships a single frozen executable, because four copies of the
same Qt would be four times the download and none of the benefit. The wrapper a
desktop entry calls says which application it wants with ``--app``, and this
answers by running that application's own entry point.
"""

import os
import sys

from officer.core.args import without_flags

#: The applications a launcher may ask for, and the entry point each lives in.
APPS = {
    "writer": "officer.writer.app",
    "rsheet": "officer.rsheet.app",
    "presentr": "officer.presentr.app",
    "hub": "officer.app",
}


def requested(argv: list) -> str:
    """Which application the launcher asked for: the flag, or its own name.

    The last ``--app`` wins, because a wrapper adds its own and whatever came
    in front of it is the caller's, which is the more specific wish.
    """
    if "--app" in argv:
        at = max(i for i, arg in enumerate(argv) if arg == "--app") + 1
        value = argv[at].lower() if at < len(argv) else ""
        if value in APPS:
            return value
    name = os.path.basename(argv[0]).lower() if argv else ""
    for app in ("writer", "rsheet", "presentr"):
        if name.endswith(app):
            return app
    return "hub"


def main() -> None:
    app = requested(sys.argv)
    sys.argv[:] = without_flags()
    module = __import__(APPS[app], fromlist=["main"])
    module.main()


if __name__ == "__main__":
    main()
