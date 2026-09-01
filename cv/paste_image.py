"""Accept a clipboard image (Ctrl+V) in Streamlit.

st.file_uploader cannot take paste. This small HTML component listens for
image paste on the page and returns JPEG/PNG bytes.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit.components.v1 as components

_FRONTEND = Path(__file__).resolve().parent / "paste_image_frontend"
_paste = components.declare_component("rollforming_paste_image", path=str(_FRONTEND))


def _decode_component_value(raw) -> bytes | None:
    if not raw:
        return None
    data_url = raw.get("dataUrl") if isinstance(raw, dict) else None
    if not isinstance(data_url, str) or "," not in data_url:
        return None
    try:
        return base64.b64decode(data_url.split(",", 1)[1])
    except Exception:
        return None


def listen_for_pasted_image(*, key: str = "paste_image") -> bytes | None:
    """If the operator just pasted an image, return its bytes."""
    return _decode_component_value(_paste(key=key, default=None))
