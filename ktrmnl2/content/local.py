from __future__ import annotations

import random
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence

from ktrmnl2.content.images import IMAGE_SUFFIXES


class PlaylistState(Enum):
    EMPTY = "empty"
    READY = "ready"
    EXHAUSTED = "exhausted"


class LocalImages:
    """Track one pass through the configured image directory."""

    def __init__(self, config, random_source=None):
        self.config = config
        self._random = random_source or random.Random()
        self._last_path: Optional[Path] = None
        self.reset()

    def reset(self):
        self._signature = ()
        self._order = []
        self._cursor = 0
        self.state = PlaylistState.EMPTY

    def directory(self) -> Optional[Path]:
        configured = str(self.config.get("local_image_dir", "") or "").strip()
        return Path(configured) if configured else None

    def paths(self) -> list[Path]:
        directory = self.directory()
        if directory is None:
            return []
        try:
            return sorted(
                path
                for path in directory.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
            )
        except OSError:
            return []

    def _reset_order(self, paths: Sequence[Path]) -> None:
        order = list(paths)
        if bool(getattr(self.config, "local_image_shuffle", False)):
            self._random.shuffle(order)
            if (
                len(order) > 1
                and self._last_path is not None
                and order[0] == self._last_path
            ):
                order[0], order[1] = order[1], order[0]
        self._order = order
        self._cursor = 0
        self.state = PlaylistState.READY if order else PlaylistState.EMPTY

    def next_path(self) -> Optional[Path]:
        paths = self.paths()
        signature = tuple(str(path) for path in paths)
        if signature != self._signature:
            self._signature = signature
            self._reset_order(paths)
        elif self.state is PlaylistState.EXHAUSTED:
            self._reset_order(paths)
        if self.state is PlaylistState.EMPTY:
            return None
        path = self._order[self._cursor]
        self._cursor += 1
        if self._cursor == len(self._order):
            self.state = PlaylistState.EXHAUSTED
        self._last_path = path
        return path
