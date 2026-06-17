#!/usr/bin/env python3
"""Benchmark different model/reasoning-effort combos against example-phrase.md."""
import json
import os
import time
import urllib.error
import urllib.request
import tomllib

CFG_PATH = os.path.expanduser("~/.config/smart-dictate/config.toml")
KEY_FILE = os.path.expanduser("~/.config/voxtype/groq-api-key")
PHRASE_PATH = os.path.expanduser("~/codebase/smart-dictate/example-phrase.md")
ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

with open(CFG_PATH, "rb") as f:
    CFG = tomllib.load(f)
API_KEY = open(KEY_FILE).read().strip()
TEXT = open(PHRASE_PATH).read().strip()

SYS_PROMPT = CFG["rephrase"].get(
    "system_prompt",
    "You are an experienced editor. Rewrite the text to be more fluent, natural, and concise. Remove redundancy, filler, and unnecessary words while preserving ALL key information, data, technical terms, commands, file paths, and code names unchanged. The output should be substantially shorter but still complete in meaning and context. PRESERVE THE ORIGINAL LANGUAGE: if the input is in Turkish, output in Turkish; if English, output in English. Output only the rewritten text, no explanations.",
)

CONFIGS = [
    ("openai/gpt-oss-120b", "low", {"reasoning_effort": "low"}),
    ("llama-3.3-70b-versatile", "default", {}),
    ("llama-3.1-8b-instant", "default", {}),
]


def run(model: str, label: str, extra: dict, runs: int = 3):
    print(f"\n=== {model} | reasoning_effort={label} | {runs} runs ===")
    times = []
    for i in range(runs):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYS_PROMPT},
                {"role": "user", "content": f"Rewrite this text more clearly:\n\n{TEXT}"},
            ],
            "temperature": 0.3,
            "max_completion_tokens": 65536,
        }
        payload.update(extra)
        req = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "benchmark/1.0",
            },
        )
        try:
            start = time.time()
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                data = json.loads(resp.read())
            elapsed = time.time() - start
            content = data["choices"][0]["message"].get("content", "")
            reasoning = data["choices"][0]["message"].get("reasoning", "")
            finish = data["choices"][0].get("finish_reason", "?")
            usage = data.get("usage", {})
            times.append(elapsed)
            print(
                f"  run {i+1}: {elapsed:.2f}s | content_len={len(content)} "
                f"reasoning_len={len(reasoning)} finish={finish} "
                f"tokens={usage.get('total_tokens', '?')}"
            )
            if content:
                print(f"    OUTPUT: {content}")
            if not content and reasoning:
                print(f"    REASONING_ONLY: {reasoning[:150]}...")
        except Exception as e:
            print(f"  run {i+1}: ERROR {type(e).__name__}: {e}")
    if times:
        print(f"  avg: {sum(times)/len(times):.2f}s | min: {min(times):.2f}s | max: {max(times):.2f}s")


for model, label, extra in CONFIGS:
    run(model, label, extra, runs=5)