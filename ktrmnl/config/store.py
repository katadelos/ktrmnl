from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ktrmnl.config.defaults import DEFAULTS, UI_PROFILE_DEFAULTS
from ktrmnl.config.validation import (
    profile_key,
    validate_mode,
    validate_qt_backend,
    validate_value,
)


class ConfigState(Enum):
    DEFAULTS = "defaults"
    PERSISTED = "persisted"


def configured_qt_backend(path: Path) -> str:
    """Read the launch setting strictly, before any display owner is acquired."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return str(DEFAULTS["qt_backend"])
    if not isinstance(payload, dict):
        raise ValueError("The app configuration must be a JSON object.")
    return validate_qt_backend(payload.get("qt_backend", DEFAULTS["qt_backend"]))


class KtrmnlConfig:
    """Thread-safe persistent settings with launcher-supplied defaults.

    The store deliberately has no knowledge of a particular runtime. Device
    and host launchers choose their own paths and may provide a small set of
    default overrides, while controllers consume the same configuration API.
    """

    def __init__(
        self,
        path: Optional[Path] = None,
        defaults: Optional[Mapping[str, Any]] = None,
    ):
        self.path = Path(path or device_config_path())
        self._lock = threading.RLock()
        self._values = deepcopy(DEFAULTS)
        self._values["local_image_dir"] = str(self.path.parent / "images")
        if defaults:
            unknown = set(defaults).difference(DEFAULTS)
            if unknown:
                raise KeyError(next(iter(unknown)))
            self._values.update(deepcopy(dict(defaults)))
        self._initial_values = deepcopy(self._values)
        self._state = ConfigState.DEFAULTS
        self._load()

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        loaded_value = False
        for key in DEFAULTS:
            if key not in payload:
                continue
            value = payload[key]
            try:
                value = validate_value(key, value)
            except ValueError:
                continue
            if key == "ui_profiles":
                merged = deepcopy(UI_PROFILE_DEFAULTS)
                merged.update(value)
                value = merged
            self._values[key] = value
            loaded_value = True
        self._state = ConfigState.PERSISTED if loaded_value else ConfigState.DEFAULTS

    @property
    def configured(self) -> bool:
        """Whether a valid persisted configuration was loaded or saved."""

        with self._lock:
            return self._state is ConfigState.PERSISTED

    @property
    def setup_complete(self) -> bool:
        """Whether the on-device introduction has been completed."""

        with self._lock:
            return self._state is ConfigState.PERSISTED and bool(
                self._values.get("first_time_setup_complete")
            )

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if default is None:
                default = DEFAULTS.get(key)
            return self._values.get(key, default)

    def set(self, key: str, value: Any, persist: bool = True) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        value = validate_value(key, value)
        with self._lock:
            previous = self._values[key]
            self._values[key] = value
            if persist:
                try:
                    self.save()
                except OSError:
                    self._values[key] = previous
                    raise

    def update(self, values: Mapping[str, Any], persist: bool = True) -> None:
        """Validate and update several settings in one atomic file write."""

        unknown = set(values).difference(DEFAULTS)
        if unknown:
            raise KeyError(next(iter(unknown)))
        validated = {key: validate_value(key, value) for key, value in values.items()}
        with self._lock:
            previous = {key: self._values[key] for key in validated}
            self._values.update(validated)
            if persist:
                try:
                    self.save()
                except OSError:
                    self._values.update(previous)
                    raise

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._values)

    def ui_profile(self, width: int, height: int) -> Dict[str, float]:
        """Resolve UI sizing for a native panel, independent of orientation."""

        key = profile_key(width, height)
        with self._lock:
            profiles = self._values["ui_profiles"]
            if key in profiles:
                return dict(profiles[key])

            reference = profiles.get("800x600", UI_PROFILE_DEFAULTS["800x600"])
            return self._scaled_ui_profile(reference, width, height)

    @classmethod
    def default_ui_profile(cls, width: int, height: int) -> Dict[str, float]:
        key = profile_key(width, height)
        if key in UI_PROFILE_DEFAULTS:
            return dict(UI_PROFILE_DEFAULTS[key])
        return cls._scaled_ui_profile(UI_PROFILE_DEFAULTS["800x600"], width, height)

    @staticmethod
    def _scaled_ui_profile(
        reference: Mapping[str, float], width: int, height: int
    ) -> Dict[str, float]:
        short_edge = min(int(width), int(height))
        proportional_scale = short_edge / 600.0
        bounded_theme_scale = max(0.86, min(1.15, proportional_scale))
        multiplier = proportional_scale / bounded_theme_scale
        return {
            "text_scale": min(5.0, round(reference["text_scale"] * multiplier, 2)),
            "menu_row_height_scale": min(
                4.0, round(reference["menu_row_height_scale"] * multiplier, 2)
            ),
            "keyboard_height_ratio": reference["keyboard_height_ratio"],
        }

    def set_ui_profile(
        self,
        width: int,
        height: int,
        profile: Mapping[str, Any],
        persist: bool = True,
    ) -> None:
        key = profile_key(width, height)
        validated = validate_value("ui_profiles", {key: profile})[key]
        with self._lock:
            profiles = deepcopy(self._values["ui_profiles"])
            profiles[key] = validated
        self.set("ui_profiles", profiles, persist=persist)

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self._values, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
            self._state = ConfigState.PERSISTED

    def clear(self) -> None:
        """Remove the persisted configuration and restore launcher defaults."""

        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            try:
                temporary.unlink()
            except OSError:
                pass
            self._values = deepcopy(self._initial_values)
            self._state = ConfigState.DEFAULTS

    @property
    def api_key(self) -> str:
        return str(self.get("api_key", "") or "")

    @property
    def friendly_id(self) -> str:
        return str(self.get("friendly_id", "") or "")

    @property
    def device_name(self) -> str:
        return str(self.get("device_name", DEFAULTS["device_name"]) or "")

    @property
    def language(self) -> str:
        return str(self.get("language", "en") or "en")

    @property
    def base_url(self) -> str:
        return str(self.get("base_url", DEFAULTS["base_url"]) or "").rstrip("/")

    @property
    def content_source(self) -> str:
        value = self.get("content_source", DEFAULTS["content_source"])
        try:
            return validate_mode(value)
        except ValueError:
            return str(DEFAULTS["content_source"])

    @property
    def local_image_dir(self) -> Path:
        return Path(str(self.get("local_image_dir", DEFAULTS["local_image_dir"])))

    @property
    def local_image_refresh_rate(self) -> int:
        return int(self.get("local_image_refresh_rate", 60))

    @property
    def local_image_shuffle(self) -> bool:
        return bool(self.get("local_image_shuffle", True))

    @property
    def retry_interval(self) -> int:
        return int(self.get("retry_interval", 60))

    @property
    def wifi_essid(self) -> str:
        return str(self.get("wifi_essid", "") or "")

    @property
    def rotation(self) -> int:
        return int(self.get("rotation", 0))

    @property
    def dark_mode(self) -> bool:
        return bool(self.get("dark_mode", False))

    @property
    def qt_backend(self) -> str:
        return str(self.get("qt_backend", "auto"))

    @property
    def battery_low_threshold(self) -> int:
        return int(self.get("battery_low_threshold", 15))


def device_config_path() -> Path:
    value = os.environ.get("KTRMNL_CONFIG", "").strip()
    if value:
        return Path(value)
    data_root = os.environ.get("KTRMNL_DATA_DIR", "").strip()
    return (
        Path(data_root) if data_root else Path.home() / ".local/share/ktrmnl"
    ) / "config.json"
