from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ktrmnl import launch
from ktrmnl.config.store import configured_qt_backend


class LaunchTests(unittest.TestCase):
    def test_automatic_defaults_follow_firmware_display(self):
        for family, capable, running, expected in (
            ("kindle", True, True, "x11"),
            ("kindle", True, False, "framebuffer"),
            ("kindle", False, False, "framebuffer"),
            ("kobo", False, False, "framebuffer"),
            ("kobo", False, True, "framebuffer"),
        ):
            with self.subTest(family=family, capable=capable, running=running):
                self.assertEqual(
                    launch.select_backend(
                        family, "auto", capable=capable, running=running
                    ),
                    expected,
                )

    def test_explicit_selection_does_not_fall_back(self):
        self.assertEqual(
            launch.select_backend("kindle", "framebuffer", capable=True, running=True),
            "framebuffer",
        )
        for family, capable, running in (
            ("kindle", False, False),
            ("kindle", True, False),
            ("kobo", False, True),
        ):
            with self.subTest(family=family, capable=capable, running=running):
                with self.assertRaises(ValueError):
                    launch.select_backend(
                        family, "x11", capable=capable, running=running
                    )

    def test_x11_capability_uses_installed_firmware_interfaces(self):
        job = Mock()
        job.is_file.return_value = True
        with (
            patch.object(launch, "X11_JOB", job),
            patch.object(launch.os, "access", return_value=True),
        ):
            self.assertTrue(launch.stock_x11_capable("kindle"))
            self.assertFalse(launch.stock_x11_capable("kobo"))
            job.is_file.return_value = False
            self.assertFalse(launch.stock_x11_capable("kindle"))

    def test_prelaunch_honors_config_path_before_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            environment_config = root / "environment.json"
            explicit_config = root / "explicit.json"
            environment_config.write_text(json.dumps({"qt_backend": "x11"}))
            explicit_config.write_text(json.dumps({"qt_backend": "framebuffer"}))
            socket = Mock()
            socket.is_socket.return_value = True
            with (
                patch.dict(
                    os.environ, {"KTRMNL_CONFIG": str(environment_config)}, clear=True
                ),
                patch.object(launch, "stock_x11_capable", return_value=True),
                patch.object(launch, "X11_SOCKET", socket),
                patch.object(launch.os, "execv") as execute,
            ):
                self.assertEqual(launch.main(["kindle", "--menu"]), 0)
                self.assertEqual(os.environ["QT_QPA_PLATFORM"], "xcb")
                arguments = execute.call_args.args[1]
                self.assertEqual(
                    arguments[arguments.index("--config") + 1], str(environment_config)
                )

                self.assertEqual(
                    launch.main(["kindle", "--config", str(explicit_config), "--menu"]),
                    0,
                )
                self.assertEqual(os.environ["QT_QPA_PLATFORM"], "ereader")
                self.assertEqual(os.environ["KTRMNL_X11_AVAILABLE"], "1")
                self.assertNotIn("DISPLAY", os.environ)
                arguments = execute.call_args.args[1]
                self.assertEqual(
                    arguments[arguments.index("--config") + 1], str(explicit_config)
                )
                self.assertEqual(arguments[-1], "--menu")
                self.assertEqual(
                    arguments[1:4], ["-m", "k2.adapters.session", "kindle"]
                )

    def test_unavailable_explicit_x11_does_not_start_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps({"qt_backend": "x11"}))
            socket = Mock()
            socket.is_socket.return_value = False
            with (
                patch.object(launch, "stock_x11_capable", return_value=True),
                patch.object(launch, "X11_SOCKET", socket),
                patch.object(launch.os, "execv") as execute,
                contextlib.redirect_stderr(io.StringIO()) as error,
            ):
                self.assertEqual(launch.main(["kindle", "--config", str(path)]), 2)
                self.assertIn("Stock X11 is not running", error.getvalue())
                execute.assert_not_called()

    def test_missing_setting_is_automatic_but_invalid_setting_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            self.assertEqual(configured_qt_backend(path), "auto")
            path.write_text("{}")
            self.assertEqual(configured_qt_backend(path), "auto")
            path.write_text('{"qt_backend":"invalid"}')
            with self.assertRaisesRegex(ValueError, "qt_backend"):
                configured_qt_backend(path)


if __name__ == "__main__":
    unittest.main()
