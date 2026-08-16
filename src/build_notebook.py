"""Convert notebooks/01_eda.py (percent-format) into a .ipynb.

The notebook is authored as a plain script so it can be executed and verified in
CI -- an .ipynb that has never been run is a liability in a submission. This
converts the verified script into the notebook reviewers expect to open.
"""
from __future__ import annotations

import json
from pathlib import Path

from common import ROOT

SRC = ROOT / "notebooks" / "01_eda.py"
DST = ROOT / "notebooks" / "01_eda.ipynb"


def parse_cells(text: str) -> list[dict]:
    cells: list[dict] = []
    kind, buf = "code", []

    def flush() -> None:
        body = "\n".join(buf).strip("\n")
        if not body.strip():
            return
        if kind == "markdown":
            lines = [
                (line[2:] if line.startswith("# ") else line.lstrip("#"))
                for line in body.split("\n")
            ]
            cells.append(
                {"cell_type": "markdown", "metadata": {},
                 "source": [f"{l}\n" for l in lines][:-1] + [lines[-1]]}
            )
        else:
            src = body.split("\n")
            cells.append(
                {"cell_type": "code", "execution_count": None, "metadata": {},
                 "outputs": [], "source": [f"{l}\n" for l in src][:-1] + [src[-1]]}
            )

    for line in text.split("\n"):
        if line.startswith("# %% [markdown]"):
            flush()
            kind, buf = "markdown", []
        elif line.startswith("# %%"):
            flush()
            kind, buf = "code", []
        else:
            buf.append(line)
    flush()
    return cells


def main() -> None:
    nb = {
        "cells": parse_cells(SRC.read_text(encoding="utf-8")),
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    DST.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    n_md = sum(1 for c in nb["cells"] if c["cell_type"] == "markdown")
    n_code = sum(1 for c in nb["cells"] if c["cell_type"] == "code")
    print(f"Wrote {DST} — {n_md} markdown cells, {n_code} code cells")


if __name__ == "__main__":
    main()
