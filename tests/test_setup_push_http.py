from __future__ import annotations

import base64
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from PyQt5.QtCore import QCoreApplication, QObject, pyqtSignal

from ktrmnl2.config.store import KtrmnlConfig
from ktrmnl2.content.controller import ContentController
from ktrmnl2.network.push import ListenerState, PushWebServer

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _NoopNetwork(QObject):
    resultReady = pyqtSignal(int, object)

    def fetch_display(self, *_args: object) -> None:
        raise AssertionError("empty base_url must not start HTTP")

    def close(self) -> None:
        pass


class _Device:
    def display_size(self):
        return (800, 600)

    def battery(self):
        return {"available": True, "percent": 75}

    def mac_address(self):
        return "00:11:22:33:44:55"

    def device(self):
        return {"model": "Test reader"}

    def reader_name(self):
        return "test"

    def radio(self):
        return {"available": True, "powered": True, "operational": True}

    def suspend(self):
        pass


class _Wifi:
    pass


class _Controller:
    def __init__(self, content: ContentController):
        self.content = content


class SetupPushHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def _wait_for(self, predicate, timeout: float = 1.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.application.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.application.processEvents()
        return bool(predicate())

    def test_live_push_and_interrupt_endpoints(self) -> None:
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
            server = PushWebServer(
                config,
                _Controller(content),
                _Wifi(),
                host="127.0.0.1",
                public_host="127.0.0.1",
                port=0,
            )
            server.start()
            self.assertTrue(server.running, server.error)
            base_url = server.url.rstrip("/")
            try:
                setup_page = requests.get(base_url + "/", timeout=1)
                self.assertEqual(setup_page.status_code, 404)
                hidden_font = requests.get(
                    base_url + "/assets/fonts/KTRMNLDINMittelschrift-Regular.otf",
                    timeout=1,
                )
                self.assertEqual(hidden_font.status_code, 404)
                hidden_config = requests.post(
                    base_url + "/configure",
                    data={"content_source": "http_push"},
                    allow_redirects=False,
                    timeout=1,
                )
                self.assertEqual(hidden_config.status_code, 404)
                wrong_interrupt = requests.post(
                    base_url + "/push/interrupt",
                    json={"message": "wrong mode"},
                    timeout=1,
                )
                self.assertEqual(wrong_interrupt.status_code, 404)

                valid = requests.post(
                    base_url + "/push/image",
                    data=PNG_1X1,
                    headers={"Content-Type": "image/png"},
                    timeout=1,
                )
                self.assertEqual(valid.status_code, 200)
                self.assertEqual(valid.json()["status"], "queued")
                self.assertTrue(self._wait_for(lambda: content.hasContent))
                self.assertTrue(list((root / "runtime").glob("push-current-*.png")))

                invalid = requests.post(
                    base_url + "/push/image", data=b"not-an-image", timeout=1
                )
                self.assertEqual(invalid.status_code, 400)
                self.assertIn("image", invalid.json()["error"])

                content.setMode("interrupt")
                self.assertTrue(server.running)
                wrong_image = requests.post(
                    base_url + "/push/image",
                    data=PNG_1X1,
                    headers={"Content-Type": "image/png"},
                    timeout=1,
                )
                self.assertEqual(wrong_image.status_code, 404)
                previous_status = content.status
                bad_ttl = requests.post(
                    base_url + "/push/interrupt",
                    json={"message": "bad", "expires_in": 0},
                    timeout=1,
                )
                self.assertEqual(bad_ttl.status_code, 400)

                first = requests.post(
                    base_url + "/push/interrupt",
                    json={"message": "first", "title": "One", "expires_in": 30},
                    timeout=1,
                )
                second = requests.post(
                    base_url + "/push/interrupt",
                    json={
                        "text": "second",
                        "title": "Two",
                        "expires_in": 30,
                        "invert": True,
                    },
                    timeout=1,
                )
                self.assertEqual(first.status_code, 200)
                self.assertEqual(second.status_code, 200)
                self.assertGreater(second.json()["sequence"], first.json()["sequence"])
                self.assertTrue(
                    self._wait_for(
                        lambda: content.interruptActive
                        and content.interruptTitle == "Two"
                    )
                )
                self.assertEqual(content.interruptMessage, "second")
                self.assertTrue(content.interruptInverted)
                self.assertTrue(content.dismissInterrupt())
                self.assertEqual(content.status, previous_status)

                expiring = requests.post(
                    base_url + "/push/interrupt",
                    json={"message": "short", "expires_in": 0.05},
                    timeout=1,
                )
                self.assertEqual(expiring.status_code, 200)
                self.assertTrue(self._wait_for(lambda: content.interruptActive))
                self.assertTrue(
                    self._wait_for(lambda: not content.interruptActive, timeout=0.5)
                )
                self.assertEqual(content.status, previous_status)

                content.setMode("trmnl")
                self.assertFalse(server.running)
                with patch(
                    "ktrmnl2.network.push._ReusableHTTPServer",
                    side_effect=OSError("port busy"),
                ):
                    content.setMode("http_push")
                self.assertEqual(server._state, ListenerState.FAILED)
                self.assertFalse(server.running)
                server._reconcile()
                self.assertTrue(server.running)
                server.stop()
                content.setMode("interrupt")
                self.assertFalse(server.running)
                self.assertEqual(server._state, ListenerState.STOPPED)
                server.start()
                self.assertTrue(server.running)
            finally:
                server.stop()
                content.close()
