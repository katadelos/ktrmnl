from __future__ import annotations

import base64
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PyQt5.QtCore import (
    QCoreApplication,
    QEventLoop,
    QObject,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)

from ktrmnl2.app.controller import KtrmnlController
from ktrmnl2.config.store import KtrmnlConfig
from ktrmnl2.content.controller import (
    SPECIAL_FUNCTION_SLEEP_SECONDS,
    ContentController,
    ContentState,
    RefreshDeadline,
)
from ktrmnl2.content.http import (
    DisplayFetchFailure,
    DisplayFetchResult,
    display_headers,
)
from ktrmnl2.content.inbox import PushInbox
from ktrmnl2.device.power import PowerState, SleepAttempt, StockPower
from ktrmnl2.i18n import TranslationManager

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _NoopNetwork(QObject):
    resultReady = pyqtSignal(int, object)

    def fetch_display(self, *_args: object) -> None:
        raise AssertionError("empty base_url must not start an HTTP request")

    def close(self) -> None:
        pass


class _DeferredNetwork(QObject):
    resultReady = pyqtSignal(int, object)

    def __init__(self):
        super().__init__()
        self.requests = []
        self.connection_resets = 0

    def fetch_display(self, generation: int, *args: object) -> None:
        self.requests.append((generation, args))

    def reset_connections(self) -> None:
        self.connection_resets += 1

    def close(self) -> None:
        pass


class _Device:
    def __init__(self):
        self.suspend_durations = []
        self.radio_power_events = []
        self.battery_available = True
        self.battery_percent = 80

    def display_size(self):
        return (800, 600)

    def battery(self):
        return {
            "available": self.battery_available,
            "percent": self.battery_percent,
            "status": "Discharging",
            "health": "Good",
            "present": True,
            "online": False,
        }

    def mac_address(self):
        return "00:11:22:33:44:55"

    def device(self):
        return {"model": "Test reader"}

    def reader_name(self):
        return "test"

    def radio(self):
        return {"available": True, "powered": True, "operational": True}

    def set_radio_powered(self, powered: bool):
        self.radio_power_events.append(bool(powered))

    def suspend_for(self, seconds: int):
        self.suspend_durations.append(seconds)

    def suspend(self):
        self.suspend_durations.append(None)


class _Wifi(QObject):
    statusChanged = pyqtSignal()
    stateChanged = pyqtSignal()
    connectedChanged = pyqtSignal()

    connected = True
    connecting = False
    connectedSsid = ""
    statusText = "ready"
    operation_busy = False

    def __init__(self):
        super().__init__()
        self.connected = True
        self.poll_resumes = []

    def pause_polling(self):
        pass

    def resume_polling(self, *, after_sleep=False):
        self.poll_resumes.append(after_sleep)
        if after_sleep:
            self.connected = False
            self.connectedChanged.emit()

    def close(self):
        pass


class _Display:
    def __init__(self):
        self.inverted = False
        self.refresh_waits = 0
        self.interactive_modes = []

    def set_night_mode(self, enabled: bool):
        self.inverted = bool(enabled)

    def set_rotation(self, _rotation: int):
        pass

    def full_refresh(self):
        pass

    def transition_refresh(self, inverted=None):
        if inverted is not None:
            self.inverted = bool(inverted)

    def set_interactive_mode(self, active: bool):
        self.interactive_modes.append(bool(active))

    def wait_for_refresh(self):
        self.refresh_waits += 1


class _Window(QObject):
    activeChanged = pyqtSignal()
    visibleChanged = pyqtSignal()

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.opened_menus = []

    def isVisible(self):
        return True

    def isActive(self):
        return True

    @pyqtSlot("QVariant")
    def openMenu(self, page):
        self.opened_menus.append(page)
        self.controller.setUiState("menu")


class PushStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def test_backend_choice_is_capability_scoped_and_applies_next_launch(self) -> None:
        for available in (False, True):
            with (
                self.subTest(available=available),
                tempfile.TemporaryDirectory() as temporary,
                patch.dict(
                    os.environ,
                    {
                        "KTRMNL2_X11_AVAILABLE": "1" if available else "0",
                        "QT_QPA_PLATFORM": "xcb",
                    },
                ),
            ):
                root = Path(temporary)
                config = KtrmnlConfig(root / "config.json")
                device, wifi = _Device(), _Wifi()
                content = ContentController(
                    config,
                    device,
                    wifi=wifi,
                    network_client=_NoopNetwork(),
                    cache_dir=root / "cache",
                )
                controller = KtrmnlController(
                    config,
                    device,
                    wifi,
                    content,
                    _Display(),
                    Path(__file__).resolve().parent.parent / "menu.json",
                )
                try:
                    controller.openMenuPage("display")
                    items = {item["id"]: item for item in controller.menuItems}
                    self.assertEqual("setting-qt-backend" in items, available)
                    if available:
                        self.assertEqual(
                            [
                                choice["value"]
                                for choice in items["setting-qt-backend"]["choices"]
                                if choice["selected"]
                            ],
                            ["x11"],
                        )
                    with patch.object(content, "reloadConfig") as reload_content:
                        self.assertEqual(
                            controller.applySetting(
                                "setting-qt-backend", "framebuffer"
                            ),
                            available,
                        )
                        reload_content.assert_not_called()
                    self.assertEqual(os.environ["QT_QPA_PLATFORM"], "xcb")
                    self.assertEqual(
                        KtrmnlConfig(config.path).qt_backend,
                        "framebuffer" if available else "auto",
                    )
                finally:
                    controller.close()

    def test_editor_cursor_moves_across_whole_graphemes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = KtrmnlConfig(root / "config.json")
            device, wifi = _Device(), _Wifi()
            content = ContentController(
                config,
                device,
                wifi=wifi,
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config,
                device,
                wifi,
                content,
                _Display(),
                Path(__file__).resolve().parent.parent / "menu.json",
            )
            self.addCleanup(controller.close)
            text = "A😀e\u0301B"
            self.assertEqual(controller.textCursorPosition(text, 6, -1), 5)
            self.assertEqual(controller.textCursorPosition(text, 5, -1), 3)
            self.assertEqual(controller.textCursorPosition(text, 3, -1), 1)
            self.assertEqual(controller.textCursorPosition(text, 1, 1), 3)
            self.assertEqual(controller.textCursorPosition(text, 3, 1), 5)
            self.assertEqual(controller.textCursorPosition(text, 0, -1), 0)
            self.assertEqual(controller.textCursorPosition(text, 6, 1), 6)

    def _ready_power(self, refresh_seconds=60, mode="trmnl", suspended=True):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        image = root / "display.png"
        image.write_bytes(PNG_1X1)
        config = KtrmnlConfig(
            root / "config.json",
            defaults={
                "base_url": "http://example.test",
                "api_key": "token",
                "local_image_dir": str(root),
            },
        )
        network, wifi, device, display = (
            _DeferredNetwork(),
            _Wifi(),
            _Device(),
            _Display(),
        )
        content = ContentController(
            config, device, wifi=wifi, network_client=network, cache_dir=root / "cache"
        )
        controller = KtrmnlController(
            config,
            device,
            wifi,
            content,
            display,
            Path(__file__).resolve().parent.parent / "menu.json",
        )
        self.addCleanup(controller.close)
        network.resultReady.emit(
            network.requests[0][0], DisplayFetchResult(image, refresh_seconds, "", 1, 1)
        )
        if mode != "trmnl":
            content.setMode(mode)
        window = _Window(controller)
        power = StockPower(config, device, wifi, content, controller, display, window)
        self.addCleanup(power.close)
        if suspended:
            power._attempt = SleepAttempt(
                False, 135.0, refresh=content.pause_refresh(), paused_at=100.0
            )
            power._transition(PowerState.SUSPENDING)
        clock = patch("ktrmnl2.device.power.time.monotonic", return_value=100.0)
        clock.start()
        self.addCleanup(clock.stop)
        return power, content, controller, wifi, network, window

    def test_suspend_drains_wifi_and_cancellation_restores_polling(self):
        power, content, controller, wifi, _network, _window = self._ready_power(
            suspended=False
        )
        wifi.operation_busy = True
        power._automatic_suspend()
        self.assertEqual(power.state, PowerState.DRAINING)
        self.assertEqual(content.state, ContentState.SCHEDULED)
        self.assertFalse(power.suspending)
        controller.setUiState("menu")
        self.assertEqual(power.state, PowerState.IDLE)
        self.assertEqual(content.state, ContentState.SCHEDULED)
        self.assertEqual(wifi.poll_resumes, [False])
        self.assertIsNone(power._attempt)

    def test_menu_during_display_fence_cancels_suspend(self):
        power, content, controller, wifi, _network, _window = self._ready_power(
            suspended=False
        )
        with (
            patch.object(
                power.display,
                "wait_for_refresh",
                side_effect=lambda: controller.setUiState("menu"),
            ),
            patch.object(power._executor, "submit") as submit,
        ):
            power._automatic_suspend()
        submit.assert_not_called()
        self.assertEqual(power.state, PowerState.IDLE)
        self.assertEqual(content.state, ContentState.SCHEDULED)
        self.assertEqual(wifi.poll_resumes, [False])

    def test_modal_policy_blocks_sleep_and_closed_controller_stays_closed(self):
        power, _content, controller, _wifi, _network, _window = self._ready_power(
            suspended=False
        )
        controller.setUiState("modal")
        self.assertFalse(controller.sleepReady)
        self.assertEqual(power.state, PowerState.IDLE)
        self.assertFalse(controller.handleInput("menu"))
        controller.setUiState("content")
        self.assertTrue(controller.sleepReady)
        self.assertEqual(power.state, PowerState.SETTLING)
        controller.close()
        controller.setUiState("content")
        self.assertFalse(controller.sleepReady)

    def test_suspend_blocker_keeps_refresh_deadline_and_enters_cooldown(self):
        power, content, _controller, wifi, _network, _window = self._ready_power(
            suspended=False
        )
        wifi.operation_busy = True
        power._automatic_suspend()
        with patch("ktrmnl2.device.power.time.monotonic", return_value=106.0):
            power._drain_network()
            self.assertEqual(power.state, PowerState.COOLDOWN)
            self.assertTrue(power._retry.isActive())
        self.assertEqual(content.state, ContentState.SCHEDULED)
        self.assertTrue(content._timer.isActive())
        self.assertFalse(power.suspending)
        self.assertEqual(wifi.poll_resumes, [False])

    def test_suspend_hands_deadline_back_after_worker_completion(self):
        power, content, _controller, _wifi, network, _window = self._ready_power(
            suspended=False
        )
        activity = []
        power.activityChanged.connect(lambda: activity.append(power.suspending))
        with (
            patch.object(
                power.hal,
                "suspend_status",
                create=True,
                return_value={
                    "available": True,
                    "max_sleep_seconds": 65535,
                },
            ),
            patch.object(
                power.hal,
                "suspend_for",
                return_value={
                    "slept_ms": 60000,
                    "sleep_gap_ms": 60000,
                    "reason": "RTC",
                },
            ) as suspend,
        ):
            power._automatic_suspend()
            self.assertEqual(power.state, PowerState.SUSPENDING)
            self.assertEqual(content.state, ContentState.PAUSED)
            loop = QEventLoop()
            content.busyChanged.connect(loop.quit)
            QTimer.singleShot(1000, loop.quit)
            loop.exec_()
            content.busyChanged.disconnect(loop.quit)
            self.assertEqual(suspend.call_count, 1)
        self.assertEqual(activity, [True, False])
        self.assertEqual(power.state, PowerState.IDLE)
        self.assertEqual(content.state, ContentState.WAITING_NETWORK)
        self.assertEqual(len(network.requests), 1)
        self.assertEqual(power.display.refresh_waits, 1)

    def test_refresh_tokens_cannot_be_copied_or_reused(self):
        power, content, _controller, _wifi, network, _window = self._ready_power()
        token = power._attempt.refresh
        self.assertFalse(
            content.resume_refresh(
                RefreshDeadline(token.generation, token.remaining_ms)
            )
        )
        self.assertTrue(content.resume_refresh(token, refresh=True))
        self.assertFalse(content.resume_refresh(token, refresh=True))
        self.assertEqual(content.state, ContentState.FETCHING)
        self.assertEqual(len(network.requests), 2)
        self.assertTrue(power._attempt.cancel.is_set())

    def test_closed_content_ignores_requests_and_late_completions(self):
        _power, content, _controller, wifi, network, _window = self._ready_power(
            suspended=False
        )
        content.refresh()
        generation = network.requests[-1][0]
        revision = content.imageRevision
        content.close()
        content.refresh()
        content.setMode("local_images")
        content.reloadConfig()
        wifi.connectedChanged.emit()
        network.resultReady.emit(
            generation, DisplayFetchFailure("offline", "late reply")
        )
        self.assertEqual(content.state, ContentState.CLOSED)
        self.assertFalse(content.busy)
        self.assertFalse(content._timer.isActive())
        self.assertFalse(content._network_ready_timer.isActive())
        self.assertEqual(content.imageRevision, revision)
        self.assertEqual(len(network.requests), 2)

    def test_rtc_refresh_waits_for_fresh_wifi_and_runs_once(self):
        power, content, controller, wifi, network, _window = self._ready_power()
        power._complete(
            power._attempt,
            {"slept_ms": 60000, "sleep_gap_ms": 60000, "reason": "RTC"},
            None,
        )
        self.assertEqual(network.connection_resets, 1)
        self.assertEqual(content.state, ContentState.WAITING_NETWORK)
        self.assertFalse(power.suspending)
        self.assertFalse(wifi.connected)
        self.assertEqual(len(network.requests), 1)
        controller.setUiState("menu")
        self.assertEqual(content.state, ContentState.WAITING_NETWORK)
        wifi.connected = True
        wifi.connectedChanged.emit()
        wifi.connectedChanged.emit()
        self.application.processEvents()
        self.assertEqual(len(network.requests), 2)
        self.assertEqual(power.state, PowerState.IDLE)
        self.assertIsNone(content._paused_refresh)
        self.assertFalse(power._settle.isActive())

    def test_wake_network_timeout_restores_retry_without_immediate_http(self):
        power, content, _controller, wifi, network, _window = self._ready_power()
        power._complete(
            power._attempt,
            {"slept_ms": 60000, "sleep_gap_ms": 60000, "reason": "RTC"},
            None,
        )
        with patch("ktrmnl2.content.controller.time.monotonic", return_value=131.0):
            content._poll_network_ready()
        self.assertEqual(len(network.requests), 1)
        self.assertTrue(content._timer.isActive())
        self.assertIsNone(content._paused_refresh)
        self.assertIn("Wi-Fi did not become ready", content.status)
        self.assertEqual(content.state, ContentState.SCHEDULED)
        wifi.connected = True
        wifi.connectedChanged.emit()
        self.application.processEvents()
        self.assertEqual(len(network.requests), 2)

    def test_mode_change_cancels_the_post_wake_network_wait(self):
        power, content, _controller, wifi, network, _window = self._ready_power()
        power._complete(
            power._attempt,
            {"slept_ms": 60000, "sleep_gap_ms": 60000, "reason": "RTC"},
            None,
        )
        content.setMode("local_images")
        revision = content.imageRevision
        self.assertEqual(power.state, PowerState.SETTLING)
        self.assertTrue(content._timer.isActive())
        wifi.connected = True
        wifi.connectedChanged.emit()
        self.application.processEvents()
        self.assertEqual(content.imageRevision, revision)
        self.assertEqual(len(network.requests), 1)

    def test_manual_wake_restores_remaining_time_and_opens_menu(self):
        power, content, _controller, wifi, network, window = self._ready_power()
        remaining = power._attempt.refresh.remaining_ms
        power._attempt.manual = True
        power._complete(
            power._attempt,
            {"slept_ms": 2000, "sleep_gap_ms": 2000, "reason": "POWER"},
            None,
        )
        self.assertEqual(network.connection_resets, 1)
        self.assertEqual(window.opened_menus, ["root"])
        self.assertEqual(len(network.requests), 1)
        self.assertAlmostEqual(
            content._timer.remainingTime(), remaining - 2000, delta=250
        )
        self.assertFalse(wifi.connected)
        self.assertTrue(wifi.poll_resumes[-1])

    def test_suspend_with_ticking_monotonic_does_not_double_count_elapsed(self):
        power, content, _controller, _wifi, _network, _window = self._ready_power()
        remaining = power._attempt.refresh.remaining_ms
        power._attempt.manual = True
        with patch("ktrmnl2.device.power.time.monotonic", return_value=102.0):
            power._complete(
                power._attempt,
                {"slept_ms": 2000, "sleep_gap_ms": 0, "reason": "POWER"},
                None,
            )
        self.assertAlmostEqual(
            content._timer.remainingTime(), remaining - 2000, delta=250
        )

    def test_early_rtc_wake_preserves_a_long_content_deadline(self):
        power, content, _controller, wifi, network, window = self._ready_power(
            refresh_seconds=86400
        )
        remaining = power._attempt.refresh.remaining_ms
        power._complete(
            power._attempt,
            {"slept_ms": 65535000, "sleep_gap_ms": 65535000, "reason": "RTC"},
            None,
        )
        self.assertEqual(len(network.requests), 1)
        self.assertEqual(window.opened_menus, [])
        self.assertEqual(power.state, PowerState.SETTLING)
        self.assertFalse(content._network_ready_timer.isActive())
        self.assertAlmostEqual(
            content._timer.remainingTime(), remaining - 65535000, delta=250
        )
        self.assertTrue(wifi.poll_resumes[-1])

    def test_local_image_rtc_wake_refreshes_without_waiting_for_wifi(self):
        power, content, _controller, wifi, network, _window = self._ready_power(
            mode="local_images"
        )
        revision = content.imageRevision
        power._complete(
            power._attempt,
            {"slept_ms": 60000, "sleep_gap_ms": 60000, "reason": "RTC"},
            None,
        )
        self.assertGreater(content.imageRevision, revision)
        self.assertEqual(power.state, PowerState.SETTLING)
        self.assertFalse(content._network_ready_timer.isActive())
        self.assertFalse(wifi.connected)
        self.assertEqual(len(network.requests), 1)

    def test_interrupt_sequence_handoff_is_thread_safe(self) -> None:
        inbox = PushInbox()

        def publish(index: int):
            return inbox.publish_interrupt(f"message-{index}", title=f"title-{index}")

        with ThreadPoolExecutor(max_workers=8) as executor:
            items = list(executor.map(publish, range(40)))
        self.assertEqual(sorted(item.sequence for item in items), list(range(1, 41)))
        self.assertEqual(inbox.latest_interrupt().sequence, 40)
        with self.assertRaisesRegex(ValueError, "positive"):
            inbox.publish_interrupt("bad", expires_in=0)
        with self.assertRaisesRegex(ValueError, "empty"):
            inbox.publish_interrupt("  ")

    def test_request_dimensions_follow_logical_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = KtrmnlConfig(
                Path(temporary) / "config.json", defaults={"base_url": ""}
            )
            device = _Device()
            headers = display_headers(config, device, None)
            self.assertEqual(
                (headers["png-width"], headers["png-height"]), ("800", "600")
            )
            config.set("rotation", 90, persist=False)
            headers = display_headers(config, device, None)
            self.assertEqual(
                (headers["png-width"], headers["png-height"]), ("600", "800")
            )

    def test_completion_from_old_mode_cannot_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "old.png"
            image_path.write_bytes(PNG_1X1)
            config = KtrmnlConfig(
                root / "config.json",
                defaults={
                    "base_url": "http://127.0.0.1:9",
                    "api_key": "token",
                    "local_image_dir": str(root / "empty"),
                },
            )
            network = _DeferredNetwork()
            content = ContentController(
                config,
                _Device(),
                network_client=network,
                cache_dir=root / "cache",
            )
            self.addCleanup(content.close)
            content.start()
            self.assertEqual(len(network.requests), 1)
            old_generation = network.requests[0][0]
            content.setMode("local_images")
            network.resultReady.emit(
                old_generation,
                DisplayFetchResult(image_path, 60, "", 1, 1),
            )
            self.assertEqual(content.mode, "local_images")
            self.assertFalse(content.hasContent)

    def test_server_sleep_sets_next_refresh_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "display.png"
            image_path.write_bytes(PNG_1X1)
            config = KtrmnlConfig(
                root / "config.json",
                defaults={"base_url": "http://127.0.0.1:9", "api_key": "token"},
            )
            network = _DeferredNetwork()
            content = ContentController(
                config,
                _Device(),
                network_client=network,
                cache_dir=root / "cache",
            )
            self.addCleanup(content.close)
            content.start()
            first_generation = network.requests[-1][0]
            network.resultReady.emit(
                first_generation,
                DisplayFetchResult(image_path, 37, "sleep", 1, 1),
            )
            self.assertEqual(
                content._timer.interval(), SPECIAL_FUNCTION_SLEEP_SECONDS * 1000
            )

            content.setMode("interrupt")
            interrupt_generation = network.requests[-1][0]
            network.resultReady.emit(
                interrupt_generation,
                DisplayFetchResult(image_path, 41, "sleep", 1, 1),
            )
            self.assertEqual(content._timer.interval(), 41000)

    def test_startup_request_waits_for_wifi_and_recovers_on_late_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = KtrmnlConfig(
                root / "config.json",
                defaults={
                    "base_url": "https://example.test",
                    "api_key": "token",
                },
            )
            wifi = _Wifi()
            wifi.connected = False
            network = _DeferredNetwork()
            content = ContentController(
                config,
                _Device(),
                wifi=wifi,
                network_client=network,
                cache_dir=root / "cache",
            )
            self.addCleanup(content.close)

            content.start()
            self.assertEqual(network.requests, [])
            self.assertEqual(content.presentationState, "loading")

            wifi.connected = True
            wifi.connectedChanged.emit()
            self.assertEqual(len(network.requests), 1)
            generation = network.requests[0][0]

            wifi.connected = False
            wifi.connectedChanged.emit()
            network.resultReady.emit(
                generation,
                DisplayFetchFailure("offline", "TRMNL server is unreachable"),
            )
            self.assertEqual(content.presentationState, "offline")

            wifi.connected = True
            wifi.connectedChanged.emit()
            loop = QEventLoop()
            QTimer.singleShot(5, loop.quit)
            loop.exec_()
            self.assertEqual(len(network.requests), 2)
            self.assertEqual(content.presentationState, "loading")

    def test_queued_interrupt_is_consumed_on_mode_start_and_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = KtrmnlConfig(
                root / "config.json",
                defaults={
                    "base_url": "",
                },
            )
            content = ContentController(
                config,
                _Device(),
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
            )
            self.addCleanup(content.close)
            content.start()
            previous_status = content.status
            content.publishInterrupt(
                "queued before mode change",
                title="Queued",
                expires_in=0.05,
                invert=True,
            )
            self.assertFalse(content.interruptActive)
            content.setMode("interrupt")
            self.assertTrue(content.interruptActive)
            self.assertEqual(content.interruptTitle, "Queued")
            self.assertTrue(content.interruptInverted)

            content.publishInterrupt("newer", title="Newest", expires_in=0.05)
            self.assertEqual(content.interruptTitle, "Newest")
            self.assertFalse(content.interruptInverted)

            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec_()
            self.assertFalse(content.interruptActive)
            self.assertEqual(content.status, previous_status)

    def test_http_push_displays_only_the_latest_transient_image(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = KtrmnlConfig(
                root / "config.json",
                defaults={
                    "base_url": "",
                    "content_source": "http_push",
                },
            )
            content = ContentController(
                config,
                _Device(),
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
                push_runtime_dir=root / "runtime",
            )
            content.start()
            item = content.publishPushImage(PNG_1X1, filename="tiny.png")
            self.assertEqual(item.sequence, 1)
            self.assertTrue(content.hasContent)
            self.assertEqual(content.presentationState, "ready")
            transient = list((root / "runtime").glob("push-current-*.png"))
            self.assertEqual(len(transient), 1)
            content.close()
            self.assertFalse(transient[0].exists())

    def test_low_battery_warning_is_dismissed_until_charge_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            menu_path = root / "menu.json"
            menu_path.write_text('{"pages":{"root":[]}}', encoding="utf-8")
            config = KtrmnlConfig(root / "config.json", defaults={"base_url": ""})
            device = _Device()
            wifi = _Wifi()
            content = ContentController(
                config,
                device,
                wifi=wifi,
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config, device, wifi, content, _Display(), menu_path
            )
            self.addCleanup(controller.close)

            device.battery_percent = 10
            controller.refreshDeviceStatus()
            self.assertTrue(controller.lowBatteryWarningActive)

            self.assertTrue(controller.dismissLowBatteryWarning())
            device.battery_percent = 9
            controller.refreshDeviceStatus()
            self.assertFalse(controller.lowBatteryWarningActive)

            device.battery_percent = 16
            controller.refreshDeviceStatus()
            device.battery_percent = 10
            controller.refreshDeviceStatus()
            self.assertTrue(controller.lowBatteryWarningActive)

    def test_interrupt_waits_behind_open_menu(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            menu_path = root / "menu.json"
            menu_path.write_text('{"pages":{"root":[]}}', encoding="utf-8")
            config = KtrmnlConfig(
                root / "config.json",
                defaults={"base_url": "", "content_source": "interrupt"},
            )
            device = _Device()
            wifi = _Wifi()
            content = ContentController(
                config,
                device,
                wifi=wifi,
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config, device, wifi, content, _Display(), menu_path
            )
            self.addCleanup(controller.close)

            controller.setUiState("menu")
            content.publishInterrupt("Queued behind menu", expires_in=30)

            self.assertTrue(content.interruptActive)
            self.assertFalse(controller.handleInput("down"))
            self.assertTrue(content.interruptActive)
            controller.setUiState("content")
            self.assertTrue(controller.handleInput("down"))
            self.assertFalse(content.interruptActive)

    def test_content_settings_follow_mode_and_keep_their_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            menu_path = root / "menu.json"
            menu_path.write_text(
                '{"pages":{"content":['
                '{"id":"setting-content-source"},'
                '{"id":"setting-base-url"},'
                '{"id":"setting-api-key"},'
                '{"id":"setting-local-directory"},'
                '{"id":"setting-local-refresh"},'
                '{"id":"setting-local-shuffle"}]}}',
                encoding="utf-8",
            )
            config = KtrmnlConfig(
                root / "config.json",
                defaults={
                    "base_url": "https://example.test",
                    "api_key": "stored-token",
                    "content_source": "trmnl",
                    "local_image_dir": str(root / "saved-images"),
                    "local_image_refresh_rate": 321,
                    "local_image_shuffle": False,
                },
            )
            content = ContentController(
                config,
                _Device(),
                wifi=_Wifi(),
                network_client=_DeferredNetwork(),
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config, _Device(), _Wifi(), content, _Display(), menu_path
            )
            self.addCleanup(controller.close)

            controller.openMenuPage("content")
            self.assertEqual(
                [item["id"] for item in controller.menuItems],
                ["setting-content-source", "setting-base-url", "setting-api-key"],
            )
            self.assertFalse(controller.applySetting("setting-local-refresh", 99))
            self.assertEqual(config.local_image_refresh_rate, 321)

            self.assertTrue(
                controller.applySetting("setting-content-source", "local_images")
            )
            self.assertEqual(
                [item["id"] for item in controller.menuItems],
                [
                    "setting-content-source",
                    "setting-local-directory",
                    "setting-local-refresh",
                    "setting-local-shuffle",
                ],
            )
            self.assertEqual(config.local_image_dir, root / "saved-images")
            self.assertEqual(config.local_image_refresh_rate, 321)
            self.assertFalse(config.local_image_shuffle)
            self.assertEqual(controller.settingDefinition("setting-base-url"), {})
            self.assertFalse(controller.applySetting("setting-api-key", "replacement"))

            self.assertTrue(
                controller.applySetting("setting-content-source", "interrupt")
            )
            self.assertEqual(
                [item["id"] for item in controller.menuItems],
                ["setting-content-source", "setting-base-url", "setting-api-key"],
            )
            self.assertTrue(
                controller.applySetting("setting-content-source", "http_push")
            )
            self.assertEqual(
                [item["id"] for item in controller.menuItems],
                ["setting-content-source"],
            )
            self.assertEqual(config.base_url, "https://example.test")
            self.assertEqual(config.api_key, "stored-token")
            self.assertEqual(config.local_image_dir, root / "saved-images")
            self.assertEqual(config.local_image_refresh_rate, 321)
            self.assertFalse(config.local_image_shuffle)

    def test_numeric_editors_use_localized_bounds_and_preserve_invalid_values(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = KtrmnlConfig(
                root / "config.json",
                defaults={
                    "base_url": "",
                    "content_source": "local_images",
                    "local_image_dir": str(root / "images"),
                    "local_image_refresh_rate": 321,
                },
            )
            translator = TranslationManager(config)
            content = ContentController(
                config,
                _Device(),
                wifi=_Wifi(),
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config,
                _Device(),
                _Wifi(),
                content,
                _Display(),
                Path(__file__).resolve().parents[1] / "menu.json",
                translator=translator,
            )
            self.addCleanup(controller.close)
            controller.openMenuPage("content")
            definition = controller.settingDefinition("setting-local-refresh")
            self.assertEqual(definition["editorTitle"], "Refresh interval")
            self.assertEqual(definition["unitText"], "seconds")
            self.assertIn("86,400", definition["rangeHint"])
            for invalid, message in (
                ("abc", "Enter a whole number."),
                ("0", "Enter 1–86,400 seconds."),
                ("86401", "Enter 1–86,400 seconds."),
            ):
                with self.subTest(invalid=invalid):
                    self.assertFalse(
                        controller.applySetting("setting-local-refresh", invalid)
                    )
                    self.assertEqual(controller.settingError, message)
                    self.assertEqual(config.local_image_refresh_rate, 321)
            self.assertTrue(controller.applySetting("setting-local-refresh", "86400"))
            self.assertEqual(KtrmnlConfig(config.path).local_image_refresh_rate, 86400)
            self.assertEqual(controller.settingError, "")
            self.assertFalse(
                controller.applySetting("setting-battery-threshold", "101")
            )
            self.assertEqual(controller.settingError, "Enter 1–100%.")

            translator.setLanguage("de", persist=False)
            definition = controller.settingDefinition("setting-local-refresh")
            self.assertEqual(definition["unitText"], "Sekunden")
            self.assertIn("86.400", definition["rangeHint"])
            self.assertFalse(controller.applySetting("setting-local-refresh", "0"))
            self.assertIn("86.400", controller.settingError)
            self.assertIn("Sekunden", controller.settingError)
            self.assertNotIn("local_image_refresh_rate", controller.settingError)

    def test_contextual_menu_items_are_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            menu_path = root / "menu.json"
            menu_path.write_text(
                '{"pages":{"root":['
                '{"id":"status","label":"Status"},'
                '{"id":"exit","label":"Exit ktrmnl"}]}}',
                encoding="utf-8",
            )

            def menu_items(show_exit_item: bool):
                config = KtrmnlConfig(
                    root / ("simulator.json" if show_exit_item else "device.json"),
                    defaults={"base_url": ""},
                )
                device = _Device()
                wifi = _Wifi()
                content = ContentController(
                    config,
                    device,
                    wifi=wifi,
                    network_client=_NoopNetwork(),
                    cache_dir=root / "cache",
                )
                controller = KtrmnlController(
                    config,
                    device,
                    wifi,
                    content,
                    _Display(),
                    menu_path,
                    show_exit_item=show_exit_item,
                )
                try:
                    return [item["id"] for item in controller.menuItems]
                finally:
                    controller.close()

            self.assertEqual(menu_items(False), ["status"])
            self.assertEqual(menu_items(True), ["status", "exit"])

    def test_first_content_fetch_backfills_id_and_enables_system_action(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image_path = root / "display.png"
            image_path.write_bytes(PNG_1X1)
            menu_path = root / "menu.json"
            menu_path.write_text(
                '{"pages":{"system":['
                '{"id":"show-trmnl-id","label":"Show TRMNL ID"}]}}',
                encoding="utf-8",
            )
            config = KtrmnlConfig(
                root / "config.json",
                defaults={"base_url": "https://example.test", "api_key": "token"},
            )
            device = _Device()
            wifi = _Wifi()
            network = _DeferredNetwork()
            content = ContentController(
                config,
                device,
                wifi=wifi,
                network_client=network,
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config, device, wifi, content, _Display(), menu_path
            )
            self.addCleanup(controller.close)

            controller.openMenuPage("system")
            self.assertEqual(controller.menuItems, [])
            generation = network.requests[-1][0]
            network.resultReady.emit(
                generation,
                DisplayFetchResult(image_path, 60, "", 1, 1, friendly_id="A3l1nT"),
            )

            self.assertEqual(config.friendly_id, "A3l1nT")
            self.assertEqual(controller.friendlyId, "A3l1nT")
            self.assertEqual(
                [item["id"] for item in controller.menuItems],
                ["show-trmnl-id"],
            )

    def test_dashboard_name_changes_without_modifying_firmware_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            menu_path = root / "menu.json"
            menu_path.write_text(
                '{"pages":{"system":['
                '{"id":"setting-device-name","label":"Device name"}]}}',
                encoding="utf-8",
            )
            config = KtrmnlConfig(root / "config.json", defaults={"base_url": ""})
            device = _Device()
            wifi = _Wifi()
            content = ContentController(
                config,
                device,
                wifi=wifi,
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config,
                device,
                wifi,
                content,
                _Display(),
                menu_path,
            )
            self.addCleanup(controller.close)

            controller.openMenuPage("system")
            self.assertEqual(controller.menuItems[0]["detail"], "ktrmnl")
            self.assertTrue(
                controller.applySetting("setting-device-name", "Kitchen Panel")
            )
            self.assertEqual(config.device_name, "Kitchen Panel")
            self.assertEqual(controller.deviceName, "Kitchen Panel")
            self.assertFalse(
                controller.applySetting("setting-device-name", "invalid\nname")
            )
            self.assertEqual(config.device_name, "Kitchen Panel")

    def test_touch_setup_completes_without_network_or_api_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            menu_path = root / "menu.json"
            menu_path.write_text('{"pages":{"root":[]}}', encoding="utf-8")
            config = KtrmnlConfig(root / "config.json", defaults={"base_url": ""})
            device, wifi = _Device(), _Wifi()
            wifi.connected = False
            content = ContentController(
                config,
                device,
                wifi=wifi,
                network_client=_NoopNetwork(),
                cache_dir=root / "cache",
            )
            controller = KtrmnlController(
                config,
                device,
                wifi,
                content,
                _Display(),
                menu_path,
                initial_first_run=True,
            )
            self.addCleanup(controller.close)
            self.assertEqual(config.rotation, 0)
            self.assertTrue(controller.finishFirstTimeSetup())
            self.assertFalse(controller.firstRun)
            self.assertTrue(KtrmnlConfig(config.path).setup_complete)
            self.assertEqual(device.radio_power_events, [])
            self.assertEqual(device.suspend_durations, [])


if __name__ == "__main__":
    unittest.main()
