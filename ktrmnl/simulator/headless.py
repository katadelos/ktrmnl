from __future__ import annotations

import json
import sys
from enum import Enum
from typing import Any, Dict

from PyQt5.QtCore import (
    Q_ARG,
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPointF,
    QSocketNotifier,
    Qt,
    pyqtSlot,
)
from PyQt5.QtGui import QKeyEvent, QMouseEvent

from ktrmnl.simulator.options import MENU_PAGES


class ControlState(Enum):
    OPEN = "open"
    CLOSED = "closed"


class HeadlessController(QObject):
    """JSON-lines control surface for deterministic host runs."""

    def __init__(self, runtime, controller, content, display, device, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.controller = controller
        self.content = content
        self.display = display
        self.device = device
        self.wifi = controller.wifi
        self._state = ControlState.OPEN
        self.notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Read, self)
        self.notifier.activated.connect(self._read_request)
        QCoreApplication.instance().aboutToQuit.connect(self.close)

    @pyqtSlot()
    def ready(self) -> None:
        self._write({"event": "ready", "state": self.state()})

    def state(self) -> Dict[str, Any]:
        root = self._root()
        secret_editor_name = (
            "wifiPage"
            if str(root.property("menuPage")) == "wifi-password"
            else "settingsKeyboardLayer"
        )
        secret_editor = root.findChild(QObject, secret_editor_name)
        keyboard = (
            secret_editor.findChild(QObject, "onScreenKeyboard")
            if secret_editor
            else None
        )
        first_run_start = root.findChild(QObject, "firstRunStartButton")
        return {
            "ui": {
                "menuOpen": bool(root.property("menuOpen")),
                "menuPage": str(root.property("menuPage")),
                "menuIndex": int(root.property("menuIndex")),
                "keyboardVisible": bool(root.property("keyboardVisible")),
                "secretRevealed": bool(
                    secret_editor
                    and secret_editor.property(
                        "passwordRevealed"
                        if secret_editor_name == "wifiPage"
                        else "secretRevealed"
                    )
                ),
                "keyboardSelectionActive": bool(
                    keyboard and keyboard.property("selectionActive")
                ),
                "keyboardRow": int(keyboard.property("currentRow")) if keyboard else -1,
                "keyboardColumn": (
                    int(keyboard.property("currentColumn")) if keyboard else -1
                ),
                "keyboardShifted": bool(keyboard and keyboard.property("shifted")),
                "keyboardSymbols": bool(keyboard and keyboard.property("symbols")),
                "width": int(root.property("width")),
                "height": int(root.property("height")),
                "nativeWidth": int(root.property("simulatorNativeWidth")),
                "nativeHeight": int(root.property("simulatorNativeHeight")),
                "textScale": float(root.property("simulatorTextScale")),
                "rowHeightScale": float(root.property("simulatorRowHeightScale")),
                "menuRowHeight": int(root.property("simulatorMenuRowHeight")),
                "keyboardHeightRatio": float(
                    root.property("simulatorKeyboardHeightRatio")
                ),
                "simulatorPanelOpen": bool(root.property("simulatorPanelOpen")),
                "simulatorPanelTab": int(root.property("simulatorPanelTab")),
                "firstRunActive": bool(root.property("firstRunActive")),
                "languageSelectionActive": bool(
                    root.property("languageSelectionActive")
                ),
                "firstRunWelcomeActive": bool(root.property("firstRunWelcomeActive")),
                "firstRunActionText": (
                    str(first_run_start.property("text")) if first_run_start else ""
                ),
                "language": str(root.property("simulatorLanguage")),
                "appOverlay": str(root.property("appOverlay")),
            },
            "content": {
                "mode": self.content.mode,
                "status": self.content.status,
                "imageSource": self.content.imageSource,
                "busy": self.content.busy,
                "refreshRate": self.content.refreshRate,
                "interruptActive": self.content.interruptActive,
                "interruptTitle": self.content.interruptTitle,
                "interruptMessage": self.content.interruptMessage,
                "interruptInverted": self.content.interruptInverted,
            },
            "device": {
                "board": self.controller.board,
                "model": self.controller.model,
                "battery": self.controller.batteryText,
                "radio": self.controller.radioText,
                "darkMode": self.controller.darkMode,
                "displayInverted": self.display.nightMode,
            },
            "wifi": self.wifi.snapshot(),
        }

    @pyqtSlot(int)
    def _read_request(self, _fd: int) -> None:
        if self._state is ControlState.CLOSED:
            return
        line = sys.stdin.readline()
        if not line:
            self.close()
            QCoreApplication.quit()
            return
        request_id = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
            request_id = request.get("id")
            command = request.get("command")
            if command == "state":
                result = self.state()
            elif command == "input":
                self._input(request)
                result = self.state()
            elif command == "quit":
                result = self.state()
                self._write({"id": request_id, "ok": True, "state": result})
                self.close()
                QCoreApplication.quit()
                return
            else:
                raise ValueError("command must be state, input, or quit")
            self._write({"id": request_id, "ok": True, "state": result})
        except (
            AttributeError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            self._write({"id": request_id, "ok": False, "error": str(error)})

    def close(self) -> None:
        self._state = ControlState.CLOSED
        self.notifier.setEnabled(False)

    def _input(self, request: Dict[str, Any]) -> None:
        action = request.get("action")
        root = self._root()
        if action == "toggle-menu":
            if self.controller.handleInput("menu"):
                return
            if bool(root.property("menuOpen")):
                QMetaObject.invokeMethod(root, "closeMenu", Qt.DirectConnection)
            else:
                self._open_menu(root, "root")
        elif action == "open-menu":
            self._open_menu(root, str(request.get("page", "root")))
        elif action == "show-first-run":
            QMetaObject.invokeMethod(root, "showFirstRun", Qt.DirectConnection)
        elif action == "set-first-run":
            QMetaObject.invokeMethod(
                root,
                "setSimulatorFirstRun",
                Qt.DirectConnection,
                Q_ARG("QVariant", bool(request.get("active", True))),
            )
        elif action == "close-menu":
            QMetaObject.invokeMethod(root, "closeMenu", Qt.DirectConnection)
        elif action == "refresh":
            self.controller.refresh()
        elif action == "set-mode":
            self.controller.setMode(str(request["mode"]))
        elif action == "publish-interrupt":
            self.content.publishInterrupt(
                str(request.get("message", "Simulator interrupt")),
                title=str(request.get("title", "Message")),
                expires_in=request.get("expires_in", 30),
                invert=bool(request.get("invert", False)),
            )
        elif action == "dismiss-interrupt":
            self.controller.dismissInterrupt()
        elif action == "toggle-dark":
            self.controller.toggleDarkMode()
        elif action == "toggle-rotation":
            self.controller.toggleRotation()
        elif action == "toggle-wifi":
            self.controller.toggleWifi()
        elif action == "scan-wifi":
            self.wifi.scan()
        elif action == "wifi-select":
            self.wifi.selectNetwork(str(request["ssid"]))
        elif action == "wifi-connect":
            self.wifi.connectNetwork(
                str(request["ssid"]), str(request.get("password", ""))
            )
        elif action == "key":
            if not self.controller.handleInput("key"):
                self._key(request["key"], str(request.get("text", "")))
        elif action == "tap":
            if not self.controller.handleInput("tap"):
                self._tap(float(request["x"]), float(request["y"]))
        elif action in {
            "up",
            "down",
            "left",
            "right",
            "select",
            "back",
            "menu",
            "next",
            "home",
        }:
            if self.controller.handleInput(str(action)):
                return
            self._key(
                {
                    "up": "Up",
                    "down": "Down",
                    "left": "Left",
                    "right": "Right",
                    "select": "Enter",
                    "back": "Escape",
                    "menu": "M",
                    "next": "R",
                    "home": "Home",
                }[str(action)]
            )
        elif action in {"keyboard", "backspace"}:
            QMetaObject.invokeMethod(
                root,
                "handleAction",
                Qt.DirectConnection,
                Q_ARG("QVariant", str(action)),
            )
        else:
            raise ValueError(f"unknown input action: {action}")

    def _open_menu(self, root, page: str) -> None:
        if page not in MENU_PAGES:
            raise ValueError(f"unknown menu page: {page}")
        QMetaObject.invokeMethod(
            root, "openMenu", Qt.DirectConnection, Q_ARG("QVariant", page)
        )

    def _tap(self, x: float, y: float) -> None:
        root = self._root()
        position = QPointF(x, y)
        QCoreApplication.sendEvent(
            root,
            QMouseEvent(
                QEvent.MouseButtonPress,
                position,
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier,
            ),
        )
        QCoreApplication.sendEvent(
            root,
            QMouseEvent(
                QEvent.MouseButtonRelease,
                position,
                Qt.LeftButton,
                Qt.NoButton,
                Qt.NoModifier,
            ),
        )

    def _key(self, value: Any, text: str = "") -> None:
        root = self._root()
        if isinstance(value, int):
            key = value
        else:
            name = str(value)
            key = getattr(Qt, name if name.startswith("Key_") else f"Key_{name}", None)
            if key is None:
                raise ValueError(f"unknown Qt key: {name}")
        QCoreApplication.sendEvent(
            root, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, text)
        )
        QCoreApplication.sendEvent(
            root, QKeyEvent(QEvent.KeyRelease, key, Qt.NoModifier, text)
        )

    def _root(self):
        roots = self.runtime.rootObjects()
        if not roots:
            raise ValueError("QML root is not loaded")
        return roots[0]

    @staticmethod
    def _write(response: Dict[str, Any]) -> None:
        print(json.dumps(response, sort_keys=True), flush=True)
