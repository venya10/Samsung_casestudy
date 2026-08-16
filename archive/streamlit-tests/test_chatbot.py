"""Headless checks for the floating chat widget and the full-page assistant.

These exercise the deterministic fallback path deliberately, not whatever the
live model would say -- that's the realistic default to test (it's what the
dashboard falls back to for anyone running it without a key), and unlike a real
model's output it's exact and reproducible, which is what a test needs.

`monkeypatch.delenv` clears both key env vars for every test in this module
regardless of what's actually in the developer's `.env` -- without it, a real
`GEMINI_API_KEY` sitting in `.env` for local use would silently flip these tests
over to making live network calls: slower, non-deterministic, and quietly
burning the developer's own API quota just from running `pytest`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))


@pytest.fixture(autouse=True)
def _no_live_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


def _harness(body: str) -> Path:
    p = ROOT / "tests" / "_harness_chatbot_tmp.py"
    p.write_text(
        "import sys\nfrom pathlib import Path\n"
        f"sys.path.insert(0, r'{ROOT / 'app'}')\n"
        "import state, theme, chatbot\n"
        "theme.page_setup('Test')\nstate.init()\nstate.consume()\n"
        + body, encoding="utf-8")
    return p


def test_floating_widget_renders_with_no_history():
    p = _harness("import streamlit as st\n"
                 "st.session_state['current_page'] = 'Overview'\n"
                 "chatbot.floating_widget()\n")
    at = AppTest.from_file(str(p), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    p.unlink()


def test_full_page_renders_with_no_history():
    p = _harness("chatbot.full_page()\n")
    at = AppTest.from_file(str(p), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    p.unlink()


def test_asking_a_question_answers_and_is_shared_across_entry_points():
    p = _harness(
        "import streamlit as st\n"
        "st.session_state['current_page'] = 'Channels'\n"
        "chatbot.floating_widget()\n")
    at = AppTest.from_file(str(p), default_timeout=60)
    at.run()
    (at.chat_input(key="fab_chat_input")
       .set_value("Is the influencer program worth the spend?").run())
    assert not at.exception, at.exception
    chat = at.session_state["chat"]
    assert len(chat) == 2
    assert chat[0]["role"] == "user"
    assert chat[1]["role"] == "assistant"
    assert chat[1]["content"]      # fallback still produces a real answer
    p.unlink()


def test_page_context_includes_active_filters():
    p = _harness(
        "import streamlit as st\n"
        "st.session_state['current_page'] = 'Portfolio'\n"
        "st.session_state['xf'] = {'product': {'values': ['Galaxy S24'], 'src': 't'}}\n"
        "st.write(chatbot._page_context())\n")
    at = AppTest.from_file(str(p), default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    text = at.markdown[-1].value
    assert "Portfolio" in text and "Galaxy S24" in text
    p.unlink()
