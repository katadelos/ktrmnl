"""Choose Qt's display backend before the shared stock display session starts."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import MutableMapping, Optional, Sequence

from ktrmnl2.config.store import configured_qt_backend, device_config_path
from ktrmnl2.config.validation import validate_qt_backend

X11_JOB = Path("/etc/upstart/x.conf")
X11_SERVER = Path("/usr/bin/Xorg")
X11_SOCKET = Path("/tmp/.X11-unix/X0")


def stock_x11_capable(family: str) -> bool:
    return family == "kindle" and X11_JOB.is_file() and os.access(X11_SERVER, os.X_OK)


def select_backend(family: str, requested: str, *, capable: bool, running: bool) -> str:
    requested = validate_qt_backend(requested)
    if requested == "auto":
        return "x11" if family == "kindle" and running else "framebuffer"
    if requested == "x11":
        if family != "kindle" or not capable:
            raise ValueError("Stock X11 is not supported by this firmware.")
        if not running:
            raise ValueError(
                "Stock X11 is not running. Start the stock interface or set "
                "qt_backend to framebuffer in the app configuration."
            )
    return requested


def prepare_environment(
    family: str, config_path: Path, environment: MutableMapping[str, str]
) -> str:
    capable = stock_x11_capable(family)
    selected = select_backend(
        family,
        configured_qt_backend(config_path),
        capable=capable,
        running=X11_SOCKET.is_socket(),
    )
    # Keep this capability after the supervisor stops X for direct rendering.
    environment["KTRMNL2_X11_AVAILABLE"] = "1" if capable else "0"
    if selected == "x11":
        environment["QT_QPA_PLATFORM"] = "xcb"
        environment["DISPLAY"] = ":0"
        environment.pop("QT_QPA_FB_HIDECURSOR", None)
    else:
        environment["QT_QPA_PLATFORM"] = "ereader"
        environment["QT_QPA_FB_HIDECURSOR"] = "1"
        environment.pop("DISPLAY", None)
    return selected


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("family", choices=("kindle", "kobo"))
    parser.add_argument("--config", type=Path, default=device_config_path())
    args, arguments = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    try:
        prepare_environment(args.family, args.config, os.environ)
    except (OSError, ValueError) as error:
        print(f"ktrmnl2: {error}", file=sys.stderr)
        return 2
    os.execv(
        sys.executable,
        [
            sys.executable,
            "-m",
            "k2.adapters.session",
            args.family,
            "--retain-display",
            "--module",
            "ktrmnl2.device",
            "--config",
            str(args.config),
            *arguments,
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
