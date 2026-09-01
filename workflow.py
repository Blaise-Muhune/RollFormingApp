"""Shared workflow state and navigation for the unified roll-forming app.

Stage 1 (Inspect) publishes a fitted rim equation into session state.
Stage 2 (Correct) consumes that payload so operators do not need to download
and re-upload JSON between two separate apps.
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

STEP_HOME = "home"
STEP_INSPECT = "inspect"
STEP_CORRECT = "correct"

RIM_PAYLOAD_KEY = "rim_equation_payload"
RIM_JSON_KEY = "rim_equation_json"
RIM_READY_KEY = "rim_equation_ready"
RIM_TARGET_RADIUS_KEY = "inspect_target_radius_in"
RIM_SOURCE_KEY = "rim_equation_source"
RIM_META_KEY = "rim_equation_meta"


def ensure_workflow_state() -> None:
    """Initialize workflow keys used across pages."""
    st.session_state.setdefault(RIM_READY_KEY, False)
    st.session_state.setdefault(RIM_PAYLOAD_KEY, None)
    st.session_state.setdefault(RIM_JSON_KEY, None)
    st.session_state.setdefault(RIM_TARGET_RADIUS_KEY, None)
    st.session_state.setdefault(RIM_SOURCE_KEY, None)
    st.session_state.setdefault(RIM_META_KEY, None)


def publish_rim_equation(
    payload: dict[str, Any],
    *,
    target_radius_inches: float | None = None,
    source: str = "inspect",
    meta: dict[str, Any] | None = None,
) -> str:
    """Store the Inspect-stage rim equation for Correct-stage consumption."""
    ensure_workflow_state()
    rim_json = json.dumps(payload, indent=2)
    # Idempotent: Inspect reruns while results are on screen; only invalidate
    # Correct-stage state when the equation actually changes.
    if (
        st.session_state.get(RIM_READY_KEY)
        and st.session_state.get(RIM_JSON_KEY) == rim_json
    ):
        if target_radius_inches is not None:
            st.session_state[RIM_TARGET_RADIUS_KEY] = float(target_radius_inches)
        if meta is not None:
            st.session_state[RIM_META_KEY] = meta
        return rim_json

    st.session_state[RIM_PAYLOAD_KEY] = payload
    st.session_state[RIM_JSON_KEY] = rim_json
    st.session_state[RIM_READY_KEY] = True
    st.session_state[RIM_SOURCE_KEY] = source
    st.session_state[RIM_META_KEY] = meta or {}
    if target_radius_inches is not None:
        st.session_state[RIM_TARGET_RADIUS_KEY] = float(target_radius_inches)
    # Invalidate any previously parsed Correct-stage coefficients so Correct
    # reloads the newest Inspect result, and allow target radius to refresh.
    st.session_state["ellipse_coefficients"] = None
    st.session_state["ellipse_autoload_token"] = rim_json
    st.session_state["ellipse_source"] = "inspect"
    st.session_state.pop("correct_target_radius_locked", None)
    return rim_json


def clear_rim_equation() -> None:
    """Drop the in-session handoff (does not clear machine/material setup)."""
    ensure_workflow_state()
    st.session_state[RIM_PAYLOAD_KEY] = None
    st.session_state[RIM_JSON_KEY] = None
    st.session_state[RIM_READY_KEY] = False
    st.session_state[RIM_TARGET_RADIUS_KEY] = None
    st.session_state[RIM_SOURCE_KEY] = None
    st.session_state[RIM_META_KEY] = None
    st.session_state["ellipse_coefficients"] = None
    st.session_state.pop("ellipse_autoload_token", None)


def rim_equation_ready() -> bool:
    ensure_workflow_state()
    return bool(st.session_state.get(RIM_READY_KEY) and st.session_state.get(RIM_JSON_KEY))


def get_rim_equation_json() -> str | None:
    ensure_workflow_state()
    value = st.session_state.get(RIM_JSON_KEY)
    return value if isinstance(value, str) and value.strip() else None


def get_inspect_target_radius() -> float | None:
    ensure_workflow_state()
    value = st.session_state.get(RIM_TARGET_RADIUS_KEY)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def render_workflow_nav(active: str) -> None:
    """Top-of-page step strip used by Quick Run, Inspect, and Correct."""
    ensure_workflow_state()
    ready = rim_equation_ready()

    # Spacer so the first row of buttons clears Streamlit's top toolbar.
    st.markdown('<div style="height:0.35rem"></div>', unsafe_allow_html=True)

    home_label = "Check roll"
    inspect_label = "2 · Inspect"
    correct_label = "3 · Correct"
    if ready:
        correct_label = "3 · Correct ✓"

    c1, c2, c3, status = st.columns([1, 1, 1, 1.4], gap="small")
    with c1:
        if st.button(
            home_label,
            use_container_width=True,
            type="primary" if active == STEP_HOME else "secondary",
            key=f"nav_home_{active}",
        ):
            st.switch_page("app.py")
    with c2:
        if st.button(
            inspect_label,
            use_container_width=True,
            type="primary" if active == STEP_INSPECT else "secondary",
            key=f"nav_inspect_{active}",
        ):
            st.switch_page("pages/1_Inspect.py")
    with c3:
        if st.button(
            correct_label,
            use_container_width=True,
            type="primary" if active == STEP_CORRECT else "secondary",
            key=f"nav_correct_{active}",
            disabled=False,
        ):
            st.switch_page("pages/2_Correct.py")
    with status:
        if ready:
            src = st.session_state.get(RIM_SOURCE_KEY) or "inspect"
            st.success(f"Rim equation ready ({src})")
        else:
            st.info("No rim equation yet — use Check roll / Inspect, or upload JSON on Correct.")

    st.divider()

