from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Mapping
from urllib.parse import parse_qs, urlparse

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

LOGGER = logging.getLogger("ktrmnl.push")


class _ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _PushRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.info("http client=%s %s", self.client_address[0], format_string % args)

    def do_GET(self) -> None:
        self.server.push_app.handle_get(self)

    def do_POST(self) -> None:
        self.server.push_app.handle_post(self)


class ListenerState(Enum):
    STOPPED = "stopped"
    IDLE = "idle"
    STARTING = "starting"
    LISTENING = "listening"
    STOPPING = "stopping"
    FAILED = "failed"


class PushRoute(Enum):
    OFF = ""
    IMAGE = "http_push"
    INTERRUPT = "interrupt"


class PushWebServer(QObject):
    """LAN image and interrupt endpoints, active only in the matching mode."""

    runningChanged = pyqtSignal()
    capabilitiesChanged = pyqtSignal()
    _MAX_BODY = 64 * 1024
    _MAX_IMAGE_BODY = 32 * 1024 * 1024

    def __init__(
        self,
        config,
        controller,
        wifi,
        *,
        host=None,
        port=None,
        public_host=None,
        firewall=None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.controller = controller
        self.wifi = wifi
        self.firewall = firewall
        self.host = str(host or os.environ.get("KTRMNL_PUSH_HOST", "0.0.0.0"))
        self.port = int(
            port if port is not None else os.environ.get("KTRMNL_PUSH_PORT", 8080)
        )
        if not 0 <= self.port <= 65535:
            raise ValueError("push port must be between 0 and 65535")
        self.public_host = str(public_host or "").strip()
        self._server = None
        self._thread = None
        self._state_lock = threading.RLock()
        self._state = ListenerState.STOPPED
        self._route = PushRoute.OFF
        self.error = ""
        controller.content.modeChanged.connect(self._reconcile)
        if hasattr(wifi, "stateChanged"):
            wifi.stateChanged.connect(self._network_changed)

    @pyqtSlot()
    def _network_changed(self):
        self.runningChanged.emit()
        self._reconcile()

    def _close_firewall(self):
        if self.firewall is not None:
            try:
                self.firewall.close()
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                self.error = str(error)
                LOGGER.exception("Could not remove the LAN push firewall exception")

    @pyqtProperty(bool, notify=runningChanged)
    def running(self):
        with self._state_lock:
            return self._state is ListenerState.LISTENING

    @pyqtProperty(str, notify=capabilitiesChanged)
    def pushMode(self):
        with self._state_lock:
            return self._route.value

    @pyqtProperty(str, notify=runningChanged)
    def url(self):
        host = self.public_host or str(getattr(self.wifi, "ipAddress", ""))
        if not host:
            host = self.host if self.host not in {"0.0.0.0", "::"} else "127.0.0.1"
        port = "" if self.port == 80 else f":{self.port}"
        return f"http://{host}{port}/"

    @pyqtSlot()
    def _reconcile(self):
        mode = self.controller.content.mode
        route = {"interrupt": PushRoute.INTERRUPT, "http_push": PushRoute.IMAGE}.get(
            mode, PushRoute.OFF
        )
        with self._state_lock:
            changed = route is not self._route
            self._route = route
            if self._state is not ListenerState.STOPPED:
                if route is PushRoute.OFF:
                    self._stop_listener(ListenerState.IDLE)
                else:
                    self._start_listener()
        if changed:
            self.capabilitiesChanged.emit()

    def start(self) -> None:
        with self._state_lock:
            if self._state is not ListenerState.STOPPED:
                return
            self._close_firewall()
            self._state = ListenerState.IDLE
        self._reconcile()

    def _start_listener(self) -> None:
        # Lifecycle operations hold the lock through bind/start/stop. Request
        # handlers only observe a completely installed listener and route.
        if self._state not in {ListenerState.IDLE, ListenerState.FAILED}:
            return
        self._state = ListenerState.STARTING
        server = None
        try:
            server = _ReusableHTTPServer((self.host, self.port), _PushRequestHandler)
            if self.firewall is not None:
                self.firewall.open(self.host, int(server.server_address[1]))
            server.push_app = self
            thread = threading.Thread(
                target=server.serve_forever, name="ktrmnl-inbound-http", daemon=True
            )
            thread.start()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            if server is not None:
                server.server_close()
            self._close_firewall()
            self.error = str(error)
            self._state = ListenerState.FAILED
            self.runningChanged.emit()
            LOGGER.exception("Could not start the LAN push listener")
            return
        self._server, self._thread = server, thread
        self.port = int(server.server_address[1])
        self.error = ""
        self._state = ListenerState.LISTENING
        self.runningChanged.emit()
        LOGGER.info("push server listening on %s", self.url)

    def stop(self) -> None:
        with self._state_lock:
            self._stop_listener(ListenerState.STOPPED)

    def _stop_listener(self, final_state: ListenerState) -> None:
        server, thread = self._server, self._thread
        self._state = ListenerState.STOPPING
        self._server = self._thread = None
        try:
            if server is not None:
                server.shutdown()
                server.server_close()
                if thread is not threading.current_thread():
                    thread.join(timeout=2)
            self._close_firewall()
        finally:
            self._state = final_state
        if server is not None:
            self.runningChanged.emit()
            LOGGER.info("inbound server stopped")

    def _read_body(self, request: BaseHTTPRequestHandler, maximum: int) -> bytes:
        try:
            length = int(request.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid request body") from None
        if length < 0 or length > maximum:
            raise ValueError("request body is too large")
        request.connection.settimeout(15)
        body = request.rfile.read(length)
        if len(body) != length:
            raise ValueError("incomplete request body")
        return body

    def _read_json(self, request: BaseHTTPRequestHandler) -> Dict[str, Any]:
        body = self._read_body(request, self._MAX_BODY)
        if not body:
            raise ValueError("request body is empty")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError):
            raise ValueError("request body must be valid JSON") from None
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _send(
        self,
        request: BaseHTTPRequestHandler,
        body: bytes,
        content_type: str = "text/html; charset=utf-8",
        status: int = 200,
        cache_control: str = "no-store",
    ) -> None:
        request.send_response(status)
        request.send_header("Content-Type", content_type)
        request.send_header("Content-Length", str(len(body)))
        request.send_header("Cache-Control", cache_control)
        request.end_headers()
        request.wfile.write(body)

    def _send_json(
        self,
        request: BaseHTTPRequestHandler,
        payload: Mapping[str, Any],
        status: int = 200,
    ) -> None:
        self._send(
            request,
            json.dumps(dict(payload), sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            ),
            "application/json; charset=utf-8",
            status,
        )

    def handle_get(self, request):
        self._send(request, b"Not found\n", "text/plain; charset=utf-8", 404)

    def handle_post(self, request: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(request.path)
        push_mode = self.pushMode
        if parsed.path == "/push/image" and push_mode != "http_push":
            self._send_json(request, {"error": "image push mode is not active"}, 404)
            return
        if parsed.path == "/push/interrupt" and push_mode != "interrupt":
            self._send_json(request, {"error": "interrupt mode is not active"}, 404)
            return
        if parsed.path not in {"/push/image", "/push/interrupt"}:
            self._send(request, b"Not found\n", "text/plain; charset=utf-8", 404)
            return
        try:
            if parsed.path == "/push/image":
                body = self._read_body(request, self._MAX_IMAGE_BODY)
                if not body:
                    raise ValueError("image body is empty")
                query = parse_qs(parsed.query, keep_blank_values=True)
                filename = str(query.get("filename", [""])[-1])
                item = self.controller.content.publishPushImage(
                    body,
                    filename=filename,
                    content_type=str(request.headers.get("Content-Type", "")),
                )
                self._send_json(
                    request,
                    {"status": "queued", "sequence": item.sequence, "bytes": len(body)},
                )
                return
            if parsed.path == "/push/interrupt":
                payload = self._read_json(request)
                message = payload.get("message") or payload.get("text") or ""
                item = self.controller.content.publishInterrupt(
                    message,
                    title=payload.get("title", ""),
                    expires_in=payload.get("expires_in"),
                    invert=payload.get("invert", False),
                )
                self._send_json(
                    request,
                    {
                        "status": "queued",
                        "sequence": item.sequence,
                        "expires_in": item.expires_in,
                        "invert": item.invert,
                    },
                )
                return
        except ValueError as error:
            LOGGER.warning("invalid push request path=%s: %s", parsed.path, error)
            self._send_json(request, {"error": str(error)}, 400)
        except Exception:  # keep an HTTP error local to this request
            LOGGER.exception("push request failed path=%s", parsed.path)
            self._send_json(request, {"error": "push request failed"}, 500)
