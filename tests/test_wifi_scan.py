from __future__ import annotations

import unittest
from enum import IntEnum
from types import SimpleNamespace

from PyQt5.QtCore import QObject

from ktrmnl.network.wifi import WifiLink, WifiManager


class WifiScanTests(unittest.TestCase):
    def test_hidden_and_blank_ssids_are_excluded_and_strongest_bssid_wins(self):
        wifi = WifiManager.__new__(WifiManager)
        QObject.__init__(wifi)
        wifi._link = WifiLink.CONNECTED
        wifi._connected_ssid = "Visible"
        security = IntEnum("Security", {"WPA_PSK": 1}).WPA_PSK
        wifi._selected_ssid = ""
        points = [
            SimpleNamespace(ssid="Visible", signal_dbm=-42, security=security),
            SimpleNamespace(ssid="Visible", signal_dbm=-60, security=security),
            SimpleNamespace(ssid="", signal_dbm=-50, security=security),
            SimpleNamespace(ssid="   ", signal_dbm=-60, security=security),
        ]
        wifi._replace_networks(
            points, [], SimpleNamespace(security_write=1 << security)
        )
        self.assertEqual(
            wifi.networks,
            [
                {
                    "ssid": "Visible",
                    "signal": -42,
                    "security": "WPA2",
                    "secured": True,
                    "connected": True,
                    "saved": False,
                    "profile_id": "",
                    "password_editable": True,
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
