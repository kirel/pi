"""Test credential rendering with public test vectors, never real secrets."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "wifi", pathlib.Path(__file__).parents[1] / "files" / "provision_wifi.py"
)
wifi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wifi)


class WifiRenderingTest(unittest.TestCase):
    def settings(self):
        return {"country": "DE", "profiles": [{
            "name": "home", "ssid_ref": "ssid", "password_ref": "password",
        }]}

    def test_public_wpa2_test_vector(self):
        with patch.object(wifi, "read_field", side_effect=[b"IEEE", b"password"]):
            result = wifi.render(self.settings()).decode()
        self.assertIn("psk=f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e", result)
        self.assertNotIn("password", result)

    def test_ssid_cannot_inject_configuration(self):
        ssid = b'evil"\nnetwork={'
        with patch.object(wifi, "read_field", side_effect=[ssid, b"password"]):
            result = wifi.render(self.settings()).decode()
        self.assertIn("ssid=" + ssid.hex(), result)
        self.assertEqual(result.count("network={"), 1)

    def test_multiple_profiles_keep_independent_priorities(self):
        settings = self.settings()
        settings["profiles"][0]["priority"] = 10
        settings["profiles"].append({"name": "offsite", "ssid_ref": "ssid2",
                                     "password_ref": "password2", "priority": 5})
        with patch.object(wifi, "read_field", side_effect=[b"home", b"password", b"offsite", b"anotherpass"]):
            result = wifi.render(settings).decode()
        self.assertEqual(result.count("network={"), 2)
        self.assertIn("priority=10", result)
        self.assertIn("priority=5", result)

    def test_invalid_passphrase_rejected(self):
        with patch.object(wifi, "read_field", side_effect=[b"home", b"short"]):
            with self.assertRaises(ValueError):
                wifi.render(self.settings())

    def test_literal_ssid_reads_only_password(self):
        settings = self.settings()
        profile = settings["profiles"][0]
        del profile["ssid_ref"]
        profile["ssid"] = "IEEE"
        with patch.object(wifi, "read_field", return_value=b"password") as reader:
            result = wifi.render(settings).decode()
        reader.assert_called_once_with("password")
        self.assertIn("psk=f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e", result)

    def test_ambiguous_ssid_rejected(self):
        settings = self.settings()
        settings["profiles"][0]["ssid"] = "IEEE"
        with self.assertRaises(ValueError):
            wifi.render(settings)


if __name__ == "__main__":
    unittest.main()
