from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PyQt5.QtCore import QCoreApplication

from ktrmnl.config.defaults import SUPPORTED_LANGUAGES
from ktrmnl.config.store import KtrmnlConfig
from ktrmnl.i18n import CATALOG_ROOT, TranslationManager


class TranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QCoreApplication.instance() or QCoreApplication([])

    def test_catalogs_have_the_same_keys_as_english(self) -> None:
        english = json.loads((CATALOG_ROOT / "en.json").read_text(encoding="utf-8"))

        for language in SUPPORTED_LANGUAGES:
            with self.subTest(language=language):
                catalog = json.loads(
                    (CATALOG_ROOT / f"{language}.json").read_text(encoding="utf-8")
                )
                self.assertEqual(set(catalog), set(english))
                self.assertTrue(
                    all(isinstance(value, str) for value in catalog.values())
                )

    def test_language_change_can_remain_in_memory_until_setup_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path)
            translator = TranslationManager(config)

            self.assertTrue(translator.setLanguage("pl", persist=False))
            self.assertEqual(translator.language, "pl")
            self.assertEqual(translator.languageName, "Polski")
            self.assertFalse(path.exists())

            config.update({"base_url": "https://example.test"})
            self.assertEqual(KtrmnlConfig(path).language, "pl")


if __name__ == "__main__":
    unittest.main()
