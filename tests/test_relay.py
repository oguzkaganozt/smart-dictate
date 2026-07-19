"""Unit tests for Relay rename compatibility behavior."""
import importlib.util
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "relay"


def _load():
    loader = SourceFileLoader("relay_cli", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


relay = _load()


class ReleaseAssetTests(unittest.TestCase):
    def test_prefers_relay_archive(self):
        release = {
            "assets": [
                {"name": "smart-dictate-v2.tar.gz"},
                {"name": "SHA256SUMS"},
                {"name": "relay-v2.tar.gz"},
            ]
        }
        tarball, sums = relay._find_assets(release)
        self.assertEqual(tarball["name"], "relay-v2.tar.gz")
        self.assertEqual(sums["name"], "SHA256SUMS")

    def test_accepts_legacy_archive(self):
        release = {
            "assets": [
                {"name": "smart-dictate-v2.tar.gz"},
                {"name": "SHA256SUMS"},
            ]
        }
        tarball, _ = relay._find_assets(release)
        self.assertEqual(tarball["name"], "smart-dictate-v2.tar.gz")

    def test_requires_checksum_asset(self):
        with self.assertRaises(SystemExit):
            relay._find_assets({"assets": [{"name": "relay-v2.tar.gz"}]})


if __name__ == "__main__":
    unittest.main()
