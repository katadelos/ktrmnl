from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional, Sequence

from PyQt5.QtCore import (
    Qt,
    QTimer,
)
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import QApplication

from ktrmnl2.app.controller import KtrmnlController
from ktrmnl2.app.runtime import (
    ApplicationDependencies,
    ApplicationOptions,
    ApplicationRuntime,
)
from ktrmnl2.config.store import KtrmnlConfig
from ktrmnl2.content.controller import ContentController
from ktrmnl2.i18n import TranslationManager
from ktrmnl2.log import configure as configure_logging
from ktrmnl2.network.push import PushWebServer
from ktrmnl2.resources import RESOURCE_ROOT
from ktrmnl2.simulator.backends import (
    SimulatorDevice,
    SimulatorDisplayBackend,
    SimulatorInputBackend,
)
from ktrmnl2.simulator.backends import (
    logical_size as display_size_for_rotation,
)
from ktrmnl2.simulator.controls import SimulatorControls
from ktrmnl2.simulator.headless import HeadlessController
from ktrmnl2.simulator.options import parse_args
from ktrmnl2.simulator.preview import (
    QmlWatcher,
    ScreenshotController,
    write_scenario_content,
)
from ktrmnl2.simulator.wifi import SimulatorWifiManager

LOGGER = logging.getLogger("ktrmnl2.simulator")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.headless or args.screenshot:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    configure_logging(runtime="simulator")

    config_path = Path(args.config)
    config = KtrmnlConfig(
        config_path,
        defaults={
            "base_url": "",
            "local_image_dir": str(Path.home() / "Pictures" / "ktrmnl2"),
        },
    )
    if args.scenario in {"content", "empty"}:
        config.update(
            {
                "content_source": "local_images",
                "local_image_dir": str(
                    config_path.parent
                    / (
                        "scenario-content"
                        if args.scenario == "content"
                        else "scenario-empty"
                    )
                ),
                "local_image_shuffle": False,
            },
            persist=False,
        )
    elif args.scenario == "offline":
        config.update({"content_source": "trmnl", "base_url": ""}, persist=False)
    elif args.scenario in {"loading", "error"}:
        config.set("content_source", "trmnl", persist=False)
    elif args.scenario == "interrupt":
        config.set("content_source", "interrupt", persist=False)
    if args.mode:
        config.set("content_source", args.mode, persist=False)
    if args.rotation is not None:
        config.set("rotation", args.rotation, persist=False)
    native_size = (
        (args.width, args.height) if args.width is not None else args.display_size
    )
    logical_size = display_size_for_rotation(native_size, config.rotation)

    LOGGER.info(
        "starting host runtime config=%s mode=%s size=%sx%s headless=%s screenshot=%s",
        config.path,
        config.content_source,
        logical_size[0],
        logical_size[1],
        bool(args.headless),
        args.screenshot or "none",
    )
    QGuiApplication.setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)
    application = QApplication(sys.argv[:1])
    application.setApplicationName("ktrmnl2-sim")
    application.setOrganizationName("ktrmnl2")
    translator = TranslationManager(config, parent=application)
    if args.watch or args.headless or args.screenshot:
        application.setQuitOnLastWindowClosed(False)
    scenario_image_path: Optional[Path] = None
    if args.scenario == "content":
        scenario_image_path = Path(config.local_image_dir) / "exact-viewport.png"
    elif args.scenario == "interrupt":
        scenario_image_path = (
            config.path.parent
            / "scenario-interrupt"
            / f"underlying-{logical_size[0]}x{logical_size[1]}.png"
        )
    if scenario_image_path is not None:
        write_scenario_content(scenario_image_path, logical_size)

    device = SimulatorDevice(
        display_size=native_size,
        battery_percent=args.battery_percent,
        battery_status=args.battery_status,
        radio_powered=not args.radio_off,
        board=args.fake_board,
        model=args.fake_model,
    )
    display = SimulatorDisplayBackend(native_size, config.rotation, application)
    wifi = SimulatorWifiManager(config, device, args.wifi_ssid, application)
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
        show_exit_item=True,
        initial_first_run=bool(args.first_run),
        translator=translator,
        parent=application,
    )
    simulator_controls = SimulatorControls(
        config, device, display, controller, wifi, application
    )
    if args.scenario == "loading":
        content.setExternalStatus("TRMNL content request active.", "loading")
    elif args.scenario == "empty":
        content.setExternalStatus("No local images.", "empty")
    elif args.scenario == "offline":
        content.setExternalStatus("TRMNL server not available.", "offline")
    elif args.scenario == "error":
        content.setExternalStatus("Invalid content response.", "error")
    elif args.scenario == "interrupt":
        # A deterministic prior frame makes the screenshot exercise the real
        # interrupt contract: the popover is transient and the exact TRMNL
        # content beneath it remains mounted and unchanged.
        content._set_image(scenario_image_path, "pixel_exact")
        content.setExternalStatus("Content updated.", "ready")
        content.publishInterrupt(
            "The front door was opened.",
            title="Home alert",
            expires_in=300,
            invert=True,
        )
    input_backend = SimulatorInputBackend(application)
    push_server = PushWebServer(
        config,
        controller,
        wifi,
        host="127.0.0.1",
        public_host="127.0.0.1",
        port=max(1, min(65535, int(args.push_port))),
    )
    screenshot_controller = ScreenshotController(application)
    screenshot_path = ""
    if args.screenshot:
        resolved = args.screenshot.resolve()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(resolved)

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
            qml_path=RESOURCE_ROOT / "qml" / "SimulatorMain.qml",
            display_size=logical_size,
            family=args.family,
            initial_menu_open=bool(args.menu),
            initial_menu_page=args.menu_page,
            context_properties={
                "runtimeIsHeadless": bool(args.headless),
                "runtimeScreenshotPath": screenshot_path,
                "runtimeInitialEditSetting": str(args.edit_setting or ""),
                "i18n": translator,
                "screenshotController": screenshot_controller,
                "simulatorDisplay": display,
                "simulatorControls": simulator_controls,
                "runtimeSimulatorPanelEnabled": bool(args.controls)
                or (not args.headless and not bool(args.screenshot)),
                "runtimeInitialSimulatorPanelOpen": bool(args.controls),
            },
        ),
    )
    if not runtime.load():
        runtime.close()
        return 1

    watcher = None
    if args.watch:
        watcher = QmlWatcher(
            runtime,
            (RESOURCE_ROOT / "qml", RESOURCE_ROOT / "menu.json"),
            application,
        )

    headless_controller = None
    if args.headless and not args.screenshot:
        headless_controller = HeadlessController(
            runtime.engine, controller, content, display, device, application
        )
        QTimer.singleShot(0, headless_controller.ready)

    # Keep Python references alive for the complete Qt event loop.
    application._ktrmnl_watcher = watcher  # type: ignore[attr-defined]
    application._ktrmnl_headless = headless_controller  # type: ignore[attr-defined]
    return int(application.exec_())
