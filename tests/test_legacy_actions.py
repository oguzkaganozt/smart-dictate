"""Cloud-processing gates for the legacy direct action shortcuts."""
import importlib.util
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    path = SCRIPTS / name
    loader = SourceFileLoader(name.replace("-", "_"), str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


rephrase = _load("voxtype-rephrase")
summarize = _load("voxtype-summarize")


class LegacyCloudGateTests(unittest.TestCase):
    def test_rephrase_cloud_off_makes_no_model_or_paste_call(self):
        with mock.patch.object(rephrase, "get_selected_text", return_value="source"), \
             mock.patch.object(rephrase.relay_settings, "load", return_value={
                 "cloud_processing": False}), \
             mock.patch.object(rephrase, "rephrase") as model, \
             mock.patch.object(rephrase, "paste_text") as paste, \
             mock.patch.object(rephrase, "_notify_err") as notify, \
             mock.patch.object(rephrase, "log"):
            rc = rephrase.main()
        self.assertEqual(rc, 1)
        model.assert_not_called()
        paste.assert_not_called()
        notify.assert_called_once()

    def test_summarize_cloud_off_makes_no_model_or_popup_call(self):
        with mock.patch.object(summarize, "get_selected_text", return_value="source"), \
             mock.patch.object(summarize.relay_settings, "load", return_value={
                 "cloud_processing": False}), \
             mock.patch.object(summarize, "summarize") as model, \
             mock.patch.object(summarize, "show_popup") as popup, \
             mock.patch.object(summarize, "_notify_start"), \
             mock.patch.object(summarize, "_notify_err") as notify, \
             mock.patch.object(summarize, "log"):
            rc = summarize.main()
        self.assertEqual(rc, 1)
        model.assert_not_called()
        popup.assert_not_called()
        notify.assert_called_once()


if __name__ == "__main__":
    unittest.main()
