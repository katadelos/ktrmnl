from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from enum import Enum, auto
from typing import Any, Dict, List

from PyQt5.QtCore import QObject, QTimer, pyqtProperty, pyqtSignal, pyqtSlot

from ktrmnl2.config.store import KtrmnlConfig
from ktrmnl2.device.hal import EreaderClient

LOGGER = logging.getLogger("ktrmnl2.wifi")
_SECURITY = {
    "OPEN": "Open",
    "WPA_PSK": "WPA2",
    "SAE": "WPA3",
    "WEP": "WEP",
    "ENTERPRISE": "Enterprise",
    "UNKNOWN": "Unknown",
}


class WifiError(RuntimeError):
    """Stock firmware could not complete a Wi-Fi request."""


class WifiOperation(Enum):
    IDLE = "idle"
    STATUS = "status"
    SCAN = "scan"
    CONNECT = "connect"
    RADIO = "radio"


class WifiPolling(Enum):
    NORMAL = auto()
    RECOVERING = auto()
    PAUSED = auto()
    CLOSED = auto()


class WifiLink(Enum):
    UNAVAILABLE = auto()
    CHECKING = auto()
    OFF = auto()
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()


class WifiManager(QObject):
    """Asynchronous stock Wi-Fi profiles, scans and connection status via HAL."""

    networksChanged = pyqtSignal()
    stateChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    selectedNetworkChanged = pyqtSignal()
    connectedChanged = pyqtSignal()
    _operationFinished = pyqtSignal(object, object, object)

    def __init__(self, config: KtrmnlConfig, hal: EreaderClient, parent=None):
        super().__init__(parent)
        self.config, self.hal = config, hal
        self._operation = WifiOperation.IDLE
        self._polling = WifiPolling.NORMAL
        self._link = WifiLink.UNAVAILABLE
        self._last_error = ""
        self._error_operation = None
        self._connected_ssid = ""
        self._ip_address = ""
        self._signal_strength = 0
        self._selected_ssid = ""
        self._selected_security = "Open"
        self._selected_profile_id = ""
        self._password_editable = False
        self._status_text = "Reading stock Wi-Fi status."
        self._networks: List[Dict[str, Any]] = []
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ktrmnl-wifi"
        )
        self._operationFinished.connect(self._operation_finished)
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(5000)
        self._status_timer.timeout.connect(self._poll_status)
        self._recovery_timer = QTimer(self)
        self._recovery_timer.setSingleShot(True)
        self._recovery_timer.timeout.connect(self._finish_recovery)
        self._set_polling(WifiPolling.NORMAL)
        self._poll_status()

    @pyqtProperty(bool, notify=stateChanged)
    def available(self):
        return self._link is not WifiLink.UNAVAILABLE

    @pyqtProperty("QVariantList", notify=networksChanged)
    def networks(self):
        return self._networks

    @pyqtProperty(bool, notify=stateChanged)
    def scanning(self):
        return self._operation is WifiOperation.SCAN

    @pyqtProperty(bool, notify=stateChanged)
    def connecting(self):
        return self._operation is WifiOperation.CONNECT

    @pyqtProperty(bool, notify=connectedChanged)
    def connected(self):
        return self._link is WifiLink.CONNECTED

    @pyqtProperty(str, notify=statusChanged)
    def statusText(self):
        return self._status_text

    @pyqtProperty(str, notify=selectedNetworkChanged)
    def selectedSsid(self):
        return self._selected_ssid

    @pyqtProperty(str, notify=selectedNetworkChanged)
    def selectedSecurity(self):
        return self._selected_security

    @pyqtProperty(bool, notify=selectedNetworkChanged)
    def requiresPassword(self):
        return self._password_editable and not self._selected_profile_id

    @pyqtProperty(bool, notify=selectedNetworkChanged)
    def passwordEditable(self):
        return self._password_editable

    @pyqtProperty(str, notify=stateChanged)
    def connectedSsid(self):
        return self._connected_ssid

    @pyqtProperty(str, notify=stateChanged)
    def ipAddress(self):
        return self._ip_address

    @pyqtProperty(int, notify=stateChanged)
    def signalStrength(self):
        return self._signal_strength

    def _set_status(self, text):
        if text != self._status_text:
            self._status_text = str(text)
            self.statusChanged.emit()

    def _submit(self, name, operation):
        if (
            self._polling in {WifiPolling.PAUSED, WifiPolling.CLOSED}
            or self.operation_busy
        ):
            return False
        self._operation = name
        if name is not WifiOperation.STATUS:
            self._last_error = ""
            self._error_operation = None
        self.stateChanged.emit()

        def work():
            try:
                # Each operation owns a handle; the UI's input handle stays responsive.
                with self.hal.new_device() as device:
                    result = operation(device)
                error = None
            except Exception as failure:
                result, error = None, failure
            self._operationFinished.emit(name, result, error)

        self._executor.submit(work)
        return True

    @pyqtSlot(object, object, object)
    def _operation_finished(self, name, result, error):
        if self._polling is WifiPolling.CLOSED or name is not self._operation:
            return
        self._operation = WifiOperation.IDLE
        if error is not None:
            LOGGER.warning("Wi-Fi %s failed: %s", name.value, error)
            self._error_operation = name
            self._last_error = "Wi-Fi " + name.value + " failed: " + str(error)
            self._set_status(self._last_error)
            if name is WifiOperation.STATUS:
                self._set_link(WifiLink.UNAVAILABLE)
            else:
                # Observe an uncertain mutation; never repeat it automatically.
                self._poll_status()
        else:
            if self._error_operation is WifiOperation.STATUS:
                self._error_operation = None
                self._last_error = ""
            if name is WifiOperation.SCAN:
                points, profiles, capabilities, status = result
                self._replace_networks(points, profiles, capabilities)
                self._apply_status(status)
                self._set_status(
                    "Select a Wi-Fi network." if points else "No networks found."
                )
            elif name is WifiOperation.CONNECT:
                status, profiles = result
                self._update_saved_networks(profiles)
                self._apply_status(status)
            else:
                self._apply_status(result)
        self.stateChanged.emit()

    def _set_link(self, link, ssid="", address="", signal=0):
        previous = (self.connected, self._connected_ssid)
        self._link = link
        self._connected_ssid = ssid if self.connected else ""
        self._ip_address = address if self.connected else ""
        self._signal_strength = signal
        self._mark_connected_network()
        if self.connected and self._polling is WifiPolling.RECOVERING:
            self._finish_recovery()
        if previous != (self.connected, self._connected_ssid):
            self.connectedChanged.emit()
        self.stateChanged.emit()

    def _apply_status(self, status):
        if status.state.name == "CONNECTED" and status.address:
            link = WifiLink.CONNECTED
        elif status.state.name == "OFF":
            link = WifiLink.OFF
        elif status.state.name == "CONNECTING":
            link = WifiLink.CONNECTING
        else:
            link = WifiLink.DISCONNECTED
        self._set_link(link, status.ssid, status.address, status.signal_dbm or 0)
        if self._last_error:
            self._set_status(self._last_error)
        elif self.connected:
            if self.config.wifi_essid != status.ssid:
                self.config.set("wifi_essid", status.ssid)
            self._set_status("Connected to " + status.ssid + ".")
        elif link is WifiLink.OFF:
            self._set_status("Wi-Fi is off.")
        elif link is WifiLink.CONNECTING:
            self._set_status("Connecting to Wi-Fi.")
        else:
            self._set_status("Select a Wi-Fi network.")

    @staticmethod
    def _profile_ids(profiles):
        identifiers = {}
        for profile in profiles:
            identifiers.setdefault(
                (profile.ssid, _SECURITY[profile.security.name]), profile.id
            )
        return identifiers

    def _replace_networks(self, points, profiles, capabilities):
        identifiers = self._profile_ids(profiles)
        networks = {}
        for point in points:
            if not point.ssid.strip():
                continue
            value = {
                "ssid": point.ssid,
                "signal": point.signal_dbm if point.signal_dbm is not None else -100,
                "security": _SECURITY[point.security.name],
                "secured": point.security.name != "OPEN",
                "connected": self.connected and point.ssid == self._connected_ssid,
                "profile_id": identifiers.get(
                    (point.ssid, _SECURITY[point.security.name]), ""
                ),
                "password_editable": point.security.name in {"WPA_PSK", "SAE"}
                and bool(capabilities.security_write & (1 << point.security)),
            }
            value["saved"] = bool(value["profile_id"])
            previous = networks.get(point.ssid)
            if previous is None or value["signal"] > previous["signal"]:
                networks[point.ssid] = value
        self._networks = sorted(
            networks.values(), key=lambda item: item["signal"], reverse=True
        )
        self.networksChanged.emit()
        if self._selected_ssid:
            self.selectNetwork(self._selected_ssid)

    def _update_saved_networks(self, profiles):
        identifiers = self._profile_ids(profiles)
        for network in self._networks:
            network["profile_id"] = identifiers.get(
                (network["ssid"], network["security"]), ""
            )
            network["saved"] = bool(network["profile_id"])
        self.networksChanged.emit()
        self.selectNetwork(self._selected_ssid)

    def _mark_connected_network(self):
        changed = False
        for network in self._networks:
            connected = self.connected and network["ssid"] == self._connected_ssid
            if connected != network["connected"]:
                network["connected"] = connected
                changed = True
        if changed:
            self.networksChanged.emit()

    @pyqtSlot()
    def scan(self):
        def scan(device):
            if not device.get_wifi():
                device.set_wifi(True)
            return (
                device.wifi_scan(),
                device.wifi_list_networks(),
                device.get_wifi_capabilities(),
                device.get_wifi_status(),
            )

        if self._submit(WifiOperation.SCAN, scan):
            self._set_status("Scanning for Wi-Fi networks.")

    @pyqtSlot(str)
    def selectNetwork(self, ssid):
        self._selected_ssid = str(ssid)
        network = next((item for item in self._networks if item["ssid"] == ssid), {})
        self._selected_security = network.get("security", "WPA2")
        self._selected_profile_id = network.get("profile_id", "")
        self._password_editable = network.get("password_editable", False)
        self.selectedNetworkChanged.emit()

    @pyqtSlot(str, str)
    def connectNetwork(self, ssid, password):
        if not ssid:
            self._set_status("Select a Wi-Fi network.")
            return
        if self._selected_ssid != ssid:
            self.selectNetwork(ssid)
        security_name = self._selected_security

        def connect(device):
            from ereader_hal import WifiConfig, WifiSecurity

            if not device.get_wifi():
                device.set_wifi(True)
            profiles = [
                item
                for item in device.wifi_list_networks()
                if item.ssid == ssid and _SECURITY[item.security.name] == security_name
            ]
            if profiles and not password:
                identifier = profiles[0].id
            else:
                security = {
                    "Open": WifiSecurity.OPEN,
                    "WPA2": WifiSecurity.WPA_PSK,
                    "WPA3": WifiSecurity.SAE,
                }.get(security_name)
                if (
                    security is None
                    or not device.get_wifi_capabilities().security_write
                    & (1 << security)
                ):
                    raise WifiError(
                        "Use stock Wi-Fi settings for this network's security mode"
                    )
                if security != WifiSecurity.OPEN and not password:
                    raise WifiError(
                        "This network has no saved credentials. Enter its Wi-Fi password."
                    )
                config = WifiConfig(
                    ssid=ssid, security=security, password=password or None
                )
                if profiles:
                    identifier = profiles[0].id
                    result = device.wifi_update_network(identifier, config)
                    identifier = result.network_id or identifier
                else:
                    identifier = device.wifi_add_network(config).network_id
            device.wifi_connect(identifier, wait_for_address=True, timeout_ms=30000)
            return device.get_wifi_status(), device.wifi_list_networks()

        if self._submit(WifiOperation.CONNECT, connect):
            self._set_status("Connecting to " + str(ssid) + ".")

    @pyqtSlot()
    def toggleRadio(self):
        def toggle(device):
            device.set_wifi(not device.get_wifi())
            return device.get_wifi_status()

        self._submit(WifiOperation.RADIO, toggle)

    @property
    def operation(self):
        return self._operation

    @property
    def polling(self):
        return self._polling

    @property
    def link(self):
        return self._link

    @property
    def operation_busy(self):
        return self._operation is not WifiOperation.IDLE

    def _set_polling(self, state):
        self._status_timer.stop()
        self._recovery_timer.stop()
        self._polling = state
        if state in {WifiPolling.NORMAL, WifiPolling.RECOVERING}:
            self._status_timer.start(1000 if state is WifiPolling.RECOVERING else 5000)
        if state is WifiPolling.RECOVERING:
            self._recovery_timer.start(30000)

    def _finish_recovery(self):
        if self._polling is WifiPolling.RECOVERING:
            self._set_polling(WifiPolling.NORMAL)

    def pause_polling(self):
        if self._polling is not WifiPolling.CLOSED:
            self._set_polling(WifiPolling.PAUSED)

    def resume_polling(self, *, after_sleep=False):
        if self._polling is WifiPolling.CLOSED:
            return
        if after_sleep:
            # A pre-suspend address must never authorize a post-wake request.
            self._set_link(WifiLink.CHECKING)
            self._set_status("Checking Wi-Fi after wake.")
        self._set_polling(WifiPolling.RECOVERING if after_sleep else WifiPolling.NORMAL)
        self._poll_status()

    def _poll_status(self):
        if self._polling in {WifiPolling.NORMAL, WifiPolling.RECOVERING}:
            self._submit(WifiOperation.STATUS, lambda device: device.get_wifi_status())

    def close(self):
        if self._polling is WifiPolling.CLOSED:
            return
        self._set_polling(WifiPolling.CLOSED)
        self._executor.shutdown(wait=True, cancel_futures=True)
