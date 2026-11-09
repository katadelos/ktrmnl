from __future__ import annotations

import base64
import errno
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import requests
from PyQt5.QtCore import QCoreApplication, QEventLoop, QTimer
from urllib3.exceptions import MaxRetryError, NewConnectionError

from ktrmnl.content.http import (
    DisplayFetchFailure,
    DisplayFetchResult,
    DisplayMetadata,
    RequestsWorker,
)

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        fixture = self.server.fixture  # type: ignore[attr-defined]
        fixture.paths.append(self.path)
        fixture.connections.append(self.client_address)
        if self.path == "/api/display":
            fixture.display_headers = dict(self.headers.items())
        elif self.path == "/api/setup":
            fixture.setup_headers = dict(self.headers.items())
        if fixture.delay:
            time.sleep(fixture.delay)
        if self.path == "/api/display":
            status = fixture.display_status
            body = fixture.display_body
            content_type = "application/json"
        elif self.path == "/api/setup":
            status = fixture.setup_status
            body = fixture.setup_body
            content_type = "application/json"
        elif self.path == "/api/image.png":
            status = fixture.image_status
            body = fixture.image_body
            content_type = "image/png"
        else:
            status = 404
            body = b"not found"
            content_type = "text/plain"
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


class _KeepAliveHandler(_Handler):
    protocol_version = "HTTP/1.1"


