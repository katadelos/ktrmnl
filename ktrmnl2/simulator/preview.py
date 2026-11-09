from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from PyQt5.QtCore import (
    QCoreApplication,
    QObject,
    Qt,
    QTimer,
    pyqtSlot,
)
from PyQt5.QtGui import QImage, QPainter, QPen

from ktrmnl2.app.runtime import (
    ApplicationRuntime,
)

LOGGER = logging.getLogger("ktrmnl2.simulator")


def write_scenario_content(path: Path, size: Tuple[int, int]) -> None:
    """Create an exact-viewport fixture entirely inside the host boundary."""

    width, height = size
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.setPen(QPen(Qt.black, 1))
    painter.drawRect(0, 0, width - 1, height - 1)
    painter.drawLine(0, 0, width - 1, height - 1)
    painter.drawLine(width - 1, 0, 0, height - 1)
    painter.drawText(24, 40, f"Exact viewport · {width} × {height}")
    painter.end()
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"could not create simulator content fixture: {path}")


class ScreenshotController(QObject):
    @pyqtSlot()
    def finish(self) -> None:
        QCoreApplication.quit()


class QmlWatcher(QObject):
    def __init__(self, runtime: ApplicationRuntime, paths: Sequence[Path], parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.paths = tuple(paths)
        self._files = self._snapshot()
        self._timer = QTimer(self)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        QCoreApplication.instance().aboutToQuit.connect(self._timer.stop)

    def _snapshot(self) -> Dict[str, int]:
        files: List[Path] = []
        for path in self.paths:
            files.extend(path.rglob("*.qml") if path.is_dir() else [path])
        return {str(path): path.stat().st_mtime_ns for path in files if path.exists()}

    def _poll(self) -> None:
        current = self._snapshot()
        if current == self._files:
            return
        self._files = current
        if not self.runtime.reload():
            LOGGER.error("QML reload failed; watching for the next change")
