"""AI Assistant -- full-page view. The same conversation and the same assistant
also reachable from the floating chat button on every other page; see
app/chatbot.py, which both share.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import chatbot  # noqa: E402

chatbot.full_page()