class _Fixture:
    def __init__(self, handler=_Handler):
        self.display_status = 200
        self.display_body = json.dumps(
            {"image_url": "image.png", "refresh_rate": 45}
        ).encode("utf-8")
        self.image_status = 200
        self.image_body = PNG_1X1
        self.setup_status = 200
        self.setup_body = json.dumps(
            {
                "status": 200,
                "api_key": "server-secret",
                "friendly_id": "A3l1nT",
            }
        ).encode("utf-8")
        self.delay = 0.0
        self.paths: list[str] = []
        self.connections = []
        self.display_headers: dict[str, str] = {}
        self.setup_headers: dict[str, str] = {}
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.fixture = self  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def display_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/api/display"

    @property
    def setup_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/api/setup"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class RequestsWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def _fetch(
        self,
        fixture: _Fixture,
        *,
        read_timeout: float = 1.0,
        discover_identity: bool = False,
    ):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        worker = RequestsWorker(
            Path(temporary.name), connect_timeout=0.2, read_timeout=read_timeout
        )
        self.addCleanup(worker.close)
        loop = QEventLoop()
        outcomes = []

        def completed(_generation: int, outcome: object) -> None:
            outcomes.append(outcome)
            loop.quit()

        worker.resultReady.connect(completed)
        started = time.monotonic()
        worker.fetch_display(
            7,
            fixture.display_url,
            {
                "access-token": "secret-test-token",
                "ID": "00:11:22:33:44:55",
                "png-width": "800",
                "png-height": "600",
            },
            fixture.setup_url if discover_identity else "",
        )
        submit_duration = time.monotonic() - started
        QTimer.singleShot(3000, loop.quit)
        loop.exec_()
        self.assertLess(submit_duration, 0.05, "fetch_display blocked the caller")
        self.assertEqual(len(outcomes), 1)
        return outcomes[0]

    def test_wake_reset_opens_a_new_connection_without_replaying_requests(self) -> None:
        with (
            _Fixture(_KeepAliveHandler) as fixture,
            tempfile.TemporaryDirectory() as temporary,
        ):
            worker = RequestsWorker(Path(temporary))
            try:
                first = worker._executor.submit(
                    worker._fetch_metadata, fixture.display_url, {}
                )
                worker.reset_connections()
                second = worker._executor.submit(
                    worker._fetch_metadata, fixture.display_url, {}
                )
                self.assertIsInstance(first.result(2), DisplayMetadata)
                self.assertIsInstance(second.result(2), DisplayMetadata)
                third = worker._executor.submit(
                    worker._fetch_metadata, fixture.display_url, {}
                )
                self.assertIsInstance(third.result(2), DisplayMetadata)
                self.assertNotEqual(fixture.connections[0], fixture.connections[1])
                self.assertEqual(fixture.connections[1], fixture.connections[2])
                self.assertEqual(fixture.paths, ["/api/display"] * 3)
            finally:
                worker.close()

    def test_connection_logs_keep_causes_without_secrets(self) -> None:
        secret = "secret-token-in-url-and-message"
        cause = OSError(errno.ECONNRESET, secret)
        connection_error = NewConnectionError(None, secret)
        connection_error.__cause__ = cause
        error = requests.ConnectionError(
            MaxRetryError(None, "https://" + secret, connection_error)
        )
        with tempfile.TemporaryDirectory() as temporary:
            worker = RequestsWorker(Path(temporary))
            try:
                operations = (
                    (
                        "display",
                        lambda: worker._fetch_metadata("https://" + secret, {}),
                    ),
                    (
                        "setup",
                        lambda: worker._fetch_setup_identity("https://" + secret, {}),
                    ),
                    ("image", lambda: worker._fetch_display("https://" + secret, {})),
                )
                for operation, fetch in operations:
                    with (
                        self.subTest(operation=operation),
                        patch.object(worker._session, "get", side_effect=error),
                        self.assertLogs("ktrmnl.content", level="WARNING") as logs,
                    ):
                        if operation == "image":
                            with patch.object(
                                worker,
                                "_fetch_metadata",
                                return_value=DisplayMetadata(
                                    "https://" + secret, 60, ""
                                ),
                            ):
                                outcome = fetch()
                        else:
                            outcome = fetch()
                    self.assertIsInstance(outcome, DisplayFetchFailure)
                    output = "\n".join(logs.output)
                    self.assertIn("operation=" + operation, output)
                    self.assertIn("NewConnectionError", output)
                    self.assertIn("ECONNRESET", output)
                    self.assertNotIn(secret, output)
                    self.assertNotIn("https://", output)
            finally:
                worker.close()

    def test_valid_json_and_relative_image_url(self) -> None:
        with _Fixture() as fixture:
            outcome = self._fetch(fixture)
        self.assertIsInstance(outcome, DisplayFetchResult)
        self.assertEqual(outcome.refresh_rate, 45)
        self.assertEqual((outcome.width, outcome.height), (1, 1))
        self.assertEqual(fixture.paths, ["/api/display", "/api/image.png"])
        self.assertEqual(fixture.display_headers.get("png-width"), "800")

    def test_content_fetch_backfills_friendly_id(self) -> None:
        with _Fixture() as fixture:
            outcome = self._fetch(fixture, discover_identity=True)
        self.assertIsInstance(outcome, DisplayFetchResult)
        self.assertEqual(outcome.friendly_id, "A3l1nT")
        self.assertEqual(
            fixture.paths, ["/api/display", "/api/image.png", "/api/setup"]
        )
        self.assertNotIn("access-token", fixture.setup_headers)

    def test_content_fetch_keeps_image_when_identity_discovery_fails(self) -> None:
        with _Fixture() as fixture:
            fixture.setup_body = json.dumps({"status": 200}).encode("utf-8")
            outcome = self._fetch(fixture, discover_identity=True)
        self.assertIsInstance(outcome, DisplayFetchResult)
        self.assertEqual(outcome.friendly_id, "")
        self.assertNotIn("access-token", fixture.setup_headers)

    def test_http_error_is_rejected(self) -> None:
        with _Fixture() as fixture:
            fixture.display_status = 503
            outcome = self._fetch(fixture)
        self.assertIsInstance(outcome, DisplayFetchFailure)
        self.assertIn("HTTP 503", outcome.detail)

    def test_missing_refresh_rate_is_rejected(self) -> None:
        with _Fixture() as fixture:
            fixture.display_body = json.dumps({"image_url": "image.png"}).encode(
                "utf-8"
            )
            outcome = self._fetch(fixture)
        self.assertIsInstance(outcome, DisplayFetchFailure)
        self.assertIn("refresh_rate", outcome.detail)

    def test_invalid_json_and_invalid_image_are_rejected(self) -> None:
        with _Fixture() as fixture:
            fixture.display_body = b"not-json"
            json_outcome = self._fetch(fixture)
        self.assertIsInstance(json_outcome, DisplayFetchFailure)
        self.assertIn("valid JSON", json_outcome.detail)

        with _Fixture() as fixture:
            fixture.image_body = b"not-an-image"
            image_outcome = self._fetch(fixture)
        self.assertIsInstance(image_outcome, DisplayFetchFailure)
        self.assertIn("invalid downloaded image", image_outcome.detail)

    def test_read_timeout_is_bounded(self) -> None:
        with _Fixture() as fixture:
            fixture.delay = 0.2
            started = time.monotonic()
            outcome = self._fetch(fixture, read_timeout=0.05)
            elapsed = time.monotonic() - started
        self.assertIsInstance(outcome, DisplayFetchFailure)
        self.assertEqual(outcome.presentation_state, "offline")
        self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
