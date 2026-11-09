from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from ktrmnl2.content.inbox import InterruptMessage


class InterruptState(Enum):
    HIDDEN = "hidden"
    VISIBLE = "visible"


@dataclass(frozen=True)
class ActiveInterrupt:
    message: InterruptMessage
    deadline: float
    previous_status: str


class InterruptOverlay(QObject):
    """Own the active interrupt, expiry timer and last consumed sequence."""

    changed = pyqtSignal()
    statusChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._interrupt_state = InterruptState.HIDDEN
        self._interrupt: Optional[ActiveInterrupt] = None
        self._interrupt_sequence = 0
        self._interrupt_timer = QTimer(self)
        self._interrupt_timer.setSingleShot(True)
        self._interrupt_timer.timeout.connect(self._interrupt_timeout)

    def receive(self, item: InterruptMessage, current_status: str) -> None:
        if item.sequence <= self._interrupt_sequence:
            return
        previous_status = (
            self._interrupt.previous_status if self._interrupt else current_status
        )
        self._interrupt_sequence = item.sequence
        self._interrupt = ActiveInterrupt(
            item, time.monotonic() + item.expires_in, previous_status
        )
        self._interrupt_state = InterruptState.VISIBLE
        self._arm_interrupt_timer()
        self.statusChanged.emit("Interrupt: " + item.title)
        self.changed.emit()

    def _arm_interrupt_timer(self) -> None:
        remaining_ms = max(
            1, int(math.ceil((self._interrupt.deadline - time.monotonic()) * 1000))
        )
        self._interrupt_timer.start(min(2_000_000_000, remaining_ms))

    def _interrupt_timeout(self) -> None:
        if self._interrupt_state is InterruptState.HIDDEN:
            return
        if time.monotonic() < self._interrupt.deadline:
            self._arm_interrupt_timer()
        else:
            self.dismiss()

    def dismiss(self) -> bool:
        if self._interrupt_state is InterruptState.HIDDEN:
            return False
        self._interrupt_timer.stop()
        previous_status = self._interrupt.previous_status
        self._interrupt_state = InterruptState.HIDDEN
        self._interrupt = None
        self.changed.emit()
        if previous_status:
            self.statusChanged.emit(previous_status)
        return True

    @property
    def active(self) -> bool:
        return self._interrupt_state is InterruptState.VISIBLE

    @property
    def title(self) -> str:
        return self._interrupt.message.title if self._interrupt else ""

    @property
    def message(self) -> str:
        return self._interrupt.message.message if self._interrupt else ""

    @property
    def inverted(self) -> bool:
        return self._interrupt.message.invert if self._interrupt else False
