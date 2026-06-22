"""Unit tests for voxtype-clean-dictation pure logic.

Stdlib only (unittest) to match the no-dependencies constraint. The script
has no .py extension and runs as an executable, so we load it by path.
Importing it only reads config/env at module level (no network, no exit),
which is safe under test.

Run: python3 -m unittest discover -s tests
"""
import importlib.util
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
