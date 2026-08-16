"""AI Marketing Assistant — Gemini with read-only SQL access to the analytical model.

Design decision: this is NOT retrieval-augmented generation over the CSVs. RAG over
tabular data makes the model read numbers out of retrieved text, which is exactly
where language models hallucinate. Instead the model is given a semantic layer
(table schemas + KPI definitions, in prompts/system_prompt.md) and a read-only SQL
tool. It writes a query, DuckDB computes the answer, and the model explains the rows
it got back. Every figure in an answer is therefore computed, not recalled.

The agentic loop is written out by hand rather than using an SDK's own tool runner,
because the loop itself is a deliverable for this case study -- the reviewer should
be able to read exactly what happens between question and answer. Every tool call is
logged to the transcript so the workflow is auditable.

Runs on Google's Gemini API (a free tier is available via Google AI Studio, no
billing required to start) rather than a paid provider. The tool definitions, the
turn loop and the guardrails below are provider-agnostic in spirit -- only the
actual API call, message format and error types in `ask()` are Gemini-specific.

If no API key is present the assistant falls back to a deterministic responder that
answers the five brief questions from the same tables, so a demo never dead-ends.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

import duckdb
import pandas as pd

import site_data
from common import DUCKDB_PATH, PROMPTS, ROOT

# Load .env if present so a local key works without exporting it every session.
# Never overrides an already-set environment variable.
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except ImportError:  # dotenv is optional; the env var alone is enough
    pass

# "-latest" is a Google-maintained alias, not a pinned version: it always resolves
# to their current recommended model. A pinned version (gemini-2.5-flash) broke
# within the same session it was written in -- Google restricted it from new API
# keys and pointed callers at newer models instead -- so the alias is what avoids
# that recurring, without needing to track version numbers by hand.
#
# The lite tier, not the full flash tier: "gemini-flash-latest" currently resolves
# to gemini-3.7-flash, whose free tier allows only 20 requests/day/project --
# exhausted almost immediately in real use. "gemini-flash-lite-latest" carries a
# far more generous free quota and is plenty capable for tool-calling SQL and
# writing a short, director-brief answer over a well-defined schema.
MODEL = "gemini-flash-lite-latest"
# Caps the final answer's length, not just a safety ceiling -- a director-brief
# answer fits in a few hundred tokens, so a low cap is what actually keeps
# replies short and fast rather than relying on the model to self-limit.
MAX_TOKENS = 700
MAX_ROWS = 200          # rows returned to the model from any single query
MAX_TURNS = 12          # hard stop on the agentic loop

# --------------------------------------------------------------------------
# SQL guardrails
# --------------------------------------------------------------------------
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|"
    r"install|load|pragma|set|call)\b",
    re.IGNORECASE,
)


class UnsafeQuery(ValueError):
    pass


def _validate_sql(sql: str) -> str:
    """Allow a single read-only statement and nothing else.

    The connection is opened read-only as well, so this is defence in depth rather
    than the only control -- but a clear error message beats a DuckDB permission
    error when the model gets it wrong, because the model can then correct itself.
    """
    cleaned = sql.strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeQuery("Empty query.")
    if ";" in cleaned:
        raise UnsafeQuery("Only one statement per call. Remove the semicolon.")
    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        raise UnsafeQuery("Only SELECT and WITH queries are allowed.")
    if _FORBIDDEN.search(cleaned):
        raise UnsafeQuery("This database is read-only. Only SELECT queries are allowed.")
    return cleaned


def _connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


def _as_markdown(df: pd.DataFrame) -> str:
    """Render a frame with per-column number formatting.

    A single global float format cannot serve both a $1.6M fee and a 0.0037
    engagement rate -- one comes out as scientific notation, the other as 0.00.
    Formatting per column by magnitude keeps both legible, which matters because
    the model reads these tables and then quotes the figures back to the user.
    """
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            continue
        s = out[col].astype(float)
        biggest = s.abs().max()
        if pd.isna(biggest):
            continue
        if biggest >= 1000:
            out[col] = s.map(lambda v: "" if pd.isna(v) else f"{v:,.0f}")
        elif biggest >= 1:
            out[col] = s.map(lambda v: "" if pd.isna(v) else f"{v:,.2f}")
        else:
            out[col] = s.map(lambda v: "" if pd.isna(v) else f"{v:.4f}")
    return out.to_markdown(index=False)


# --------------------------------------------------------------------------
# Tool implementations
# --------------------------------------------------------------------------
def tool_run_sql(sql: str) -> str:
    try:
        cleaned = _validate_sql(sql)
    except UnsafeQuery as exc:
        return f"QUERY REJECTED: {exc}"
    try:
        with _connect() as con:
            df = con.execute(cleaned).fetchdf()
    except Exception as exc:  # surfaced to the model so it can fix its own SQL
        return f"SQL ERROR: {type(exc).__name__}: {exc}"

    truncated = len(df) > MAX_ROWS
    body = _as_markdown(df.head(MAX_ROWS))
    note = (
        f"\n\n[{len(df)} rows matched; showing the first {MAX_ROWS}. "
        "Add aggregation or a LIMIT if you need a narrower result.]"
        if truncated
        else f"\n\n[{len(df)} row(s)]"
    )
    return body + note


def tool_describe_schema(table: str | None = None) -> str:
    with _connect() as con:
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        if table:
            if table not in tables:
                return f"No table named '{table}'. Available: {', '.join(sorted(tables))}"
            cols = con.execute(f"DESCRIBE {table}").fetchdf()
            n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            return f"### {table} ({n} rows)\n\n" + cols[
                ["column_name", "column_type"]
            ].to_markdown(index=False)
        lines = []
        for t in sorted(tables):
            cols = con.execute(f"DESCRIBE {t}").fetchdf()["column_name"].tolist()
            lines.append(f"**{t}**: {', '.join(cols)}")
        return "\n\n".join(lines)


def tool_get_alerts(severity: str | None = None, current_only: bool = True) -> str:
    table = "alerts_current" if current_only else "alerts"
    sql = f"SELECT week, market, entity, severity, rule, category, detail, owner, action FROM {table}"
    if severity:
        sql += f" WHERE severity = '{severity.lower()}'"
    sql += " ORDER BY severity_rank" if not severity else ""
    return tool_run_sql(sql.replace(" ORDER BY severity_rank", ""))


def tool_get_analysis() -> str:
    """The pre-computed analysis, with its caveats attached."""
    with _connect() as con:
        eff = con.execute(
            """
            SELECT channel, media_type, spend_aed, sales_aed, conversions, roas,
                   roi_gross_margin, cpa_aed, efficiency_index, share_of_spend,
                   share_of_sales, payback
            FROM channel_efficiency ORDER BY spend_aed DESC
            """
        ).fetchdf()
        ms = con.execute(
            """
            SELECT market, mer_rank, spend_aed, sales_aed, mer, mer_vs_peer_median,
                   sales_gap_vs_peer_aed, quartile
            FROM market_scorecard ORDER BY mer DESC
            """
        ).fetchdf()
        pm = con.execute(
            """
            SELECT channel, coefficient, ci_low, ci_high, p_value, significant_5pct
            FROM panel_model ORDER BY coefficient DESC
            """
        ).fetchdf()
        ps = con.execute(
            "SELECT product, spend_aed, sales_aed, roas, support_index "
            "FROM product_summary ORDER BY sales_aed DESC"
        ).fetchdf()
        plan = con.execute(
            "SELECT channel, action, spend_aed, spend_change_aed, sales_impact_aed, "
            "margin_impact_aed FROM reallocation ORDER BY roas DESC"
        ).fetchdf()

    return (
        "### Channel efficiency (AED)\n"
        + _as_markdown(eff)
        + "\n\n_TV and PR show null ROI because they carry no attributed sales in "
          "this dataset. That is a measurement gap, not a score of zero._\n"
        "\n### Market scorecard\n" + _as_markdown(ms)
        + "\n\n### Panel model — association, NOT contribution\n"
        + _as_markdown(pm)
        + "\n\n_Weekly market sales on channel spend with market fixed effects. "
          "Where the confidence interval crosses zero the channel cannot be "
          "distinguished from no effect. No carryover or saturation is modelled; "
          "8 weeks cannot identify either._\n"
        "\n### Products\n" + _as_markdown(ps)
        + "\n\n### Directional reallocation\n" + _as_markdown(plan)
        + "\n\n_Directional, not an optimum: without a response curve there is no "
          "way to estimate diminishing returns._"
    )


# Gemini's function-declaration schema is the same JSON-Schema shape Anthropic
# uses, just with the property renamed (`parameters` not `input_schema`) and type
# names in Gemini's own Schema.Type enum (STRING/OBJECT/BOOLEAN, uppercase) rather
# than JSON Schema's lowercase "string"/"object"/"boolean".
TOOLS = [
    {
        "name": "run_sql",
        "description": (
            "Run a read-only SQL query against the Samsung MENA marketing database "
            "(DuckDB). Use this for any question that needs a number. Call "
            "describe_schema first if you are unsure of a column name. Prefer "
            "aggregating in SQL over returning many rows. Only SELECT and WITH are "
            "permitted; a rejected or failed query returns an error message you can "
            "read and correct."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "sql": {
                    "type": "STRING",
                    "description": "A single SELECT or WITH statement, no trailing semicolon.",
                }
            },
            "required": ["sql"],
        },
    },
    {
        "name": "describe_schema",
        "description": (
            "List the tables and columns available. Call with no arguments for an "
            "overview of every table, or with a table name for its column types and "
            "row count. Use this before writing SQL against an unfamiliar table."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "table": {
                    "type": "STRING",
                    "description": "Optional table name for detailed column types.",
                }
            },
        },
    },
    {
        "name": "get_alerts",
        "description": (
            "Return Early Warning System alerts with their severity, owner and "
            "recommended action. Call this for questions about risks, what is going "
            "wrong, or what needs attention. Defaults to the current week; set "
            "current_only=false for the full alert history across all 52 weeks."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "severity": {
                    "type": "STRING",
                    "enum": ["critical", "high", "medium"],
                    "description": "Optional severity filter.",
                },
                "current_only": {
                    "type": "BOOLEAN",
                    "description": "True (default) for the latest week only.",
                },
            },
        },
    },
    {
        "name": "get_analysis",
        "description": (
            "Return the pre-computed analysis in one call: channel efficiency, the "
            "8-market scorecard, the panel model with confidence intervals, product "
            "summary, and the directional reallocation. Call this for any question "
            "about channel effectiveness, where budget should move, how markets "
            "compare, or what to optimise. Prefer this over re-deriving from the "
            "fact tables -- it carries the caveats and handles channels that have no "
            "revenue attribution correctly, which raw SQL over the facts will not."
        ),
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]

DISPATCH = {
    "run_sql": tool_run_sql,
    "describe_schema": tool_describe_schema,
    "get_alerts": tool_get_alerts,
    "get_analysis": tool_get_analysis,
}


# --------------------------------------------------------------------------
# Prompt assembly
# --------------------------------------------------------------------------
def build_system_prompt() -> str:
    """Static guidance plus a live schema dump.

    The schema is generated from the database rather than hand-maintained, so the
    prompt cannot drift out of sync with the tables when the real Samsung files
    replace the synthetic ones.
    """
    static = (PROMPTS / "system_prompt.md").read_text(encoding="utf-8")
    return static + "\n\n## Live schema\n\n" + tool_describe_schema()


# --------------------------------------------------------------------------
# Agentic loop
# --------------------------------------------------------------------------
@dataclass
class Turn:
    """One question and everything that happened while answering it."""
    question: str
    answer: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    stopped_because: str = ""


def has_api_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _to_content(role: str, text: str, types):
    """The caller (app/chatbot.py) hands history around as plain {"role","content"}
    dicts in Anthropic's role vocabulary ("user"/"assistant") so the UI layer stays
    provider-agnostic. Gemini calls the second role "model" instead -- translated
    here, at the boundary, rather than pushing a Gemini-specific vocabulary up into
    the chat UI that has to work regardless of which provider is behind it."""
    return types.Content(role="model" if role == "assistant" else "user",
                         parts=[types.Part(text=text)])


def ask(question: str, history: list[dict] | None = None, verbose: bool = False) -> Turn:
    """Answer one question, running the tool loop to completion."""
    if not has_api_key():
        return _fallback_answer(question)

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types

    client = genai.Client()  # reads GEMINI_API_KEY / GOOGLE_API_KEY itself
    turn = Turn(question=question)
    contents = [_to_content(m["role"], m["content"], types) for m in (history or [])]
    contents.append(types.Content(role="user", parts=[types.Part(text=question)]))

    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        tools=[types.Tool(function_declarations=TOOLS)],
        max_output_tokens=MAX_TOKENS,
        # Low, not zero: this is a fact-lookup-and-explain task, not creative
        # writing, and the default temperature measurably increased the odds
        # of a supporting figure (e.g. TV's cost per GRP) getting misquoted
        # from "close enough" memory instead of the tool result actually in
        # front of it. A live audit caught this at the default temperature.
        temperature=0.2,
    )

    for _ in range(MAX_TURNS):
        try:
            response = client.models.generate_content(
                model=MODEL, contents=contents, config=config,
            )
        except genai_errors.ClientError as exc:
            # 429 is the free tier's rate/quota limit; other 4xx are usually a bad
            # or missing key. Both come through as ClientError, distinguished by
            # status code rather than a dedicated exception type.
            if getattr(exc, "code", None) == 429:
                turn.answer = "Rate limited by the free tier. Wait a moment and ask again."
                turn.stopped_because = "rate_limit"
            else:
                turn.answer = f"API error {getattr(exc, 'code', '')}: {exc}"
                turn.stopped_because = "api_error"
            return turn
        except genai_errors.ServerError as exc:
            turn.answer = f"Gemini server error: {exc}"
            turn.stopped_because = "api_error"
            return turn
        except Exception as exc:  # network-level failures, not an API error object
            turn.answer = f"Could not reach the API: {type(exc).__name__}: {exc}"
            turn.stopped_because = "connection_error"
            return turn

        candidates = response.candidates or []
        if not candidates or candidates[0].content is None:
            # A safety block or empty response comes back as HTTP 200 with no
            # candidate content, so indexing parts below would break here.
            reason = candidates[0].finish_reason if candidates else "no candidates"
            turn.answer = f"The model returned no answer ({reason})."
            turn.stopped_because = "empty_response"
            return turn

        candidate = candidates[0]
        contents.append(candidate.content)
        parts = candidate.content.parts or []

        calls = [p for p in parts if p.function_call is not None]
        if not calls:
            turn.answer = "".join(p.text for p in parts if p.text)
            turn.stopped_because = str(candidate.finish_reason or "STOP")
            return turn

        response_parts = []
        for p in calls:
            fc = p.function_call
            fn = DISPATCH.get(fc.name)
            args = dict(fc.args) if fc.args else {}
            if fn is None:
                output, is_error = f"No such tool: {fc.name}", True
            else:
                try:
                    output, is_error = fn(**args), False
                except Exception as exc:
                    output, is_error = f"Tool failed: {type(exc).__name__}: {exc}", True

            turn.tool_calls.append(
                {"tool": fc.name, "input": args, "output": output, "error": is_error}
            )
            if verbose:
                print(f"  -> {fc.name}({json.dumps(args)[:120]})")

            response_parts.append(types.Part.from_function_response(
                name=fc.name,
                response={"error" if is_error else "result": output},
            ))
        # All results for one model turn go back in a SINGLE content block -- as
        # with Anthropic's tool_result batching, splitting them across separate
        # turns teaches the model to stop making parallel tool calls.
        contents.append(types.Content(role="user", parts=response_parts))

    turn.answer = (
        f"Stopped after {MAX_TURNS} tool rounds without reaching an answer. "
        "Try asking a narrower question."
    )
    turn.stopped_because = "max_turns"
    return turn


def _wow_series(vals: list[float]) -> float | None:
    """First half of a series vs. the second half. Mirrors build_site.py's
    _wow() exactly -- the AI narrative's "spend fell" and the deterministic
    trend badge next to it must always agree."""
    clean = [v for v in vals if v is not None and not pd.isna(v)]
    if len(clean) < 2:
        return None
    mid = -(-len(clean) // 2)
    prior, cur = sum(clean[:mid]) / mid, sum(clean[mid:]) / (len(clean) - mid)
    return (cur / prior - 1) if prior else None


def ask_page_insights(active: dict) -> dict:
    """AI-written narrative + recommended actions for the Insights & Actions
    page, scoped to the current filter.

    Reuses site_data.tables() -- the exact same filtered tables the live
    filter bar itself fetches -- so the AI's figures cannot disagree with the
    deterministic version already rendered on the page; only the wording and
    the action list are new. Button-triggered from the client, not called on
    every filter change (see assets/app_pages.js), to keep filtering itself
    free and instant.
    """
    if not has_api_key():
        return {"live": False}

    t = site_data.tables(active)
    spine, eff = t.get("fact_market_week"), t.get("channel_efficiency")
    pve, sc = t.get("paid_vs_earned"), t.get("influencer_scorecard")
    alerts_current = t.get("alerts_current")

    if spine is None or not len(spine) or eff is None or not len(eff):
        return {"live": True, "error": "No rows match the current filter."}

    total_sales = float(spine["sales_aed"].sum())
    total_spend = float(spine["spend_aed"].sum())
    total_conv = float(spine["conversions"].sum())
    blended_mer = (total_sales / total_spend) if total_spend else None

    by_week = spine.groupby("week", as_index=False).agg(
        sales_aed=("sales_aed", "sum"), spend_aed=("spend_aed", "sum"),
        conversions=("conversions", "sum"))
    sales_wow = _wow_series(by_week["sales_aed"].tolist())
    spend_wow = _wow_series(by_week["spend_aed"].tolist())
    conv_wow = _wow_series(by_week["conversions"].tolist())
    mer_wow = _wow_series((by_week["sales_aed"] / by_week["spend_aed"]).tolist())

    context = (
        "### Totals (current filter)\n"
        f"- Sales: {total_sales:,.0f} AED\n- Media spend: {total_spend:,.0f} AED\n"
        f"- Conversions: {total_conv:,.0f}\n"
        f"- Blended MER: {'n/a' if blended_mer is None else f'{blended_mer:.2f}x'}\n"
        "\n### Week-over-week (first half of the filtered weeks vs. the second half)\n"
    )
    for label, w in [("Sales", sales_wow), ("Media spend", spend_wow),
                      ("MER", mer_wow), ("Conversions", conv_wow)]:
        context += f"- {label}: {'n/a' if w is None else f'{w*100:+.0f}%'}\n"

    context += "\n### Channel efficiency\n" + _as_markdown(
        eff[["channel", "media_type", "spend_aed", "sales_aed", "roas", "cpa_aed",
             "share_of_spend", "revenue_attributed"]])

    if pve is not None and len(pve):
        context += "\n\n### Paid vs earned\n" + _as_markdown(pve)
    if sc is not None and len(sc):
        context += "\n\n### Influencer scorecard\n" + _as_markdown(
            sc[["influencer", "market", "spend_aed", "cpa_aed", "roas", "flag"]])
    n_open = len(alerts_current) if alerts_current is not None else 0
    crit = int((alerts_current["severity"] == "critical").sum()) if n_open else 0
    context += f"\n\n### Early-warning alerts\n{n_open} currently open, {crit} critical."

    prompt = (
        "You are a sharp marketing analyst briefing Samsung MENA leadership on "
        "the numbers below (the current filter slice). Use ONLY these numbers "
        "-- do not invent a channel, market, product, figure, or claim not "
        "present here, and do not mention a metric or channel this filter has "
        "dropped.\n\n"
        + context
        + "\n\nRespond with strict JSON, no markdown, no extra keys, no "
        'commentary outside the JSON:\n'
        '{"insights": [string, ...], "actions": [string, ...]}\n\n'
        "insights: 4 to 6 sharp, one-line bullets on what these numbers MEAN "
        "for the business -- the interpretation and the 'so what', not a "
        "restatement of the figures. Connect metrics where it matters (e.g. "
        "spend and sales moving together vs. diverging, which channels are "
        "carrying performance vs. dragging it, what a measurement gap implies). "
        "A media-spend DECREASE is favourable here (lower cost for similar "
        "return), not a problem -- say so plainly if it applies. Cite a figure "
        "only when it substantiates the point, never just to list it.\n\n"
        "actions: 3 to 5 short, imperative one-line bullets, ranked by "
        "priority, each grounded in a specific number or finding above (e.g. "
        "name the channel, the gap, the alert count) -- no throat-clearing, "
        "no restating the insight, just the action.\n\n"
        "Every bullet in both lists must be ONE sentence, plain text, no bold "
        "or markdown syntax, and genuinely earn its place -- prefer fewer, "
        "sharper bullets over padding out the count."
    )

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types

    client = genai.Client()
    try:
        response = client.models.generate_content(
            model=MODEL, contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=MAX_TOKENS,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
    except genai_errors.ClientError as exc:
        if getattr(exc, "code", None) == 429:
            return {"live": True, "error": "Rate limited by the free tier. Wait a moment and try again."}
        return {"live": True, "error": f"API error {getattr(exc, 'code', '')}: {exc}"}
    except genai_errors.ServerError as exc:
        return {"live": True, "error": f"Gemini server error: {exc}"}
    except Exception as exc:  # network-level failures, not an API error object
        return {"live": True, "error": f"Could not reach the API: {type(exc).__name__}: {exc}"}

    parts = response.candidates[0].content.parts if response.candidates and response.candidates[0].content else []
    text = "".join(p.text for p in (parts or []) if p.text).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except Exception:
        return {"live": True, "error": "The model returned malformed output. Try again."}

    return {
        "live": True,
        "insights": parsed.get("insights") or [],
        "actions": parsed.get("actions") or [],
    }


# --------------------------------------------------------------------------
# Deterministic fallback (no API key)
# --------------------------------------------------------------------------
def _fallback_answer(question: str) -> Turn:
    """Answer the brief's five questions from the same tables, without the API.

    This exists so the dashboard demo cannot dead-end on a missing or rate-limited
    key. It pattern-matches the question rather than understanding it, and says so.
    """
    q = question.lower()
    turn = Turn(question=question, stopped_because="fallback_no_api_key")
    prefix = "_No API key set — deterministic fallback, not a reasoned answer._\n\n"

    if any(k in q for k in ("optimi", "next month", "recommend", "should", "next")):
        body = tool_run_sql(
            "SELECT channel, action, spend_change_aed, sales_impact_aed, "
            "margin_impact_aed FROM reallocation ORDER BY sales_impact_aed DESC"
        )
        head = "**Directional budget shift**\n\n"
    elif "influencer" in q:
        body = tool_run_sql(
            """
            SELECT influencer, market, spend_aed, cpa_aed, roas, flag
            FROM influencer_scorecard ORDER BY cpa_aed DESC LIMIT 5
            """
        )
        head = "**Worst cost per acquisition.** None clears breakeven.\n\n"
    elif any(k in q for k in ("market", "subsidiary", "country", "compare markets")):
        body = tool_run_sql(
            "SELECT market, mer_rank, spend_aed, sales_aed, mer, "
            "mer_vs_peer_median, sales_gap_vs_peer_aed, quartile "
            "FROM market_scorecard ORDER BY mer DESC"
        )
        head = "**The eight subsidiaries benchmarked against each other**\n\n"
    elif any(k in q for k in ("product", "device", "galaxy", "fold", "buds")):
        body = tool_run_sql(
            "SELECT product, spend_aed, sales_aed, conversions, roas, aov_aed, "
            "support_index FROM product_summary ORDER BY sales_aed DESC"
        )
        head = "**Product portfolio**\n\n"
    elif any(k in q for k in ("awareness", "brand", "sentiment", "intent")):
        body = tool_run_sql(
            "SELECT market, brand_awareness, purchase_intent, sentiment, "
            "share_of_voice, competitor_sov, sov_gap FROM market_scorecard "
            "ORDER BY brand_awareness DESC"
        )
        head = "**Brand metrics by market** (indicative index, not a tracker).\n\n"
    elif any(k in q for k in ("earned", "paid vs", "paid versus", "organic")):
        body = tool_run_sql("SELECT * FROM paid_vs_earned")
        head = "**Paid versus earned**\n\n"
    elif any(k in q for k in ("roi", "roas", "return", "channel", "campaign", "tv")):
        body = tool_run_sql(
            "SELECT channel, spend_aed, sales_aed, roas, roi_gross_margin "
            "FROM channel_efficiency ORDER BY spend_aed DESC"
        )
        head = ("**Channel efficiency.** TV shows null ROI — no attributed sales, "
                "not a zero score.\n\n")
    else:
        body = tool_get_alerts()
        head = (
            "I can only match prepared analyses without an API key. Here are the "
            "current alerts; try asking about channels, markets, products, "
            "influencers, brand, or what to optimise next.\n\n"
        )

    turn.answer = prefix + head + body
    return turn


# --------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    questions = sys.argv[1:] or [
        "Which channel delivered the highest ROI, and where should we move budget next month?",
        "Which influencers underperformed and how much did they cost us?",
        "Why did brand awareness increase despite lower media spend?",
        "Compare paid media versus earned media.",
        "What should we optimise next month?",
    ]
    key = "using the API" if has_api_key() else "NO API KEY -- deterministic fallback"
    print(f"Samsung MENA Marketing Assistant ({key})\n" + "=" * 78)
    for q in questions:
        print(f"\nQ: {q}\n" + "-" * 78)
        t = ask(q, verbose=True)
        print(t.answer)
        if t.tool_calls:
            print(f"\n[{len(t.tool_calls)} tool call(s): "
                  f"{', '.join(c['tool'] for c in t.tool_calls)}]")
