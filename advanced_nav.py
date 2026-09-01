"""Top-right page menu — replaces Streamlit's sidebar page list."""

from __future__ import annotations

import streamlit as st

_PAGES = (
    ("check", "Check roll", "app.py"),
    ("inspect", "Inspect", "pages/1_Inspect.py"),
    ("correct", "Correct", "pages/2_Correct.py"),
)


def _hide_sidebar_page_nav() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"],
        [data-testid="stSidebarNavItems"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _menu_popover(*, active: str) -> None:
    with st.popover("⋮", use_container_width=True):
        for key, label, path in _PAGES:
            if st.button(
                label,
                key=f"top_menu_{key}",
                use_container_width=True,
                type="primary" if active == key else "secondary",
            ):
                st.switch_page(path)


def render_top_menu(*, active: str, title_html: str | None = None) -> None:
    """Three-dot menu in the top-right; optional title on the same row."""
    _hide_sidebar_page_nav()
    if title_html:
        left, right = st.columns([11, 1], vertical_alignment="top")
        with left:
            st.markdown(title_html, unsafe_allow_html=True)
        with right:
            _menu_popover(active=active)
    else:
        _, right = st.columns([11, 1], vertical_alignment="top")
        with right:
            _menu_popover(active=active)
