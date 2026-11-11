from __future__ import annotations

import ctypes
from enum import Enum
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtGui import QGuiApplication


class DisplayError(RuntimeError):
    """The stock display integration cannot complete an operation."""


class DisplayState(Enum):
    DETACHED = "detached"
    ATTACHED = "attached"


class RefreshMode(Enum):
    NORMAL = "normal"
    INTERACTIVE = "interactive"


class StockDisplayBackend:
    """Refresh the app through its Qt platform's display owner."""

    def __init__(self):
        self._window = None
        self._refresh = None
        self._night_mode = False
        self._platform = None
        self._mode = RefreshMode.NORMAL
        self._state = DisplayState.DETACHED

    def _load_platform(self):
        if QGuiApplication.platformName() != "ereader":
            return
        paths = (
            Path(p) / "platforms/libqereader.so"
            for p in QCoreApplication.libraryPaths()
        )
        path = next(p for p in paths if p.is_file())
        self._platform = ctypes.CDLL(str(path))
        for name, arguments, result in (
            ("ereader_set_interactive_mode", [ctypes.c_bool], None),
            ("ereader_request_full_refresh", [], None),
            ("ereader_wait_for_refresh", [], ctypes.c_bool),
        ):
            function = getattr(self._platform, name)
            function.argtypes, function.restype = arguments, result

    def attach(self, window, refresh) -> None:
        self.close()
        self._window = window
        self._refresh = refresh
        self._load_platform()
        self._state = DisplayState.ATTACHED
        self.set_interactive_mode(self._mode is RefreshMode.INTERACTIVE)

    def set_night_mode(self, enabled: bool) -> None:
        # QML paints the application's dark palette. Do not invert stock chrome.
        self._night_mode = bool(enabled)

    def set_rotation(self, rotation: int) -> None:
        if int(rotation) not in {0, 90, 180, 270}:
            raise DisplayError(f"Unsupported display rotation: {rotation}")
        # QML owns the scene transform, keeping drawing and input coordinates together.

    def set_interactive_mode(self, active: bool) -> None:
        self._mode = RefreshMode.INTERACTIVE if active else RefreshMode.NORMAL
        if self._platform is not None:
            self._platform.ereader_set_interactive_mode(
                self._mode is RefreshMode.INTERACTIVE
            )

    def full_refresh(self) -> None:
        if self._state is DisplayState.DETACHED:
            return
        if self._refresh is not None:
            self._refresh.request_cleanup(full=True)
            self._window.update()
        elif self._platform is not None:
            self._platform.ereader_request_full_refresh()
            self._window.update()

    def transition_refresh(self, inverted: Optional[bool] = None) -> None:
        if inverted is not None:
            self.set_night_mode(inverted)
        self.full_refresh()

    def wait_for_refresh(self) -> None:
        if self._state is DisplayState.DETACHED:
            return
        if self._refresh is not None:
            # The stock compositor exposes drawing submission, not a panel fence.
            self._refresh.flush_pending()
        elif (
            self._platform is not None and not self._platform.ereader_wait_for_refresh()
        ):
            raise DisplayError("The display has not finished refreshing")

    def close(self) -> None:
        self._state = DisplayState.DETACHED
        if self._refresh is not None:
            self._refresh.close()
            self._refresh = None
        self._window = None
        self._platform = None
