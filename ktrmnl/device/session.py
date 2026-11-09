from __future__ import annotations

import logging
import socket
from enum import Enum
from pathlib import Path

from ktrmnl.app.runtime import (
    RuntimeState,
)

LOGGER = logging.getLogger("ktrmnl.device")


class ActivityState(Enum):
    STARTING = "starting"
    ACTIVE = "active"
    SLEEPING = "sleeping"
    BACKGROUND = "background"
    CLOSED = "closed"


class FocusState(Enum):
    ACQUIRING = "acquiring"
    ACQUIRED = "acquired"


class DisplaySession:
    """Coordinate display retention, awake ownership and physical input."""

    def __init__(self, runtime, power, window, input_backend, directory):
        self.runtime = runtime
        self.power = power
        self.window = window
        self.input = input_backend
        self.control_path = str(Path(directory) / "control")
        self.state = ActivityState.STARTING
        self.focus = FocusState.ACQUIRING
        power.activityChanged.connect(self.sync)
        window.activeChanged.connect(self.sync)
        window.visibleChanged.connect(self.sync)

    def sync(self):
        if (
            self.state is ActivityState.CLOSED
            or self.runtime.state is RuntimeState.CLOSED
        ):
            return True
        if self.window.isActive():
            self.focus = FocusState.ACQUIRED
        # Retain the first frame until Qt has acquired focus once.
        visible = self.window.isVisible() and (
            self.window.isActive() or self.focus is FocusState.ACQUIRING
        )
        target = (
            ActivityState.BACKGROUND
            if not visible
            else (
                ActivityState.SLEEPING
                if self.power.suspending
                else ActivityState.ACTIVE
            )
        )
        if target is self.state:
            return True
        retained = {ActivityState.ACTIVE, ActivityState.SLEEPING}
        try:
            self.input.set_active(visible)
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as control:
                control.setblocking(False)
                if self.state is ActivityState.STARTING or (target in retained) != (
                    self.state in retained
                ):
                    control.sendto(
                        b"retain" if target in retained else b"release",
                        self.control_path,
                    )
                if self.state is ActivityState.STARTING or (
                    target is ActivityState.ACTIVE
                ) != (self.state is ActivityState.ACTIVE):
                    control.sendto(
                        b"active" if target is ActivityState.ACTIVE else b"inactive",
                        self.control_path,
                    )
            self.state = target
        except OSError:
            LOGGER.exception("The k2 display session ended")
            self.runtime.application.exit(1)
            return False
        return True

    def close(self):
        if self.state is ActivityState.CLOSED:
            return
        self.state = ActivityState.CLOSED
        self.power.close()
        self.runtime.close()
