"""Tests for the frontier-model response shape parser introduced as part
of the MODEL-1 fix.  The pre-fix code only recognized a few hand-rolled
top-level string keys and would extract an empty string from any real
provider response.
"""
from shadowproof_core.model_providers import _extract_text


def test_extracts_plain_text_key():
    assert _extract_text({"text": "hi"}) == "hi"


def test_extracts_anthropic_content_blocks():
    raw = {"content": [
        {"type": "text", "text": "Hello"},
        {"type": "text", "text": ", world"},
    ]}
    assert _extract_text(raw) == "Hello, world"


def test_extracts_openai_responses_output():
    raw = {"output": [
        {"role": "assistant", "content": [
            {"type": "output_text", "text": "abc"},
            {"type": "output_text", "text": "def"},
        ]}
    ]}
    assert _extract_text(raw) == "abcdef"


def test_extracts_openai_chat_completions():
    raw = {"choices": [
        {"message": {"role": "assistant", "content": "the answer"}}
    ]}
    assert _extract_text(raw) == "the answer"


def test_extracts_gemini_candidates():
    raw = {"candidates": [
        {"content": {"parts": [
            {"text": "part 1 "},
            {"text": "part 2"},
        ]}}
    ]}
    assert _extract_text(raw) == "part 1 part 2"


def test_unknown_shape_returns_empty_string():
    assert _extract_text({"unrelated": 42}) == ""


def test_non_dict_input_stringifies():
    assert _extract_text(None) == ""
    assert _extract_text("just a string") == "just a string"


def test_content_as_plain_string_still_works():
    # Some hand-rolled adapters return Anthropic-style content as a single
    # string instead of a block list; we handle that too.
    assert _extract_text({"content": "plain"}) == "plain"
