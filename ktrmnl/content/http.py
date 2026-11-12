from __future__ import annotations

import errno
import hashlib
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Mapping, Optional, Union
from urllib.parse import urljoin

import requests
from PyQt5.QtCore import QObject, pyqtSignal

from ktrmnl import __version__
from ktrmnl.config.validation import validate_friendly_id
from ktrmnl.content.images import (
    ImageValidationError,
    logical_display_size,
    validate_image_bytes,
)

LOGGER = logging.getLogger("ktrmnl.content")
CONNECT_TIMEOUT_SECONDS = 3.05
READ_TIMEOUT_SECONDS = 15.0


def _log_transport_error(operation: str, error: BaseException) -> None:
    """Log exception types and errno only; messages can contain URLs and secrets."""
    pending = [error]
    seen = set()
    causes = []
    while pending and len(seen) < 16:
        current = pending.pop()
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        detail = type(current).__name__
        code = getattr(current, "errno", None)
        if type(code) is int:
            detail += f"(errno={code},{errno.errorcode.get(code, 'UNKNOWN')})"
        causes.append(detail)
        pending.extend(
            value
            for value in (
                current.__context__,
                current.__cause__,
                getattr(current, "reason", None),
                *current.args,
            )
            if isinstance(value, BaseException)
        )
    LOGGER.warning(
        "HTTP transport failure operation=%s causes=%s", operation, " -> ".join(causes)
    )


@dataclass(frozen=True)
class DisplayFetchResult:
    path: Path
    refresh_rate: int
    special_function: str
    width: int
    height: int
    friendly_id: str = ""


@dataclass(frozen=True)
class DisplayFetchFailure:
    presentation_state: str
    detail: str


@dataclass(frozen=True)
class DisplayMetadata:
    image_url: str
    refresh_rate: int
    special_function: str


@dataclass(frozen=True)
class SetupIdentity:
    friendly_id: str


DisplayFetchOutcome = Union[DisplayFetchResult, DisplayFetchFailure]
MetadataOutcome = Union[DisplayMetadata, DisplayFetchFailure]
SetupIdentityOutcome = Union[SetupIdentity, DisplayFetchFailure]


