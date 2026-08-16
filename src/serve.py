"""Serve the static site and answer the assistant's questions.

    python src/serve.py            ->  http://localhost:8000

Uses only the standard library's http.server -- no Flask, no extra dependency.
The site itself is static and works by double-clicking `site/index.html`; this
server exists solely to add the API routes the interactive pages call:

    GET  /api/health       ->  {"live": true|false}
    POST /api/ask          ->  {"answer_html": ..., "tool_calls": [...]}
    POST /api/tables       ->  the live filter bar's recomputed tables
    POST /api/alerts       ->  {"alerts": [...], "alerts_current": [...]} at a
                                custom sensitivity -- the Early Warning page's slider
    POST /api/upload-data  ->  replace the dataset and rebuild everything --
                                the Data page's upload button, passcode-gated

If no API key is set the health route reports live=false and the page falls back
to the prepared answers baked into the HTML, saying so on screen.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import alerts  # noqa: E402
import assistant  # noqa: E402
import data_upload  # noqa: E402
import site_data  # noqa: E402
from common import ROOT  # noqa: E402

SITE = ROOT / "site"
# A host like Render sets $PORT itself and expects the process to bind 0.0.0.0;
# locally (no $PORT set) this falls back to the same 127.0.0.1:8000 as before.
PORT = int(os.environ.get("PORT", 8000))
HOST = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"

# Unset by default -- the Data page's upload button is disabled with an
# explanatory note unless this is configured, so a public deploy can't have
# its live dataset replaced by anyone with the URL. Same env-var pattern as
# GEMINI_API_KEY.
UPLOAD_PASSCODE = os.environ.get("UPLOAD_PASSCODE")

# The pipeline mutates shared state on disk (data/raw, data/processed, site/)
# and module-level singletons (ingest.DQ, validate_site's failure counters) --
# ThreadingHTTPServer runs each request on its own thread, so two uploads
# arriving at once could interleave and corrupt either. One at a time.
_upload_lock = threading.Lock()

# Tables the filter API sends to the client. GLOBAL_ONLY ones are always the
# full, unfiltered table -- see site_data.py for why (panel_model, market peer
# comparisons, etc. are not valid on a subset).
API_TABLES = site_data.FACT_TABLES + site_data.DERIVED + site_data.GLOBAL_ONLY


def _records(df) -> list:
    """DataFrame -> JSON-safe records. `DataFrame.where(df.notna(), None)` looks
    like it should turn NaN into null but silently doesn't on float columns --
    pandas coerces None back to NaN to keep the column numeric, so json.dumps
    then emits the bare (non-standard) `NaN` token, which browsers' JSON.parse
    rejects outright. pandas' own to_json takes NaN -> null correctly; round
    tripping through it is what actually gets valid JSON."""
    if df is None or not len(df):
        return []
    return json.loads(df.to_json(orient="records"))


# --------------------------------------------------------------------------
# Minimal markdown -> HTML
# --------------------------------------------------------------------------
def md_to_html(md: str) -> str:
    """Convert the subset of markdown the assistant actually emits.

    Deliberately small: paragraphs, bold, italics, inline code, and pipe tables.
    A full markdown dependency would be more code to audit for one page of chat.
    """
    md = md.replace("\r\n", "\n")
    lines = md.split("\n")
    out: list[str] = []
    i = 0

    def inline(s: str) -> str:
        s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
        s = re.sub(r"_([^_]+)_", r"<i>\1</i>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        return s

    while i < len(lines):
        line = lines[i]

        # Pipe table: header row, separator row, then body rows.
        if (
            line.strip().startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1])
        ):
            def cells(row: str) -> list[str]:
                return [c.strip() for c in row.strip().strip("|").split("|")]

            head = cells(line)
            i += 2
            body_rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                body_rows.append(cells(lines[i]))
                i += 1
            ths = "".join(f"<th>{inline(h)}</th>" for h in head)
            trs = "".join(
                "<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>"
                for r in body_rows
            )
            out.append(
                f'<div class="table-wrap"><table><thead><tr>{ths}</tr></thead>'
                f"<tbody>{trs}</tbody></table></div>"
            )
            continue

        if not line.strip():
            i += 1
            continue

        if line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
            i += 1
            continue
        if line.startswith("## "):
            out.append(f"<h3>{inline(line[3:])}</h3>")
            i += 1
            continue

        if re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(f"<li>{inline(re.sub(r'^\\s*[-*]\\s+', '', lines[i]))}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("|"):
            para.append(lines[i])
            i += 1
        out.append("<p>" + inline(" ".join(para)) + "</p>")

    return "".join(out)


# --------------------------------------------------------------------------
# Handler
# --------------------------------------------------------------------------
class Handler(SimpleHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200) -> None:
        blob = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self):  # noqa: N802
        if self.path.split("?")[0] == "/api/health":
            self._json({"live": assistant.has_api_key(), "model": assistant.MODEL,
                        "upload_enabled": bool(UPLOAD_PASSCODE)})
            return
        super().do_GET()

    def do_POST(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/api/ask":
            self._handle_ask()
        elif path == "/api/tables":
            self._handle_tables()
        elif path == "/api/alerts":
            self._handle_alerts()
        elif path == "/api/insights":
            self._handle_insights()
        elif path == "/api/upload-data":
            self._handle_upload_data()
        else:
            self.send_error(404)

    def _handle_ask(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            question = (payload.get("question") or "").strip()
            if not question:
                self._json({"error": "empty question"}, 400)
                return

            turn = assistant.ask(question)
            self._json({
                "answer_html": md_to_html(turn.answer),
                "stopped_because": turn.stopped_because,
                "tool_calls": [
                    {"tool": c["tool"], "sql": c["input"].get("sql", "")}
                    for c in turn.tool_calls
                ],
            })
        except Exception as exc:  # never leave the page hanging on a spinner
            self._json({"answer_html": f"<p>Server error: {exc}</p>",
                        "tool_calls": []}, 500)

    def _handle_tables(self) -> None:
        """The static site's live filter API. Body: {"week": [...], "channel":
        [...], "product": [...], "market": [...]} -- any dim omitted or empty
        means "all". Recomputes exactly like app/data.py; see site_data.py for
        which tables are recomputed on the slice vs. always sent in full."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            active = {d: body.get(d) or [] for d in site_data.DIMS}
            t = site_data.tables(active)
            self._json({name: _records(t.get(name)) for name in API_TABLES})
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def _handle_insights(self) -> None:
        """The Insights & Actions page's "Generate AI insights" button. Body:
        {"week": [...], "channel": [...], "product": [...], "market": [...]},
        same shape as /api/tables -- reuses the same filter signature so the
        AI's write-up is scoped to whatever the page is currently showing."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            active = {d: body.get(d) or [] for d in site_data.DIMS}
            self._json(assistant.ask_page_insights(active))
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def _handle_upload_data(self) -> None:
        """The Data page's "Replace the dataset" button. Not a form post --
        the client sends the raw file bytes as the body (no multipart parsing
        needed since we control both ends), with the passcode and original
        filename in headers:

            X-Upload-Passcode: <passcode>
            X-Filename: <original name, e.g. mydata.xlsx>

        Body: raw file bytes.
        """
        if not UPLOAD_PASSCODE:
            self._json({"ok": False,
                        "error": "Uploads are disabled on this server (no UPLOAD_PASSCODE set)."},
                       403)
            return
        if self.headers.get("X-Upload-Passcode") != UPLOAD_PASSCODE:
            self._json({"ok": False, "error": "Wrong passcode."}, 401)
            return

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0 or length > data_upload.MAX_BYTES:
            self._json({"ok": False, "error": "Missing file or file too large (25MB limit)."}, 413)
            return
        body = self.rfile.read(length)
        filename = self.headers.get("X-Filename", "upload.csv")

        if not _upload_lock.acquire(blocking=False):
            self._json({"ok": False, "error": "Another upload is already in progress. Try again shortly."}, 409)
            return
        try:
            result = data_upload.apply_upload(body, filename)
            self._json({"ok": True, **result})
        except data_upload.UploadRejected as exc:
            self._json({"ok": False, "error": str(exc)}, 400)
        except Exception as exc:
            self._json({"ok": False, "error": f"Unexpected error: {type(exc).__name__}: {exc}"}, 500)
        finally:
            _upload_lock.release()

    def _handle_alerts(self) -> None:
        """Recompute alerts with a manager-adjustable sensitivity -- the
        Early Warning page's slider. Body: {"min_relative_gap": 0.08}. This
        only moves the shared default floor; a rule with its own hand-tuned
        override (e.g. SENT-01's sentiment rule) is unaffected -- see
        alerts.run_alerts(). Always evaluated over the full, unfiltered
        dataset, same as the static build; week/market filters narrow which
        alerts are DISPLAYED client-side, not which rules fire."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            gap = body.get("min_relative_gap")
            gap = None if gap is None else float(gap)
            if gap is not None and not (0.0 <= gap <= 1.0):
                self._json({"error": "min_relative_gap must be between 0 and 1"}, 400)
                return
            alerts_df = alerts.run_alerts(min_relative_gap=gap)
            current_df = alerts.latest_alerts(alerts_df)
            self._json({"alerts": _records(alerts_df),
                        "alerts_current": _records(current_df)})
        except Exception as exc:
            self._json({"error": str(exc)}, 500)

    def log_message(self, fmt, *args):
        # send_error() logs with an HTTPStatus object as one of the args (e.g. on
        # a stray favicon.ico 404) -- "in" on a non-string blew this up before.
        if "/api/" in str(args[0] if args else ""):
            super().log_message(fmt, *args)


def main() -> None:
    if not SITE.exists():
        raise SystemExit("site/ not found — run `python src/build_site.py` first.")

    live = assistant.has_api_key()
    handler = partial(Handler, directory=str(SITE))
    server = ThreadingHTTPServer((HOST, PORT), handler)

    print(f"\n  Samsung MENA Marketing Intelligence")
    print(f"  http://localhost:{PORT}\n")
    print(f"  AI assistant : {'LIVE (' + assistant.MODEL + ')' if live else 'offline — no GEMINI_API_KEY, using prepared answers'}")
    print("  Ctrl-C to stop\n")

    if HOST == "127.0.0.1":  # local run only -- a cloud host has no browser to open
        try:
            webbrowser.open(f"http://localhost:{PORT}")
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")


if __name__ == "__main__":
    main()
