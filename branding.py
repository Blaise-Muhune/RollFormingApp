"""Niles Steel Tank branding assets for the operator UI."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_STATIC = Path(__file__).resolve().parent / "static"
# Opaque PNG: white/maroon logo on solid black (readable on the dark band).
LOGO_PATH = _STATIC / "niles-steel-tank-logo-opaque.png"
LOGO_FALLBACK_PATH = _STATIC / "niles-steel-tank-logo.png"


def _resolve_logo() -> Path | None:
    """Find the logo on disk (Cloud-safe: try package dir and CWD)."""
    candidates = (
        LOGO_PATH,
        LOGO_FALLBACK_PATH,
        Path.cwd() / "static" / "niles-steel-tank-logo-opaque.png",
        Path.cwd() / "static" / "niles-steel-tank-logo.png",
    )
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def render_logo_band() -> None:
    """Black NST band with a large centered logo (``st.image`` — Cloud-safe)."""
    path = _resolve_logo()

    # Full-bleed black bar behind the logo.
    st.markdown(
        '<div class="app-brand-band app-brand-band--bg" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )

    # Marker + centered logo (st.image always works when the PNG is on disk).
    st.markdown(
        '<span class="app-brand-logo-flag" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
    if path is None:
        st.markdown(
            '<p class="app-brand-fallback">Niles Steel Tank</p>',
            unsafe_allow_html=True,
        )
    else:
        # One wide center column keeps the logo visually centered.
        _l, mid, _r = st.columns([1.15, 1.7, 1.15])
        with mid:
            st.image(str(path), use_container_width=True)

    st.markdown(
        '<div class="app-brand-band-spacer" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
