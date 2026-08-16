"""The AI assistant, in two forms: a full page and a floating widget.

Both read and write the SAME `st.session_state.chat` list, so a conversation
started from the floating button on the Channels page is still there if the user
later opens the full AI Assistant page -- one assistant, two doors into it.

The assistant itself (src/assistant.py) already answers from every table every
page reads, so "answer questions from any page" needs no new intelligence, only
a way to reach it from anywhere. What this module adds on top:
  * a short page/filter context line prepended to each question, so "what does
    this chart show" resolves against where the user actually is
  * the floating trigger + popover, present on every page via Home.py

Streamlit quirk worth stating: calling st.rerun() right after appending to
session_state inside a popover closes the popover on the next render (its
open/closed state doesn't survive an explicit rerun the way it survives the
implicit rerun that st.chat_input's own submission already triggers). So the
answer is written directly into the already-open popover instead of triggering
a second rerun -- see _floating_turn below.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import assistant  # noqa: E402
import state  # noqa: E402

SUGGESTED = [
    "Which channel should get more budget next month, and why?",
    "Are there any markets underperforming their peers?",
    "Is the influencer program worth the spend?",
    "What's driving the difference between our best and worst channel?",
    "Which alerts need attention this week?",
]


def _ensure_state() -> list[dict]:
    st.session_state.setdefault("chat", [])
    return st.session_state.chat


def _page_context() -> str:
    """One line on where the user is, so "this chart" and "this page" resolve."""
    page = st.session_state.get("current_page", "the dashboard")
    active = state.active()
    if not active:
        return f"[User is currently on the {page} page. No filters are active.]"
    parts = "; ".join(f"{d}={', '.join(str(v) for v in vals)}"
                      for d, vals in active.items())
    return f"[User is currently on the {page} page, filtered to: {parts}.]"


def _turn(question: str) -> assistant.Turn:
    """Ask, recording both sides of the exchange in the shared history."""
    chat = _ensure_state()
    history = [{"role": m["role"], "content": m["content"]} for m in chat]
    chat.append({"role": "user", "content": question})
    turn = assistant.ask(f"{_page_context()}\n\n{question}", history=history)
    chat.append({"role": "assistant", "content": turn.answer,
                "tool_calls": turn.tool_calls})
    return turn


def _render_tool_calls(container, tool_calls: list[dict]) -> None:
    with container.expander(f"{len(tool_calls)} tool call(s)"):
        for tc in tool_calls:
            container.markdown(f"**{tc['tool']}**`({tc['input']})`")
            container.code(str(tc["output"])[:2000], language="markdown")


# --------------------------------------------------------------------------
# Full page (views/assistant.py)
# --------------------------------------------------------------------------
def full_page() -> None:
    import theme

    theme.head("AI marketing assistant", "Ask it about the numbers on this platform",
               "Answers are grounded in read-only SQL against the same tables "
               "every chart reads -- it cannot see anything the dashboard "
               "doesn't already show, and every answer traces back to a query "
               "you can inspect below. The same conversation is also reachable "
               "from the chat button on every page.")

    if not assistant.has_api_key():
        theme.note(
            "No <code>GEMINI_API_KEY</code> is set in this environment, so "
            "questions are answered by a deterministic fallback covering the "
            "case study's five questions rather than a live model. Set the key "
            "and restart to enable free-form questions.", warn=True)

    chat = _ensure_state()

    if not chat:
        st.markdown('<div class="sec">Try asking</div>', unsafe_allow_html=True)
        cols = st.columns(len(SUGGESTED))
        for c, q in zip(cols, SUGGESTED):
            if c.button(q, use_container_width=True, key=f"sugg_{q[:12]}"):
                st.session_state.pending = q

    for msg in chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("tool_calls"):
                _render_tool_calls(st, msg["tool_calls"])

    question = st.chat_input("Ask about spend, ROI, markets, alerts...",
                             key="page_chat_input")
    question = question or st.session_state.pop("pending", None)

    if question:
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            with st.spinner("Querying the data..."):
                turn = _turn(question)
            st.markdown(turn.answer)
            if turn.tool_calls:
                _render_tool_calls(st, turn.tool_calls)


# --------------------------------------------------------------------------
# Floating widget (called once from Home.py, present on every page)
# --------------------------------------------------------------------------
def floating_widget() -> None:
    chat = _ensure_state()

    with st.container(key="chat_fab"):
        # A single space, not "" -- st.popover needs a non-empty label. The
        # label text itself is hidden via CSS (.stMarkdownContainer display:none
        # on this button), leaving only the Material icon visible.
        with st.popover(" ", icon=":material/auto_awesome:", use_container_width=False):
            st.markdown('<div class="fab-head">'
                        '<span class="fab-title">Ask the assistant</span>'
                        '<span class="fab-sub">Grounded in this dashboard\'s data'
                        '</span></div>', unsafe_allow_html=True)

            box = st.container(height=320)
            if not chat:
                box.caption("Ask about any channel, market, product, influencer "
                           "or alert -- from any page.")
            for msg in chat:
                with box.chat_message(msg["role"]):
                    box.markdown(msg["content"])
                    if msg.get("tool_calls"):
                        _render_tool_calls(box, msg["tool_calls"])

            question = st.chat_input("Ask a question...", key="fab_chat_input")
            if question:
                with box.chat_message("user"):
                    box.markdown(question)
                with box.chat_message("assistant"):
                    with st.spinner("Querying the data..."):
                        turn = _turn(question)
                    box.markdown(turn.answer)
                    if turn.tool_calls:
                        _render_tool_calls(box, turn.tool_calls)
