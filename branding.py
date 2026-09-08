"""Niles Steel Tank branding for the operator UI."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_STATIC = Path(__file__).resolve().parent / "static"
# Kept for page_icon / favicon only.
LOGO_PATH = _STATIC / "niles-steel-tank-logo-opaque.png"
LOGO_FALLBACK_PATH = _STATIC / "niles-steel-tank-logo.png"


def _resolve_logo() -> Path | None:
    """Find a logo file for the browser tab icon."""
    for path in (LOGO_PATH, LOGO_FALLBACK_PATH):
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def render_logo_band() -> None:
    """Black brand band with text only (no image)."""
    st.markdown(
        '<div class="app-brand-band">'
        '<span class="app-brand-fallback">Niles Steel Tank</span>'
        "</div>",
        unsafe_allow_html=True,
    )
