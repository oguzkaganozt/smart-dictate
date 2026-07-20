"""Unit tests for the Relay action registry and context formatter (stdlib only).

Locks the V2 Relay Bar contract: the action set, ids, kinds, and the
context-line format so the bar UI and the future action runner can't drift.
"""
import importlib.util
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parent.parent / "scripts" / "_relay_actions.py"


def _load():
    spec = importlib.util.spec_from_file_location("_relay_actions", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


actions = _load()


class ActionRegistryTests(unittest.TestCase):
    def test_ids_are_unique_and_ordered(self):
        ids = actions.action_ids()
        self.assertEqual(ids, ["dictate", "rewrite", "shorten", "translate",
                               "summarize", "explain", "custom"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_action_has_id_label_kind(self):
        for a in actions.ACTIONS:
            self.assertIn("id", a)
            self.assertIn("label", a)
            self.assertIn("kind", a)
            self.assertTrue(a["id"])
            self.assertTrue(a["label"])

    def test_kinds_are_known(self):
        valid = {"dictation", "transform", "result", "custom"}
        for a in actions.ACTIONS:
            self.assertIn(a["kind"], valid)

    def test_dictate_is_first(self):
        self.assertEqual(actions.ACTIONS[0]["id"], "dictate")

    def test_action_by_id_found(self):
        self.assertEqual(actions.action_by_id("rewrite")["kind"], "transform")

    def test_action_by_id_missing_returns_none(self):
        self.assertIsNone(actions.action_by_id("nope"))

    def test_visible_actions_matches_all(self):
        self.assertEqual(actions.visible_actions(), actions.ACTIONS)


class DictationCommandTests(unittest.TestCase):
    def test_command_is_voxtype_record_toggle(self):
        self.assertEqual(actions.dictation_command(), ["voxtype", "record", "toggle"])

    def test_returns_a_copy(self):
        a = actions.dictation_command()
        a.append("mutated")
        self.assertEqual(actions.dictation_command(), ["voxtype", "record", "toggle"])

    def test_does_not_block_or_capture_audio(self):
        # toggle only signals the daemon; it must not be a recording command.
        cmd = actions.dictation_command()
        self.assertNotIn("start", cmd)
        self.assertNotIn("transcribe", cmd)


class ActionSpecTests(unittest.TestCase):
    def test_every_action_id_has_a_spec(self):
        for a in actions.ACTIONS:
            if a["id"] == "dictate":
                continue  # dictation is launched, not a Groq action
            self.assertIn(a["id"], actions.ACTION_SPECS,
                           f"missing ACTION_SPECS for {a['id']}")

    def test_specs_have_required_fields(self):
        for aid, spec in actions.ACTION_SPECS.items():
            self.assertIn("system", spec)
            self.assertIn("user", spec)
            self.assertIn("temperature", spec)
            self.assertIn("ceiling", spec)
            self.assertIn("{text}", spec["user"])

    def test_custom_spec_forbids_external_effect(self):
        # V2: Custom Action produces text only; no commands/files/messages.
        s = actions.ACTION_SPECS["custom"]["system"]
        self.assertTrue(any(w in s.lower() for w in ("not execute", "no command", "text only", "do not execute")))
        self.assertTrue("external" in s.lower() or "affect" in s.lower())


class BuildMessagesTests(unittest.TestCase):
    def test_rewrite_includes_text(self):
        sys_, user = actions.build_messages("rewrite", "hello world")
        self.assertIn("hello world", user)
        self.assertIn("rewritten text", sys_.lower() or sys_)

    def test_translate_uses_target_lang(self):
        _, user = actions.build_messages("translate", "hi", target_lang="Turkish")
        self.assertIn("Turkish", user)

    def test_custom_uses_instruction(self):
        _, user = actions.build_messages("custom", "hi", instruction="make it a haiku")
        self.assertIn("make it a haiku", user)

    def test_context_appended_as_data(self):
        _, user = actions.build_messages("rewrite", "hi",
                                          context_text="DATA ONLY\nActive app: x")
        self.assertIn("DATA ONLY", user)


class _FakeGroq:
    def __init__(self, output="result", fail=None, no_key=False):
        self._output = output
        self._fail = fail
        self._no_key = no_key
        self.last_payload = None
        self.vision_model_called = False

    def load_config(self, *sections):
        return {s: {} for s in sections}

    def resolve_model(self, cfg, section=None, prefix=None, user_model=""):
        return user_model or "text-model"

    def resolve_vision_model(self, cfg, section=None, prefix=None, user_model=""):
        self.vision_model_called = True
        return user_model or "vision-model"

    def resolve_endpoint(self, cfg, section=None, prefix=None):
        return "https://fake"

    def get_api_key(self, cfg=None):
        return "" if self._no_key else "key"

    def build_payload(self, model, system, user_content, *, temperature, max_completion_tokens):
        self.last_payload = {"model": model, "system": system, "user_content": user_content,
                              "temperature": temperature,
                              "max_completion_tokens": max_completion_tokens}
        return self.last_payload

    def token_budget(self, input_text, system, *, ceiling=4096, **kw):
        return 512

    def text_image_content(self, text, image_b64):
        if not image_b64:
            return text
        return [{"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": f"data:...{image_b64[:8]}"}}]

    def call_groq(self, endpoint, api_key, payload, *, timeout, user_agent):
        if self._fail:
            raise self._fail
        return self._output


class RunActionTests(unittest.TestCase):
    def test_success_returns_output(self):
        groq = _FakeGroq(output="cleaned")
        out, err = actions.run_action("rewrite", "hello", groq)
        self.assertEqual(out, "cleaned")
        self.assertIsNone(err)

    def test_cloud_off_returns_error(self):
        # V2: cloud processing off -> remote actions unavailable.
        out, err = actions.run_action("rewrite", "hello", _FakeGroq(),
                                      cloud_processing=False)
        self.assertIsNone(out)
        self.assertIn("cloud", err.lower())

    def test_no_api_key_returns_error(self):
        out, err = actions.run_action("rewrite", "hello", _FakeGroq(no_key=True))
        self.assertIsNone(out)
        self.assertIn("api_key", err.lower())

    def test_unknown_action(self):
        out, err = actions.run_action("nope", "hello", _FakeGroq())
        self.assertIsNone(out)
        self.assertIn("unknown", err)

    def test_empty_input(self):
        out, err = actions.run_action("rewrite", "  ", _FakeGroq())
        self.assertIsNone(out)
        self.assertIn("no input", err)

    def test_too_long_input(self):
        out, err = actions.run_action("rewrite", "a" * (actions.MAX_INPUT + 1), _FakeGroq())
        self.assertIsNone(out)
        self.assertIn("too long", err)

    def test_http_error_returns_error_not_raise(self):
        import urllib.error
        out, err = actions.run_action("rewrite", "hello",
                                       _FakeGroq(fail=urllib.error.HTTPError("u", 429, "rate", {}, None)))
        self.assertIsNone(out)
        self.assertIn("429", err)

    def test_empty_output_returns_error(self):
        out, err = actions.run_action("rewrite", "hello", _FakeGroq(output=""))
        self.assertIsNone(out)
        self.assertIn("empty", err)

    def test_generic_error_returns_error_not_raise(self):
        out, err = actions.run_action("rewrite", "hello", _FakeGroq(fail=RuntimeError("boom")))
        self.assertIsNone(out)
        self.assertIn("RuntimeError", err)

    def test_context_passed_when_provided(self):
        groq = _FakeGroq(output="ok")
        actions.run_action("rewrite", "hi", groq,
                           context_text="DATA ONLY\nActive app: ghostty")
        self.assertIn("DATA ONLY", groq.last_payload["user_content"])

    def test_vision_model_used_when_image_and_sharing_on(self):
        # V2 step 10: context sharing on + image -> vision model + multimodal.
        groq = _FakeGroq(output="ok")
        actions.run_action("explain", "describe this", groq,
                           context_sharing=True, image_b64="ZmFrZQ==")
        self.assertTrue(groq.vision_model_called)
        self.assertIsInstance(groq.last_payload["user_content"], list)

    def test_text_model_when_no_image_even_if_sharing_on(self):
        groq = _FakeGroq(output="ok")
        actions.run_action("rewrite", "hi", groq, context_sharing=True, image_b64=None)
        self.assertFalse(groq.vision_model_called)
        self.assertEqual(groq.last_payload["model"], "text-model")
        self.assertIsInstance(groq.last_payload["user_content"], str)

    def test_image_ignored_when_context_sharing_off(self):
        # V2: context sharing off -> image never sent, even if present.
        groq = _FakeGroq(output="ok")
        actions.run_action("explain", "hi", groq,
                           context_sharing=False, image_b64="ZmFrZQ==")
        self.assertFalse(groq.vision_model_called)
        self.assertIsInstance(groq.last_payload["user_content"], str)

    def test_image_ignored_when_cloud_off(self):
        # cloud off wins: no call at all.
        out, err = actions.run_action("explain", "hi", _FakeGroq(),
                                      cloud_processing=False,
                                      context_sharing=True, image_b64="ZmFrZQ==")
        self.assertIsNone(out)
        self.assertIn("cloud", err.lower())

    def test_settings_text_model_override_used(self):
        groq = _FakeGroq(output="ok")
        actions.run_action("rewrite", "hi", groq, text_model="custom/text")
        self.assertEqual(groq.last_payload["model"], "custom/text")

    def test_settings_vision_model_override_used(self):
        groq = _FakeGroq(output="ok")
        actions.run_action(
            "explain", "hi", groq,
            context_sharing=True, image_b64="ZmFrZQ==",
            vision_model="custom/vision")
        self.assertEqual(groq.last_payload["model"], "custom/vision")


class FormatContextTests(unittest.TestCase):
    def test_full_context_matches_v2_mockup(self):
        self.assertEqual(
            actions.format_context("Firefox", has_selection=True, has_image=True),
            "Context: Firefox · Selected text · Image",
        )

    def test_no_app_shows_unknown(self):
        self.assertTrue(actions.format_context(has_selection=True).startswith("Context: Unknown app"))

    def test_empty_app_shows_unknown(self):
        self.assertTrue(
            actions.format_context("   ", has_selection=True, has_image=True)
            .startswith("Context: Unknown app"),
        )

    def test_missing_sources_stated_explicitly(self):
        line = actions.format_context("Ghostty")
        self.assertIn("No selection", line)
        self.assertIn("No image", line)

    def test_separator_is_middot(self):
        self.assertIn(" · ", actions.format_context("Firefox", True, True))

    def test_includes_title_arg_ignored_gracefully(self):
        # title is accepted but not yet rendered in the one-liner (step 9).
        line = actions.format_context("Firefox", title="Inbox", has_selection=True)
        self.assertIn("Firefox", line)


if __name__ == "__main__":
    unittest.main()
