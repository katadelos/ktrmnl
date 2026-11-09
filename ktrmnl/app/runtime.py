from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import eboard
from PyQt5.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QUrl,
    pyqtSignal,
)
from PyQt5.QtQml import QQmlApplicationEngine

from ktrmnl.app.presentation import ContentPresentation
from ktrmnl.config.store import KtrmnlConfig

LOGGER = logging.getLogger("ktrmnl.app")


@dataclass
class ApplicationDependencies:
    """Concrete runtime services supplied by a launcher."""

    config: KtrmnlConfig
    device: Any
    wifi: Any
    content: Any
    display: Any
    input_backend: Any
    controller: Any
    push_server: Any


@dataclass(frozen=True)
class ApplicationOptions:
    qml_path: Path
    display_size: Tuple[int, int]
    device: bool = False
    family: Optional[str] = None
    initial_menu_open: bool = False
    initial_menu_page: str = "root"
    context_properties: Mapping[str, Any] = field(default_factory=dict)


class InputRouter(QObject):
    """Route all physical input through interrupt dismissal first."""

    actionReceived = pyqtSignal(str)
    textReceived = pyqtSignal(str)

    def __init__(self, backend: Any, controller: Any, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._backend = backend
        self._controller = controller
        backend.actionReceived.connect(self._on_action)
        backend.textReceived.connect(self._on_text)

    def _on_action(self, action: str) -> None:
        action = str(action)
        if action == "power":
            self._controller.requestSuspend()
            return
        if self._controller.handleInput(action):
            return
        self.actionReceived.emit(action)

    def _on_text(self, value: str) -> None:
        if self._controller.handleInput("text"):
            return
        self.textReceived.emit(str(value))

    def close(self) -> None:
        self._backend.close()


class RuntimeState(Enum):
    CREATED = "created"
    LOADING = "loading"
    RUNNING = "running"
    RELOADING = "reloading"
    FAILED = "failed"
    CLOSED = "closed"


class ApplicationRuntime(QObject):
    """Shared QML bootstrap for device and host compositions."""

    def __init__(
        self,
        application: Any,
        dependencies: ApplicationDependencies,
        options: ApplicationOptions,
    ):
        super().__init__(application)
        self.application = application
        self.dependencies = dependencies
        self.options = options
        self.engine = QQmlApplicationEngine()
        self.keyboard_display = eboard.install(
            self.engine,
            device=options.device,
            family=options.family,
        )
        self.input_router = InputRouter(
            dependencies.input_backend, dependencies.controller, self
        )
        self.state = RuntimeState.CREATED

        dependencies.display.set_night_mode(dependencies.config.dark_mode)
        dependencies.push_server.start()
        if dependencies.push_server.error:
            LOGGER.error(dependencies.push_server.error)

        self.presentation = ContentPresentation(
            dependencies.content,
            dependencies.controller,
            self,
        )
        context = self.engine.rootContext()
        context.setContextProperty("ktrmnl", dependencies.controller)
        context.setContextProperty("content", self.presentation)
        context.setContextProperty("wifi", dependencies.wifi)
        context.setContextProperty("inputBridge", self.input_router)
        context.setContextProperty("pushRuntime", dependencies.push_server)
        context.setContextProperty("runtimeDisplayWidth", options.display_size[0])
        context.setContextProperty("runtimeDisplayHeight", options.display_size[1])
        ui_profile = dependencies.config.ui_profile(*options.display_size)
        context.setContextProperty("runtimeTextScale", ui_profile["text_scale"])
        context.setContextProperty(
            "runtimeRowHeightScale", ui_profile["menu_row_height_scale"]
        )
        context.setContextProperty(
            "runtimeKeyboardHeightRatio", ui_profile["keyboard_height_ratio"]
        )
        context.setContextProperty("runtimeInitialMenuOpen", options.initial_menu_open)
        context.setContextProperty("runtimeInitialMenuPage", options.initial_menu_page)
        for name, value in options.context_properties.items():
            context.setContextProperty(str(name), value)

        application.aboutToQuit.connect(self.close)
        dependencies.controller.exitRequested.connect(application.quit)

    def load(self) -> bool:
        if self.state not in {
            RuntimeState.CREATED,
            RuntimeState.RELOADING,
            RuntimeState.FAILED,
        }:
            return self.state is RuntimeState.RUNNING
        self.state = RuntimeState.LOADING
        self.dependencies.controller.reloadMenu()
        self.engine.load(QUrl.fromLocalFile(str(self.options.qml_path.resolve())))
        loaded = bool(self.engine.rootObjects())
        if not loaded:
            LOGGER.error("QML failed to load from %s", self.options.qml_path)
        if loaded:
            window = self.engine.rootObjects()[0]
            refresh = self.keyboard_display.attach(window)
            if hasattr(self.dependencies.display, "attach"):
                self.dependencies.display.attach(window, refresh)
        self.state = RuntimeState.RUNNING if loaded else RuntimeState.FAILED
        return loaded

    def reload(self) -> bool:
        if self.state not in {RuntimeState.RUNNING, RuntimeState.FAILED}:
            return False
        self.state = RuntimeState.RELOADING
        self.dependencies.display.close()
        self.keyboard_display.close()
        for root in self.engine.rootObjects():
            root.setProperty("visible", False)
            root.deleteLater()
            QCoreApplication.sendPostedEvents(root, QEvent.DeferredDelete)
        self.engine.clearComponentCache()
        self.keyboard_display = eboard.install(
            self.engine,
            device=self.options.device,
            family=self.options.family,
        )
        return self.load()

    def close(self) -> None:
        if self.state is RuntimeState.CLOSED:
            return
        self.state = RuntimeState.CLOSED
        self.dependencies.push_server.stop()
        self.input_router.close()
        self.dependencies.wifi.close()
        self.dependencies.controller.close()
        self.dependencies.display.close()
        self.keyboard_display.close()
        self.dependencies.device.close()
        self.presentation.close()
