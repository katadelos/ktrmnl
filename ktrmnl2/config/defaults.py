from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class ContentMode(str, Enum):
    TRMNL = "trmnl"
    INTERRUPT = "interrupt"
    LOCAL_IMAGES = "local_images"
    HTTP_PUSH = "http_push"


CONTENT_MODES = tuple(mode.value for mode in ContentMode)
QT_BACKENDS = ("auto", "x11", "framebuffer")
SUPPORTED_LANGUAGES = (
    "en",
    "de",
    "fr",
    "es",
    "it",
    "pt",
    "nl",
    "pl",
    "cs",
    "sv",
    "zh",
    "ja",
)

UI_PROFILE_DEFAULTS: Dict[str, Dict[str, float]] = {
    "800x600": {
        "text_scale": 1.80,
        "menu_row_height_scale": 1.40,
        "keyboard_height_ratio": 0.43,
    },
    "1024x758": {
        "text_scale": 1.98,
        "menu_row_height_scale": 1.54,
        "keyboard_height_ratio": 0.43,
    },
    "1448x1072": {
        "text_scale": 2.80,
        "menu_row_height_scale": 2.18,
        "keyboard_height_ratio": 0.43,
    },
}

DEFAULTS: Dict[str, Any] = {
    "language": "en",
    "api_key": "",
    "friendly_id": "",
    "device_name": "ktrmnl",
    "base_url": "",
    "content_source": "trmnl",
    "wifi_essid": "",
    "first_time_setup_complete": False,
    "local_image_dir": "",
    "local_image_refresh_rate": 60,
    "local_image_shuffle": True,
    "retry_interval": 60,
    "rotation": 0,
    "dark_mode": False,
    "frontlight_enabled": False,
    "frontlight_brightness": 50,
    "qt_backend": "auto",
    "sleep_between_refreshes": True,
    "battery_low_threshold": 15,
    "ui_profiles": UI_PROFILE_DEFAULTS,
}
