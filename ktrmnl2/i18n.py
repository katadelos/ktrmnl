from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from ktrmnl2.config.defaults import SUPPORTED_LANGUAGES
from ktrmnl2.config.store import KtrmnlConfig
from ktrmnl2.resources import RESOURCE_ROOT

LOGGER = logging.getLogger("ktrmnl2.i18n")
CATALOG_ROOT = RESOURCE_ROOT / "translations"

LANGUAGES = (
    ("en", "English"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("es", "Español"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("nl", "Nederlands"),
    ("pl", "Polski"),
    ("cs", "Čeština"),
    ("sv", "Svenska"),
    ("zh", "中文"),
    ("ja", "日本語"),
)


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class TranslationManager(QObject):
    """Small JSON-catalog translator shared by Python and QML."""

    languageChanged = pyqtSignal()

    def __init__(
        self,
        config: KtrmnlConfig,
        catalog_root: Optional[Path] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.config = config
        self.catalog_root = Path(catalog_root or CATALOG_ROOT)
        self._catalogs: Dict[str, Dict[str, str]] = {}
        self._language = config.language
        self._load_catalog("en")
        self._load_catalog(self._language)

    def _load_catalog(self, language: str) -> Dict[str, str]:
        language = str(language)
        if language in self._catalogs:
            return self._catalogs[language]
        catalog: Dict[str, str] = {}
        try:
            payload = json.loads(
                (self.catalog_root / f"{language}.json").read_text(encoding="utf-8")
            )
            if not isinstance(payload, dict):
                raise ValueError("catalog root must be an object")
            catalog = {
                str(key): str(value)
                for key, value in payload.items()
                if isinstance(key, str) and isinstance(value, str)
            }
        except (OSError, TypeError, ValueError) as error:
            LOGGER.error("could not load translation catalog %s: %s", language, error)
        self._catalogs[language] = catalog
        return catalog

    def translate(
        self,
        key: str,
        fallback: str = "",
        values: Optional[Mapping[str, Any]] = None,
        language: Optional[str] = None,
    ) -> str:
        language = str(language or self._language)
        selected = self._load_catalog(language)
        english = self._load_catalog("en")
        text = selected.get(str(key), english.get(str(key), str(fallback or key)))
        if values:
            try:
                text = text.format_map(_SafeFormat(values))
            except (TypeError, ValueError):
                pass
        return text

    @pyqtProperty(str, notify=languageChanged)
    def language(self) -> str:
        return self._language

    @pyqtProperty(str, notify=languageChanged)
    def languageName(self) -> str:
        return next(
            (name for code, name in LANGUAGES if code == self._language),
            self._language,
        )

    @pyqtProperty("QVariantList", constant=True)
    def languages(self):
        return [
            {"code": code, "name": name}
            for code, name in LANGUAGES
            if code in SUPPORTED_LANGUAGES
        ]

    @pyqtSlot(str, result=str)
    @pyqtSlot(str, str, result=str)
    def text(self, key: str, fallback: str = "") -> str:
        return self.translate(str(key), str(fallback))

    @pyqtSlot(str, str, result=str)
    def textFor(self, language: str, key: str) -> str:
        return self.translate(str(key), language=str(language))

    @pyqtSlot(str, "QVariantMap", result=str)
    def format(self, key: str, values: Mapping[str, Any]) -> str:
        return self.translate(str(key), values=dict(values))

    @pyqtSlot(str, result=bool)
    @pyqtSlot(str, bool, result=bool)
    def setLanguage(self, language: str, persist: bool = True) -> bool:
        language = str(language).strip().lower()
        if language not in SUPPORTED_LANGUAGES:
            return False
        try:
            self.config.set("language", language, persist=bool(persist))
        except (OSError, TypeError, ValueError):
            LOGGER.exception("could not save language %s", language)
            return False
        if language != self._language:
            self._language = language
            self._load_catalog(language)
            self.languageChanged.emit()
        return True
