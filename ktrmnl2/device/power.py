"""Power owns suspend; content owns refresh and network readiness."""

from __future__ import annotations

import errno
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from PyQt5.QtCore import Q_ARG, QMetaObject, QObject, Qt, QTimer, pyqtSignal, pyqtSlot

from ktrmnl2.content.controller import ContentState, RefreshDeadline

LOGGER = logging.getLogger("ktrmnl2.power")


class PowerState(Enum):
    IDLE = auto()
    SETTLING = auto()
    COOLDOWN = auto()
    DRAINING = auto()
    SUSPENDING = auto()
    RESUMING = auto()
    CLOSED = auto()


@dataclass
class SleepAttempt:
    manual: bool
    drain_deadline: float
    cancel: threading.Event = field(default_factory=threading.Event)
    refresh: Optional[RefreshDeadline] = None
    paused_at: float = 0.0


class StockPower(QObject):
    activityChanged = pyqtSignal()
    _finished = pyqtSignal(object, object, object)
    _GRACE_MS = 5000
    _BLOCKER_WAIT_SECONDS = 5.0

    def __init__(
        self, config, hal, wifi, content, controller, display, window, parent=None
    ):
        super().__init__(parent)
        self.config, self.hal, self.wifi = config, hal, wifi
        self.content, self.controller = content, controller
        self.display, self.window = display, window
        self._state = PowerState.IDLE
        self._attempt: Optional[SleepAttempt] = None
        self._retry_after = 0.0
        self._wake_guard_until = 0.0
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ktrmnl-power"
        )
        self._finished.connect(self._complete)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.timeout.connect(self._automatic_suspend)
        self._drain = QTimer(self)
        self._drain.setInterval(100)
        self._drain.timeout.connect(self._drain_network)
        self._retry = QTimer(self)
        self._retry.setSingleShot(True)
        self._retry.timeout.connect(self.reconsider)
        controller.suspendRequested.connect(self.request_suspend)
        controller.userInteracted.connect(self.user_interacted)
        controller.powerPolicyChanged.connect(self.reconsider)
        controller.deviceChanged.connect(self.reconsider)
        content.stateChanged.connect(self.reconsider)
        for signal in (
            content.imageRevisionChanged,
            content.modeChanged,
            content.hasContentChanged,
            content.busyChanged,
            content.interruptChanged,
            content.refreshRateChanged,
        ):
            signal.connect(self._content_changed)
        window.activeChanged.connect(self.reconsider)
        window.visibleChanged.connect(self.reconsider)
        self.reconsider()

    @property
    def state(self):
        return self._state

    @property
    def suspending(self):
        """Release the supervisor's awake lease only while native suspend runs."""
        return self._state is PowerState.SUSPENDING

    def _transition(self, state):
        if state is self._state:
            return
        if self._state is PowerState.CLOSED:
            raise RuntimeError("Power coordinator is closed")
        was_suspending = self.suspending
        self._settle.stop()
        self._drain.stop()
        self._retry.stop()
        self._state = state
        if state is PowerState.SETTLING:
            self._settle.start(self._GRACE_MS)
        elif state is PowerState.COOLDOWN:
            self._retry.start(
                max(1, math.ceil((self._retry_after - time.monotonic()) * 1000))
            )
        elif state is PowerState.DRAINING:
            self._drain.start()
        if was_suspending != self.suspending:
            self.activityChanged.emit()

    def _eligible(self):
        return (
            bool(self.config.get("sleep_between_refreshes", True))
            and self.window.isVisible()
            and self.window.isActive()
            and self.controller.sleepReady
            and self.content.mode in {"trmnl", "local_images"}
            and self.content.hasContent
            and self.content.state in {ContentState.SCHEDULED, ContentState.PAUSED}
            and not self.content.interruptActive
        )

    @pyqtSlot()
    def reconsider(self):
        if self._state in {PowerState.CLOSED, PowerState.RESUMING}:
            return
        eligible = self._eligible()
        if self._state in {PowerState.DRAINING, PowerState.SUSPENDING}:
            invalid_deadline = (
                self._state is PowerState.SUSPENDING
                and self._attempt.refresh is not None
                and not self.content.refresh_paused(self._attempt.refresh)
            )
            if (
                (not self._attempt.manual and not eligible)
                or invalid_deadline
                or not self.window.isActive()
                or not self.window.isVisible()
            ):
                self._cancel_attempt()
            return
        if not eligible:
            self._transition(PowerState.IDLE)
        elif time.monotonic() < self._retry_after:
            self._transition(PowerState.COOLDOWN)
        else:
            self._transition(PowerState.SETTLING)

    @pyqtSlot()
    def _content_changed(self):
        if self._state in {PowerState.CLOSED, PowerState.RESUMING}:
            return
        if self._state is PowerState.DRAINING and self._attempt.manual:
            return
        self.user_interacted()

    @pyqtSlot()
    def user_interacted(self):
        if self._state in {PowerState.CLOSED, PowerState.RESUMING}:
            return
        if self._state is PowerState.SETTLING:
            self._transition(PowerState.IDLE)
        self._cancel_attempt()
        self.reconsider()

    @pyqtSlot()
    def _automatic_suspend(self):
        if self._state is PowerState.SETTLING and self._eligible():
            self._begin(False)
        else:
            self.reconsider()

    @pyqtSlot()
    def request_suspend(self):
        if (
            self._state in {PowerState.CLOSED, PowerState.RESUMING}
            or time.monotonic() < self._wake_guard_until
        ):
            return
        if self._state in {PowerState.DRAINING, PowerState.SUSPENDING}:
            self._cancel_attempt()
            return
        if self.window.isVisible() and self.window.isActive():
            self._begin(True)

    def _begin(self, manual):
        if self._state not in {
            PowerState.IDLE,
            PowerState.SETTLING,
            PowerState.COOLDOWN,
        }:
            return
        self._attempt = SleepAttempt(
            manual,
            time.monotonic() + (35 if manual else self._BLOCKER_WAIT_SECONDS),
        )
        self._transition(PowerState.DRAINING)
        if not self.content.busy:
            self.wifi.pause_polling()
        if manual:
            self.controller.setPowerStatus(
                "Waiting for the current update before sleeping."
            )
        self._drain_network()

    @pyqtSlot()
    def _drain_network(self):
        if self._state is not PowerState.DRAINING:
            return
        attempt = self._attempt
        if attempt.cancel.is_set() or (not attempt.manual and not self._eligible()):
            self._complete(attempt, {}, None)
            return
        if self.content.busy:
            if time.monotonic() >= attempt.drain_deadline:
                self._complete(
                    attempt,
                    {},
                    RuntimeError("The content update is still in progress."),
                )
            return
        self.wifi.pause_polling()
        if self.wifi.operation_busy:
            if time.monotonic() >= attempt.drain_deadline:
                self._complete(
                    attempt, {}, RuntimeError("Wi-Fi is still processing a request.")
                )
            return
        attempt.paused_at = time.monotonic()
        attempt.refresh = self.content.pause_refresh()
        if not attempt.manual and (
            attempt.refresh is None or attempt.refresh.remaining_ms < 1500
        ):
            self._complete(attempt, {}, None)
            return
        try:
            self.display.wait_for_refresh()
        except Exception as error:
            self._complete(attempt, {}, error)
            return
        # The display fence may dispatch Qt events that cancel this attempt.
        if self._state is not PowerState.DRAINING or self._attempt is not attempt:
            return
        if attempt.cancel.is_set():
            self._complete(attempt, {}, None)
            return
        self.controller.setPowerStatus("Preparing to sleep.")
        self._transition(PowerState.SUSPENDING)
        self._executor.submit(self._suspend, attempt)

    def _suspend(self, attempt):
        result, error = {}, None
        try:
            deadline = time.monotonic() + self._BLOCKER_WAIT_SECONDS
            while not attempt.cancel.is_set():
                status = self.hal.suspend_status(timed=not attempt.manual)
                if status["available"]:
                    if attempt.cancel.is_set():
                        break
                    if attempt.manual:
                        result = self.hal.suspend(cancelled=attempt.cancel.is_set)
                    else:
                        remaining = attempt.refresh.remaining_ms - int(
                            (time.monotonic() - attempt.paused_at) * 1000
                        )
                        if remaining < 1000:
                            break
                        limit = int(status["max_sleep_seconds"])
                        if limit <= 0:
                            raise RuntimeError(
                                "Timed wake is unavailable on this device."
                            )
                        result = self.hal.suspend_for(
                            min(limit, math.ceil(remaining / 1000)),
                            cancelled=attempt.cancel.is_set,
                        )
                    break
                reason = str(status["reason"])
                if "usb" in reason.lower():
                    raise RuntimeError(
                        "USB keeps the device awake. Refresh continues without sleep."
                    )
                if not status["blocked"] or time.monotonic() >= deadline:
                    raise RuntimeError(reason)
                attempt.cancel.wait(0.2)
        except Exception as failure:
            error = failure
            result = {
                "slept_ms": int(getattr(failure, "slept_ms", 0)),
                "sleep_gap_ms": int(getattr(failure, "sleep_gap_ms", 0)),
                "reason": str(getattr(failure, "wake_reason", "UNKNOWN")),
            }
            if (
                attempt.cancel.is_set()
                and not result["slept_ms"]
                and getattr(failure, "errno", None) == errno.ECANCELED
            ):
                result, error = {}, None
        self._finished.emit(attempt, result, error)

    def _cancel_attempt(self):
        if self._state not in {PowerState.DRAINING, PowerState.SUSPENDING}:
            return
        self._attempt.cancel.set()
        if self._state is PowerState.DRAINING:
            self._complete(self._attempt, {}, None)

    @pyqtSlot(object, object, object)
    def _complete(self, attempt, result, error):
        if attempt is not self._attempt or self._state not in {
            PowerState.DRAINING,
            PowerState.SUSPENDING,
        }:
            return
        # Signals emitted while restoring services must not start another sleep.
        self._transition(PowerState.RESUMING)
        self.controller.restoreFrontlight()
        slept_ms = int(result.get("slept_ms", 0))
        if slept_ms:
            self.content.reset_network_after_sleep()
        elapsed_ms = max(0, int((time.monotonic() - attempt.paused_at) * 1000)) + max(
            0, int(result.get("sleep_gap_ms", 0))
        )
        reason = str(result.get("reason", "UNKNOWN"))
        # An RTC can wake early, or split a long refresh over several sleeps.
        due = (
            attempt.refresh is not None
            and elapsed_ms + 1000 >= attempt.refresh.remaining_ms
        )
        rtc_refresh = bool(slept_ms and reason == "RTC" and not attempt.manual and due)
        if slept_ms:
            LOGGER.info("resumed reason=%s slept_ms=%s", reason, slept_ms)
            self._wake_guard_until = time.monotonic() + 1.5
            self.controller.setPowerStatus("Awake.")
            if attempt.manual or reason != "RTC":
                QMetaObject.invokeMethod(
                    self.window,
                    "openMenu",
                    Qt.DirectConnection,
                    Q_ARG("QVariant", "root"),
                )
        if error is not None:
            LOGGER.warning("suspend postponed: %s", error)
            self.controller.setPowerStatus(str(error))
            self._retry_after = time.monotonic() + 30
        elif not slept_ms:
            self.controller.setPowerStatus("")
        # Invalidate the old link before returning the deadline to content.
        # Content's WAITING_NETWORK state handles a due update after RTC wake.
        self.wifi.resume_polling(after_sleep=bool(slept_ms))
        self.content.resume_refresh(
            attempt.refresh, elapsed_ms=elapsed_ms, refresh=rtc_refresh
        )
        if slept_ms:
            self.controller.refreshDeviceStatus()
        self._attempt = None
        self._transition(PowerState.IDLE)
        self.reconsider()

    def close(self):
        if self._state is PowerState.CLOSED:
            return
        if self._attempt is not None:
            self._attempt.cancel.set()
        self._transition(PowerState.CLOSED)
        # Let native cancellation restore the radio/frontlight before HAL closes.
        self._executor.shutdown(wait=True, cancel_futures=True)
        self._attempt = None
