"""Roll Forming app entry — top bar navigation (Check roll + More menu)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent

check_roll = st.Page(
    ROOT / "check_roll_page.py",
    title="Check roll",
    icon=":material/fact_check:",
    default=True,
)
inspect = st.Page(
    ROOT / "pages" / "1_Inspect.py",
    title="Inspect",
    icon=":material/search:",
)
correct = st.Page(
    ROOT / "pages" / "2_Correct.py",
    title="Correct",
    icon=":material/tune:",
)

pg = st.navigation(
    {
        "": [check_roll],
        "More": [inspect, correct],
    },
    position="top",
)
pg.run()
