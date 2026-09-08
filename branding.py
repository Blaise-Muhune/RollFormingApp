"""Niles Steel Tank branding assets for the operator UI."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_STATIC = Path(__file__).resolve().parent / "static"
# Original PNG has transparency — black areas become invisible on our light UI.
LOGO_PATH = _STATIC / "niles-steel-tank-logo-opaque.png"
LOGO_FALLBACK_PATH = _STATIC / "niles-steel-tank-logo.png"


def _logo_bytes() -> bytes:
    if LOGO_PATH.is_file():
        return LOGO_PATH.read_bytes()
    if LOGO_FALLBACK_PATH.is_file():
        return LOGO_FALLBACK_PATH.read_bytes()
    return b""


@lru_cache(maxsize=1)
def logo_data_uri() -> str:
    raw = _logo_bytes()
    if not raw:
        return ""
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def logo_band_html() -> str:
    """Dark top band with opaque NST logo (readable on any page background)."""
    uri = logo_data_uri()
    if uri:
        logo = f'<img class="app-logo-band" src="{uri}" alt="Niles Steel Tank" />'
    else:
        logo = '<span class="app-brand-fallback">Niles Steel Tank</span>'
    return (
        '<div class="app-brand-band" '
        'style="background:#111111;padding:0.75rem 1rem;text-align:center;'
        'display:flex;justify-content:center;align-items:center;'
        'margin:0 0 1rem 0;border-bottom:2px solid #111111;">'
        f"{logo}</div>"
    )
