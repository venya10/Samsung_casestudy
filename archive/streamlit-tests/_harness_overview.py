"""Test harness: runs state.consume() + the Overview page without st.navigation.

AppTest (streamlit 1.41) does not execute page content registered through
st.navigation/st.Page, so the real Home.py entry point cannot be driven by
AppTest directly. This harness reproduces Home.py's actual sequence -- init,
consume, then the page body -- so the cross-filter logic is exercised exactly
as it runs in production, just without the multipage shell around it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import state
import theme

theme.page_setup("Overview")
state.init()
state.consume()

exec(compile(
    (Path(__file__).resolve().parents[1] / "app" / "views" / "overview.py")
    .read_text(encoding="utf-8"),
    "overview.py", "exec"))
