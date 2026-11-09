from __future__ import annotations

from typing import Dict, Optional, Tuple

from PyQt5.QtCore import (
    QObject,
    pyqtProperty,
    pyqtSignal,
)


def logical_size(native_size: Tuple[int, int], rotation: int) -> Tuple[int, int]:
    width, height = native_size
    return (height, width) if rotation in {90, 270} else (width, height)


class SimulatorDevice:
    """Deterministic stock-reader host device."""

    def __init__(
        self,
        *,
        display_size: Tuple[int, int],
        battery_percent: int,
        battery_status: str,
        radio_powered: bool,
        board: str,
        model: str,
    ):
        self._display_size = tuple(display_size)
        self._battery_percent = int(battery_percent)
        self._battery_status = str(battery_status)
        self._radio_powered = bool(radio_powered)
        self._board = str(board)
        self._model = str(model)

    def reader_name(self) -> str:
        return self._board

    def device(self) -> Dict[str, str]:
        return {
            "model": self._model,
            "board_id": "SIMULATOR",
            "serial": "SIM000000001",
            "compatible": "amazon,kt6",
            "mac_address": self.mac_address(),
            "frontlight_available": True,
        }

    def display_size(self) -> Tuple[int, int]:
        return self._display_size

    def set_display_size(self, width: int, height: int) -> None:
        self._display_size = (int(width), int(height))

    def battery(self) -> Dict[str, object]:
        return {
            "available": True,
            "percent": self._battery_percent,
            "status": self._battery_status,
            "health": "Good",
            "present": True,
            "online": self._battery_status == "Charging",
        }

    def radio(self) -> Dict[str, object]:
        return {
            "available": True,
            "powered": self._radio_powered,
            "operational": self._radio_powered,
            "writable": True,
            "interface": "wlan0",
            "name": "Deterministic Wi-Fi",
            "driver": "host-fake",
        }

    def set_radio_powered(self, powered: bool) -> None:
        self._radio_powered = bool(powered)

    def set_frontlight(self, _enabled: bool, _brightness: int) -> None:
        pass

    def mac_address(self) -> str:
        return "02:00:00:00:00:42"

    def close(self) -> None:
        pass


class SimulatorInputBackend(QObject):
    actionReceived = pyqtSignal(str)
    textReceived = pyqtSignal(str)

    def close(self) -> None:
        pass


class SimulatorDisplayBackend(QObject):
    nightModeChanged = pyqtSignal()
    rotationChanged = pyqtSignal()
    geometryChanged = pyqtSignal()
    fullRefreshRequested = pyqtSignal()

    def __init__(self, native_size: Tuple[int, int], rotation: int, parent=None):
        super().__init__(parent)
        self._native_size = tuple(native_size)
        self._night_mode = False
        self._rotation = int(rotation)

    @pyqtProperty(bool, notify=nightModeChanged)
    def nightMode(self) -> bool:
        return self._night_mode

    @pyqtProperty(int, notify=rotationChanged)
    def rotation(self) -> int:
        return self._rotation

    @pyqtProperty(int, notify=geometryChanged)
    def logicalWidth(self) -> int:
        return logical_size(self._native_size, self._rotation)[0]

    @pyqtProperty(int, notify=geometryChanged)
    def logicalHeight(self) -> int:
        return logical_size(self._native_size, self._rotation)[1]

    @pyqtProperty(int, notify=geometryChanged)
    def nativeWidth(self) -> int:
        return self._native_size[0]

    @pyqtProperty(int, notify=geometryChanged)
    def nativeHeight(self) -> int:
        return self._native_size[1]

    def set_night_mode(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled != self._night_mode:
            self._night_mode = enabled
            self.nightModeChanged.emit()

    def set_rotation(self, rotation: int) -> None:
        rotation = int(rotation) % 360
        if rotation != self._rotation:
            self._rotation = rotation
            self.rotationChanged.emit()
            self.geometryChanged.emit()

    def set_native_size(self, width: int, height: int) -> None:
        native_size = (int(width), int(height))
        if native_size != self._native_size:
            self._native_size = native_size
            self.geometryChanged.emit()

    def full_refresh(self) -> None:
        self.fullRefreshRequested.emit()

    def transition_refresh(self, inverted: Optional[bool] = None) -> None:
        if inverted is not None:
            self.set_night_mode(inverted)
        self.fullRefreshRequested.emit()

    def set_interactive_mode(self, active: bool) -> None:
        pass

    def wait_for_refresh(self) -> None:
        pass

    def close(self) -> None:
        pass
