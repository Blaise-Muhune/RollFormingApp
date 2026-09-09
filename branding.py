"""Niles Steel Tank branding for the operator UI."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

# Plain ASCII — emoji page icons can break on some Windows consoles/encodings.
PAGE_ICON = "RF"

_STATIC = Path(__file__).resolve().parent / "static"
LOGO_PATH = _STATIC / "niles-steel-tank-logo-opaque.png"
LOGO_FALLBACK_PATH = _STATIC / "niles-steel-tank-logo.png"


def render_logo_band() -> None:
    """Black brand band with text only (no image)."""
    st.markdown(
        '<div class="app-brand-band">'
        '<span class="app-brand-fallback">Niles Steel Tank</span>'
        "</div>",
        unsafe_allow_html=True,
    )
