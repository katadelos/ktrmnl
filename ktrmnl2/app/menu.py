from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from PyQt5.QtCore import QLocale

_MODE_LABELS = {
    "trmnl": "TRMNL",
    "interrupt": "Interrupt",
    "local_images": "Local images",
    "http_push": "HTTP push",
}

SETTING_SPECS: Dict[str, Dict[str, object]] = {
    "setting-content-source": {
        "key": "content_source",
        "kind": "choice",
        "choices": [
            {"value": value, "label": label, "shortLabel": short_label}
            for (value, label), short_label in zip(
                _MODE_LABELS.items(), ("TRMNL", "Interrupt", "Local", "Push")
            )
        ],
    },
    "setting-base-url": {
        "key": "base_url",
        "kind": "text",
        "modes": ("trmnl", "interrupt"),
    },
    "setting-api-key": {
        "key": "api_key",
        "kind": "text",
        "secret": True,
        "modes": ("trmnl", "interrupt"),
    },
    "setting-local-directory": {
        "key": "local_image_dir",
        "kind": "text",
        "editorTitleKey": "editor.local_directory",
        "editorTitle": "Image folder",
        "modes": ("local_images",),
    },
    "setting-local-refresh": {
        "key": "local_image_refresh_rate",
        "kind": "number",
        "editorTitleKey": "editor.local_refresh",
        "editorTitle": "Refresh interval",
        "minimum": 1,
        "maximum": 86400,
        "unit": "seconds",
        "modes": ("local_images",),
    },
    "setting-local-shuffle": {
        "key": "local_image_shuffle",
        "kind": "toggle",
        "modes": ("local_images",),
    },
    "setting-rotation": {
        "key": "rotation",
        "kind": "choice",
        "choices": [
            {"value": value, "label": f"{value}°"} for value in (0, 90, 180, 270)
        ],
    },
    "setting-dark-mode": {"key": "dark_mode", "kind": "toggle"},
    "setting-frontlight": {"key": "frontlight_enabled", "kind": "toggle"},
    "setting-frontlight-brightness": {
        "key": "frontlight_brightness",
        "kind": "number",
        "minimum": 1,
        "maximum": 100,
        "unit": "%",
    },
    "setting-qt-backend": {
        "key": "qt_backend",
        "kind": "choice",
        "choices": [
            {"value": "x11", "label": "Stock X11", "shortLabel": "X11"},
            {"value": "framebuffer", "label": "Framebuffer"},
        ],
    },
    "setting-sleep": {"key": "sleep_between_refreshes", "kind": "toggle"},
    "setting-retry-interval": {
        "key": "retry_interval",
        "kind": "number",
        "minimum": 5,
        "maximum": 86400,
        "unit": "seconds",
    },
    "setting-battery-threshold": {
        "key": "battery_low_threshold",
        "kind": "number",
        "editorTitleKey": "editor.battery_threshold",
        "editorTitle": "Battery warning",
        "minimum": 1,
        "maximum": 100,
        "unit": "%",
    },
    "setting-device-name": {"key": "device_name", "kind": "text"},
}

_SUBMENU_ITEMS = {
    "content-settings",
    "display-settings",
    "wifi-settings",
    "system-settings",
    "status",
    "wifi-setup",
    "language",
}


