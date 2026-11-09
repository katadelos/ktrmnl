from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ktrmnl.config.store import KtrmnlConfig


class ConfigPersistenceTests(unittest.TestCase):
    def test_qt_backend_is_validated_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path)
            self.assertEqual(config.qt_backend, "auto")
            config.set("qt_backend", "framebuffer")
            self.assertEqual(KtrmnlConfig(path).qt_backend, "framebuffer")
            with self.assertRaisesRegex(ValueError, "qt_backend"):
                config.set("qt_backend", "wayland")
            self.assertEqual(config.qt_backend, "framebuffer")

    def test_missing_file_is_unconfigured_until_first_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path)

            self.assertFalse(config.configured)
            config.set("language", "pl")

            self.assertTrue(config.configured)
            self.assertEqual(KtrmnlConfig(path).language, "pl")

    def test_local_setup_completes_without_an_api_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path)
            config.set("language", "pl")

            self.assertTrue(config.configured)
            self.assertFalse(config.setup_complete)
            config.set("first_time_setup_complete", True)
            self.assertTrue(config.setup_complete)
            self.assertTrue(KtrmnlConfig(path).setup_complete)

    def test_friendly_id_is_validated_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path)
            config.set("friendly_id", "A3l1nT")

            self.assertEqual(config.friendly_id, "A3l1nT")
            self.assertEqual(KtrmnlConfig(path).friendly_id, "A3l1nT")
            with self.assertRaisesRegex(ValueError, "spaces or control"):
                config.set("friendly_id", "not an id")
            self.assertEqual(config.friendly_id, "A3l1nT")

    def test_dashboard_name_is_trimmed_validated_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path)
            config.set("device_name", "  Kitchen Display • 2  ")

            self.assertEqual(config.device_name, "Kitchen Display • 2")
            self.assertEqual(KtrmnlConfig(path).device_name, "Kitchen Display • 2")
            for invalid in (
                "",
                "   ",
                "Kitchen\nDisplay",
                "\tKitchen",
                "Kitchen\x00",
                "x" * 65,
            ):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    config.set("device_name", invalid)
            self.assertEqual(config.device_name, "Kitchen Display • 2")
            config.set("device_name", "x" * 64)
            self.assertEqual(len(KtrmnlConfig(path).device_name), 64)

    def test_server_url_rejects_text_after_a_port(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = KtrmnlConfig(Path(directory) / "config.json")
            config.set("base_url", "https://example.test:8443")
            self.assertEqual(config.base_url, "https://example.test:8443")

            with self.assertRaisesRegex(ValueError, "invalid port"):
                config.set("base_url", "https://example.test:8443junk/api")
            with self.assertRaisesRegex(ValueError, "invalid port"):
                config.set("base_url", "https://example.test:/api")
            with self.assertRaisesRegex(ValueError, "must not contain a path"):
                config.set("base_url", "https://example.test:8443/api")
            self.assertEqual(config.base_url, "https://example.test:8443")

    def test_push_directory_is_not_a_persisted_setting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = KtrmnlConfig(Path(directory) / "config.json")
            with self.assertRaises(KeyError):
                config.set("push_directory", str(Path(directory) / "push"))
            self.assertNotIn("push_directory", config.snapshot())

    def test_clear_removes_file_and_restores_launcher_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path, defaults={"base_url": ""})
            config.update({"language": "cs", "base_url": "https://example.test"})
            self.assertTrue(path.exists())

            config.clear()

            self.assertFalse(path.exists())
            self.assertFalse(config.configured)
            self.assertEqual(config.language, "en")
            self.assertEqual(config.base_url, "")

    def test_unknown_language_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = KtrmnlConfig(Path(directory) / "config.json")

            with self.assertRaises(ValueError):
                config.set("language", "xx")

    def test_failed_set_raises_and_rolls_back_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = Path(directory) / "not-a-directory"
            blocked_parent.write_text("file", encoding="utf-8")
            config = KtrmnlConfig(blocked_parent / "config.json")

            with self.assertRaises(OSError):
                config.set("rotation", 90)

            self.assertEqual(config.rotation, 0)

    def test_failed_update_is_atomic_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = Path(directory) / "not-a-directory"
            blocked_parent.write_text("file", encoding="utf-8")
            config = KtrmnlConfig(blocked_parent / "config.json")

            with self.assertRaises(OSError):
                config.update({"content_source": "http_push", "dark_mode": True})

            self.assertEqual(config.content_source, "trmnl")
            self.assertFalse(config.dark_mode)

    def test_ui_profiles_resolve_for_each_panel_size(self) -> None:
        config = KtrmnlConfig(Path("/does/not/exist/config.json"))

        self.assertEqual(
            config.ui_profile(800, 600),
            {
                "text_scale": 1.8,
                "menu_row_height_scale": 1.4,
                "keyboard_height_ratio": 0.43,
            },
        )
        self.assertEqual(config.ui_profile(1448, 1072)["text_scale"], 2.8)
        self.assertEqual(config.ui_profile(600, 800), config.ui_profile(800, 600))

    def test_ui_profile_edit_is_persisted_for_its_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = KtrmnlConfig(path)
            config.set_ui_profile(
                1024,
                758,
                {
                    "text_scale": 2.15,
                    "menu_row_height_scale": 1.7,
                    "keyboard_height_ratio": 0.48,
                },
            )

            restored = KtrmnlConfig(path)
            self.assertEqual(
                restored.ui_profile(758, 1024),
                {
                    "text_scale": 2.15,
                    "menu_row_height_scale": 1.7,
                    "keyboard_height_ratio": 0.48,
                },
            )


if __name__ == "__main__":
    unittest.main()
