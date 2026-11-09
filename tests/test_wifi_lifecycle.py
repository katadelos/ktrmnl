from __future__ import annotations

import tempfile
import threading
import unittest
from enum import IntEnum
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QCoreApplication, QEventLoop, QTimer

from ktrmnl.config.store import KtrmnlConfig
from ktrmnl.network.wifi import WifiLink, WifiManager, WifiOperation, WifiPolling


class _Security(IntEnum):
    OPEN = 0
    WPA_PSK = 1
    SAE = 2
    ENTERPRISE = 4


class _Device:
    def __init__(self):
        self.status = SimpleNamespace(
            state=SimpleNamespace(name="CONNECTED"),
            ssid="Home",
            address="192.0.2.10",
            signal_dbm=-48,
        )
        self.calls = []
        self.block = threading.Event()
        self.block.set()
        self.fail = False
        self.fail_connect = False
        self.profiles = []
        self.points = [
            SimpleNamespace(ssid="Home", security=_Security.WPA_PSK, signal_dbm=-48)
        ]
        self.security_write = 1 << _Security.WPA_PSK

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get_wifi_status(self):
        self.calls.append("status")
        self.block.wait(1)
        if self.fail:
            raise OSError("stock Wi-Fi unavailable")
        return self.status

    def get_wifi(self):
        return True

    def set_wifi(self, enabled):
        self.calls.append(("power", enabled))

    def wifi_scan(self):
        self.calls.append("scan")
        return self.points

    def wifi_list_networks(self):
        self.calls.append("profiles")
        return list(self.profiles)

    def get_wifi_capabilities(self):
        self.calls.append("capabilities")
        return SimpleNamespace(security_write=self.security_write)

    def wifi_update_network(self, identifier, config):
        self.calls.append(("update", identifier, config))
        return SimpleNamespace(network_id=identifier)

    def wifi_add_network(self, config):
        self.calls.append(("add", config))
        self.profiles.append(
            SimpleNamespace(
                id="new-profile", ssid=config.ssid, security=config.security
            )
        )
        return SimpleNamespace(network_id="new-profile")

    def wifi_connect(self, identifier, **options):
        self.calls.append(("connect", identifier))
        if self.fail_connect:
            raise OSError("Credentials rejected")


class WifiLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        modules = patch.dict(
            "sys.modules",
            {
                "ereader_hal": SimpleNamespace(
                    WifiConfig=SimpleNamespace, WifiSecurity=_Security
                ),
            },
        )
        modules.start()
        self.addCleanup(modules.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.device = _Device()
        self.wifi = WifiManager(
            KtrmnlConfig(Path(self.directory.name) / "config.json"),
            SimpleNamespace(new_device=lambda: self.device),
        )
        self.wait_idle()

    def tearDown(self):
        self.device.block.set()
        self.wifi.close()
        self.directory.cleanup()

    def wait_idle(self):
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(5)
        timer.timeout.connect(
            lambda: loop.quit() if not self.wifi.operation_busy else None
        )
        timer.start()
        QTimer.singleShot(1500, loop.quit)
        loop.exec_()
        timer.stop()
        self.assertFalse(self.wifi.operation_busy)

    def test_paused_polling_rejects_new_operations(self):
        self.wifi.pause_polling()
        self.assertEqual(self.wifi.polling, WifiPolling.PAUSED)
        self.device.calls.clear()
        self.wifi.scan()
        self.wifi.toggleRadio()
        self.wifi._poll_status()
        self.assertEqual(self.device.calls, [])
        self.assertEqual(self.wifi.operation, WifiOperation.IDLE)
        self.wifi.resume_polling()
        self.wait_idle()
        self.assertEqual(self.device.calls, ["status"])

    def test_recovery_timeout_returns_to_normal_polling(self):
        self.device.status = SimpleNamespace(
            state=SimpleNamespace(name="OFF"),
            ssid="",
            address="",
            signal_dbm=0,
        )
        self.wifi.resume_polling(after_sleep=True)
        self.assertEqual(self.wifi.link, WifiLink.CHECKING)
        self.wait_idle()
        self.assertEqual(self.wifi.polling, WifiPolling.RECOVERING)
        self.wifi._finish_recovery()
        self.assertEqual(self.wifi.polling, WifiPolling.NORMAL)
        self.assertEqual(self.wifi._status_timer.interval(), 5000)
        self.assertFalse(self.wifi._recovery_timer.isActive())

    def test_close_rejects_operations_and_late_results(self):
        self.wifi.close()
        self.device.calls.clear()
        self.wifi.scan()
        self.wifi.resume_polling(after_sleep=True)
        self.wifi._operation_finished(WifiOperation.STATUS, self.device.status, None)
        self.assertEqual(self.wifi.polling, WifiPolling.CLOSED)
        self.assertEqual(self.device.calls, [])
        self.assertFalse(self.wifi._status_timer.isActive())
        self.assertFalse(self.wifi._recovery_timer.isActive())

    def test_initial_status_does_not_modify_stock_network(self):
        self.assertTrue(self.wifi.connected)
        self.assertEqual(self.wifi.connectedSsid, "Home")
        self.assertEqual(self.wifi.ipAddress, "192.0.2.10")
        self.assertEqual(self.device.calls, ["status"])

    def test_slow_firmware_call_does_not_block_qt_or_queue_duplicate_status(self):
        self.device.block.clear()
        self.wifi._poll_status()
        self.wifi._poll_status()
        self.assertEqual(self.wifi.operation, WifiOperation.STATUS)
        self.application.processEvents()
        self.device.block.set()
        self.wait_idle()
        self.assertEqual(self.device.calls, ["status", "status"])

    def test_status_failure_clears_stale_connection(self):
        self.device.fail = True
        self.wifi._poll_status()
        self.wait_idle()
        self.assertFalse(self.wifi.available)
        self.assertFalse(self.wifi.connected)
        self.assertEqual(self.wifi.ipAddress, "")
        self.assertIn("stock Wi-Fi unavailable", self.wifi.statusText)

    def test_wake_discards_stale_connection_until_fresh_status(self):
        self.wifi.pause_polling()
        self.device.block.clear()
        self.wifi.resume_polling(after_sleep=True)
        self.assertFalse(self.wifi.connected)
        self.assertEqual(self.wifi.ipAddress, "")
        self.assertEqual(self.wifi._status_timer.interval(), 1000)
        self.assertEqual(self.wifi.polling, WifiPolling.RECOVERING)
        self.assertEqual(self.wifi.link, WifiLink.CHECKING)
        self.device.status = SimpleNamespace(
            state=SimpleNamespace(name="CONNECTING"),
            ssid="Home",
            address="",
            signal_dbm=-48,
        )
        self.device.block.set()
        self.wait_idle()
        self.assertFalse(self.wifi.connected)
        self.device.status = SimpleNamespace(
            state=SimpleNamespace(name="CONNECTED"),
            ssid="Home",
            address="192.0.2.10",
            signal_dbm=-48,
        )
        self.wifi._poll_status()
        self.wait_idle()
        self.assertTrue(self.wifi.connected)
        self.wifi.resume_polling()
        self.wait_idle()
        self.assertEqual(self.wifi._status_timer.interval(), 5000)

    def test_failed_mutation_is_observed_without_replay(self):
        calls = []

        def mutation(device):
            calls.append("mutation")
            raise OSError("result uncertain")

        self.wifi._submit(WifiOperation.CONNECT, mutation)
        self.wait_idle()
        self.assertEqual(calls, ["mutation"])
        self.assertEqual(self.device.calls, ["status", "status"])
        self.assertIn("result uncertain", self.wifi.statusText)

    def test_saved_read_only_security_connects_without_credentials(self):
        self.device.points[0].security = _Security.ENTERPRISE
        self.device.profiles = [
            SimpleNamespace(
                id="work-profile", ssid="Home", security=_Security.ENTERPRISE
            )
        ]
        self.device.security_write = 0
        self.wifi.scan()
        self.wait_idle()
        self.wifi.selectNetwork("Home")
        self.assertTrue(self.wifi.networks[0]["saved"])
        self.assertFalse(self.wifi.requiresPassword)
        self.assertFalse(self.wifi.passwordEditable)
        self.device.calls.clear()
        self.wifi.connectNetwork("Home", "")
        self.wait_idle()
        self.assertEqual(
            self.device.calls,
            ["profiles", ("connect", "work-profile"), "status", "profiles"],
        )

    def test_saved_profile_must_match_network_security(self):
        self.device.profiles = [
            SimpleNamespace(
                id="work-profile", ssid="Home", security=_Security.ENTERPRISE
            )
        ]
        self.wifi.scan()
        self.wait_idle()
        self.wifi.selectNetwork("Home")
        self.assertFalse(self.wifi.networks[0]["saved"])
        self.assertTrue(self.wifi.requiresPassword)
        self.device.calls.clear()
        self.wifi.connectNetwork("Home", "")
        self.wait_idle()
        self.assertFalse(any(isinstance(call, tuple) for call in self.device.calls))
        self.assertIn("no saved credentials", self.wifi.statusText)

    def test_failed_saved_connection_can_update_password_and_retry(self):
        self.device.profiles = [
            SimpleNamespace(id="home-profile", ssid="Home", security=_Security.WPA_PSK)
        ]
        self.wifi.scan()
        self.wait_idle()
        self.wifi.selectNetwork("Home")
        self.device.fail_connect = True
        self.wifi.connectNetwork("Home", "")
        self.wait_idle()
        self.assertIn("Credentials rejected", self.wifi.statusText)
        self.assertTrue(self.wifi.passwordEditable)
        self.device.fail_connect = False
        self.device.calls.clear()
        self.wifi.connectNetwork("Home", "changed-password")
        self.wait_idle()
        update = next(
            call
            for call in self.device.calls
            if isinstance(call, tuple) and call[0] == "update"
        )
        self.assertEqual(update[1], "home-profile")
        self.assertEqual(update[2].password, "changed-password")
        self.assertIn(("connect", "home-profile"), self.device.calls)
        self.assertEqual(self.wifi.statusText, "Connected to Home.")

    def test_password_changes_require_write_capability(self):
        self.device.profiles = [
            SimpleNamespace(id="home-profile", ssid="Home", security=_Security.WPA_PSK)
        ]
        self.device.security_write = 0
        self.wifi.scan()
        self.wait_idle()
        self.wifi.selectNetwork("Home")
        self.device.calls.clear()
        self.wifi.connectNetwork("Home", "changed-password")
        self.wait_idle()
        self.assertFalse(any(isinstance(call, tuple) for call in self.device.calls))
        self.assertIn("Use stock Wi-Fi settings", self.wifi.statusText)

    def test_new_password_is_saved_for_later_reuse(self):
        self.wifi.scan()
        self.wait_idle()
        self.wifi.selectNetwork("Home")
        self.assertTrue(self.wifi.requiresPassword)
        self.wifi.connectNetwork("Home", "new-password")
        self.wait_idle()
        self.assertTrue(self.wifi.networks[0]["saved"])
        self.assertFalse(self.wifi.requiresPassword)
        self.assertIn(("connect", "new-profile"), self.device.calls)


if __name__ == "__main__":
    unittest.main()