class WorkerState(Enum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


class RequestsWorker(QObject):
    """Single-worker requests.Session boundary for all outgoing HTTP."""

    resultReady = pyqtSignal(int, object)

    def __init__(
        self,
        cache_dir: Path,
        *,
        session: Optional[requests.Session] = None,
        connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = READ_TIMEOUT_SECONDS,
        parent=None,
    ):
        super().__init__(parent)
        self._cache_dir = Path(cache_dir)
        self._session = session or requests.Session()
        self._timeouts = (
            max(0.05, float(connect_timeout)),
            max(0.05, float(read_timeout)),
        )
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ktrmnl-http"
        )
        self._lock = threading.Lock()
        self._state = WorkerState.OPEN

    def reset_connections(self) -> None:
        """Discard pre-suspend sockets before subsequent queued HTTP requests."""
        with self._lock:
            if self._state is WorkerState.OPEN:
                self._executor.submit(self._reset_connections)

    def _reset_connections(self) -> None:
        # Session.close clears adapter pools without losing session settings.
        self._session.close()
        LOGGER.info("HTTP connection pools reset after wake")

    def fetch_display(
        self,
        generation: int,
        display_url: str,
        headers: Mapping[str, str],
        setup_url: str = "",
    ) -> None:
        with self._lock:
            if self._state is not WorkerState.OPEN:
                return
            future = self._executor.submit(
                self._fetch_display,
                display_url,
                dict(headers),
                str(setup_url or ""),
            )
        future.add_done_callback(
            lambda completed: self._finished(generation, completed)
        )

    def _fetch_display(
        self,
        display_url: str,
        headers: Dict[str, str],
        setup_url: str = "",
    ) -> DisplayFetchOutcome:
        metadata = self._fetch_metadata(display_url, headers)
        if isinstance(metadata, DisplayFetchFailure):
            return metadata

        try:
            image_response = self._session.get(
                metadata.image_url, timeout=self._timeouts
            )
            image_response.raise_for_status()
        except requests.Timeout as error:
            _log_transport_error("image", error)
            return DisplayFetchFailure("offline", "image download timed out")
        except requests.ConnectionError as error:
            _log_transport_error("image", error)
            return DisplayFetchFailure("offline", "image server is unreachable")
        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", 0)
            return DisplayFetchFailure(
                "error", f"image server returned HTTP {status or 'error'}"
            )
        except requests.RequestException:
            return DisplayFetchFailure("error", "image download failed")

        data = bytes(image_response.content)
        try:
            image_info = validate_image_bytes(data)
        except ImageValidationError as error:
            return DisplayFetchFailure(
                "error", "invalid downloaded image: " + str(error)
            )
        digest = hashlib.sha256(data).hexdigest()
        destination = self._cache_dir / (digest + image_info.suffix)
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                temporary = destination.with_suffix(destination.suffix + ".tmp")
                temporary.write_bytes(data)
                temporary.replace(destination)
            self._prune_cache()
        except OSError:
            return DisplayFetchFailure("error", "downloaded image could not be cached")
        friendly_id = ""
        if setup_url:
            identity = self._fetch_setup_identity(setup_url, headers)
            if isinstance(identity, SetupIdentity):
                friendly_id = identity.friendly_id
            else:
                LOGGER.warning(
                    "TRMNL friendly ID discovery failed after content fetch: %s",
                    identity.detail,
                )
        return DisplayFetchResult(
            path=destination,
            refresh_rate=metadata.refresh_rate,
            special_function=metadata.special_function,
            width=image_info.width,
            height=image_info.height,
            friendly_id=friendly_id,
        )

    def _fetch_setup_identity(
        self,
        setup_url: str,
        headers: Dict[str, str],
    ) -> SetupIdentityOutcome:
        with self._lock:
            if self._state is not WorkerState.OPEN:
                return DisplayFetchFailure("error", "request was cancelled")
        identity_headers = {
            key: headers[key]
            for key in ("ID", "User-Agent")
            if key in headers and headers[key]
        }
        try:
            response = self._session.get(
                setup_url,
                headers=identity_headers,
                timeout=self._timeouts,
            )
            response.raise_for_status()
        except requests.Timeout as error:
            _log_transport_error("setup", error)
            return DisplayFetchFailure("offline", "TRMNL setup request timed out")
        except requests.ConnectionError as error:
            _log_transport_error("setup", error)
            return DisplayFetchFailure("offline", "TRMNL setup server is unreachable")
        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", 0)
            return DisplayFetchFailure(
                "error", f"TRMNL setup server returned HTTP {status or 'error'}"
            )
        except requests.RequestException:
            return DisplayFetchFailure("error", "TRMNL setup request failed")

        try:
            payload = response.json()
        except (TypeError, ValueError):
            return DisplayFetchFailure(
                "error", "TRMNL setup response is not valid JSON"
            )
        if not isinstance(payload, dict):
            return DisplayFetchFailure(
                "error", "TRMNL setup response must be a JSON object"
            )
        try:
            friendly_id = validate_friendly_id(payload.get("friendly_id"))
        except ValueError as error:
            return DisplayFetchFailure("error", str(error))
        if not friendly_id:
            return DisplayFetchFailure(
                "error", "TRMNL setup response has no valid friendly_id"
            )
        return SetupIdentity(friendly_id=friendly_id)

    def _fetch_metadata(
        self,
        display_url: str,
        headers: Dict[str, str],
    ) -> MetadataOutcome:
        with self._lock:
            if self._state is not WorkerState.OPEN:
                return DisplayFetchFailure("error", "request was cancelled")
        try:
            response = self._session.get(
                display_url, headers=headers, timeout=self._timeouts
            )
            response.raise_for_status()
        except requests.Timeout as error:
            _log_transport_error("display", error)
            return DisplayFetchFailure("offline", "TRMNL request timed out")
        except requests.ConnectionError as error:
            _log_transport_error("display", error)
            return DisplayFetchFailure("offline", "TRMNL server is unreachable")
        except requests.HTTPError as error:
            status = getattr(error.response, "status_code", 0)
            return DisplayFetchFailure(
                "error", f"TRMNL server returned HTTP {status or 'error'}"
            )
        except requests.RequestException:
            return DisplayFetchFailure("error", "TRMNL request failed")

        try:
            payload = response.json()
        except (TypeError, ValueError):
            return DisplayFetchFailure("error", "TRMNL response is not valid JSON")
        if not isinstance(payload, dict):
            return DisplayFetchFailure("error", "TRMNL response must be a JSON object")
        image_url = payload.get("image_url")
        if not isinstance(image_url, str) or not image_url.strip():
            return DisplayFetchFailure("error", "TRMNL response has no valid image_url")
        resolved_image_url = urljoin(response.url, image_url.strip())

        refresh_value = payload.get("refresh_rate")
        if isinstance(refresh_value, bool):
            return DisplayFetchFailure(
                "error", "TRMNL refresh_rate must be a positive integer"
            )
        try:
            refresh_rate = int(refresh_value)
        except (TypeError, ValueError):
            return DisplayFetchFailure(
                "error", "TRMNL refresh_rate must be a positive integer"
            )
        if refresh_rate <= 0:
            return DisplayFetchFailure(
                "error", "TRMNL refresh_rate must be a positive integer"
            )
        refresh_rate = min(86400, refresh_rate)

        special_value = payload.get("special_function")
        if special_value is None:
            special_function = ""
        elif isinstance(special_value, str):
            special_function = special_value.strip().lower()
        else:
            return DisplayFetchFailure(
                "error", "TRMNL special_function must be a string"
            )
        return DisplayMetadata(
            image_url=resolved_image_url,
            refresh_rate=refresh_rate,
            special_function=special_function,
        )

    def _prune_cache(self) -> None:
        try:
            paths = sorted(
                self._cache_dir.iterdir(),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            for path in paths[12:]:
                if path.is_file():
                    path.unlink()
        except OSError:
            return

    def _finished(self, generation: int, future: Future) -> None:
        try:
            outcome = future.result()
        except Exception:
            LOGGER.exception("unexpected outgoing HTTP worker failure")
            outcome = DisplayFetchFailure("error", "unexpected HTTP worker failure")
        self.resultReady.emit(generation, outcome)

    def close(self) -> None:
        with self._lock:
            if self._state is not WorkerState.OPEN:
                return
            self._state = WorkerState.CLOSING
            # Close is serialized after the only possible in-flight operation.
            self._executor.submit(self._close_session)
            self._executor.shutdown(wait=False)

    def _close_session(self) -> None:
        try:
            self._session.close()
        finally:
            with self._lock:
                self._state = WorkerState.CLOSED


def display_headers(config, device, wifi) -> Dict[str, str]:
    try:
        battery = device.battery()
        battery_percent = (
            max(0, min(100, int(battery["percent"])))
            if battery.get("available")
            else None
        )
    except Exception:
        battery_percent = None
    try:
        identifier = str(device.mac_address() or "00:00:00:00:00:00")
    except Exception:
        identifier = "00:00:00:00:00:00"
    width, height = logical_display_size(device, config.rotation)
    rssi = int(getattr(wifi, "signalStrength", 0) or 0)
    headers = {
        "access-token": config.api_key,
        "png-width": str(width),
        "png-height": str(height),
        "rssi": str(rssi),
        "ID": identifier,
        "User-Agent": "ktrmnl/" + __version__,
    }
    if battery_percent is not None:
        headers["battery-percent"] = str(battery_percent)
    return headers
