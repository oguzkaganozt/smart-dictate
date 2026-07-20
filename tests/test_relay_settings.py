"""Unit tests for Relay privacy settings (stdlib only)."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE = Path(__file__).resolve().parent.parent / "scripts" / "_relay_settings.py"


def _load():
    spec = importlib.util.spec_from_file_location("_relay_settings", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


settings = _load()


class LoadDefaultsTests(unittest.TestCase):
    def test_missing_file_returns_defaults(self):
        cfg = settings.load(Path("/nonexistent/x.toml"))
        self.assertEqual(cfg, settings.DEFAULTS)

    def test_defaults_cloud_on_context_off_until_consent(self):
        cfg = settings.DEFAULTS
        self.assertTrue(cfg["cloud_processing"])
        self.assertTrue(cfg["context_sharing"])
        self.assertFalse(cfg["context_sharing_consented"])
        self.assertEqual(cfg["text_model"], "")
        self.assertEqual(cfg["vision_model"], "")
        self.assertFalse(cfg["right_ctrl_visual_context"])


class LoadFileTests(unittest.TestCase):
    def test_parses_privacy_section(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("[privacy]\ncloud_processing = false\ncontext_sharing = true\ncontext_sharing_consented = true\n")
            p = Path(f.name)
        try:
            cfg = settings.load(p)
        finally:
            p.unlink()
        self.assertFalse(cfg["cloud_processing"])
        self.assertTrue(cfg["context_sharing"])
        self.assertTrue(cfg["context_sharing_consented"])

    def test_malformed_file_falls_back_to_defaults(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write("not valid toml {{{")
            p = Path(f.name)
        try:
            cfg = settings.load(p)
        finally:
            p.unlink()
        self.assertEqual(cfg, settings.DEFAULTS)

    def test_non_bool_values_ignored(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[privacy]\ncloud_processing = "yes"\n')
            p = Path(f.name)
        try:
            cfg = settings.load(p)
        finally:
            p.unlink()
        self.assertTrue(cfg["cloud_processing"])  # default kept

    def test_parses_models_and_dictation_sections(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write(
                '[models]\ntext_model = "qwen/custom"\n'
                'vision_model = "meta-llama/vision"\n'
                '[dictation]\nright_ctrl_visual_context = true\n')
            p = Path(f.name)
        try:
            cfg = settings.load(p)
        finally:
            p.unlink()
        self.assertEqual(cfg["text_model"], "qwen/custom")
        self.assertEqual(cfg["vision_model"], "meta-llama/vision")
        self.assertTrue(cfg["right_ctrl_visual_context"])

    def test_invalid_model_in_file_falls_back_to_auto(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[models]\ntext_model = "bad model; rm -rf /"\n')
            p = Path(f.name)
        try:
            cfg = settings.load(p)
        finally:
            p.unlink()
        self.assertEqual(cfg["text_model"], "")


class SaveRoundtripTests(unittest.TestCase):
    def test_save_then_load(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.toml"
            settings.save({"cloud_processing": False, "context_sharing": False,
                           "context_sharing_consented": True}, p)
            cfg = settings.load(p)
        self.assertFalse(cfg["cloud_processing"])
        self.assertFalse(cfg["context_sharing"])
        self.assertTrue(cfg["context_sharing_consented"])

    def test_save_drops_unknown_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.toml"
            settings.save({"cloud_processing": True, "bogus": "x"}, p)
            text = p.read_text()
        self.assertIn("[privacy]", text)
        self.assertNotIn("bogus", text)

    def test_save_roundtrips_models_and_right_ctrl_visual(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.toml"
            settings.save({
                "text_model": "qwen/custom",
                "vision_model": "meta-llama/vision",
                "right_ctrl_visual_context": True,
            }, p)
            cfg = settings.load(p)
        self.assertEqual(cfg["text_model"], "qwen/custom")
        self.assertEqual(cfg["vision_model"], "meta-llama/vision")
        self.assertTrue(cfg["right_ctrl_visual_context"])


class EnabledTests(unittest.TestCase):
    def test_cloud_enabled_default(self):
        self.assertTrue(settings.cloud_processing_enabled({"cloud_processing": True}))

    def test_cloud_disabled(self):
        self.assertFalse(settings.cloud_processing_enabled({"cloud_processing": False}))

    def test_context_sharing_requires_consent(self):
        # V2: context sharing on ONLY after consent.
        self.assertFalse(settings.context_sharing_enabled(
            {"context_sharing": True, "context_sharing_consented": False}))
        self.assertTrue(settings.context_sharing_enabled(
            {"context_sharing": True, "context_sharing_consented": True}))

    def test_context_sharing_off_even_if_consented(self):
        self.assertFalse(settings.context_sharing_enabled(
            {"context_sharing": False, "context_sharing_consented": True}))

    def test_right_ctrl_visual_requires_toggle_sharing_and_consent(self):
        self.assertFalse(settings.right_ctrl_visual_enabled({
            "right_ctrl_visual_context": False,
            "context_sharing": True,
            "context_sharing_consented": True,
        }))
        self.assertFalse(settings.right_ctrl_visual_enabled({
            "right_ctrl_visual_context": True,
            "context_sharing": False,
            "context_sharing_consented": True,
        }))
        self.assertFalse(settings.right_ctrl_visual_enabled({
            "right_ctrl_visual_context": True,
            "context_sharing": True,
            "context_sharing_consented": False,
        }))
        self.assertTrue(settings.right_ctrl_visual_enabled({
            "right_ctrl_visual_context": True,
            "context_sharing": True,
            "context_sharing_consented": True,
        }))


class ModelValidationTests(unittest.TestCase):
    def test_valid_model_ids(self):
        for value in ("qwen/qwen3.6-27b", "meta-llama/model_v1", "a.b/c-d"):
            self.assertTrue(settings.valid_model_id(value))

    def test_empty_allowed_only_when_requested(self):
        self.assertFalse(settings.valid_model_id(""))
        self.assertTrue(settings.valid_model_id("", allow_empty=True))

    def test_rejects_unsafe_or_malformed_ids(self):
        for value in ("bad model", "model;rm", "$(cmd)", 'model"quote', "a" * 201):
            self.assertFalse(settings.valid_model_id(value))

    def test_model_helpers_sanitize_invalid_values(self):
        self.assertEqual(settings.text_model({"text_model": "qwen/custom"}), "qwen/custom")
        self.assertEqual(settings.text_model({"text_model": "bad model"}), "")
        self.assertEqual(settings.vision_model({"vision_model": "meta/v"}), "meta/v")


class ConsentTests(unittest.TestCase):
    def test_consent_turns_on_and_persists(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.toml"
            cfg = settings.consent_to_context_sharing(p)
            self.assertTrue(cfg["context_sharing"])
            self.assertTrue(cfg["context_sharing_consented"])
            reloaded = settings.load(p)
        self.assertTrue(reloaded["context_sharing_consented"])
        self.assertTrue(settings.context_sharing_enabled(reloaded))


if __name__ == "__main__":
    unittest.main()
