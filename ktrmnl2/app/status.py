from __future__ import annotations

import logging
import socket
from enum import Enum
from typing import Dict, Mapping, Optional

from PyQt5.QtCore import QObject, QSocketNotifier, QTimer, pyqtSignal, pyqtSlot

LOGGER = logging.getLogger("ktrmnl2.controller")


class BatteryAlert(Enum):
    ARMED = "armed"
    VISIBLE = "visible"
    ACKNOWLEDGED = "acknowledged"


class PowerMonitorState(Enum):
    UNAVAILABLE = "unavailable"
    LISTENING = "listening"
    PENDING = "pending"
    CLOSED = "closed"


class DeviceStatus(QObject):
    """Cached reader state and battery alerts, refreshed by kernel events."""

    changed = pyqtSignal()
    alertChanged = pyqtSignal()
    frontlightChanged = pyqtSignal()
    _POWER_EVENT_RESCAN_MS = 2500

    def __init__(self, config, hal, translator=None, parent=None):
        super().__init__(parent)
        self.config, self.hal, self.translator = config, hal, translator
        self._device: Dict[str, object] = {}
        self._battery: Dict[str, object] = {}
        self._radio: Dict[str, object] = {}
        self._battery_alert = BatteryAlert.ARMED
        self._power_monitor_state = PowerMonitorState.UNAVAILABLE
        self._power_event_socket = None
        self._power_event_notifier = None
        self._power_event_refresh_timer = QTimer(self)
        self._power_event_refresh_timer.setSingleShot(True)
        self._power_event_refresh_timer.timeout.connect(self.refresh)
        self._listen_for_power_events()

    @property
    def frontlight_available(self):
        return bool(self._device.get("frontlight_available"))

    def _listen_for_power_events(self) -> None:
        """Refresh battery state from kernel change events without polling."""

        if not hasattr(socket, "AF_NETLINK"):
            return
        try:
            power_socket = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15)
            power_socket.setblocking(False)
            power_socket.bind((0, 1))
        except OSError as error:
            LOGGER.warning("kernel power event listener unavailable: %s", error)
            return
        self._power_monitor_state = PowerMonitorState.LISTENING
        self._power_event_socket = power_socket
        self._power_event_notifier = QSocketNotifier(
            power_socket.fileno(), QSocketNotifier.Read, self
        )
        self._power_event_notifier.activated.connect(self._read_power_events)

    @pyqtSlot(int)
    def _read_power_events(self, _socket_fd: int) -> None:
        power_socket = self._power_event_socket
        if self._power_monitor_state in {
            PowerMonitorState.UNAVAILABLE,
            PowerMonitorState.CLOSED,
        }:
            return
        relevant = False
        latest_percent = None
        while True:
            try:
                payload = power_socket.recv(16384)
            except BlockingIOError:
                break
            except OSError as error:
                LOGGER.warning("kernel power event read failed: %s", error)
                break
            fields = {}
            for raw_field in payload.split(b"\0"):
                key, separator, value = raw_field.partition(b"=")
                if separator:
                    fields[key.decode("ascii", "ignore")] = value.decode(
                        "ascii", "ignore"
                    )
            if fields.get("SUBSYSTEM") == "power_supply" or "BATTERY" in fields:
                relevant = True
                raw_percent = fields.get(
                    "BATTERY_PERCENT", fields.get("POWER_SUPPLY_CAPACITY")
                )
                try:
                    latest_percent = max(0, min(100, int(raw_percent)))
                except (TypeError, ValueError):
                    pass
        if not relevant:
            return
        if latest_percent is not None:
            self._battery = dict(self._battery)
            self._battery.update(
                {"available": True, "present": True, "percent": latest_percent}
            )
            self.evaluate_battery()
            self.changed.emit()
        # Reconcile the full power-supply inventory after the kernel event.
        self._power_monitor_state = PowerMonitorState.PENDING
        self._power_event_refresh_timer.start(self._POWER_EVENT_RESCAN_MS)

    def _t(
        self, key: str, fallback: str, values: Optional[Mapping[str, object]] = None
    ) -> str:
        if self.translator is None:
            return str(fallback).format(**values) if values else str(fallback)
        return self.translator.translate(str(key), str(fallback), values)

    @property
    def board(self) -> str:
        return str(self._device.get("reader_name") or "unknown")

    @property
    def model(self) -> str:
        return str(self._device.get("model") or "Unknown")

    @property
    def battery_low(self) -> bool:
        if not self._battery.get("available"):
            return False
        try:
            threshold = max(
                0, min(100, int(getattr(self.config, "battery_low_threshold", 15)))
            )
            return int(self._battery.get("percent", 0)) <= threshold
        except (TypeError, ValueError):
            return False

    def _battery_percent(self) -> Optional[int]:
        if not self._battery.get("available") or self._battery.get("present") is False:
            return None
        try:
            return max(0, min(100, int(self._battery["percent"])))
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def battery_percent(self) -> int:
        percent = self._battery_percent()
        return percent if percent is not None else 0

    @property
    def warning_active(self) -> bool:
        return self._battery_alert is BatteryAlert.VISIBLE

    def evaluate_battery(self) -> None:
        percent = self._battery_percent()
        if percent is None:
            return
        threshold = self.config.battery_low_threshold
        if percent > threshold:
            self._set_battery_alert(BatteryAlert.ARMED)
        elif self._battery_alert is BatteryAlert.ARMED:
            self._set_battery_alert(BatteryAlert.VISIBLE)

    def _set_battery_alert(self, state: BatteryAlert) -> None:
        if state is self._battery_alert:
            return
        self._battery_alert = state
        self.alertChanged.emit()

    @property
    def battery_text(self) -> str:
        if not self._battery.get("available"):
            return "Battery unavailable"
        status = str(self._battery.get("status") or "Unknown")
        text = f"{self._battery.get('percent', 0)}% · {status}"
        return text + " · Low" if self.battery_low else text

    @property
    def radio_text(self) -> str:
        if not self._radio.get("available"):
            return self._t("detail.not_set", "Not set")
        state = (
            self._t("detail.on", "On")
            if self._radio.get("powered")
            else self._t("detail.off", "Off")
        )
        if self._radio.get("operational"):
            state += " · " + self._t("status.active", "active")
        return state

    @pyqtSlot(result=bool)
    def dismiss_warning(self) -> bool:
        if self._battery_alert is not BatteryAlert.VISIBLE:
            return False
        self._set_battery_alert(BatteryAlert.ACKNOWLEDGED)
        return True

    @pyqtSlot()
    def refresh(self) -> None:
        if self._power_monitor_state is PowerMonitorState.CLOSED:
            return
        if self._power_monitor_state is PowerMonitorState.PENDING:
            self._power_event_refresh_timer.stop()
            self._power_monitor_state = PowerMonitorState.LISTENING
        frontlight_available = self._device.get("frontlight_available")
        try:
            self._device = dict(self.hal.device())
            self._device["reader_name"] = self.hal.reader_name()
        except Exception:
            self._device = {"reader_name": "unknown", "model": "Unknown"}
        try:
            self._battery = dict(self.hal.battery())
        except Exception:
            self._battery = {"available": False, "percent": 0, "status": "Unavailable"}
        try:
            self._radio = dict(self.hal.radio())
        except Exception:
            self._radio = {"available": False, "powered": False, "operational": False}
        self.evaluate_battery()
        if self._device.get("frontlight_available") != frontlight_available:
            self.frontlightChanged.emit()
        self.changed.emit()

    def close(self):
        if self._power_monitor_state is PowerMonitorState.CLOSED:
            return
        self._power_monitor_state = PowerMonitorState.CLOSED
        self._power_event_refresh_timer.stop()
        if self._power_event_notifier is not None:
            self._power_event_notifier.setEnabled(False)
            self._power_event_notifier.deleteLater()
            self._power_event_notifier = None
        if self._power_event_socket is not None:
            self._power_event_socket.close()
            self._power_event_socket = None
