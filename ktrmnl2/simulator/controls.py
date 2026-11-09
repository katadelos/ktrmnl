from __future__ import annotations

from typing import Dict, List

from PyQt5.QtCore import (
    QObject,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

from ktrmnl2.app.controller import KtrmnlController
from ktrmnl2.config.store import KtrmnlConfig
from ktrmnl2.simulator.backends import SimulatorDevice, SimulatorDisplayBackend
from ktrmnl2.simulator.wifi import SimulatorWifiManager


class SimulatorControls(QObject):
    """Host-only preview controls and a readable configuration snapshot."""

    textScaleChanged = pyqtSignal()
    rowHeightScaleChanged = pyqtSignal()
    keyboardHeightRatioChanged = pyqtSignal()
    settingsChanged = pyqtSignal()

    _SETTING_ROWS = (
        ("device_name", "Device name"),
        ("content_source", "Content source"),
        ("base_url", "Server URL"),
        ("api_key", "API token"),
        ("wifi_essid", "Saved Wi-Fi network"),
        ("local_image_dir", "Local image directory"),
        ("local_image_refresh_rate", "Local image refresh"),
        ("local_image_shuffle", "Shuffle local images"),
        ("retry_interval", "Retry interval"),
        ("rotation", "Rotation"),
        ("dark_mode", "Dark mode"),
        ("battery_low_threshold", "Low battery warning"),
    )

    _MODE_LABELS = {
        "trmnl": "TRMNL",
        "interrupt": "Interrupt",
        "local_images": "Local images",
        "http_push": "HTTP push",
    }

    def __init__(
        self,
        config: KtrmnlConfig,
        device: SimulatorDevice,
        display: SimulatorDisplayBackend,
        controller: KtrmnlController,
        wifi: "SimulatorWifiManager",
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.device = device
        self.display = display
        self.controller = controller
        self.wifi = wifi
        profile = config.ui_profile(*device.display_size())
        self._text_scale = profile["text_scale"]
        self._row_height_scale = profile["menu_row_height_scale"]
        self._keyboard_height_ratio = profile["keyboard_height_ratio"]
        controller.statusChanged.connect(self.settingsChanged.emit)
        controller.darkModeChanged.connect(self.settingsChanged.emit)
        controller.rotationChanged.connect(self.settingsChanged.emit)
        controller.configStateChanged.connect(self.settingsChanged.emit)
        wifi.stateChanged.connect(self.settingsChanged.emit)
        wifi.connectedChanged.connect(self.settingsChanged.emit)

    @pyqtProperty(float, notify=textScaleChanged)
    def textScale(self) -> float:
        return self._text_scale

    @pyqtSlot(float)
    def setTextScale(self, value: float) -> None:
        value = round(max(0.5, min(5.0, float(value))), 2)
        if value != self._text_scale:
            self._text_scale = value
            self._save_profile()
            self.textScaleChanged.emit()
            self.settingsChanged.emit()

    @pyqtProperty(float, notify=rowHeightScaleChanged)
    def rowHeightScale(self) -> float:
        return self._row_height_scale

    @pyqtSlot(float)
    def setRowHeightScale(self, value: float) -> None:
        value = round(max(0.5, min(4.0, float(value))), 2)
        if value != self._row_height_scale:
            self._row_height_scale = value
            self._save_profile()
            self.rowHeightScaleChanged.emit()
            self.settingsChanged.emit()

    @pyqtProperty(float, notify=keyboardHeightRatioChanged)
    def keyboardHeightRatio(self) -> float:
        return self._keyboard_height_ratio

    @pyqtSlot(float)
    def setKeyboardHeightRatio(self, value: float) -> None:
        value = round(max(0.25, min(0.75, float(value))), 2)
        if value != self._keyboard_height_ratio:
            self._keyboard_height_ratio = value
            self._save_profile()
            self.keyboardHeightRatioChanged.emit()
            self.settingsChanged.emit()

    @pyqtSlot(bool)
    def setFirstRunActive(self, active: bool) -> None:
        """Set the host-only onboarding state without altering saved settings."""

        active = bool(active)
        self.controller._set_first_run(active)
        self.settingsChanged.emit()

    def _save_profile(self) -> None:
        self.config.set_ui_profile(
            *self.device.display_size(),
            {
                "text_scale": self._text_scale,
                "menu_row_height_scale": self._row_height_scale,
                "keyboard_height_ratio": self._keyboard_height_ratio,
            },
        )

    def _load_profile(self) -> None:
        profile = self.config.ui_profile(*self.device.display_size())
        text_changed = profile["text_scale"] != self._text_scale
        row_changed = profile["menu_row_height_scale"] != self._row_height_scale
        keyboard_changed = (
            profile["keyboard_height_ratio"] != self._keyboard_height_ratio
        )
        self._text_scale = profile["text_scale"]
        self._row_height_scale = profile["menu_row_height_scale"]
        self._keyboard_height_ratio = profile["keyboard_height_ratio"]
        if text_changed:
            self.textScaleChanged.emit()
        if row_changed:
            self.rowHeightScaleChanged.emit()
        if keyboard_changed:
            self.keyboardHeightRatioChanged.emit()

    @pyqtSlot(int, int, result=bool)
    def setDisplaySize(self, width: int, height: int) -> bool:
        width, height = int(width), int(height)
        if not 64 <= width <= 4096 or not 64 <= height <= 4096:
            return False
        self.device.set_display_size(width, height)
        self.display.set_native_size(width, height)
        self._load_profile()
        self.settingsChanged.emit()
        return True

    @pyqtProperty(str, constant=True)
    def configPath(self) -> str:
        return str(self.config.path)

    @pyqtProperty(str, notify=settingsChanged)
    def activeUiProfile(self) -> str:
        width, height = self.device.display_size()
        return f"{width} × {height}"

    @pyqtProperty(float, notify=settingsChanged)
    def defaultTextScale(self) -> float:
        return self.config.default_ui_profile(*self.device.display_size())["text_scale"]

    @pyqtProperty(float, notify=settingsChanged)
    def defaultRowHeightScale(self) -> float:
        return self.config.default_ui_profile(*self.device.display_size())[
            "menu_row_height_scale"
        ]

    @pyqtProperty(float, notify=settingsChanged)
    def defaultKeyboardHeightRatio(self) -> float:
        return self.config.default_ui_profile(*self.device.display_size())[
            "keyboard_height_ratio"
        ]

    @pyqtProperty("QVariantList", notify=settingsChanged)
    def settings(self):
        values = self.config.snapshot()
        rows: List[Dict[str, str]] = [
            {
                "key": "active_ui_profile",
                "label": "Active UI profile",
                "value": self.activeUiProfile,
            },
            {
                "key": "ui_text_scale",
                "label": "UI text size",
                "value": f"{round(self._text_scale * 100)}%",
            },
            {
                "key": "ui_row_height_scale",
                "label": "Menu row height",
                "value": f"{round(self._row_height_scale * 100)}%",
            },
            {
                "key": "ui_keyboard_height",
                "label": "Keyboard height",
                "value": f"{round(self._keyboard_height_ratio * 100)}%",
            },
        ]
        for resolution, profile in sorted(values["ui_profiles"].items()):
            rows.append(
                {
                    "key": f"ui_profile_{resolution}",
                    "label": f"UI {resolution.replace('x', ' × ')}",
                    "value": (
                        f"Text {round(profile['text_scale'] * 100)}% · "
                        f"rows {round(profile['menu_row_height_scale'] * 100)}% · "
                        f"keyboard {round(profile['keyboard_height_ratio'] * 100)}%"
                    ),
                }
            )
        for key, label in self._SETTING_ROWS:
            value = values.get(key)
            if key == "content_source":
                formatted = self._MODE_LABELS.get(str(value), str(value))
            elif key == "api_key":
                formatted = "Stored" if value else "Not set"
            elif key in {
                "dark_mode",
                "local_image_shuffle",
            }:
                formatted = "On" if bool(value) else "Off"
            elif key in {"local_image_refresh_rate", "retry_interval"}:
                formatted = f"{value} seconds"
            elif key == "battery_low_threshold":
                formatted = f"{value}%"
            elif key == "rotation":
                formatted = f"{value}°"
            else:
                formatted = str(value or "Not set")
            rows.append({"key": key, "label": label, "value": formatted})
        return rows
