"""Every page must render without an exception, both unfiltered and under a
representative filter. This is the fast smoke test to run after touching any
view module or app/data.py -- the app's own st.exception surfacing means a
failed page shows a red traceback instead of crashing, so this has to check
at.exception explicitly rather than trusting a clean process exit.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

PAGES = ["overview", "channels", "portfolio", "influencers", "brand",
        "early_warning", "data_explorer", "assistant"]


def run(page: str) -> AppTest:
    os.environ["PAGE"] = page
    at = AppTest.from_file(str(ROOT / "tests" / "_harness_page.py"),
                           default_timeout=120)
    at.run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_clean(page):
    at = run(page)
    assert not at.exception, f"{page}: {at.exception}"


@pytest.mark.parametrize("page", ["overview", "channels", "portfolio", "brand",
                                  "early_warning", "data_explorer"])
def test_page_renders_under_a_market_filter(page):
    os.environ["PAGE"] = page
    at = AppTest.from_file(str(ROOT / "tests" / "_harness_page.py"),
                           default_timeout=120)
    at.session_state["xf"] = {"market": {"values": ["SGE"], "src": "test"}}
    at.run()
    assert not at.exception, f"{page} under market filter: {at.exception}"


@pytest.mark.parametrize("page", ["overview", "channels", "portfolio",
                                  "data_explorer"])
def test_page_renders_under_a_channel_filter(page):
    os.environ["PAGE"] = page
    at = AppTest.from_file(str(ROOT / "tests" / "_harness_page.py"),
                           default_timeout=120)
    at.session_state["xf"] = {"channel": {"values": ["Search"], "src": "test"}}
    at.run()
    assert not at.exception, f"{page} under channel filter: {at.exception}"


def test_page_renders_under_a_product_filter():
    os.environ["PAGE"] = "portfolio"
    at = AppTest.from_file(str(ROOT / "tests" / "_harness_page.py"),
                           default_timeout=120)
    at.session_state["xf"] = {"product": {"values": ["Galaxy S24"], "src": "test"}}
    at.run()
    assert not at.exception, at.exception
