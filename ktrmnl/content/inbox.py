from __future__ import annotations

import logging
import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ktrmnl.content.images import ImageInfo, validate_image_bytes


@dataclass(frozen=True)
class PushImage:
    sequence: int
    image_bytes: bytes
    image_info: ImageInfo
    filename: str = ""
    content_type: str = ""


@dataclass(frozen=True)
class InterruptMessage:
    sequence: int
    message: str
    title: str
    expires_in: float
    invert: bool


class PushInbox:
    """Thread-safe latest-value handoff from inbound HTTP threads."""

    def __init__(self):
        self._lock = threading.Lock()
        self._image_sequence = 0
        self._interrupt_sequence = 0
        self._latest_image: Optional[PushImage] = None
        self._latest_interrupt: Optional[InterruptMessage] = None

    def publish_image(
        self,
        image_bytes: bytes,
        *,
        filename: str = "",
        content_type: str = "",
    ) -> PushImage:
        data = bytes(image_bytes)
        image_info = validate_image_bytes(data)
        with self._lock:
            self._image_sequence += 1
            item = PushImage(
                self._image_sequence,
                data,
                image_info,
                str(filename or ""),
                str(content_type or ""),
            )
            self._latest_image = item
            return item

    def latest_image(self) -> Optional[PushImage]:
        with self._lock:
            return self._latest_image

    def publish_interrupt(
        self,
        message: str,
        *,
        title: str = "",
        expires_in: Optional[float] = None,
        invert: bool = False,
    ) -> InterruptMessage:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must not be empty")
        if title is not None and not isinstance(title, str):
            raise ValueError("title must be a string")
        if expires_in is None:
            ttl = 30.0
        elif isinstance(expires_in, bool):
            raise ValueError("expires_in must be a positive number")
        else:
            try:
                ttl = float(expires_in)
            except (TypeError, ValueError):
                raise ValueError("expires_in must be a positive number") from None
        if not math.isfinite(ttl) or ttl <= 0:
            raise ValueError("expires_in must be a positive number")
        if not isinstance(invert, bool):
            raise ValueError("invert must be a boolean")
        with self._lock:
            self._interrupt_sequence += 1
            item = InterruptMessage(
                self._interrupt_sequence,
                message.strip(),
                (title or "").strip() or "Message",
                ttl,
                invert,
            )
            self._latest_interrupt = item
            return item

    def latest_interrupt(self) -> Optional[InterruptMessage]:
        with self._lock:
            return self._latest_interrupt


class PushImageStore:
    """Atomically replace and clean up this runtime's transient pushed image."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.path: Optional[Path] = None

    def write(self, item: PushImage) -> Path:
        previous = self.path
        destination = (
            self.directory
            / f"push-current-{os.getpid()}-{id(self):x}{item.image_info.suffix}"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_bytes(item.image_bytes)
        temporary.replace(destination)
        self.path = destination
        if previous is not None and previous != destination:
            self._remove(previous)
        return destination

    @staticmethod
    def _remove(path: Path):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logging.getLogger("ktrmnl.content").warning(
                "could not remove transient push image %s", path
            )

    def close(self):
        if self.path is not None:
            self._remove(self.path)
            self.path = None
