"""Samsung MENA Marketing Intelligence -- Streamlit entry point.

Run:  streamlit run app/Home.py

Selections are consumed before any page renders, so every visual on screen
reflects the same filter state within a single run.
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

import chatbot  # noqa: E402
import state  # noqa: E402
import theme  # noqa: E402

SECTIONS = {
    "Analyze": [
        ("views/overview.py", "Overview"),
        ("views/channels.py", "Channels"),
        ("views/portfolio.py", "Portfolio"),
        ("views/influencers.py", "Influencers"),
        ("views/brand.py", "Brand & Share"),
    ],
    "Tools": [
        ("views/early_warning.py", "Early Warning"),
        ("views/data_explorer.py", "Data"),
        ("views/assistant.py", "AI Assistant"),
    ],
}

theme.page_setup("Overview")
state.init()
state.consume()

first = True
pages = {}
for section, entries in SECTIONS.items():
    section_pages = []
    for path, title in entries:
        section_pages.append(st.Page(
            path, title=title, icon=f":material/{theme.NAV_ICONS[title]}:",
            url_path=title.lower().replace(" & ", "-").replace(" ", "-"),
            default=first))
        first = False
    pages[section] = section_pages

# Branding renders into the sidebar's user-content slot; CSS reorders it above
# the nav list, which Streamlit always renders in a fixed slot of its own
# regardless of call order (see theme.py's sidebar CSS comment).
theme.sidebar_brand("MENA · 8 markets · weeks 1–8 · AED")

nav = st.navigation(pages)   # position="sidebar" is the default
st.session_state["current_page"] = nav.title    # read by chatbot._page_context()
theme.sidebar_active_link_script()

nav.run()

if nav.title != "AI Assistant":     # the full page already IS the assistant
    chatbot.floating_widget()
