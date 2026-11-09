from __future__ import annotations

from typing import Any, Dict, List

from PyQt5.QtCore import (
    QObject,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

from ktrmnl.config.store import KtrmnlConfig
from ktrmnl.network.wifi import WifiLink, WifiOperation, WifiPolling
from ktrmnl.simulator.backends import SimulatorDevice


class SimulatorWifiManager(QObject):
    networksChanged = pyqtSignal()
    stateChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    selectedNetworkChanged = pyqtSignal()
    connectedChanged = pyqtSignal()

    _NETWORKS = (
        ("TRMNL Wi-Fi", -48, "WPA2"),
        ("Kindle Guest", -67, "Open"),
        ("Reader Lab", -79, "WPA2"),
    )

    def __init__(
        self,
        config: KtrmnlConfig,
        device: SimulatorDevice,
        initial_ssid: str,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.hal = device
        self._networks: List[Dict[str, Any]] = []
        self._status = "Wi-Fi ready."
        self._selected_ssid = ""
        self._selected_security = ""
        self._saved_networks = {
            (ssid, security)
            for ssid, _signal, security in self._NETWORKS
            if ssid == initial_ssid
        }
        self._operation = WifiOperation.IDLE
        self._polling = WifiPolling.NORMAL
        self._connected_ssid = str(initial_ssid) if device.radio()["powered"] else ""
        self._link = (
            WifiLink.CONNECTED
            if self._connected_ssid
            else WifiLink.DISCONNECTED if self.radioPowered else WifiLink.OFF
        )
        self._ip_address = "192.168.1.42" if self.connected else ""
        self._signal_strength = -48 if self.connected else 0
        self._replace_networks()

    def _replace_networks(self) -> None:
        self._networks = [
            {
                "ssid": ssid,
                "signal": signal,
                "security": security,
                "secured": security != "Open",
                "connected": self.connected and ssid == self._connected_ssid,
                "saved": (ssid, security) in self._saved_networks,
                "profile_id": (
                    "sim-" + ssid if (ssid, security) in self._saved_networks else ""
                ),
                "password_editable": security in {"WPA2", "WPA3"},
            }
            for ssid, signal, security in self._NETWORKS
        ]
        self.networksChanged.emit()

    def _set_status(self, value: str) -> None:
        if value != self._status:
            self._status = str(value)
            self.statusChanged.emit()

    @pyqtProperty(bool, notify=stateChanged)
    def available(self) -> bool:
        return self._polling is not WifiPolling.CLOSED

    @pyqtProperty("QVariantList", notify=networksChanged)
    def networks(self):
        return self._networks

    @pyqtProperty(bool, notify=stateChanged)
    def scanning(self) -> bool:
        return self._operation is WifiOperation.SCAN

    @pyqtProperty(bool, notify=stateChanged)
    def connecting(self) -> bool:
        return self._operation is WifiOperation.CONNECT

    @pyqtProperty(bool, notify=connectedChanged)
    def connected(self) -> bool:
        return self._link is WifiLink.CONNECTED

    @pyqtProperty(bool, notify=stateChanged)
    def radioPowered(self) -> bool:
        return bool(self.hal.radio()["powered"])

    @pyqtProperty(str, notify=statusChanged)
    def statusText(self) -> str:
        return self._status

    @pyqtProperty(str, notify=selectedNetworkChanged)
    def selectedSsid(self) -> str:
        return self._selected_ssid

    @pyqtProperty(str, notify=selectedNetworkChanged)
    def selectedSecurity(self) -> str:
        return self._selected_security

    @pyqtProperty(bool, notify=selectedNetworkChanged)
    def requiresPassword(self) -> bool:
        return (
            self.passwordEditable
            and (self._selected_ssid, self._selected_security)
            not in self._saved_networks
        )

    @pyqtProperty(bool, notify=selectedNetworkChanged)
    def passwordEditable(self) -> bool:
        return self._selected_security in {"WPA2", "WPA3"}

    @pyqtProperty(str, notify=stateChanged)
    def connectedSsid(self) -> str:
        return self._connected_ssid

    @pyqtProperty(str, notify=stateChanged)
    def ipAddress(self) -> str:
        return self._ip_address

    @pyqtProperty(int, notify=stateChanged)
    def signalStrength(self) -> int:
        return self._signal_strength

    @pyqtSlot()
    def scan(self) -> None:
        if self._polling is WifiPolling.CLOSED:
            return
        self._operation = WifiOperation.SCAN
        self.stateChanged.emit()
        self._replace_networks()
        self._operation = WifiOperation.IDLE
        self._set_status("Select a Wi-Fi network.")
        self.stateChanged.emit()

    @pyqtSlot(str)
    def selectNetwork(self, ssid: str) -> None:
        if self._polling is WifiPolling.CLOSED:
            return
        network = next((item for item in self._networks if item["ssid"] == ssid), None)
        if network is None:
            self._set_status("The Wi-Fi network is not available.")
            return
        self._selected_ssid = str(ssid)
        self._selected_security = str(network["security"])
        self.selectedNetworkChanged.emit()
        self._set_status(
            "Enter the Wi-Fi password."
            if self.requiresPassword
            else "Wi-Fi connection ready."
        )

    @pyqtSlot(str, str)
    def connectNetwork(self, ssid: str, password: str) -> None:
        self._connect(str(ssid), str(password), "")

    def _connect(self, ssid: str, password: str, security: str) -> None:
        if self._polling is WifiPolling.CLOSED:
            return
        if not ssid:
            self._set_status("Select a Wi-Fi network.")
            return
        self._selected_ssid = ssid
        self._selected_security = security or next(
            (item["security"] for item in self._networks if item["ssid"] == ssid),
            "WPA2" if password else "Open",
        )
        self.selectedNetworkChanged.emit()
        if (password or self.requiresPassword) and not 8 <= len(password) <= 64:
            self._set_status("The Wi-Fi password must contain 8 to 64 characters.")
            return
        self._operation = WifiOperation.CONNECT
        self.stateChanged.emit()
        self.hal.set_radio_powered(True)
        self._link = WifiLink.CONNECTED
        self._operation = WifiOperation.IDLE
        self._connected_ssid = ssid
        self._ip_address = "192.168.1.42"
        self._signal_strength = -48
        self._saved_networks.add((ssid, self._selected_security))
        self.config.set("wifi_essid", ssid)
        self._replace_networks()
        self.selectedNetworkChanged.emit()
        self.connectedChanged.emit()
        self.stateChanged.emit()
        self._set_status("Connected to " + ssid + ".")

    @pyqtSlot()
    def toggleRadio(self) -> None:
        if self._polling is WifiPolling.CLOSED:
            return
        powered = not bool(self.hal.radio()["powered"])
        self._link = WifiLink.DISCONNECTED if powered else WifiLink.OFF
        self.hal.set_radio_powered(powered)
        if not powered:
            self._connected_ssid = ""
            self._ip_address = ""
            self._signal_strength = 0
            self._replace_networks()
            self.connectedChanged.emit()
        self.stateChanged.emit()
        self._set_status("Wi-Fi radio on." if powered else "Wi-Fi radio off.")

    def snapshot(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "status": self.statusText,
            "scanning": self.scanning,
            "connecting": self.connecting,
            "connected": self.connected,
            "connected_ssid": self.connectedSsid,
            "ip_address": self.ipAddress,
            "signal_strength": self.signalStrength,
            "networks": [dict(network) for network in self._networks],
        }

    def close(self) -> None:
        self._polling = WifiPolling.CLOSED
        self._operation = WifiOperation.IDLE
