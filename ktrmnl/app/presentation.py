from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from PyQt5.QtCore import (
    QObject,
    QUrl,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import QImage


class ContentPresentation(QObject):
    """Invert content images inside the application window for dark mode."""

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

    def __init__(
        self,
        source,
        controller: Any,
        parent=None,
    ):
        super().__init__(parent)
        self._source = source
        self._controller = controller
        self._temporary = tempfile.TemporaryDirectory(prefix="ktrmnl-display-")
        self._cache_dir = Path(self._temporary.name)
        self._inverted_key = None
        self._preview_revision = 0
        source.imageSourceChanged.connect(self._refresh_image)
        source.imagePresentationChanged.connect(self.imagePresentationChanged)
        source.hasContentChanged.connect(self.hasContentChanged)
        source.presentationStateChanged.connect(self.presentationStateChanged)
        source.statusChanged.connect(self.statusChanged)
        source.modeChanged.connect(self.modeChanged)
        source.refreshRateChanged.connect(self.refreshRateChanged)
        source.busyChanged.connect(self.busyChanged)
        source.interruptChanged.connect(self.interruptChanged)
        controller.darkModeChanged.connect(self._refresh_image)

    def _refresh_image(self) -> None:
        self._preview_revision += 1
        self.imageSourceChanged.emit()
        self.imageRevisionChanged.emit()

    def _inverted_source(self) -> str:
        source = self._source.imageSource
        if not source or not self._controller.darkMode:
            return source
        url = QUrl(source)
        if not url.isLocalFile():
            return source
        source_path = Path(url.toLocalFile())
        key = (source, self._source.imageRevision)
        destination = self._cache_dir / "inverted.png"
        if key != self._inverted_key:
            image = QImage(str(source_path))
            if image.isNull():
                return source
            image.invertPixels(QImage.InvertRgb)
            try:
                self._cache_dir.mkdir(parents=True, exist_ok=True)
                temporary = destination.with_suffix(".tmp.png")
                if not image.save(str(temporary), "PNG"):
                    return source
                temporary.replace(destination)
                self._inverted_key = key
            except OSError:
                return source
        return QUrl.fromLocalFile(str(destination.resolve())).toString()

    @pyqtProperty(str, notify=imageSourceChanged)
    def imageSource(self) -> str:
        return self._inverted_source()

    @pyqtProperty(int, notify=imageRevisionChanged)
    def imageRevision(self) -> int:
        return int(self._source.imageRevision) + self._preview_revision

    @pyqtProperty(str, notify=imagePresentationChanged)
    def imagePresentation(self) -> str:
        return self._source.imagePresentation

    @pyqtProperty(bool, notify=hasContentChanged)
    def hasContent(self) -> bool:
        return self._source.hasContent

    @pyqtProperty(str, notify=presentationStateChanged)
    def presentationState(self) -> str:
        return self._source.presentationState

    @pyqtProperty(str, notify=statusChanged)
    def status(self) -> str:
        return self._source.status

    @pyqtProperty(str, notify=modeChanged)
    def mode(self) -> str:
        return self._source.mode

    @pyqtProperty(int, notify=refreshRateChanged)
    def refreshRate(self) -> int:
        return self._source.refreshRate

    @pyqtProperty(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._source.busy

    @pyqtProperty(bool, notify=interruptChanged)
    def interruptActive(self) -> bool:
        return self._source.interruptActive

    @pyqtProperty(str, notify=interruptChanged)
    def interruptTitle(self) -> str:
        return self._source.interruptTitle

    @pyqtProperty(str, notify=interruptChanged)
    def interruptMessage(self) -> str:
        return self._source.interruptMessage

    @pyqtProperty(bool, notify=interruptChanged)
    def interruptInverted(self) -> bool:
        return self._source.interruptInverted

    @pyqtSlot()
    def refresh(self) -> None:
        self._source.refresh()

    def close(self):
        self._temporary.cleanup()
