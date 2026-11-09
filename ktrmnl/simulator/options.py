from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence, Tuple

from ktrmnl.config.defaults import CONTENT_MODES

MENU_PAGES = (
    "root",
    "start",
    "content",
    "display",
    "wifi-settings",
    "system",
    "status",
    "wifi",
    "wifi-password",
    "wifi-connect",
    "language",
)
EDIT_SETTING_PAGES = {
    "setting-base-url": "content",
    "setting-api-key": "content",
    "setting-local-directory": "content",
    "setting-local-refresh": "content",
    "setting-device-name": "system",
    "setting-retry-interval": "wifi-settings",
    "setting-battery-threshold": "system",
}


def host_config_path() -> Path:
    configured = os.environ.get("KTRMNL_CONFIG", "").strip()
    if configured:
        return Path(configured)
    root = os.environ.get("KTRMNL_DATA_DIR", "").strip()
    if root:
        return Path(root) / "config.json"
    if sys.platform == "darwin":
        return (
            Path.home() / "Library" / "Application Support" / "ktrmnl" / "config.json"
        )
    return Path.home() / ".local" / "share" / "ktrmnl" / "config.json"


def _display_size(value: str) -> Tuple[int, int]:
    width, separator, height = str(value).lower().partition("x")
    try:
        result = (int(width), int(height))
    except ValueError as error:
        raise argparse.ArgumentTypeError("display size must be WIDTHxHEIGHT") from error
    if not separator or min(result) < 64 or max(result) > 4096:
        raise argparse.ArgumentTypeError("display size must be WIDTHxHEIGHT")
    return result


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ktrmnl host simulator")
    parser.add_argument("--config", type=Path, default=host_config_path())
    parser.add_argument("--mode", choices=CONTENT_MODES)
    parser.add_argument("--rotation", type=int, choices=(0, 90, 180, 270))
    parser.add_argument("--watch", action="store_true", help="reload QML on changes")
    parser.add_argument("--headless", action="store_true", help="use Qt offscreen mode")
    parser.add_argument("--screenshot", type=Path, help="render one frame and exit")
    parser.add_argument(
        "--controls",
        action="store_true",
        help="open the simulator control panel at startup",
    )
    parser.add_argument(
        "--display-size",
        type=_display_size,
        default=(1072, 1448),
        metavar="WIDTHxHEIGHT",
        help="fake panel's native dimensions (default: 1072x1448)",
    )
    parser.add_argument("--width", type=int, help="exact logical viewport width")
    parser.add_argument("--height", type=int, help="exact logical viewport height")
    parser.add_argument(
        "--battery-percent",
        type=int,
        choices=range(0, 101),
        default=82,
        metavar="0..100",
        help="fake battery charge",
    )
    parser.add_argument(
        "--battery-status",
        choices=("Charging", "Discharging", "Full"),
        default="Discharging",
    )
    parser.add_argument("--radio-off", action="store_true", help="start fake Wi-Fi off")
    parser.add_argument("--wifi-ssid", default="TRMNL Wi-Fi")
    parser.add_argument("--fake-board", default="kt6")
    parser.add_argument("--family", choices=("kindle", "kobo"), default="kindle")
    parser.add_argument("--fake-model", default="Kindle Basic 2024")
    parser.add_argument(
        "--scenario",
        choices=(
            "normal",
            "content",
            "loading",
            "empty",
            "offline",
            "error",
            "interrupt",
        ),
        default="normal",
        help="deterministic content state for screenshots",
    )
    parser.add_argument("--menu", action="store_true", help="open the menu at startup")
    parser.add_argument(
        "--first-run",
        action="store_true",
        help="start at the first-time language and setup flow",
    )
    parser.add_argument(
        "--menu-page",
        choices=MENU_PAGES,
        default="root",
        help="menu page to show with --menu",
    )
    parser.add_argument(
        "--edit-setting",
        choices=tuple(EDIT_SETTING_PAGES),
        help="open one setting's keyboard layer for simulator inspection",
    )
    parser.add_argument(
        "--push-port",
        type=int,
        default=int(os.environ.get("KTRMNL_PUSH_PORT", "8080")),
        help="LAN push server port",
    )
    args = parser.parse_args(list(argv))
    if args.edit_setting:
        args.menu = True
        args.menu_page = EDIT_SETTING_PAGES[args.edit_setting]
    if (args.width is None) != (args.height is None):
        parser.error("--width and --height must be supplied together")
    if args.width is not None and not (
        64 <= args.width <= 4096 and 64 <= args.height <= 4096
    ):
        parser.error("--width and --height must be between 64 and 4096")
    return args
