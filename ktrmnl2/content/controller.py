from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urljoin

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot

from ktrmnl2.config.defaults import ContentMode
from ktrmnl2.config.store import KtrmnlConfig
from ktrmnl2.content.http import (
    DisplayFetchFailure,
    DisplayFetchResult,
    RequestsWorker,
    display_headers,
)
from ktrmnl2.content.images import (
    ImageValidationError,
    logical_display_size,
    validate_image_bytes,
)
from ktrmnl2.content.inbox import InterruptMessage, PushImage, PushImageStore, PushInbox
from ktrmnl2.content.interrupts import InterruptOverlay
from ktrmnl2.content.local import LocalImages

LOGGER = logging.getLogger("ktrmnl2.content")
SPECIAL_FUNCTION_SLEEP_SECONDS = 8 * 60 * 60


class PresentationState(str, Enum):
    EMPTY = "empty"
    LOADING = "loading"
    OFFLINE = "offline"
    ERROR = "error"
    READY = "ready"


class ContentState(Enum):
    STOPPED = auto()
    IDLE = auto()  # No scheduled work: missing configuration or waiting for a push.
    WAITING_NETWORK = auto()
    FETCHING = auto()
    SCHEDULED = auto()
    PAUSED = auto()
    CLOSED = auto()


@dataclass(frozen=True)
class RefreshDeadline:
    generation: int
    remaining_ms: int


@dataclass(frozen=True)
class ContentRequest:
    generation: int
    url: str
    headers: Dict[str, str]


