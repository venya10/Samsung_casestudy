"""Ask AI — natural-language questions answered with live SQL against the model."""
from __future__ import annotations

import streamlit as st

import theme as T
from data_access import ROOT  # noqa: F401  (ensures src/ is on the path)

import assistant  # noqa: E402

T.page_setup("Ask AI", "💬")
st.title("Ask the marketing data")

live = assistant.has_api_key()

if live:
    T.note(
        "Claude answers by writing SQL against the analytical model and reading the "
        "rows back — <b>every figure in an answer is computed, not recalled</b>. "
        "Expand 'How this was answered' under any response to see the exact queries "
        "that produced it."
    )
else:
    st.warning(
        "**No `ANTHROPIC_API_KEY` found — running the deterministic fallback.** "
        "It matches your question to a prepared analysis over the same tables rather "
        "than reasoning about it, so the demo still works. Set the key in `.env` "
        "(local) or Streamlit secrets (deployed) for the full assistant.",
        icon="⚠️",
    )

SUGGESTIONS = [
    "Which campaign delivered the highest ROI?",
    "Which influencers underperformed?",
    "Why did brand awareness increase despite lower media spend?",
    "Compare paid media versus earned media.",
    "What should be optimised next month?",
]

if "chat" not in st.session_state:
    st.session_state.chat = []

st.markdown("**Try one of the brief's questions:**")
cols = st.columns(len(SUGGESTIONS))
clicked = None
for col, q in zip(cols, SUGGESTIONS):
    if col.button(q, use_container_width=True):
        clicked = q

for entry in st.session_state.chat:
    with st.chat_message("user"):
        st.markdown(entry["question"])
    with st.chat_message("assistant"):
        st.markdown(entry["answer"])
        if entry["tool_calls"]:
            with st.expander(f"How this was answered — {len(entry['tool_calls'])} tool call(s)"):
                for i, call in enumerate(entry["tool_calls"], 1):
                    st.markdown(f"**{i}. `{call['tool']}`**")
                    if call["input"].get("sql"):
                        st.code(call["input"]["sql"], language="sql")
                    elif call["input"]:
                        st.code(str(call["input"]), language="python")
                    st.text(call["output"][:2500])

question = st.chat_input("Ask about channels, influencers, brand, competitors or budget…")
question = question or clicked

if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Querying the marketing database…"):
            turn = assistant.ask(question)
        st.markdown(turn.answer)
        if turn.tool_calls:
            with st.expander(f"How this was answered — {len(turn.tool_calls)} tool call(s)"):
                for i, call in enumerate(turn.tool_calls, 1):
                    st.markdown(f"**{i}. `{call['tool']}`**")
                    if call["input"].get("sql"):
                        st.code(call["input"]["sql"], language="sql")
                    elif call["input"]:
                        st.code(str(call["input"]), language="python")
                    st.text(call["output"][:2500])
    st.session_state.chat.append(
        {"question": question, "answer": turn.answer, "tool_calls": turn.tool_calls}
    )

with st.sidebar:
    st.markdown("### How it works")
    st.markdown(
        f"""
**Model** `{assistant.MODEL}`
**Mode** {'live tool use' if live else 'deterministic fallback'}

The assistant has four tools:

- `run_sql` — read-only DuckDB
- `describe_schema` — tables and columns
- `get_alerts` — early warning feed
- `get_mmm_summary` — mix model output

It is deliberately **not** retrieval over the CSVs. RAG on tabular data makes the
model read numbers out of retrieved text, which is exactly where language models
invent figures. Giving it SQL instead means DuckDB computes every number and the
model only explains the rows it got back.

**Guardrails:** the connection is opened read-only, only `SELECT`/`WITH` pass
validation, results are row-capped, and the loop stops after
{assistant.MAX_TURNS} tool rounds.
        """
    )
    if st.button("Clear conversation"):
        st.session_state.chat = []
        st.rerun()