class SettingsMenu:
    """Build localized menu rows and editor definitions from configuration."""

    def __init__(
        self, config, device_status, path, translator=None, show_exit_item=True
    ):
        self.config, self.device_status = config, device_status
        self.translator = translator
        self._menu_path = Path(path)
        self._menu_page = "root"
        self._show_exit_item = show_exit_item
        self.qt_backend_available = os.environ.get("KTRMNL2_X11_AVAILABLE") == "1"
        self._initial_qt_backend = (
            "x11"
            if self.qt_backend_available
            and os.environ.get("QT_QPA_PLATFORM") != "ereader"
            else "framebuffer"
        )
        self._menu_pages = self._load_menu(self._menu_path)
        self.items = []

    @staticmethod
    def _load_menu(path: Path) -> Dict[str, List[Dict[str, str]]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            pages = payload.get("pages", {})
            if isinstance(pages, dict):
                return {
                    str(name): [dict(item) for item in items if isinstance(item, dict)]
                    for name, items in pages.items()
                    if isinstance(items, list)
                }
        except (OSError, ValueError, TypeError):
            pass
        return {"root": []}

    def refresh(self) -> None:
        self.items = [
            dict(item)
            for item in self._menu_pages.get(self._menu_page, [])
            if self._menu_item_is_available(item)
        ]
        for item in self.items:
            item_id = str(item.get("id") or "")
            label_key = str(item.get("labelKey") or "")
            if label_key:
                item["label"] = self._t(label_key, str(item.get("label") or ""))
            detail_key = str(item.get("detailKey") or "")
            if detail_key:
                item["detail"] = self._t(detail_key, str(item.get("detail") or ""))
            spec = SETTING_SPECS.get(item_id)
            if spec:
                item["kind"] = spec["kind"]
                item["detail"] = self._setting_detail(spec)
                if spec["kind"] == "toggle":
                    item["checked"] = bool(self.config.get(str(spec["key"])))
                if spec["kind"] == "choice":
                    current = str(self._setting_value(spec))
                    item["choices"] = [
                        {
                            "value": choice["value"],
                            "label": self._choice_label(str(spec["key"]), choice),
                            "shortLabel": self._choice_short_label(
                                str(spec["key"]), choice
                            ),
                            "selected": str(choice["value"]) == current,
                        }
                        for choice in spec.get("choices", [])
                    ]
            elif item_id in _SUBMENU_ITEMS:
                item["kind"] = "submenu"
            else:
                item["kind"] = "action"
            if item_id == "language" and self.translator is not None:
                item["detail"] = self.translator.languageName

    def _t(
        self, key: str, fallback: str, values: Optional[Mapping[str, object]] = None
    ) -> str:
        if self.translator is None:
            return str(fallback).format(**values) if values else str(fallback)
        return self.translator.translate(str(key), str(fallback), values)

    def _menu_item_is_available(self, item: Dict[str, str]) -> bool:
        item_id = str(item.get("id") or "")
        if item_id == "exit" and not self._show_exit_item:
            return False
        if item_id == "show-trmnl-id" and not self.config.friendly_id:
            return False
        return self.available(item_id)

    def available(self, item_id: str) -> bool:
        if item_id in {"setting-frontlight", "setting-frontlight-brightness"}:
            return bool(self.device_status.frontlight_available)
        if item_id == "setting-qt-backend":
            return self.qt_backend_available
        spec = SETTING_SPECS.get(str(item_id))
        if not spec:
            return True
        modes = spec.get("modes")
        if modes and self.config.content_source not in modes:
            return False
        requirements = spec.get("requires")
        if isinstance(requirements, Mapping):
            return all(
                self.config.get(str(key)) == expected
                for key, expected in requirements.items()
            )
        return True

    def unavailable_error(self, item_id: str) -> str:
        if item_id in {"setting-frontlight", "setting-frontlight-brightness"}:
            return self._t(
                "frontlight.unavailable",
                "Frontlight control is unavailable on this reader.",
            )
        if item_id == "setting-qt-backend":
            return self._t(
                "backend.unavailable",
                "This firmware does not support choosing a Qt backend.",
            )
        if SETTING_SPECS[item_id].get("modes") == ("trmnl", "interrupt"):
            return self._t(
                "setting.requires_trmnl",
                "Select TRMNL or Interrupt to edit this setting.",
            )
        return self._t(
            "setting.requires_local_images",
            "Select Local images to edit this setting.",
        )

    def _number_text(self, value: object) -> str:
        return QLocale(self.config.language).toString(int(value))

    def _number_bounds(self, spec: Mapping[str, object]) -> Dict[str, str]:
        return {
            "minimum": self._number_text(spec["minimum"]),
            "maximum": self._number_text(spec["maximum"]),
        }

    def numeric_error(self, spec: Mapping[str, object], value: object) -> str:
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return self._t("validation.whole_number", "Enter a whole number.")
        if int(spec["minimum"]) <= number <= int(spec["maximum"]):
            return ""
        if spec["unit"] == "%":
            return self._t(
                "validation.percent_range",
                "Enter {minimum}–{maximum}%.",
                self._number_bounds(spec),
            )
        return self._t(
            "validation.seconds_range",
            "Enter {minimum}–{maximum} seconds.",
            self._number_bounds(spec),
        )

    def _setting_value(self, spec: Mapping[str, object]):
        value = self.config.get(str(spec["key"]))
        if spec["key"] == "qt_backend" and value == "auto":
            return self._initial_qt_backend
        return value

    def _setting_detail(self, spec: Dict[str, object]) -> str:
        key = str(spec["key"])
        value = self._setting_value(spec)
        kind = str(spec["kind"])
        if key == "api_key":
            return (
                self._t("detail.stored", "Stored")
                if self.config.api_key
                else self._t("detail.not_set", "Not set")
            )
        if kind == "choice":
            for choice in spec.get("choices", []):
                if str(choice["value"]) == str(value):
                    return self._choice_label(key, choice)
        if kind == "toggle":
            return (
                self._t("detail.on", "On")
                if bool(value)
                else self._t("detail.off", "Off")
            )
        if kind == "number":
            value = self._number_text(value)
        unit = str(spec.get("unit") or "")
        if unit == "%":
            return f"{value}%"
        if unit:
            if unit == "seconds" and self.translator is not None:
                return self.translator.translate(
                    "status.seconds", "{count} seconds", {"count": value}
                )
            return f"{value} {unit}"
        return str(value or self._t("detail.not_set", "Not set"))

    def _choice_label(self, key: str, choice: Mapping[str, object]) -> str:
        if key == "qt_backend":
            return self._t(
                "backend." + str(choice["value"]),
                str(choice.get("label") or ""),
            )
        if key == "content_source":
            mode_key = {
                "trmnl": "mode.trmnl",
                "interrupt": "mode.interrupt",
                "local_images": "mode.local_images",
                "http_push": "mode.http_push",
            }.get(str(choice.get("value") or ""))
            if mode_key:
                return self._t(mode_key, str(choice.get("label") or ""))
        return str(choice.get("label") or "")

    def _choice_short_label(self, key: str, choice: Mapping[str, object]) -> str:
        if key == "qt_backend":
            return (
                str(choice["shortLabel"])
                if "shortLabel" in choice
                else self._choice_label(key, choice)
            )
        if key == "content_source":
            mode_key = {
                "trmnl": "mode.trmnl",
                "interrupt": "mode.interrupt_short",
                "local_images": "mode.local_short",
                "http_push": "mode.push_short",
            }.get(str(choice.get("value") or ""))
            if mode_key:
                return self._t(
                    mode_key,
                    str(choice.get("shortLabel") or choice.get("label") or ""),
                )
        return str(choice.get("shortLabel") or choice.get("label") or "")

    def open(self, page: str) -> None:
        if page not in self._menu_pages:
            page = "root"
        self._menu_page = page
        self.refresh()

    def reload(self) -> None:
        self._menu_pages = self._load_menu(self._menu_path)
        self._menu_page = "root"
        self.refresh()

    def definition(self, item_id: str):
        spec = SETTING_SPECS.get(str(item_id))
        if not spec:
            return {}
        if not self.available(str(item_id)):
            raise ValueError(self.unavailable_error(str(item_id)))
        definition = dict(spec)
        key = str(spec["key"])
        definition["itemId"] = str(item_id)
        definition["value"] = self._setting_value(spec)
        definition["hasValue"] = bool(self.config.get(key))
        if spec.get("choices"):
            current = str(self._setting_value(spec))
            definition["choices"] = [
                {
                    "value": choice["value"],
                    "label": self._choice_label(key, choice),
                    "shortLabel": self._choice_short_label(key, choice),
                    "selected": str(choice["value"]) == current,
                }
                for choice in spec["choices"]
            ]
        for item in self.items:
            if str(item.get("id") or "") == str(item_id):
                definition["label"] = str(item.get("label") or "Setting")
                break
        definition.setdefault("label", "Setting")
        definition["editorTitle"] = (
            self._t(str(spec["editorTitleKey"]), str(spec["editorTitle"]))
            if "editorTitleKey" in spec
            else definition["label"]
        )
        if spec["kind"] == "number":
            definition["unitText"] = (
                self._t("editor.unit_seconds", "seconds")
                if spec["unit"] == "seconds"
                else "%"
            )
            definition["rangeHint"] = self._t(
                "editor.allowed_range",
                "Allowed range: {minimum}–{maximum}.",
                self._number_bounds(spec),
            )
        return definition
