"""End-to-end checks for the dashboard's cross-filtering.

These run the real app headlessly with Streamlit's AppTest and inject the exact
selection payload a chart click produces, so the filter behaviour is verified
without a browser. What a browser is still needed for is the one thing this
cannot cover: that a click on a mark reaches Python at all (see the hit-layer
note in app/charts.py).

Run:  .venv/Scripts/python.exe -m pytest tests/test_crossfilter.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

HOME = str(ROOT / "tests" / "_harness_overview.py")


def sel(curve: int, index: int) -> dict:
    """The shape Streamlit hands back for a clicked point."""
    return {"selection": {"points": [{"curve_number": curve, "point_index": index,
                                      "x": 0, "y": 0}],
                          "point_indices": [index], "box": [], "lasso": []}}


def fresh() -> AppTest:
    at = AppTest.from_file(HOME, default_timeout=120)
    at.run()
    return at


def test_app_runs_clean():
    at = fresh()
    assert not at.exception, at.exception


def test_click_on_roas_bar_filters_to_that_channel():
    at = fresh()
    # ROAS bars sort ascending, so the last hit-layer point belongs to the
    # highest-ROAS channel. Hit layer is curve 1; 26 markers per bar.
    at.session_state["ov_roas~0"] = sel(1, 129)
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["xf"]["channel"]["values"] == ["Search"]


def test_filter_actually_reduces_the_numbers():
    # note: the CSS injected by theme.page_setup also contains the literal text
    # "kpirow" (it's a class selector), so match the wrapping div instead of
    # that substring or the assertion silently compares two copies of the
    # stylesheet.
    at = fresh()
    before = [m.value for m in at.markdown if 'class="kpirow"' in str(m.value)]
    at.session_state["ov_roas~0"] = sel(1, 129)
    at.run()
    after = [m.value for m in at.markdown if 'class="kpirow"' in str(m.value)]
    assert before and after and before != after, "KPI strip did not change"


def test_selection_is_not_reapplied_after_reset_is_clicked():
    """The signature guard: a stale selection must not resurrect a cleared filter.

    Overview's per-dimension "✕ Channel" chip button (state.bar()) was replaced
    by the dropdown filter_bar_controls() row, whose one clearing control is the
    single "Reset filters" button -- this exercises the same signature-guard
    path through that current UI.
    """
    at = fresh()
    at.session_state["ov_roas~0"] = sel(1, 129)
    at.run()
    assert "channel" in at.session_state["xf"]

    at.button(key="filter_bar_reset").click().run()
    assert "channel" not in at.session_state["xf"], "cleared filter came back"


def test_a_chart_only_clears_the_dimension_it_owns():
    at = fresh()
    at.session_state["ov_roas~0"] = sel(1, 129)          # channel <- Search
    at.run()
    at.session_state["ov_mer~0"] = sel(1, 200)           # market  <- some market
    at.run()
    assert "channel" in at.session_state["xf"]
    assert "market" in at.session_state["xf"]

    at.session_state["ov_mer~0"] = {"selection": {"points": []}}   # click empty space
    at.run()
    assert "market" not in at.session_state["xf"], "owner failed to clear itself"
    assert "channel" in at.session_state["xf"], "clearing one dim wiped another"


@pytest.mark.parametrize("page", ["ov_sales_line~0", "ov_grid~0"])
def test_other_charts_also_bind(page):
    at = fresh()
    at.session_state[page] = sel(1, 3)
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["xf"], f"{page} produced no filter"
