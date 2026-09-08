"""Full-screen busy lock so users don't click mid-analysis / mid-AI call.

Streamlit keeps the previous page interactive until a rerun finishes. We inject an
overlay into the parent page via ``components.html`` so it appears as soon as the
component mounts, and we also render an in-app busy screen on the dedicated
``ui_busy`` rerun path.
"""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components


def request_busy(action: str, message: str, detail: str = "", **payload) -> None:
    """Queue a busy action and rerun immediately (keeps the click handler fast)."""
    st.session_state.ui_busy = {
        "action": action,
        "message": message,
        "detail": detail
        or "Please wait — don't change settings or click other buttons.",
        "payload": payload,
    }
    st.rerun()


def clear_busy() -> None:
    st.session_state.pop("ui_busy", None)


def is_busy() -> bool:
    return bool(st.session_state.get("ui_busy")) or bool(
        st.session_state.get("hold_lock_for_analysis")
    )


def render_busy_screen(message: str, detail: str = "") -> None:
    """Dedicated in-app loading view (no competing action buttons)."""
    detail = detail or "Please wait — don't change settings or click other buttons."
    st.markdown(
        f'<div style="min-height:50vh;display:flex;flex-direction:column;align-items:center;'
        f'justify-content:center;text-align:center;gap:0.75rem;padding:1.25rem 1rem;">'
        f'<div style="width:52px;height:52px;border-radius:0;'
        f'border:4px solid rgba(17,17,17,0.15);border-top-color:#111111;'
        f'animation:rfspin 0.9s linear infinite;"></div>'
        f'<h2 style="margin:0.5rem 0 0 0;font-size:clamp(1.1rem,4vw,1.35rem);">{message}</h2>'
        f'<p style="color:#5c5c58;max-width:min(34rem,92vw);margin:0;line-height:1.45;">{detail}</p>'
        f'</div>',
        unsafe_allow_html=True,
    )


def lock_ui(message: str, detail: str = "") -> None:
    """Inject a parent-document overlay that blocks clicks across the whole app."""
    detail = detail or "Please wait — don't change settings or click other buttons."
    payload = json.dumps({"message": message, "detail": detail})
    components.html(
        f"""
        <script>
        const payload = {payload};
        const doc = window.parent.document;
        let el = doc.getElementById('rf-busy-overlay');
        if (!el) {{
          el = doc.createElement('div');
          el.id = 'rf-busy-overlay';
          doc.body.appendChild(el);
        }}
        el.style.cssText = `
          position: fixed;
          inset: 0;
          z-index: 2147483646;
          background: rgba(244, 244, 240, 0.92);
          display: flex;
          align-items: center;
          justify-content: center;
          backdrop-filter: blur(3px);
          padding: max(1rem, env(safe-area-inset-top, 0px)) max(1rem, env(safe-area-inset-right, 0px)) max(1rem, env(safe-area-inset-bottom, 0px)) max(1rem, env(safe-area-inset-left, 0px));
        `;
        el.innerHTML = `
          <div style="
            text-align: center;
            color: #111111;
            font-family: system-ui, -apple-system, Segoe UI, sans-serif;
            max-width: min(28rem, 92vw);
            padding: 1.25rem;
          ">
            <div style="
              width: 52px; height: 52px; margin: 0 auto 1rem auto;
              border-radius: 0;
              border: 4px solid rgba(17,17,17,0.15);
              border-top-color: #111111;
              animation: rfspin 0.9s linear infinite;
            "></div>
            <div style="font-size: clamp(1.05rem, 4vw, 1.35rem); font-weight: 700; margin-bottom: 0.5rem;">
              ${{payload.message}}
            </div>
            <div style="font-size: 0.92rem; color: #5c5c58; line-height: 1.45;">
              ${{payload.detail}}
            </div>
          </div>
          <style>
            @keyframes rfspin {{ to {{ transform: rotate(360deg); }} }}
          </style>
        `;
        </script>
        """,
        height=0,
        width=0,
    )


def unlock_ui() -> None:
    """Remove the parent-document overlay if present."""
    components.html(
        """
        <script>
        const el = window.parent.document.getElementById('rf-busy-overlay');
        if (el) el.remove();
        </script>
        """,
        height=0,
        width=0,
    )


class busy_overlay:
    """Context manager: lock UI for the duration of a long operation."""

    def __init__(self, message: str, detail: str = ""):
        self.message = message
        self.detail = detail

    def __enter__(self):
        lock_ui(self.message, self.detail)
        self._spinner = st.spinner(self.message)
        self._spinner.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._spinner.__exit__(exc_type, exc, tb)
        finally:
            unlock_ui()
        return False
