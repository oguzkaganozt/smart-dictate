"""Unit tests for the shared _voxtype_groq module (stdlib only).

Covers the logic the three calling scripts share, so a future refactor
can't silently drift the config precedence, token budget, reasoning_effort
mapping, or payload shape.
"""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MODULE = Path(__file__).resolve().parent.parent / "scripts" / "_voxtype_groq.py"


def _load():
    spec = importlib.util.spec_from_file_location("_voxtype_groq", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


groq = _load()


class ReasoningEffortTests(unittest.TestCase):
    def test_gpt_oss_low(self):
        self.assertEqual(groq.reasoning_effort("openai/gpt-oss-20b"), "low")
        self.assertEqual(groq.reasoning_effort("openai/gpt-oss-120b"), "low")

    def test_qwen_none(self):
        self.assertEqual(groq.reasoning_effort("qwen/qwen3.6-27b"), "none")

    def test_other_omit(self):
        self.assertIsNone(groq.reasoning_effort("llama-3.3-70b-versatile"))
        self.assertIsNone(groq.reasoning_effort("groq/compound"))


class TokenBudgetTests(unittest.TestCase):
    def test_tiny_input_hits_ceiling(self):
        self.assertEqual(groq.token_budget("", ""), 4096)

    def test_huge_input_hits_floor(self):
        self.assertEqual(groq.token_budget("a" * 40000, ""), 512)

    def test_midrange_is_computed(self):
        # 16000//4 + 0 + 20 = 4020 input tokens; 8000 - 4020 - 600 = 3380.
        self.assertEqual(groq.token_budget("a" * 16000, ""), 3380)

    def test_custom_bounds(self):
        self.assertEqual(groq.token_budget("", "", ceiling=1000), 1000)
        self.assertEqual(groq.token_budget("a" * 40000, "", floor=256), 256)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for k in ["GROQ_MODEL", "GROQ_ENDPOINT", "REPHRASE_MODEL",
                  "REPHRASE_ENDPOINT", "SUMMARIZE_MODEL", "SUMMARIZE_ENDPOINT"]:
            os.environ.pop(k, None)

    def tearDown(self):
        self._env.stop()

    def test_default_when_empty(self):
        self.assertEqual(groq.resolve_model({}), groq.DEFAULT_MODEL)
        self.assertEqual(groq.resolve_endpoint({}), groq.DEFAULT_ENDPOINT)

    def test_groq_cfg_used(self):
        self.assertEqual(groq.resolve_model({"model": "m1"}), "m1")

    def test_groq_env_beats_cfg(self):
        os.environ["GROQ_MODEL"] = "envm"
        self.assertEqual(groq.resolve_model({"model": "m1"}), "envm")

    def test_section_cfg_beats_groq(self):
        self.assertEqual(
            groq.resolve_model({"model": "m1"}, {"model": "sec"}, "REPHRASE"),
            "sec",
        )

    def test_prefix_env_wins(self):
        os.environ["REPHRASE_MODEL"] = "pref"
        os.environ["GROQ_MODEL"] = "envm"
        self.assertEqual(
            groq.resolve_model({"model": "m1"}, {"model": "sec"}, "REPHRASE"),
            "pref",
        )

    def test_endpoint_precedence(self):
        os.environ["SUMMARIZE_ENDPOINT"] = "https://sum"
        self.assertEqual(
            groq.resolve_endpoint({"endpoint": "g"}, {"endpoint": "s"}, "SUMMARIZE"),
            "https://sum",
        )


class ApiKeyTests(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("GROQ_API_KEY", None)

    def tearDown(self):
        self._env.stop()

    def test_env_wins(self):
        os.environ["GROQ_API_KEY"] = "envkey"
        self.assertEqual(groq.get_api_key({"api_key": "cfgkey"}), "envkey")

    def test_cfg_used(self):
        with mock.patch.object(groq, "KEY_FILE", Path("/nonexistent/xyz")):
            self.assertEqual(groq.get_api_key({"api_key": "cfgkey"}), "cfgkey")

    def test_key_file_fallback(self):
        with tempfile.NamedTemporaryFile("w", suffix=".key", delete=False) as f:
            f.write("  filekey\n")
            p = Path(f.name)
        try:
            with mock.patch.object(groq, "KEY_FILE", p):
                self.assertEqual(groq.get_api_key({}), "filekey")
        finally:
            p.unlink()

    def test_missing_returns_empty(self):
        with mock.patch.object(groq, "KEY_FILE", Path("/nonexistent/xyz")):
            self.assertEqual(groq.get_api_key({}), "")


class LoadConfigTests(unittest.TestCase):
    def test_missing_file_returns_empty_sections(self):
        with (
            mock.patch.object(groq, "CONFIG_PATH", Path("/nonexistent/c.toml")),
            mock.patch.object(groq, "LEGACY_CONFIG_PATH", Path("/nonexistent/old.toml")),
        ):
            cfg = groq.load_config("groq", "dictation")
        self.assertEqual(cfg, {"groq": {}, "dictation": {}})

    def test_parses_sections(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[groq]\nmodel = "x"\n[rephrase]\nmodel = "y"\n')
            p = Path(f.name)
        try:
            with (
                mock.patch.object(groq, "CONFIG_PATH", p),
                mock.patch.object(groq, "LEGACY_CONFIG_PATH", Path("/nonexistent/old.toml")),
            ):
                cfg = groq.load_config("groq", "rephrase", "summarize")
        finally:
            p.unlink()
        self.assertEqual(cfg["groq"]["model"], "x")
        self.assertEqual(cfg["rephrase"]["model"], "y")
        self.assertEqual(cfg["summarize"], {})

    def test_legacy_config_fallback(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[groq]\nmodel = "legacy"\n')
            p = Path(f.name)
        try:
            with (
                mock.patch.object(groq, "CONFIG_PATH", Path("/nonexistent/new.toml")),
                mock.patch.object(groq, "LEGACY_CONFIG_PATH", p),
            ):
                cfg = groq.load_config("groq")
        finally:
            p.unlink()
        self.assertEqual(cfg["groq"]["model"], "legacy")


class BuildPayloadTests(unittest.TestCase):
    def test_includes_reasoning_for_qwen(self):
        p = groq.build_payload("qwen/q", "sys", "usr",
                               temperature=0.3, max_completion_tokens=512)
        self.assertEqual(p["reasoning_effort"], "none")
        self.assertEqual(p["model"], "qwen/q")
        self.assertEqual(p["temperature"], 0.3)
        self.assertEqual(p["max_completion_tokens"], 512)
        self.assertEqual(p["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(p["messages"][1], {"role": "user", "content": "usr"})

    def test_omits_reasoning_for_other(self):
        p = groq.build_payload("llama-x", "s", "u",
                               temperature=0.0, max_completion_tokens=10)
        self.assertNotIn("reasoning_effort", p)


if __name__ == "__main__":
    unittest.main()
