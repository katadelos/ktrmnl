from __future__ import annotations

import errno
import logging
from enum import Enum
from typing import Dict, Tuple

LOGGER = logging.getLogger("ktrmnl.hal")


class FrontlightState(Enum):
    STOCK = "stock"
    OWNED = "owned"
    CLOSED = "closed"


class EreaderClient:
    """Application snapshots backed by the stock-firmware e-reader HAL."""

    def __init__(self):
        from k2.adapters.hardware import open_device

        self._device = open_device()
        self._info = self._device.get_info()
        self._identity = self._device.get_identity()
        self._original_frontlight = None
        self._frontlight_state = FrontlightState.STOCK
        LOGGER.info("opened e-reader HAL for %s", self._info.model)

    def new_device(self):
        """A separate handle for serialized background Wi-Fi operations."""
        from k2.adapters.hardware import open_device

        return open_device()

    def device(self) -> Dict[str, object]:
        from ereader_hal import Capability

        identity = self._device.get_identity()
        if identity.wifi_mac:
            self._identity = identity
        return {
            "model": self._info.model,
            "board_id": self._info.codes,
            "serial": identity.serial,
            "compatible": self._info.codenames,
            "mac_address": self._identity.wifi_mac,
            "touch_available": self._device.get_capability(Capability.TOUCH).available,
            "frontlight_available": self._device.get_capability(
                Capability.FRONTLIGHT
            ).available
            and self._device.get_capability(Capability.BRIGHTNESS).available,
        }

    def reader_name(self) -> str:
        return self._info.model

    def display_size(self) -> Tuple[int, int]:
        display = self._device.get_display()
        return display.width, display.height

    def battery(self) -> Dict[str, object]:
        from ereader_hal import ChargeState

        try:
            battery = self._device.get_battery()
        except OSError:
            return {"available": False, "percent": 0, "status": "Unavailable"}
        status = {
            ChargeState.UNKNOWN: "Unknown",
            ChargeState.CHARGING: "Charging",
            ChargeState.DISCHARGING: "Discharging",
            ChargeState.FULL: "Full",
            ChargeState.NOT_CHARGING: "Not charging",
        }[battery.state]
        return {
            "available": True,
            "percent": battery.percent,
            "status": status,
            "present": True,
            "online": battery.state in {ChargeState.CHARGING, ChargeState.FULL},
        }

    def radio(self) -> Dict[str, object]:
        from ereader_hal import Capability

        capability = self._device.get_capability(Capability.WIFI)
        powered = self._device.get_wifi() if capability.available else False
        return {
            "available": capability.available,
            "powered": powered,
            "operational": powered,
            "writable": capability.available,
            "interface": self._identity.wifi_interface,
            "name": "Stock Wi-Fi",
            "driver": "ereader-hal",
        }

    def mac_address(self) -> str:
        return self.device()["mac_address"]

    def wifi_interface(self) -> str:
        return self._device.get_identity().wifi_interface

    def set_radio_powered(self, powered: bool) -> None:
        self._device.set_wifi(bool(powered))

    def set_frontlight(self, enabled: bool, brightness: int) -> None:
        if self._frontlight_state is FrontlightState.CLOSED:
            raise RuntimeError("The reader is closed")
        if self._frontlight_state is FrontlightState.STOCK:
            self._original_frontlight = self._device.get_frontlight()
            self._frontlight_state = FrontlightState.OWNED
        if enabled:
            self._device.set_brightness(int(brightness))
        else:
            self._device.set_frontlight(False)

    def grab_buttons(self) -> None:
        self._device.grab_buttons()

    def release_buttons(self) -> None:
        self._device.release_buttons()

    def poll_event(self):
        return self._device.poll_event(0)

    def _suspend(self, seconds=None, cancelled=None) -> Dict[str, object]:
        from ereader_hal import Capability, EventType

        with self.new_device() as device:
            if cancelled is not None:
                device.set_lifecycle_handler(
                    lambda event: (
                        -errno.ECANCELED
                        if event.type == EventType.PREPARE_SLEEP and cancelled()
                        else 0
                    )
                )
            light = None
            try:
                if cancelled is not None and cancelled():
                    raise OSError(errno.ECANCELED, "Suspend was cancelled.")
                if device.get_info().capabilities & Capability.FRONTLIGHT:
                    light = device.get_frontlight()
                try:
                    if light is not None and light.enabled:
                        device.set_frontlight(False)
                    if seconds is None:
                        device.suspend()
                    else:
                        device.suspend_for(int(seconds))
                finally:
                    if light is not None and light.enabled:
                        device.set_brightness(light.brightness)
            except Exception as error:
                error.slept_ms = device.get_last_sleep_ms()
                error.sleep_gap_ms = device.get_last_sleep_gap_ms()
                error.wake_reason = device.get_last_wake().reason.name
                raise
            return {
                "slept_ms": device.get_last_sleep_ms(),
                "sleep_gap_ms": device.get_last_sleep_gap_ms(),
                "reason": device.get_last_wake().reason.name,
            }

    def suspend_for(self, seconds: int, cancelled=None) -> Dict[str, object]:
        """Keep the displayed image while sleeping with the frontlight off."""
        return self._suspend(seconds, cancelled)

    def suspend(self, cancelled=None) -> Dict[str, object]:
        return self._suspend(cancelled=cancelled)

    def suspend_status(self, *, timed: bool) -> Dict[str, object]:
        from ereader_hal import Capability

        with self.new_device() as device:
            state = device.get_capability(Capability.SUSPEND)
            rtc = device.get_capability(Capability.RTC_WAKE) if timed else None
            if state.available and rtc is not None and not rtc.available:
                state = rtc
            return {
                "available": state.available,
                "max_sleep_seconds": rtc.maximum if rtc is not None else 0,
                "blocked": state.blocked,
                "error": state.error,
                "reason": state.reason,
            }

    def close(self) -> None:
        if self._frontlight_state is FrontlightState.CLOSED:
            return
        try:
            if self._frontlight_state is FrontlightState.OWNED:
                if self._original_frontlight.enabled:
                    self._device.set_brightness(self._original_frontlight.brightness)
                else:
                    self._device.set_frontlight(False)
                self._original_frontlight = None
        except OSError:
            LOGGER.exception("Could not restore the reader's frontlight")
        finally:
            self._frontlight_state = FrontlightState.CLOSED
            self._device.close()
