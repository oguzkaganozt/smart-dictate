"""Unit tests for voxtype-clean-dictation pure logic.

Stdlib only (unittest) to match the no-dependencies constraint. The script
has no .py extension and runs as an executable, so we load it by path.
Importing it only reads config/env at module level (no network, no exit),
which is safe under test.

Run: python3 -m unittest discover -s tests
"""
import importlib.util
import io
import json
import sys
import unittest
import urllib.error
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "voxtype-clean-dictation"


def _load():
    # The script has no .py suffix, so spec_from_file_location can't infer a
    # loader. Use SourceFileLoader explicitly to load it as a Python module.
    loader = SourceFileLoader("voxtype_clean_dictation", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


cd = _load()

# Long enough to pass should_skip (>=90 chars, >=14 words, no code markers).
_LONG = " ".join(["word"] * 40)
_UNSET = object()


class ShouldSkipTests(unittest.TestCase):
    def test_empty_and_short_pass_through(self):
        self.assertTrue(cd.should_skip(""))
        self.assertTrue(cd.should_skip("merhaba"))
        self.assertTrue(cd.should_skip("hello there friend"))

    def test_long_sentence_is_cleaned(self):
        # >=90 chars AND >=14 words, no code markers -> not skipped.
        text = " ".join(["word"] * 20)  # 20 words, 99 chars
        self.assertGreaterEqual(len(text), 90)
        self.assertFalse(cd.should_skip(text))

    def test_char_boundary(self):
        # 89-char single token: len < 90 and 1 word < 14 -> skip.
        self.assertTrue(cd.should_skip("a" * 89))
        # 90-char single token: len not < 90, no marker -> not skipped.
        self.assertFalse(cd.should_skip("a" * 90))

    def test_word_boundary(self):
        # 13 short words: both conditions true -> skip.
        self.assertTrue(cd.should_skip(" ".join(["a"] * 13)))
        # 14 short words (< 90 chars but words not < 14), no marker -> not skip.
        self.assertFalse(cd.should_skip(" ".join(["a"] * 14)))

    def test_code_markers_force_skip(self):
        for marker in ["&&", "||", "sudo ", "git ", "docker ", "systemctl ",
                       "journalctl ", "~/", "./", "--"]:
            # Long, many-worded text that would otherwise be cleaned.
            text = " ".join(["word"] * 30) + " " + marker + "thing"
            self.assertFalse(cd.should_skip(" ".join(["word"] * 30)),
                             "control: marker-free long text is cleaned")
            self.assertTrue(cd.should_skip(text), f"marker {marker!r} should skip")


class OutputTooLongTests(unittest.TestCase):
    def test_similar_length_ok(self):
        self.assertFalse(cd.output_too_long("a" * 100, "b" * 100))

    def test_short_input_uses_additive_floor(self):
        # max(7.5, 125) = 125; 200 > 125 -> too long.
        self.assertTrue(cd.output_too_long("hello", "x" * 200))
        self.assertFalse(cd.output_too_long("hello", "x" * 120))

    def test_long_input_uses_multiplier(self):
        # max(1500, 1120) = 1500.
        self.assertFalse(cd.output_too_long("a" * 1000, "b" * 1400))
        self.assertTrue(cd.output_too_long("a" * 1000, "b" * 1600))


class MainFailOpenTests(unittest.TestCase):
    """main() must never crash or lose the transcription on any failure.

    The fail-open contract is the core safety property of the VoxType
    post-processor: on network error, missing auth, parse error, empty
    response, or oversized output, the original text is emitted unchanged so
    the daemon never blocks. These tests lock that contract end-to-end.
    """

    def _run(self, stdin_text=_LONG, *, side_effect=_UNSET, return_value=_UNSET):
        kwargs = {}
        if side_effect is not _UNSET:
            kwargs["side_effect"] = side_effect
        elif return_value is not _UNSET:
            kwargs["return_value"] = return_value
        with mock.patch.object(cd, "clean", **kwargs) as clean_mock, \
             mock.patch.object(cd, "_notify") as notify_mock:
            old_in, old_out = sys.stdin, sys.stdout
            sys.stdin = io.StringIO(stdin_text)
            out = io.StringIO()
            sys.stdout = out
            try:
                rc = cd.main()
            finally:
                sys.stdin, sys.stdout = old_in, old_out
        return rc, out.getvalue(), clean_mock, notify_mock

    def test_network_error_emits_original(self):
        rc, out, clean, _ = self._run(side_effect=urllib.error.URLError("boom"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, _LONG)
        self.assertTrue(clean.called)

    def test_timeout_emits_original(self):
        rc, out, _, _ = self._run(side_effect=TimeoutError())
        self.assertEqual(rc, 0)
        self.assertEqual(out, _LONG)

    def test_missing_auth_emits_original(self):
        rc, out, _, _ = self._run(side_effect=RuntimeError("no api key"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, _LONG)

    def test_parse_error_emits_original(self):
        rc, out, _, _ = self._run(
            side_effect=json.JSONDecodeError("no json", "{", 0))
        self.assertEqual(rc, 0)
        self.assertEqual(out, _LONG)

    def test_oserror_emits_original(self):
        rc, out, _, _ = self._run(side_effect=OSError("boom"))
        self.assertEqual(rc, 0)
        self.assertEqual(out, _LONG)

    def test_empty_response_emits_original(self):
        rc, out, _, _ = self._run(return_value="")
        self.assertEqual(rc, 0)
        self.assertEqual(out, _LONG)

    def test_oversized_output_emits_original(self):
        rc, out, _, _ = self._run(return_value="x" * 400)
        self.assertEqual(rc, 0)
        self.assertEqual(out, _LONG)

    def test_success_emits_cleaned(self):
        rc, out, _, notify = self._run(return_value="cleaned text")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "cleaned text")
        self.assertTrue(notify.called)

    def test_short_text_passes_through_without_clean(self):
        rc, out, clean, _ = self._run("merhaba")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "merhaba")
        self.assertFalse(clean.called)

    def test_empty_input_writes_nothing(self):
        rc, out, clean, _ = self._run("")
        self.assertEqual(rc, 0)
        self.assertEqual(out, "")
        self.assertFalse(clean.called)


class ContextualCleanTests(unittest.TestCase):
    def _clean(self, cfg, *, snapshot=None, live_path="", live_b64=""):
        patches = [
            mock.patch.object(cd.groq, "get_api_key", return_value="key"),
            mock.patch.object(cd.groq, "call_groq", return_value="cleaned"),
            mock.patch.object(cd.relay_context, "read_dictation_context",
                              return_value=("ghostty", "terminal")),
            mock.patch.object(cd.relay_context, "load_snapshot", return_value=snapshot),
            mock.patch.object(cd.relay_context, "capture_live_screenshot",
                              return_value=live_path),
            mock.patch.object(cd.relay_context, "encode_image_b64",
                              return_value=live_b64),
            mock.patch.object(cd.relay_settings, "load", return_value=cfg),
        ]
        entered = [p.start() for p in patches]
        try:
            output = cd.clean("a long dictated sentence for cleanup")
            return output, entered
        finally:
            for p in reversed(patches):
                p.stop()

    def test_right_ctrl_visual_default_off_does_not_capture(self):
        cfg = {
            "context_sharing": True,
            "context_sharing_consented": True,
            "right_ctrl_visual_context": False,
        }
        output, mocks = self._clean(cfg)
        self.assertEqual(output, "cleaned")
        capture_mock = mocks[4]
        self.assertFalse(capture_mock.called)

    def test_right_ctrl_visual_off_ignores_sidecar_image(self):
        cfg = {
            "context_sharing": True,
            "context_sharing_consented": True,
            "right_ctrl_visual_context": False,
        }
        snapshot = {"has_image": True, "screenshot_path": "/tmp/sidecar.png"}
        with mock.patch.object(cd.relay_context, "context_image_b64") as image:
            self._clean(cfg, snapshot=snapshot)
        image.assert_not_called()

    def test_right_ctrl_visual_captures_when_opted_in(self):
        cfg = {
            "context_sharing": True,
            "context_sharing_consented": True,
            "right_ctrl_visual_context": True,
        }
        with mock.patch.object(cd.relay_context, "delete_screenshot") as delete:
            output, mocks = self._clean(
                cfg, live_path="/tmp/right-ctrl.png", live_b64="ZmFrZQ==")
        self.assertEqual(output, "cleaned")
        self.assertTrue(mocks[4].called)
        delete.assert_called_once_with("/tmp/right-ctrl.png")

    def test_right_ctrl_visual_privacy_gate_blocks_capture(self):
        cfg = {
            "context_sharing": False,
            "context_sharing_consented": True,
            "right_ctrl_visual_context": True,
        }
        _output, mocks = self._clean(cfg)
        self.assertFalse(mocks[4].called)

    def test_context_sharing_off_blocks_app_title_capture(self):
        cfg = {
            "context_sharing": False,
            "context_sharing_consented": True,
            "right_ctrl_visual_context": True,
        }
        _output, mocks = self._clean(cfg)
        self.assertFalse(mocks[2].called)

    def test_settings_text_model_used_without_image(self):
        cfg = {
            "context_sharing": True,
            "context_sharing_consented": True,
            "right_ctrl_visual_context": False,
            "text_model": "custom/text",
        }
        with mock.patch.object(cd.groq, "resolve_model", return_value="custom/text") as resolve:
            output, _ = self._clean(cfg)
        self.assertEqual(output, "cleaned")
        resolve.assert_called_once_with(cd._cfg["groq"], user_model="custom/text")

    def test_cloud_processing_off_returns_input_without_remote_call(self):
        cfg = {
            "cloud_processing": False,
            "context_sharing": True,
            "context_sharing_consented": True,
            "right_ctrl_visual_context": True,
        }
        with mock.patch.object(cd.relay_settings, "load", return_value=cfg), \
             mock.patch.object(cd.groq, "get_api_key") as key, \
             mock.patch.object(cd.groq, "call_groq") as call, \
             mock.patch.object(cd.relay_context,
                               "capture_live_screenshot") as capture:
            output = cd.clean("original dictated text")
        self.assertEqual(output, "original dictated text")
        key.assert_not_called()
        call.assert_not_called()
        capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
