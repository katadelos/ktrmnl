from __future__ import annotations

from typing import Any, Dict, Mapping
from urllib.parse import urlsplit

from ktrmnl2.config.defaults import CONTENT_MODES, QT_BACKENDS, SUPPORTED_LANGUAGES


def validate_qt_backend(value: Any) -> str:
    backend = str(value).strip().lower()
    if backend not in QT_BACKENDS:
        raise ValueError("qt_backend must be one of " + ", ".join(QT_BACKENDS))
    return backend


def validate_device_name(value: Any) -> str:
    """Return a bounded display label without changing the device hostname."""

    raw_name = str(value or "")
    device_name = raw_name.strip()
    if not device_name:
        raise ValueError("Dashboard name is required")
    if len(device_name) > 64:
        raise ValueError("Dashboard name must be 64 characters or fewer")
    if not raw_name.isprintable():
        raise ValueError(
            "Dashboard name must not contain control characters or line breaks"
        )
    return device_name


def validate_friendly_id(value: Any) -> str:
    """Return a bounded, single-token TRMNL friendly identifier."""

    friendly_id = str(value or "").strip()
    if len(friendly_id) > 64:
        raise ValueError("TRMNL ID must be 64 characters or fewer")
    if any(ord(character) <= 32 or ord(character) == 127 for character in friendly_id):
        raise ValueError("TRMNL ID must not contain spaces or control characters")
    return friendly_id


def validate_base_url(value: Any) -> str:
    """Return a normalized HTTP(S) API base URL or raise a useful UI error."""

    url = str(value or "").strip()
    if not url:
        return ""
    if len(url) > 1024:
        raise ValueError("TRMNL URL must be 1024 characters or fewer")
    if any(ord(character) <= 32 or ord(character) == 127 for character in url):
        raise ValueError("TRMNL URL must not contain spaces or control characters")
    try:
        parsed = urlsplit(url)
    except ValueError as error:
        raise ValueError("TRMNL URL is invalid") from error
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
    ):
        raise ValueError("TRMNL URL must start with http:// or https://")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("TRMNL URL must not contain credentials")
    if parsed.netloc.endswith(":"):
        raise ValueError("TRMNL URL has an invalid port")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("TRMNL URL has an invalid port") from error
    if port == 0:
        raise ValueError("TRMNL URL port must be between 1 and 65535")
    if parsed.query or parsed.fragment:
        raise ValueError("TRMNL URL must not contain a query or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("TRMNL URL must not contain a path")
    return url.rstrip("/")


def validate_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode not in CONTENT_MODES:
        raise ValueError("content_source must be one of " + ", ".join(CONTENT_MODES))
    return mode


def validate_value(key: str, value: Any) -> Any:
    if key == "qt_backend":
        return validate_qt_backend(value)
    if key == "api_key":
        token = str(value or "").strip()
        if len(token) > 4096:
            raise ValueError("API token must be 4096 characters or fewer")
        return token
    if key == "friendly_id":
        return validate_friendly_id(value)
    if key == "device_name":
        return validate_device_name(value)
    if key == "base_url":
        return validate_base_url(value)
    if key == "language":
        language = str(value or "").strip().lower()
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(
                "language must be one of " + ", ".join(SUPPORTED_LANGUAGES)
            )
        return language
    if key == "ui_profiles":
        if not isinstance(value, Mapping):
            raise ValueError("ui_profiles must be an object keyed by WIDTHxHEIGHT")
        profiles: Dict[str, Dict[str, float]] = {}
        for raw_resolution, raw_profile in value.items():
            resolution = parse_profile_key(raw_resolution)
            if not isinstance(raw_profile, Mapping):
                raise ValueError(f"ui_profiles.{resolution} must be an object")
            required = {
                "text_scale",
                "menu_row_height_scale",
                "keyboard_height_ratio",
            }
            if set(raw_profile) != required:
                raise ValueError(
                    f"ui_profiles.{resolution} must contain "
                    + ", ".join(sorted(required))
                )
            profile = {
                "text_scale": profile_number(
                    raw_profile["text_scale"], "text_scale", 0.5, 5.0
                ),
                "menu_row_height_scale": profile_number(
                    raw_profile["menu_row_height_scale"],
                    "menu_row_height_scale",
                    0.5,
                    4.0,
                ),
                "keyboard_height_ratio": profile_number(
                    raw_profile["keyboard_height_ratio"],
                    "keyboard_height_ratio",
                    0.25,
                    0.75,
                ),
            }
            profiles[resolution] = profile
        return profiles
    if key == "content_source":
        return validate_mode(value)
    if key == "rotation":
        try:
            rotation = int(value) % 360
        except (TypeError, ValueError) as error:
            raise ValueError("rotation must be 0, 90, 180, or 270") from error
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("rotation must be 0, 90, 180, or 270")
        return rotation
    if key in {
        "local_image_refresh_rate",
        "retry_interval",
        "battery_low_threshold",
        "frontlight_brightness",
    }:
        try:
            interval = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{key} must be a number") from error
        minimum = 5 if key == "retry_interval" else 1
        maximum = (
            100 if key in {"battery_low_threshold", "frontlight_brightness"} else 86400
        )
        if not minimum <= interval <= maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}")
        return interval
    if key in {
        "dark_mode",
        "frontlight_enabled",
        "sleep_between_refreshes",
        "local_image_shuffle",
        "first_time_setup_complete",
    }:
        return bool(value)
    return value


def profile_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    try:
        number = round(float(value), 2)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number") from error
    if not minimum <= number <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return number


def profile_key(width: int, height: int) -> str:
    width, height = max(int(width), int(height)), min(int(width), int(height))
    if min(width, height) < 64 or max(width, height) > 4096:
        raise ValueError("display profile dimensions must be between 64 and 4096")
    return f"{width}x{height}"


def parse_profile_key(value: object) -> str:
    width, separator, height = str(value).lower().partition("x")
    if not separator:
        raise ValueError("ui profile keys must use WIDTHxHEIGHT")
    try:
        return profile_key(int(width), int(height))
    except ValueError as error:
        raise ValueError("ui profile keys must use WIDTHxHEIGHT") from error
