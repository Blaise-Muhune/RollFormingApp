"""Top-right page menu — replaces Streamlit's sidebar page list."""

from __future__ import annotations

import streamlit as st

from branding import render_logo_band

_PAGES = (
    ("check", "Check roll", "app.py"),
    ("inspect", "Inspect", "pages/1_Inspect.py"),
    ("correct", "Correct", "pages/2_Correct.py"),
)


def _menu_popover(*, active: str) -> None:
    with st.popover("MENU", use_container_width=True):
        for key, label, path in _PAGES:
            if st.button(
                label,
                key=f"top_menu_{key}",
                use_container_width=True,
                type="primary" if active == key else "secondary",
            ):
                st.switch_page(path)


def render_top_menu(*, active: str, title_html: str | None = None) -> None:
    """NST logo band, centered page title, MENU top-right."""
    render_logo_band()
    st.markdown('<span class="nav-header-anchor" aria-hidden="true"></span>', unsafe_allow_html=True)
    _left, center, menu_col = st.columns([2, 8, 2], vertical_alignment="center")
    with center:
        if title_html:
            st.markdown(
                f'<div class="app-header-center">{title_html}</div>',
                unsafe_allow_html=True,
            )
    with menu_col:
        _menu_popover(active=active)
