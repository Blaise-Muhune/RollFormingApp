"""Niles Steel Tank branding assets for the operator UI."""

from __future__ import annotations

import base64
from functools import lru_cache
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


def _logo_bytes() -> bytes:
    path = _resolve_logo()
    return path.read_bytes() if path is not None else b""


@lru_cache(maxsize=1)
def logo_data_uri() -> str:
    raw = _logo_bytes()
    if not raw:
        return ""
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def logo_band_html() -> str:
    """HTML-only band (legacy). Prefer ``render_logo_band()`` on Streamlit Cloud."""
    uri = logo_data_uri()
    if uri:
        logo = (
            f'<img class="app-logo-band" src="{uri}" alt="Niles Steel Tank" '
            f'style="height:2.65rem;width:auto;max-width:min(16rem,85vw);" />'
        )
    else:
        logo = '<span class="app-brand-fallback">Niles Steel Tank</span>'
    return (
        '<div class="app-brand-band" '
        'style="background:#111111;padding:0.75rem 1rem;text-align:center;'
        "display:flex;justify-content:center;align-items:center;"
        'margin:0 0 1rem 0;border-bottom:2px solid #111111;">'
        f"{logo}</div>"
    )


def render_logo_band() -> None:
    """Black NST band with logo via ``st.image`` (works on Streamlit Cloud).

    Markdown ``data:`` images are unreliable across Streamlit versions; the tab
    favicon already proves the PNG is on disk — serve it the same way Streamlit
    serves other media.
    """
    path = _resolve_logo()
    # Full-bleed black strip; logo image sits on top via negative margin.
    st.markdown(
        '<div class="app-brand-band app-brand-band--native" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    if path is None:
        st.markdown(
            '<p class="app-brand-fallback" style="text-align:center;margin:0 0 1rem 0;'
            'position:relative;z-index:2;">Niles Steel Tank</p>',
            unsafe_allow_html=True,
        )
        return

    left, mid, right = st.columns([1, 2.4, 1])
    with mid:
        # Marker so theme CSS only targets this logo row (not photo overlays).
        st.markdown(
            '<span class="app-brand-logo-flag" aria-hidden="true"></span>',
            unsafe_allow_html=True,
        )
        st.image(str(path), width=300)
    st.markdown(
        '<div class="app-brand-band-spacer" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
