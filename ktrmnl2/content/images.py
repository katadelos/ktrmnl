from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from PyQt5.QtGui import QImage

MAX_IMAGE_BYTES = 32 * 1024 * 1024
IMAGE_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}


class ImageValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    suffix: str
    width: int
    height: int


def validate_image_bytes(data: bytes) -> ImageInfo:
    """Validate a bounded raster image using the same Qt codecs as QML."""

    if not data:
        raise ImageValidationError("image body is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError("image body is too large")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix = ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        suffix = ".jpg"
    elif data.startswith((b"GIF87a", b"GIF89a")):
        suffix = ".gif"
    elif data.startswith(b"BM"):
        suffix = ".bmp"
    elif len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        suffix = ".webp"
    else:
        raise ImageValidationError("unsupported image format")
    image = QImage.fromData(data)
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        raise ImageValidationError("image body cannot be decoded")
    return ImageInfo(suffix=suffix, width=image.width(), height=image.height())


def logical_display_size(device, rotation) -> Tuple[int, int]:
    try:
        width, height = device.display_size()
        width, height = int(width), int(height)
        if width <= 0 or height <= 0:
            raise ValueError("invalid size")
    except Exception:
        width, height = (800, 600)
    if rotation in {90, 270}:
        width, height = height, width
    return width, height
