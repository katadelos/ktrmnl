from __future__ import annotations

from enum import Enum
from typing import Optional

from PyQt5.QtCore import QObject, QTimer

from ktrmnl.device.display import RefreshMode


class RefreshState(Enum):
    CLOSED = "closed"
    IDLE = "idle"
    CLEAR = "clear"
    TRANSITION = "transition"


class DisplayRefresh(QObject):
    """Coalesce UI refresh requests and own the display's interactive mode."""

    def __init__(self, display, report_error, parent=None):
        super().__init__(parent)
        self.display = display
        self._report_error = report_error
        self._refresh_state = RefreshState.IDLE
        self._refresh_inverted: Optional[bool] = None
        self._refresh_mode = RefreshMode.NORMAL

    def set_interactive(self, active: bool) -> None:
        """Keep A2 active for the complete menu visit, then settle once."""

        mode = RefreshMode.INTERACTIVE if active else RefreshMode.NORMAL
        if mode is self._refresh_mode or (
            self._refresh_state is RefreshState.CLOSED and active
        ):
            return
        try:
            self.display.set_interactive_mode(active)
        except Exception as error:
            self._report_error("Fast refresh error: " + str(error), "error")
            return
        self._refresh_mode = mode

    def request(
        self, refresh: RefreshState, *, inverted: Optional[bool] = None
    ) -> None:
        if self._refresh_state is RefreshState.CLOSED:
            return
        scheduled = self._refresh_state is not RefreshState.IDLE
        if scheduled:
            pending_refresh, pending_inverted = (
                self._refresh_state,
                self._refresh_inverted,
            )
            # A special-screen transition supersedes the panel clear normally
            # requested when a menu closes. An explicit output transform from
            # a power screen also outranks a duplicate generic transition.
            if (
                pending_refresh is RefreshState.TRANSITION
                and refresh is RefreshState.CLEAR
            ):
                return
            if (
                pending_refresh is RefreshState.TRANSITION
                and refresh is RefreshState.TRANSITION
                and pending_inverted is not None
                and inverted is None
            ):
                return
        self._refresh_state, self._refresh_inverted = refresh, inverted
        if not scheduled:
            QTimer.singleShot(0, self._perform)

    def _perform(self) -> None:
        if self._refresh_state is RefreshState.CLOSED:
            return
        refresh, inverted = self._refresh_state, self._refresh_inverted
        self._refresh_state, self._refresh_inverted = RefreshState.IDLE, None
        if refresh is RefreshState.IDLE:
            return
        try:
            if refresh is RefreshState.TRANSITION:
                self.display.transition_refresh(inverted)
            else:
                self.display.full_refresh()
        except Exception as error:
            self._report_error("Display refresh error: " + str(error), "error")

    def close(self):
        if self._refresh_state is RefreshState.CLOSED:
            return
        self.set_interactive(False)
        self._refresh_state = RefreshState.CLOSED
        self._refresh_inverted = None
