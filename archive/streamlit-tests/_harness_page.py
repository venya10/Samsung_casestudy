"""Generic per-page harness -- mirrors Home.py's init/consume sequence for
whichever view is named by the PAGE environment variable, so each page can be
smoke-tested by AppTest without going through st.navigation (which AppTest
does not execute; see _harness_overview.py for the full explanation).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import state
import theme

theme.page_setup("Test")
state.init()
state.consume()

page = os.environ["PAGE"]
exec(compile(
    (Path(__file__).resolve().parents[1] / "app" / "views" / f"{page}.py")
    .read_text(encoding="utf-8"),
    f"{page}.py", "exec"))
