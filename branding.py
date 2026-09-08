"""Niles Steel Tank branding assets for the operator UI."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

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
    """Centered logo band HTML (used by components.html — Cloud-safe)."""
    uri = logo_data_uri()
    if uri:
        logo = (
            f'<img src="{uri}" alt="Niles Steel Tank" '
            f'style="display:block;margin:0 auto;height:52px;width:auto;'
            f'max-width:min(340px,88vw);object-fit:contain;" />'
        )
    else:
        logo = (
            '<div style="color:#fff;font-family:Arial Black,Arial,sans-serif;'
            "letter-spacing:0.14em;text-transform:uppercase;font-size:15px;"
            'text-align:center;">Niles Steel Tank</div>'
        )
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<style>
  html, body {{
    margin: 0;
    padding: 0;
    background: #111111;
    overflow: hidden;
  }}
  .band {{
    background: #111111;
    width: 100%;
    min-height: 76px;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 14px 20px;
  }}
</style>
</head>
<body>
  <div class="band">{logo}</div>
</body>
</html>
"""


def render_logo_band() -> None:
    """Full-width black NST band with a large centered logo."""
    components.html(logo_band_html(), height=76, scrolling=False)
    # Pull the iframe tight to the page edges / kill Streamlit chrome gaps.
    st.markdown(
        '<span class="app-brand-iframe-flag" aria-hidden="true"></span>',
        unsafe_allow_html=True,
    )
