from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from ktrmnl.device.display import DisplayError, StockDisplayBackend


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.display = StockDisplayBackend()
        self.refresh = Mock()
        self.window = Mock()
        with patch.object(self.display, "_load_platform"):
            self.display.attach(self.window, self.refresh)

    def test_full_refresh_requests_compositor_cleanup_and_redraw(self):
        self.display.full_refresh()
        self.refresh.request_cleanup.assert_called_once_with(full=True)
        self.window.update.assert_called_once()

    def test_night_mode_and_rotation_do_not_change_global_display(self):
        self.display.set_night_mode(True)
        self.display.set_rotation(90)
        self.assertEqual(self.refresh.mock_calls, [])
        self.assertEqual(self.window.mock_calls, [])
        with self.assertRaises(DisplayError):
            self.display.set_rotation(45)

    def test_refresh_flush_uses_window_compositor(self):
        self.display.wait_for_refresh()
        self.refresh.flush_pending.assert_called_once()

    def test_close_releases_compositor_connection(self):
        self.display.close()
        self.display.close()
        self.refresh.close.assert_called_once()

    def test_platform_refresh_waits_for_panel_before_sleep(self):
        self.display._refresh = None
        platform = Mock()
        self.display._platform = platform
        self.display.full_refresh()
        platform.ereader_request_full_refresh.assert_called_once()
        self.window.update.assert_called_once()
        platform.ereader_wait_for_refresh.return_value = False
        with self.assertRaises(DisplayError):
            self.display.wait_for_refresh()
        platform.ereader_wait_for_refresh.return_value = True
        self.display.wait_for_refresh()

    def test_interactive_mode_is_applied_when_the_platform_attaches(self):
        self.display.set_interactive_mode(True)
        platform = Mock()
        with patch.object(
            self.display,
            "_load_platform",
            side_effect=lambda: setattr(self.display, "_platform", platform),
        ):
            self.display.attach(self.window, None)
        platform.ereader_set_interactive_mode.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
