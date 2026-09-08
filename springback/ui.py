import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_ASSETS = Path(__file__).resolve().parent


def _read_css(name: str) -> str:
    return (_ASSETS / name).read_text(encoding="utf-8")


def _build_css(*, wide: bool) -> str:
    css = _read_css("theme.css")
    if wide:
        css += "\n" + _read_css("theme_inspect.css")
    return css


def apply_theme(*, wide: bool = False) -> None:
    """Inject app CSS into the document head (invisible — never rendered as page text)."""
    css = _build_css(wide=wide)
    components.html(
        f"""
        <script>
        (function () {{
            const doc = window.parent.document;
            let el = doc.getElementById("rf-app-theme");
            if (!el) {{
                el = doc.createElement("style");
                el.id = "rf-app-theme";
                doc.head.appendChild(el);
            }}
            el.textContent = {json.dumps(css)};
        }})();
        </script>
        """,
        height=0,
    )


def step_label(text: str) -> None:
    st.markdown(f'<p class="step-label">{text}</p>', unsafe_allow_html=True)


def step_label_row(label: str, badge_html: str = "") -> None:
    st.markdown(
        f'<div class="step-label-row">'
        f'<p class="step-label">{label}</p>{badge_html}'
        f"</div>",
        unsafe_allow_html=True,
    )


def start_badge(start_lr: dict) -> str:
    if start_lr.get("verified"):
        return '<span class="badge badge-verified">Verified</span>'
    if start_lr.get("source") in ("chart_anchor", "chart_calibrated"):
        return '<span class="badge badge-fill">Chart</span>'
    return '<span class="badge badge-estimate">Estimate</span>'


def lr_hero(l_mm: float, r_mm: float, *, highlight: bool = False) -> str:
    cls = "lr-hero-tile highlight" if highlight else "lr-hero-tile"
    return f"""
    <div class="lr-hero">
      <div class="{cls}">
        <div class="lab">L axis</div>
        <div class="val">{l_mm:.0f}</div>
        <div class="unit">mm</div>
      </div>
      <div class="{cls}">
        <div class="lab">R axis</div>
        <div class="val">{r_mm:.0f}</div>
        <div class="unit">mm</div>
      </div>
    </div>
    """


def panel_start(title, purple=False):
    """Create the visual start of a panel used by the main page layout."""
    title_class = "panel-title-purple" if purple else "panel-title"
    st.markdown('<div class="panel-anchor"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="{title_class}">{title}</div>', unsafe_allow_html=True)


def metric_row(label, value):
    """Render a two-column label/value row with shared app styling."""
    st.markdown(
        f'<div class="metric-row"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


def big_metric(label, value):
    """Render the large headline metric used in result panels."""
    st.markdown(
        f'<div class="metric-label">{label}</div><div class="metric-big">{value}</div>',
        unsafe_allow_html=True,
    )


def number_input(label, value, min_value=None, max_value=None, step=0.1, fmt="%.3f", key=None):
    """Wrapper that normalizes numeric defaults before passing them to Streamlit."""
    return st.number_input(
        label,
        value=float(value),
        min_value=min_value,
        max_value=max_value,
        step=step,
        format=fmt,
        key=key,
    )
