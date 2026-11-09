from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Optional, Sequence

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication

from ktrmnl2.app.controller import KtrmnlController
from ktrmnl2.app.runtime import (
    ApplicationDependencies,
    ApplicationOptions,
    ApplicationRuntime,
)
from ktrmnl2.config.defaults import CONTENT_MODES
from ktrmnl2.config.store import KtrmnlConfig, device_config_path
from ktrmnl2.content.controller import ContentController
from ktrmnl2.device.display import StockDisplayBackend
from ktrmnl2.device.hal import EreaderClient
from ktrmnl2.device.input import InputBridge
from ktrmnl2.device.power import StockPower
from ktrmnl2.device.session import DisplaySession
from ktrmnl2.i18n import TranslationManager
from ktrmnl2.log import configure as configure_logging
from ktrmnl2.network.firewall import PushFirewall
from ktrmnl2.network.push import PushWebServer
from ktrmnl2.network.wifi import WifiManager
from ktrmnl2.resources import RESOURCE_ROOT

LOGGER = logging.getLogger("ktrmnl2.device")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ktrmnl2 stock e-reader client")
    parser.add_argument("--family", choices=("kindle", "kobo"), required=True)
    parser.add_argument("--config", type=Path, default=device_config_path())
    parser.add_argument("--mode", choices=CONTENT_MODES)
    parser.add_argument("--rotation", type=int, choices=(0, 90, 180, 270))
    parser.add_argument("--menu", action="store_true", help="open the menu at startup")
    parser.add_argument(
        "--menu-page", default="root", help="menu page to show with --menu"
    )
    return parser.parse_args(list(argv))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging(runtime="device")
    session_directory = os.environ.get("K2_SESSION_DIR")
    if not session_directory:
        LOGGER.error("Launch ktrmnl2 through its installed launcher")
        return 2
    if os.environ.get("K2_RETAIN_DISPLAY") != "1":
        LOGGER.error("The display supervisor must retain application content")
        return 2
    config = KtrmnlConfig(
        args.config,
        defaults={
            "local_image_dir": str(Path(os.environ["KTRMNL2_USERSTORE"]) / "images"),
        },
    )
    if args.mode:
        config.set("content_source", args.mode, persist=False)
    if args.rotation is not None:
        config.set("rotation", args.rotation, persist=False)
    os.environ["QT_QUICK_BACKEND"] = "software"
    QGuiApplication.setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)
    qt_args = ["ktrmnl2"]
    if os.environ.get("QT_QPA_PLATFORM") == "xcb":
        from k2.adapters.kindle_x11 import grayscale_visual

        qt_args += ["-visual", grayscale_visual()]
    application = QApplication(qt_args)
    application.setApplicationName("ktrmnl2")
    application.setOrganizationName("k2")
    if application.primaryScreen() is None:
        LOGGER.error("Qt could not open the e-reader display")
        return 2
    screen = application.primaryScreen().size()
    translator = TranslationManager(config, parent=application)
    try:
        device = EreaderClient()
    except (OSError, RuntimeError) as error:
        LOGGER.error("e-reader HAL initialization failed: %s", error)
        return 2
    display = StockDisplayBackend()
    wifi = WifiManager(config, device, application)
    content = ContentController(
        config,
        device,
        wifi=wifi,
        cache_dir=config.path.parent / "cache",
        parent=application,
    )
    controller = KtrmnlController(
        config=config,
        hal=device,
        wifi=wifi,
        content=content,
        display=display,
        menu_path=RESOURCE_ROOT / "menu.json",
        initial_first_run=not config.setup_complete,
        translator=translator,
        parent=application,
    )
    input_backend = InputBridge(
        device,
        application,
        exclusive_buttons=application.platformName() in {"ereader", "kobo"},
    )
    push_server = PushWebServer(
        config,
        controller,
        wifi,
        firewall=PushFirewall(device.wifi_interface),
    )
    runtime = ApplicationRuntime(
        application,
        ApplicationDependencies(
            config=config,
            device=device,
            wifi=wifi,
            content=content,
            display=display,
            input_backend=input_backend,
            controller=controller,
            push_server=push_server,
        ),
        ApplicationOptions(
            qml_path=RESOURCE_ROOT / "qml" / "Main.qml",
            display_size=(screen.width(), screen.height()),
            device=True,
            family=args.family,
            initial_menu_open=bool(args.menu),
            initial_menu_page=args.menu_page,
            context_properties={"i18n": translator},
        ),
    )
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda _signum, _frame: application.quit())
    signal_timer = QTimer(application)
    signal_timer.setInterval(100)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start()
    if not runtime.load():
        runtime.close()
        return 1
    window = runtime.engine.rootObjects()[0]
    power = StockPower(
        config, device, wifi, content, controller, display, window, application
    )
    application.aboutToQuit.disconnect(runtime.close)
    session = DisplaySession(runtime, power, window, input_backend, session_directory)
    application.aboutToQuit.connect(session.close)
    if not session.sync():
        session.close()
        return 1
    return int(application.exec_())
