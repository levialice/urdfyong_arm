import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "rdkx5_wifi_provision.py"

spec = importlib.util.spec_from_file_location("rdkx5_wifi_provision", MODULE_PATH)
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


class FakeRunner:
    def __init__(self, outputs=None):
        self.outputs = outputs or []
        self.calls = []

    def __call__(self, args, timeout=10, check=False):
        self.calls.append((args, timeout, check))
        if self.outputs:
            return self.outputs.pop(0)
        return ""


class NmcliHelperTest(unittest.TestCase):
    def test_connect_wifi_passes_ssid_and_password_as_args(self):
        runner = FakeRunner([""])
        nm = provision.Nmcli(runner=runner)

        nm.connect_wifi("Lab WiFi", "pw with spaces")

        self.assertEqual(
            runner.calls[0][0],
            ["nmcli", "device", "wifi", "connect", "Lab WiFi", "password", "pw with spaces"],
        )

    def test_connected_wifi_detects_connected_wireless_device(self):
        runner = FakeRunner(["wlan0:wifi:connected:levi\neth0:ethernet:unavailable:\n"])
        nm = provision.Nmcli(runner=runner)

        self.assertTrue(nm.has_connected_wifi("wlan0"))


class WebRenderingTest(unittest.TestCase):
    def test_render_index_contains_setup_address_and_form(self):
        html = provision.render_index([{"ssid": "levi", "signal": "90", "security": "WPA2"}], "")

        self.assertIn("RDKX5-Setup", html)
        self.assertIn("192.168.88.1", html)
        self.assertIn('name="ssid"', html)
        self.assertIn('name="password"', html)

    def test_parse_wifi_list_ignores_blank_ssids(self):
        rows = provision.parse_wifi_list("levi:90:WPA2\n:80:WPA2\nGuest:50:\n")

        self.assertEqual([row["ssid"] for row in rows], ["levi", "Guest"])

    def test_load_networks_rescans_before_listing(self):
        runner = FakeRunner(["", "levi:90:WPA2\nGuest:60:\n"])
        nm = provision.Nmcli(runner=runner)

        rows = provision.load_networks(nm)

        self.assertEqual([row["ssid"] for row in rows], ["levi", "Guest"])
        self.assertEqual(runner.calls[0][0], ["nmcli", "device", "wifi", "rescan"])
        self.assertEqual(
            runner.calls[1][0],
            ["nmcli", "--terse", "--fields", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
        )


class BootBehaviorTest(unittest.TestCase):
    def test_does_not_start_hotspot_when_wifi_is_connected(self):
        runner = FakeRunner(["wlan0:wifi:connected:levi\n"])
        nm = provision.Nmcli(runner=runner)

        result = provision.ensure_provisioning_mode(nm, iface="wlan0", wait_seconds=0)

        self.assertEqual(result, "connected")
        self.assertFalse(any("RDKX5-Setup" in " ".join(call[0]) for call in runner.calls))

    def test_starts_open_hotspot_when_wifi_is_not_connected(self):
        runner = FakeRunner(["wlan0:wifi:disconnected:\n", "", "", "", "", "", ""])
        nm = provision.Nmcli(runner=runner)

        result = provision.ensure_provisioning_mode(nm, iface="wlan0", wait_seconds=0)

        self.assertEqual(result, "hotspot")
        commands = [" ".join(call[0]) for call in runner.calls]
        self.assertTrue(any("con add type wifi" in cmd and "RDKX5-Setup" in cmd for cmd in commands))
        self.assertTrue(any("ipv4.addresses 192.168.88.1/24" in cmd for cmd in commands))


class ConnectFormTest(unittest.TestCase):
    def test_connect_from_form_connects_wifi_and_stops_hotspot(self):
        runner = FakeRunner(["", ""])
        nm = provision.Nmcli(runner=runner)

        success, message = provision.connect_from_form(nm, b"ssid=Lab+WiFi&password=secret+pw")

        self.assertTrue(success)
        self.assertIn("Lab WiFi", message)
        self.assertEqual(
            runner.calls[0][0],
            ["nmcli", "device", "wifi", "connect", "Lab WiFi", "password", "secret pw"],
        )
        self.assertEqual(runner.calls[1][0], ["nmcli", "con", "down", "RDKX5-Setup"])

    def test_connect_from_form_rejects_missing_ssid(self):
        runner = FakeRunner()
        nm = provision.Nmcli(runner=runner)

        success, message = provision.connect_from_form(nm, b"password=secret")

        self.assertFalse(success)
        self.assertIn("SSID", message)
        self.assertEqual(runner.calls, [])


class CliDefaultsTest(unittest.TestCase):
    def test_arg_parser_defaults_match_design(self):
        parser = provision.build_arg_parser()
        args = parser.parse_args(["--serve"])

        self.assertTrue(args.serve)
        self.assertEqual(args.iface, "wlan0")
        self.assertEqual(args.wait_seconds, 30)
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 80)


if __name__ == "__main__":
    unittest.main()