class ContentController(QObject):
    imageSourceChanged = pyqtSignal()
    imageRevisionChanged = pyqtSignal()
    imagePresentationChanged = pyqtSignal()
    hasContentChanged = pyqtSignal()
    presentationStateChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    modeChanged = pyqtSignal()
    refreshRateChanged = pyqtSignal()
    busyChanged = pyqtSignal()
    interruptChanged = pyqtSignal()
    friendlyIdChanged = pyqtSignal()
    stateChanged = pyqtSignal()
    _pushPublished = pyqtSignal(object)
    _interruptPublished = pyqtSignal(object)

    _NETWORK_READY_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        config: KtrmnlConfig,
        device,
        *,
        wifi=None,
        network_client: Optional[RequestsWorker] = None,
        cache_dir: Optional[Path] = None,
        push_runtime_dir: Optional[Path] = None,
        random_source: Optional[random.Random] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.device = device
        self.wifi = wifi
        self._cache_dir = self._resolve_cache_dir(cache_dir)
        self._network = network_client or RequestsWorker(self._cache_dir)
        self._network.resultReady.connect(self._network_result)
        self._local_images = LocalImages(config, random_source)
        self._inbox = PushInbox()
        self._push_images = PushImageStore(
            push_runtime_dir if push_runtime_dir is not None else Path("/tmp/ktrmnl2")
        )
        self._image_source = ""
        self._image_revision = 0
        self._image_presentation = "aspect_fit"
        self._presentation_state = PresentationState.EMPTY
        self._status = "Ready"
        self._mode = ContentMode(config.content_source)
        self._refresh_rate = 0
        self._state = ContentState.STOPPED
        self._generation = 0
        self._paused_refresh: Optional[RefreshDeadline] = None
        self._request: Optional[ContentRequest] = None
        self._network_ready_deadline = 0.0
        self._overlay = InterruptOverlay(self)
        self._overlay.changed.connect(self.interruptChanged)
        self._overlay.statusChanged.connect(self._set_status)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.refresh)
        self._network_ready_timer = QTimer(self)
        self._network_ready_timer.setInterval(250)
        self._network_ready_timer.timeout.connect(self._poll_network_ready)
        self._pushPublished.connect(self._receive_push)
        self._interruptPublished.connect(self._receive_interrupt)
        if self.wifi is not None and hasattr(self.wifi, "connectedChanged"):
            self.wifi.connectedChanged.connect(self._network_connection_changed)

    def _resolve_cache_dir(self, configured: Optional[Path]) -> Path:
        directory = (
            Path(configured)
            if configured is not None
            else self.config.path.parent / "cache"
        )
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @pyqtProperty(str, notify=imageSourceChanged)
    def imageSource(self) -> str:
        return self._image_source

    @pyqtProperty(int, notify=imageRevisionChanged)
    def imageRevision(self) -> int:
        return self._image_revision

    @pyqtProperty(str, notify=imagePresentationChanged)
    def imagePresentation(self) -> str:
        return self._image_presentation

    @pyqtProperty(bool, notify=hasContentChanged)
    def hasContent(self) -> bool:
        return bool(self._image_source)

    @pyqtProperty(str, notify=presentationStateChanged)
    def presentationState(self) -> str:
        return self._presentation_state.value

    @pyqtProperty(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @pyqtProperty(str, notify=modeChanged)
    def mode(self) -> str:
        return self._mode.value

    @pyqtProperty(int, notify=refreshRateChanged)
    def refreshRate(self) -> int:
        return self._refresh_rate

    @pyqtProperty(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._state in {ContentState.WAITING_NETWORK, ContentState.FETCHING}

    @pyqtProperty(bool, notify=interruptChanged)
    def interruptActive(self) -> bool:
        return self._overlay.active

    @pyqtProperty(str, notify=interruptChanged)
    def interruptTitle(self) -> str:
        return self._overlay.title

    @pyqtProperty(str, notify=interruptChanged)
    def interruptMessage(self) -> str:
        return self._overlay.message

    @pyqtProperty(bool, notify=interruptChanged)
    def interruptInverted(self) -> bool:
        return self._overlay.inverted

    def _set_status(self, value: str) -> None:
        value = str(value)
        if value != self._status:
            self._status = value
            self.statusChanged.emit()

    def setExternalStatus(self, value: str, state: Optional[str] = None) -> None:
        self._set_status(value)
        if state is not None:
            self._set_presentation_state(state)

    def _set_presentation_state(self, value: str) -> None:
        value = PresentationState(value)
        if value != self._presentation_state:
            self._presentation_state = value
            self.presentationStateChanged.emit()

    @property
    def state(self) -> ContentState:
        return self._state

    def _transition(
        self, state: ContentState, *, delay_ms: Optional[int] = None
    ) -> None:
        """Leave the old state's timers and context before publishing the new state."""
        if state is self._state and state is not ContentState.SCHEDULED:
            return
        if self._state is ContentState.CLOSED:
            raise RuntimeError("Content is closed")
        was_busy = self.busy
        self._timer.stop()
        self._network_ready_timer.stop()
        if state is not ContentState.PAUSED:
            self._paused_refresh = None
        if state not in {ContentState.WAITING_NETWORK, ContentState.FETCHING}:
            self._request = None
        self._state = state
        if state is ContentState.SCHEDULED:
            self._timer.start(max(1, delay_ms))
        elif state is ContentState.WAITING_NETWORK:
            self._network_ready_timer.start()
        if was_busy != self.busy:
            self.busyChanged.emit()
        self.stateChanged.emit()

    def _set_refresh_rate(self, seconds: int) -> None:
        seconds = max(1, min(86400, int(seconds)))
        if seconds != self._refresh_rate:
            self._refresh_rate = seconds
            self.refreshRateChanged.emit()

    def _set_image(self, path: Path, presentation: str) -> None:
        source = QUrl.fromLocalFile(str(path.resolve())).toString()
        had_content = self.hasContent
        presentation_changed = presentation != self._image_presentation
        self._image_source = source
        self._image_presentation = presentation
        self._image_revision += 1
        self.imageSourceChanged.emit()
        self.imageRevisionChanged.emit()
        if presentation_changed:
            self.imagePresentationChanged.emit()
        if had_content != self.hasContent:
            self.hasContentChanged.emit()

    def _clear_image(self) -> None:
        if self._image_source:
            self._image_source = ""
            self._image_revision += 1
            self.imageSourceChanged.emit()
            self.imageRevisionChanged.emit()
            self.hasContentChanged.emit()

    def start(self) -> None:
        if self._state is ContentState.STOPPED:
            self.refresh()

    @pyqtSlot(str)
    def setMode(self, mode: str) -> None:
        if self._state is ContentState.CLOSED:
            return
        requested = ContentMode(mode)
        if requested == self._mode:
            self.refresh()
            return
        self.config.set("content_source", requested.value)
        previous = self._mode
        self._stop_current_mode()
        self._mode = requested
        self.modeChanged.emit()
        if not {previous, requested}.issubset(
            {ContentMode.TRMNL, ContentMode.INTERRUPT}
        ):
            self._clear_image()
        self.refresh()

    @pyqtSlot()
    def reloadConfig(self) -> None:
        if self._state is ContentState.CLOSED:
            return
        requested = ContentMode(self.config.content_source)
        previous = self._mode
        self._stop_current_mode()
        self._local_images.reset()
        self._mode = requested
        if requested != previous:
            self.modeChanged.emit()
        if not {previous, requested}.issubset(
            {ContentMode.TRMNL, ContentMode.INTERRUPT}
        ):
            self._clear_image()
        self.refresh()

    def _store_friendly_id(self, friendly_id: str) -> bool:
        if not friendly_id:
            return False
        if friendly_id == self.config.friendly_id:
            return True
        try:
            self.config.set("friendly_id", friendly_id)
        except (OSError, TypeError, ValueError):
            LOGGER.exception("could not persist TRMNL friendly ID")
            return False
        self.friendlyIdChanged.emit()
        return True

    def _stop_current_mode(self) -> None:
        self._generation += 1
        self._transition(ContentState.STOPPED)
        self.dismissInterrupt()

    @pyqtSlot()
    def refresh(self) -> None:
        if self._state is ContentState.CLOSED:
            return
        if self.busy:
            self._consume_latest_interrupt()
            return
        self._transition(ContentState.IDLE)
        if self._mode in {ContentMode.TRMNL, ContentMode.INTERRUPT}:
            self._refresh_trmnl()
        elif self._mode is ContentMode.LOCAL_IMAGES:
            self._refresh_local_images()
        else:
            self._refresh_http_push()

    def reset_network_after_sleep(self) -> None:
        self._network.reset_connections()

    def pause_refresh(self) -> Optional[RefreshDeadline]:
        """Transfer a scheduled refresh to power; only this exact token can resume it."""
        if self._state is not ContentState.SCHEDULED:
            return None
        self._paused_refresh = RefreshDeadline(
            self._generation, max(0, self._timer.remainingTime())
        )
        self._transition(ContentState.PAUSED)
        return self._paused_refresh

    def resume_refresh(
        self,
        token: Optional[RefreshDeadline],
        elapsed_ms: int = 0,
        *,
        refresh: bool = False,
    ) -> bool:
        if not self.refresh_paused(token):
            return False
        remaining = token.remaining_ms - max(0, int(elapsed_ms))
        if refresh or remaining <= 0:
            self.refresh()
        else:
            self._schedule_ms(remaining)
        return True

    def refresh_paused(self, token: Optional[RefreshDeadline]) -> bool:
        return (
            self._state is ContentState.PAUSED
            and token is not None
            and token is self._paused_refresh
            and token.generation == self._generation
        )

    def _schedule_ms(self, milliseconds: int) -> None:
        if self._state is ContentState.CLOSED:
            return
        self._transition(ContentState.SCHEDULED, delay_ms=milliseconds)

    def _schedule(self, seconds: int) -> None:
        self._schedule_ms(max(1, min(86400, int(seconds))) * 1000)

    def _trmnl_configuration_error(self) -> str:
        if not self.config.base_url:
            return "TRMNL server not configured"
        if not self.config.api_key.strip():
            return "TRMNL API token not configured"
        return ""

    def _refresh_trmnl(self) -> None:
        configuration_error = self._trmnl_configuration_error()
        if configuration_error:
            self._set_status(configuration_error + ".")
            self._set_presentation_state(PresentationState.EMPTY)
            self._consume_latest_interrupt()
            return
        self._generation += 1
        self._request = ContentRequest(
            self._generation,
            urljoin(self.config.base_url.rstrip("/") + "/", "api/display"),
            display_headers(self.config, self.device, self.wifi),
        )
        self._set_status("TRMNL content request active.")
        self._set_presentation_state(PresentationState.LOADING)
        if self.wifi is None or self.wifi.connected:
            self._submit_network_request()
        else:
            self._network_ready_deadline = (
                time.monotonic() + self._NETWORK_READY_TIMEOUT_SECONDS
            )
            self._transition(ContentState.WAITING_NETWORK)
            self._set_status("Waiting for Wi-Fi. Connect in Network settings.")
        self._consume_latest_interrupt()

    def _consume_latest_interrupt(self) -> None:
        if self._mode is not ContentMode.INTERRUPT:
            return
        latest_interrupt = self._inbox.latest_interrupt()
        if latest_interrupt is not None:
            self._receive_interrupt(latest_interrupt)

    @pyqtSlot()
    def _network_connection_changed(self) -> None:
        if self._state is ContentState.WAITING_NETWORK:
            self._poll_network_ready()
        elif (
            self._state is ContentState.SCHEDULED
            and self._mode in {ContentMode.TRMNL, ContentMode.INTERRUPT}
            and self._presentation_state is PresentationState.OFFLINE
            and self.wifi.connected
        ):
            LOGGER.info(
                "Wi-Fi became ready after an offline result; retrying content now"
            )
            self.refresh()

    @pyqtSlot()
    def _poll_network_ready(self) -> None:
        if self._state is not ContentState.WAITING_NETWORK:
            return
        if self.wifi.connected:
            self._submit_network_request()
        elif time.monotonic() >= self._network_ready_deadline:
            self._set_status("Display offline: Wi-Fi did not become ready")
            self._set_presentation_state(PresentationState.OFFLINE)
            self._schedule(self.config.retry_interval)

    def _submit_network_request(self) -> None:
        request = self._request
        self._transition(ContentState.FETCHING)
        setup_url = ""
        if not self.config.friendly_id:
            setup_url = urljoin(self.config.base_url.rstrip("/") + "/", "api/setup")
        self._network.fetch_display(
            request.generation, request.url, request.headers, setup_url
        )

    @pyqtSlot(int, object)
    def _network_result(self, generation: int, outcome: object) -> None:
        if (
            self._state is not ContentState.FETCHING
            or self._request is None
            or generation != self._request.generation
        ):
            return
        if isinstance(outcome, DisplayFetchFailure):
            LOGGER.warning(
                "TRMNL content request failed state=%s detail=%s retry=%ss",
                outcome.presentation_state,
                outcome.detail,
                self.config.retry_interval,
            )
            prefix = (
                "Display offline: "
                if outcome.presentation_state == "offline"
                else "Display error: "
            )
            self._set_status(prefix + outcome.detail)
            self._set_presentation_state(outcome.presentation_state)
            self._schedule(self.config.retry_interval)
            return
        if not isinstance(outcome, DisplayFetchResult):
            self._set_status("Display error: invalid worker result")
            self._set_presentation_state(PresentationState.ERROR)
            self._schedule(self.config.retry_interval)
            return
        if outcome.friendly_id and not self._store_friendly_id(outcome.friendly_id):
            LOGGER.warning("content fetched but TRMNL friendly ID was not saved")
        LOGGER.info(
            "TRMNL content response accepted refresh_rate=%ss special_function=%s",
            outcome.refresh_rate,
            outcome.special_function or "none",
        )
        self._set_refresh_rate(outcome.refresh_rate)
        expected_size = logical_display_size(self.device, self.config.rotation)
        presentation = (
            "pixel_exact"
            if (outcome.width, outcome.height) == expected_size
            else "aspect_fit"
        )
        if not self._overlay.active:
            self._set_image(outcome.path, presentation)
            self._set_status("Content updated.")
        self._set_presentation_state(PresentationState.READY)
        if self._mode is ContentMode.TRMNL and outcome.special_function in {
            "sleep",
            "suspend",
        }:
            self._schedule(SPECIAL_FUNCTION_SLEEP_SECONDS)
        elif outcome.special_function and outcome.special_function not in {
            "none",
            "null",
        }:
            LOGGER.info(
                "unsupported TRMNL special_function=%r ignored",
                outcome.special_function,
            )
            self._schedule(outcome.refresh_rate)
        else:
            self._schedule(outcome.refresh_rate)

    def _refresh_local_images(self) -> None:
        directory = self._local_images.directory()
        paths = self._local_images.paths()
        if not paths:
            self._clear_image()
            if directory is None:
                self._set_status("Local image directory is not configured.")
            else:
                self._set_status("No local images: " + str(directory))
            self._set_presentation_state(PresentationState.EMPTY)
            self._schedule(self.config.retry_interval)
            return
        attempts = len(paths)
        last_error = ""
        while attempts > 0:
            attempts -= 1
            path = self._local_images.next_path()
            if path is None:
                break
            try:
                validate_image_bytes(path.read_bytes())
            except (OSError, ImageValidationError) as error:
                last_error = str(error)
                continue
            self._set_image(path, "aspect_fit")
            self._set_status("Local image: " + path.name)
            self._set_presentation_state(PresentationState.READY)
            refresh_rate = self.config.local_image_refresh_rate
            self._set_refresh_rate(refresh_rate)
            self._schedule(refresh_rate)
            return
        self._clear_image()
        self._set_status("Local image error: " + (last_error or "no decodable images"))
        self._set_presentation_state(PresentationState.ERROR)
        self._schedule(self.config.retry_interval)

    def _refresh_http_push(self) -> None:
        latest = self._inbox.latest_image()
        if latest is not None:
            self._display_push(latest)
            return
        self._clear_image()
        self._set_status("No pushed image. Send POST /push/image.")
        self._set_presentation_state(PresentationState.EMPTY)

    def publishPushImage(
        self,
        image_bytes: bytes,
        *,
        filename: str = "",
        content_type: str = "",
    ) -> PushImage:
        item = self._inbox.publish_image(
            image_bytes, filename=filename, content_type=content_type
        )
        self._pushPublished.emit(item)
        return item

    @pyqtSlot(object)
    def _receive_push(self, item: object) -> None:
        if (
            self._state is not ContentState.CLOSED
            and isinstance(item, PushImage)
            and self._mode is ContentMode.HTTP_PUSH
        ):
            self._display_push(item)

    def _display_push(self, item: PushImage) -> None:
        try:
            destination = self._push_images.write(item)
        except OSError:
            self._set_status("Push error: Image could not be displayed.")
            self._set_presentation_state(PresentationState.ERROR)
            return
        self._set_image(destination, "aspect_fit")
        self._set_status(f"Pushed image #{item.sequence}.")
        self._set_presentation_state(PresentationState.READY)

    def publishInterrupt(
        self,
        message: str,
        *,
        title: str = "",
        expires_in: Optional[float] = None,
        invert: bool = False,
    ) -> InterruptMessage:
        item = self._inbox.publish_interrupt(
            message,
            title=title,
            expires_in=expires_in,
            invert=invert,
        )
        self._interruptPublished.emit(item)
        return item

    @pyqtSlot(object)
    def _receive_interrupt(self, item: object) -> None:
        if (
            self._state is not ContentState.CLOSED
            and self._mode is ContentMode.INTERRUPT
            and isinstance(item, InterruptMessage)
        ):
            self._overlay.receive(item, self._status)

    @pyqtSlot(result=bool)
    def dismissInterrupt(self) -> bool:
        return self._overlay.dismiss()

    @pyqtSlot()
    def close(self) -> None:
        if self._state is ContentState.CLOSED:
            return
        self._stop_current_mode()
        self._transition(ContentState.CLOSED)
        self._network.close()
        self._push_images.close()
