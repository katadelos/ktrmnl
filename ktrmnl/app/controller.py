from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional

from PyQt5.QtCore import (
    QObject,
    QTextBoundaryFinder,
    QTimer,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

from ktrmnl.app.menu import SETTING_SPECS, SettingsMenu
from ktrmnl.app.refresh import DisplayRefresh, RefreshState
from ktrmnl.app.status import DeviceStatus
from ktrmnl.config.store import KtrmnlConfig
from ktrmnl.content.controller import ContentController

LOGGER = logging.getLogger("ktrmnl.controller")


class UiState(Enum):
    CONTENT = "content"
    MENU = "menu"
    MODAL = "modal"
    CLOSED = "closed"


class KtrmnlController(QObject):
    """Thin QML bridge over injected application services and authoritative state."""

    menuItemsChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    deviceChanged = pyqtSignal()
    darkModeChanged = pyqtSignal()
    rotationChanged = pyqtSignal()
    settingErrorChanged = pyqtSignal()
    configStateChanged = pyqtSignal()
    exitRequested = pyqtSignal()
    suspendRequested = pyqtSignal()
    userInteracted = pyqtSignal()
    powerStatusChanged = pyqtSignal()
    powerPolicyChanged = pyqtSignal()
    batteryAlertChanged = pyqtSignal()

    def __init__(
        self,
        config: KtrmnlConfig,
        hal,
        wifi,
        content: ContentController,
        display,
        menu_path: Path,
        show_exit_item: bool = True,
        initial_first_run: bool = False,
        translator=None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.hal = hal
        self.wifi = wifi
        self.content = content
        self.display = display
        self.translator = translator
        self._device_status = DeviceStatus(config, hal, translator, self)
        self._menu = SettingsMenu(
            config, self._device_status, menu_path, translator, show_exit_item
        )
        self._display_refresh = DisplayRefresh(display, content.setExternalStatus, self)
        self._ui_state = UiState.CONTENT
        self._first_run = bool(initial_first_run)
        self._setting_error = ""
        self._power_status = "Sleep is available on the device."
        self.content.statusChanged.connect(self.statusChanged)
        self.content.modeChanged.connect(self.statusChanged)
        self.content.modeChanged.connect(self._refresh_menu)
        self.content.friendlyIdChanged.connect(self._friendly_id_changed)
        self.wifi.statusChanged.connect(self.statusChanged)
        self.wifi.stateChanged.connect(self.statusChanged)
        if self.translator is not None:
            self.translator.languageChanged.connect(self._language_changed)
        self._refresh_menu()

        self._device_status.changed.connect(self.deviceChanged)
        self._device_status.alertChanged.connect(self.batteryAlertChanged)
        self._device_status.alertChanged.connect(self.powerPolicyChanged)
        self._device_status.frontlightChanged.connect(self._refresh_menu)
        self.refreshDeviceStatus()
        self.restoreFrontlight()
        self.content.start()

    def _refresh_menu(self) -> None:
        self._menu.refresh()
        self.menuItemsChanged.emit()

    def _t(
        self, key: str, fallback: str, values: Optional[Mapping[str, object]] = None
    ) -> str:
        if self.translator is None:
            return str(fallback).format(**values) if values else str(fallback)
        return self.translator.translate(str(key), str(fallback), values)

    def _language_changed(self) -> None:
        self._refresh_menu()
        self.statusChanged.emit()

    def _friendly_id_changed(self) -> None:
        self.configStateChanged.emit()
        self._refresh_menu()

    @pyqtProperty("QVariantList", notify=menuItemsChanged)
    def menuItems(self):
        return self._menu.items

    @pyqtProperty(bool, constant=True)
    def qtBackendAvailable(self) -> bool:
        return self._menu.qt_backend_available

    @pyqtProperty(str, notify=settingErrorChanged)
    def settingError(self) -> str:
        return self._setting_error

    @pyqtProperty(bool, notify=configStateChanged)
    def firstRun(self) -> bool:
        return self._first_run

    @pyqtProperty(str, notify=configStateChanged)
    def friendlyId(self) -> str:
        return self.config.friendly_id

    @pyqtProperty(str, notify=configStateChanged)
    def deviceName(self) -> str:
        return self.config.device_name

    def _set_first_run(self, first_run: bool) -> None:
        first_run = bool(first_run)
        if first_run == self._first_run:
            return
        self._first_run = first_run
        self.configStateChanged.emit()
        self.powerPolicyChanged.emit()

    def _set_setting_error(self, value: str) -> None:
        value = str(value)
        if value != self._setting_error:
            self._setting_error = value
            self.settingErrorChanged.emit()

    @pyqtProperty(str, notify=statusChanged)
    def statusText(self) -> str:
        return self.content.status

    @pyqtProperty(str, notify=powerStatusChanged)
    def powerStatus(self) -> str:
        return self._power_status

    def setPowerStatus(self, status: str) -> None:
        if status != self._power_status:
            self._power_status = str(status)
            self.powerStatusChanged.emit()

    @property
    def sleepReady(self) -> bool:
        return (
            self._ui_state is UiState.CONTENT
            and not self._first_run
            and not self._device_status.warning_active
        )

    @pyqtProperty(str, notify=deviceChanged)
    def board(self) -> str:
        return self._device_status.board

    @pyqtProperty(str, notify=deviceChanged)
    def model(self) -> str:
        return self._device_status.model

    @pyqtProperty(bool, notify=deviceChanged)
    def batteryLow(self) -> bool:
        return self._device_status.battery_low

    @pyqtProperty(int, notify=deviceChanged)
    def batteryPercent(self) -> int:
        return self._device_status.battery_percent

    @pyqtProperty(bool, notify=batteryAlertChanged)
    def lowBatteryWarningActive(self) -> bool:
        return self._device_status.warning_active

    @pyqtProperty(str, notify=deviceChanged)
    def batteryText(self) -> str:
        return self._device_status.battery_text

    @pyqtProperty(str, notify=deviceChanged)
    def radioText(self) -> str:
        return self._device_status.radio_text

    @pyqtProperty(str, notify=statusChanged)
    def wifiStatusText(self) -> str:
        return self.wifi.statusText

    @pyqtProperty(str, notify=statusChanged)
    def wifiNetworkText(self) -> str:
        if self.wifi.connectedSsid:
            return self.wifi.connectedSsid
        if self.config.wifi_essid:
            return self.config.wifi_essid
        return self._t("detail.not_set", "Not set")

    @pyqtProperty(str, notify=statusChanged)
    def wifiSignalText(self) -> str:
        signal = int(getattr(self.wifi, "signalStrength", 0) or 0)
        if not signal:
            return self._t("detail.unavailable", "Unavailable")
        return f"{signal} dBm"

    @pyqtProperty(str, notify=statusChanged)
    def rotationText(self) -> str:
        return f"{self.config.rotation}°"

    @pyqtProperty(int, notify=rotationChanged)
    def rotation(self) -> int:
        return self.config.rotation

    @pyqtProperty(bool, notify=darkModeChanged)
    def darkMode(self) -> bool:
        return self.config.dark_mode

    @pyqtProperty(str, notify=statusChanged)
    def baseUrl(self) -> str:
        return self.config.base_url

    @pyqtProperty(str, notify=statusChanged)
    def contentSource(self) -> str:
        return self.content.mode

    @pyqtProperty(str, notify=statusChanged)
    def localImageDirectory(self) -> str:
        return str(self.config.local_image_dir)

    @pyqtSlot(str)
    def openMenuPage(self, page: str) -> None:
        self._menu.open(page)
        self.menuItemsChanged.emit()

    @pyqtSlot()
    def reloadMenu(self) -> None:
        self._menu.reload()
        self.menuItemsChanged.emit()

    @pyqtSlot()
    def refresh(self) -> None:
        self.content.refresh()
        self.refreshDeviceStatus()

    @pyqtSlot(str)
    def setMode(self, mode: str) -> None:
        self.content.setMode(mode)

    @pyqtSlot(str, result="QVariantMap")
    def settingDefinition(self, item_id: str):
        try:
            definition = self._menu.definition(item_id)
        except ValueError as error:
            self._set_setting_error(str(error))
            return {}
        if definition:
            self._set_setting_error("")
        return definition

    @pyqtSlot(str, "QVariant", result=bool)
    def applySetting(self, item_id: str, value: object) -> bool:
        spec = SETTING_SPECS.get(str(item_id))
        if not spec:
            self._set_setting_error("This setting is not editable.")
            return False
        if not self._menu.available(str(item_id)):
            self._set_setting_error(self._menu.unavailable_error(str(item_id)))
            return False
        if spec["kind"] == "number":
            error = self._menu.numeric_error(spec, value)
            if error:
                self._set_setting_error(error)
                return False
        key = str(spec["key"])
        if not self._apply_config_values({key: value}):
            return False
        self._set_setting_error("")
        return True

    @pyqtSlot(str, result=bool)
    def toggleSetting(self, item_id: str) -> bool:
        spec = SETTING_SPECS.get(str(item_id))
        if not spec or spec.get("kind") != "toggle":
            self._set_setting_error("This setting is not a toggle.")
            return False
        key = str(spec["key"])
        return self.applySetting(str(item_id), not bool(self.config.get(key)))

    def _apply_config_values(
        self, values: object, *, reload_content: bool = True
    ) -> bool:
        """Persist and publish one validated configuration transaction."""

        if not isinstance(values, dict):
            return False
        values = {str(key): value for key, value in values.items()}
        if set(values).intersection({"api_key", "base_url"}):
            values.setdefault("friendly_id", "")
        old_rotation = self.config.rotation
        old_dark_mode = self.config.dark_mode
        old_content_source = self.config.content_source
        try:
            if set(values).intersection(
                {"frontlight_enabled", "frontlight_brightness"}
            ):
                self._save_frontlight_settings(values)
            else:
                self.config.update(values)
        except (KeyError, TypeError, ValueError) as error:
            self._set_setting_error(str(error))
            self.content.setExternalStatus(
                "Configuration error: " + str(error), "error"
            )
            return False
        except OSError as error:
            self._set_setting_error("The setting could not be applied: " + str(error))
            self.content.setExternalStatus(
                "Configuration could not be saved: " + str(error), "error"
            )
            return False
        content_keys = set(values).difference(
            {
                "rotation",
                "dark_mode",
                "frontlight_enabled",
                "frontlight_brightness",
                "qt_backend",
                "sleep_between_refreshes",
                "battery_low_threshold",
                "device_name",
            }
        )
        if content_keys and reload_content:
            self.content.reloadConfig()
        if self.config.rotation != old_rotation:
            self._apply_rotation(self.config.rotation)
            self.rotationChanged.emit()
        if self.config.dark_mode != old_dark_mode:
            self._apply_dark_mode(self.config.dark_mode)
            self.darkModeChanged.emit()
        if "battery_low_threshold" in values:
            self._device_status.evaluate_battery()
            self.deviceChanged.emit()
        if "friendly_id" in values or "device_name" in values:
            self.configStateChanged.emit()
        self.content.setExternalStatus("Configuration updated.")
        self.statusChanged.emit()
        self._set_setting_error("")
        self.powerPolicyChanged.emit()
        if self.config.content_source == old_content_source:
            self._refresh_menu()
        return True

    def _save_frontlight_settings(self, values: Mapping[str, object]) -> None:
        previous = {key: self.config.get(key) for key in values}
        self.config.update(values, persist=False)
        try:
            self.hal.set_frontlight(
                self.config.get("frontlight_enabled"),
                self.config.get("frontlight_brightness"),
            )
            self.config.save()
        except OSError:
            self.config.update(previous, persist=False)
            try:
                self.hal.set_frontlight(
                    self.config.get("frontlight_enabled"),
                    self.config.get("frontlight_brightness"),
                )
            except OSError:
                LOGGER.exception("Could not restore the previous frontlight setting")
            raise

    def restoreFrontlight(self) -> bool:
        if not self._device_status.frontlight_available:
            return True
        try:
            self.hal.set_frontlight(
                self.config.get("frontlight_enabled"),
                self.config.get("frontlight_brightness"),
            )
        except OSError as error:
            LOGGER.exception("Could not apply the frontlight setting")
            self.content.setExternalStatus("Frontlight error: " + str(error), "error")
            return False
        return True

    @pyqtSlot(result=bool)
    def finishFirstTimeSetup(self) -> bool:
        """Finish the introduction and expose the on-device content settings."""

        try:
            self.config.set("first_time_setup_complete", True)
        except (OSError, TypeError, ValueError) as error:
            self._set_setting_error(
                "Setup completion could not be saved: " + str(error)
            )
            return False
        self._set_first_run(False)
        return True

    @pyqtSlot(result=bool)
    def clearConfig(self) -> bool:
        """Clear persisted settings after the UI's explicit confirmation."""

        try:
            self.config.clear()
        except OSError as error:
            self._set_setting_error("The configuration could not be cleared.")
            self.content.setExternalStatus(
                "Configuration could not be cleared: " + str(error), "error"
            )
            return False

        if self.translator is not None:
            self.translator.setLanguage(self.config.language, persist=False)
        self.content.reloadConfig()
        self._apply_rotation(self.config.rotation)
        self._apply_dark_mode(self.config.dark_mode)
        self.restoreFrontlight()
        self.rotationChanged.emit()
        self.darkModeChanged.emit()
        self.statusChanged.emit()
        self._set_setting_error("")
        self._refresh_menu()
        self._set_first_run(True)
        QTimer.singleShot(0, self.requestTransitionRefresh)
        return True

    def _apply_dark_mode(self, enabled: bool) -> bool:
        try:
            self.display.set_night_mode(bool(enabled))
            return True
        except Exception as error:
            self.content.setExternalStatus("Dark mode error: " + str(error), "error")
            return False

    @pyqtSlot()
    def toggleDarkMode(self) -> None:
        self.toggleSetting("setting-dark-mode")

    @pyqtSlot()
    def toggleWifi(self) -> None:
        try:
            self.wifi.toggleRadio()
            self.refreshDeviceStatus()
        except Exception as error:
            self.content.setExternalStatus("Wi-Fi error: " + str(error), "error")

    def _apply_rotation(self, rotation: int) -> bool:
        try:
            self.display.set_rotation(rotation)
            return True
        except Exception as error:
            self.content.setExternalStatus("Rotation error: " + str(error), "error")
            return False

    @pyqtSlot()
    def requestFullRefresh(self) -> None:
        self._display_refresh.request(RefreshState.CLEAR)

    @pyqtSlot()
    def requestTransitionRefresh(self) -> None:
        self._display_refresh.request(RefreshState.TRANSITION)

    @pyqtSlot()
    def toggleRotation(self) -> None:
        rotation = (self.config.rotation + 90) % 360
        self.applySetting("setting-rotation", rotation)

    @pyqtSlot(result=bool)
    def dismissInterrupt(self) -> bool:
        return self.content.dismissInterrupt()

    @pyqtSlot(result=bool)
    def dismissLowBatteryWarning(self) -> bool:
        return self._device_status.dismiss_warning()

    @pyqtSlot(str, result=bool)
    def handleInput(self, action: str) -> bool:
        self.userInteracted.emit()
        if self._device_status.warning_active:
            return self.dismissLowBatteryWarning()
        if self._first_run or self._ui_state is not UiState.CONTENT:
            return False
        return self.content.dismissInterrupt()

    @pyqtSlot(str, int, int, result=int)
    def textCursorPosition(self, text: str, position: int, direction: int) -> int:
        finder = QTextBoundaryFinder(QTextBoundaryFinder.Grapheme, text)
        finder.toEnd()
        end = finder.position()
        finder.setPosition(max(0, min(position, end)))
        if direction < 0:
            return max(0, finder.toPreviousBoundary())
        boundary = finder.toNextBoundary()
        return end if boundary < 0 else boundary

    @pyqtSlot(str)
    def setUiState(self, state: str) -> None:
        if self._ui_state is UiState.CLOSED:
            return
        requested = UiState(state)
        if (
            requested not in {UiState.CONTENT, UiState.MENU, UiState.MODAL}
            or requested is self._ui_state
        ):
            return
        self._ui_state = requested
        self._display_refresh.set_interactive(requested is UiState.MENU)
        self.userInteracted.emit()
        self.powerPolicyChanged.emit()

    @pyqtSlot()
    def requestSuspend(self) -> None:
        self.suspendRequested.emit()

    @pyqtSlot()
    def requestExit(self) -> None:
        self.exitRequested.emit()

    @pyqtSlot()
    def refreshDeviceStatus(self) -> None:
        self._device_status.refresh()

    @pyqtSlot()
    def close(self) -> None:
        if self._ui_state is UiState.CLOSED:
            return
        self._ui_state = UiState.CLOSED
        self._device_status.close()
        self._display_refresh.close()
        self.content.close()
