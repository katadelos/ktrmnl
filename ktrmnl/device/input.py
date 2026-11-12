from __future__ import annotations

import logging
from enum import Enum

from PyQt5.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer, pyqtSignal

LOGGER = logging.getLogger("ktrmnl.input")


class InputState(Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    CLOSED = "closed"


class InputBridge(QObject):
    """Read physical buttons once through the HAL; Qt supplies touch and text."""

    actionReceived = pyqtSignal(str)
    textReceived = pyqtSignal(str)

    def __init__(self, hal, parent=None, *, exclusive_buttons=False):
        super().__init__(parent)
        self._hal = hal
        self._exclusive_buttons = exclusive_buttons
        self._state = InputState.INACTIVE
        self._application = QCoreApplication.instance()
        self._application.installEventFilter(self)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._read_events)
        self._timer.start()

    def set_interactive(self, interactive: bool) -> None:
        self._timer.setInterval(10 if interactive else 40)

    def set_active(self, active: bool) -> None:
        if self._state is InputState.CLOSED:
            return
        state = InputState.ACTIVE if active else InputState.INACTIVE
        if state is self._state:
            return
        if self._exclusive_buttons:
            if active:
                self._hal.grab_buttons()
            else:
                self._hal.release_buttons()
        self._state = state

    def eventFilter(self, _watched, event):
        # XCB and the framebuffer plugin can also deliver the same physical
        # buttons. Keep HAL navigation authoritative; eboard's synthetic key
        # events still reach the focused text field for editing and selection.
        if (
            self._state is InputState.ACTIVE
            and event.type() in (QEvent.KeyPress, QEvent.KeyRelease)
            and event.spontaneous()
        ):
            if event.key() in (
                Qt.Key_Up,
                Qt.Key_Down,
                Qt.Key_Left,
                Qt.Key_Right,
                Qt.Key_Return,
                Qt.Key_Enter,
                Qt.Key_Select,
                Qt.Key_Home,
                Qt.Key_Back,
                Qt.Key_Escape,
                Qt.Key_Menu,
                Qt.Key_PageUp,
                Qt.Key_PageDown,
                Qt.Key_F23,
                Qt.Key_F24,
                Qt.Key_PowerOff,
                Qt.Key_Control,
            ):
                return True
        return False

    def _read_events(self) -> None:
        from ereader_hal import Action, Button, EventType

        actions = {
            Button.PREVIOUS: "back",
            Button.NEXT: "next",
            Button.POWER: "power",
            Button.HOME: "home",
            Button.BACK: "back",
            Button.MENU: "menu",
            Button.UP: "up",
            Button.DOWN: "down",
            Button.LEFT: "left",
            Button.RIGHT: "right",
            Button.SELECT: "select",
            Button.KEYBOARD: "keyboard",
        }
        try:
            for _ in range(64):
                event = self._hal.poll_event()
                if event is None:
                    return
                if event.type != EventType.BUTTON or event.data.action != Action.PRESS:
                    continue
                # The display-retention session requires app-owned power-button sleep.
                action = actions.get(event.data.button)
                if action and self._state is InputState.ACTIVE:
                    self.actionReceived.emit(action)
        except OSError as error:
            LOGGER.warning("HAL input read failed: %s", error)

    def close(self) -> None:
        if self._state is InputState.CLOSED:
            return
        self._timer.stop()
        try:
            self.set_active(False)
        except OSError as error:
            LOGGER.warning("HAL input release failed: %s", error)
        self._state = InputState.CLOSED
        self._application.removeEventFilter(self)
