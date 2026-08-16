"""Execute every dashboard page headlessly to catch errors before a demo does.

Streamlit only surfaces an exception when a human clicks to that page. This runs
each page's module body with Streamlit's runtime stubbed out, so a broken column
name or a bad format string fails here instead of in front of a reviewer.
"""
from __future__ import annotations

import runpy
import sys
import traceback
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT / "src"))

PAGES = [APP / "Home.py"] + sorted((APP / "pages").glob("*.py"))


class _Stub:
    """Absorbs any Streamlit call, returning further stubs where needed."""

    def __init__(self, name: str = "st"):
        self._name = name

    def __call__(self, *a, **k):
        return _Stub(f"{self._name}()")

    def __getattr__(self, item):
        return _Stub(f"{self._name}.{item}")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter([_Stub(f"{self._name}[0]"), _Stub(f"{self._name}[1]")])

    def __bool__(self):
        return False


def _columns(spec, **k):
    n = spec if isinstance(spec, int) else len(spec)
    return [_Stub(f"col{i}") for i in range(n)]


def _multiselect(label, options, default=None, **k):
    return list(default if default is not None else options)


def _cache_data(func=None, **kwargs):
    if func is None:
        return lambda f: f
    return func


class _SessionState(dict):
    """Streamlit's session_state supports both item and attribute access."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __setattr__(self, key, value):
        self[key] = value


def _make_stub() -> mock.MagicMock:
    st_stub = mock.MagicMock()
    st_stub.columns.side_effect = _columns
    st_stub.multiselect.side_effect = _multiselect
    st_stub.cache_data = _cache_data
    st_stub.session_state = _SessionState()
    st_stub.chat_input.return_value = None
    st_stub.button.return_value = False
    st_stub.sidebar = _Stub("sidebar")
    st_stub.expander.return_value = _Stub("expander")
    st_stub.chat_message.return_value = _Stub("chat_message")
    st_stub.spinner.return_value = _Stub("spinner")
    return st_stub


def main() -> None:
    failures = []
    real_streamlit = sys.modules.get("streamlit")
    for page in PAGES:
        # Swap only the streamlit key. mock.patch.dict restores the WHOLE dict on
        # exit, which deletes every module imported during the patch -- including
        # pandas' pyarrow extension-type submodule, whose re-import then fails with
        # "type extension already defined". Set and restore one key instead.
        sys.modules["streamlit"] = _make_stub()
        for mod in ("theme", "data_access", "assistant"):
            sys.modules.pop(mod, None)
        try:
            runpy.run_path(str(page), run_name="__page__")
            print(f"  PASS  {page.name}")
        except Exception:
            failures.append((page.name, traceback.format_exc()))
            print(f"  FAIL  {page.name}")
        finally:
            if real_streamlit is not None:
                sys.modules["streamlit"] = real_streamlit
            else:
                sys.modules.pop("streamlit", None)

    print()
    for name, tb in failures:
        print("=" * 78)
        print(name)
        print("=" * 78)
        print(tb)
    print(f"{len(PAGES) - len(failures)}/{len(PAGES)} pages rendered without error")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
