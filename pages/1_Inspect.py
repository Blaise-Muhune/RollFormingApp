"""Inspect stage — roll-forming computer-vision workflow.

Upload an image, detect/crop the tank opening, extract the rim, compute
correction guidance, and publish the fitted rim equation into session state for
the Correct stage. Lower-level helpers live under ``cv/``.
"""

import cv2                  # Computer vision library for image processing
import json
import numpy as np
import matplotlib.pyplot as plt
import streamlit as st      # App framework for building interactive web apps in Python
from PIL import Image       # Python Imaging Library for image manipulation
from io import BytesIO      # For handling in-memory byte streams (used for image upload, specifically camera capture)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from cv.detection import load_detector, detect_and_crop_tank
from cv.preprocessing import generate_edge_map
from cv.rim_analysis import detect_rim_multistart
from cv.correction import compute_curvature_correction
from cv.rim_fit import (
    build_rim_equation_export,
    fit_rim_equation,
    format_signed_term,
    rim_equation_csv as build_rim_equation_csv,
)
from cv import openai_assist as ai
from cv import ui_busy
from springback.ui import apply_theme, step_label
from advanced_nav import render_top_menu
from branding import LOGO_PATH
from workflow import STEP_INSPECT, publish_rim_equation

ai.load_project_dotenv()

# -------------------------------------------------
# STREAMLIT PAGE SETUP
# -------------------------------------------------
st.set_page_config(
    page_title="Inspect rim",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="collapsed",
)
apply_theme(wide=True)

# Clear a stuck busy overlay from an interrupted prior run.
if st.session_state.pop("hold_lock_for_analysis", None):
    pass
if st.session_state.get("ui_busy") and st.session_state["ui_busy"].get("action") == "run_analysis":
    st.session_state.pop("ui_busy", None)

render_top_menu(
    active="inspect",
    title_html='<div class="app-title">Inspect rim</div>',
)

_INSPECT_PHOTO_HELP = (
    "Clear photo of the rolled opening, centered in frame. "
    "Avoid busy backgrounds for best auto-crop."
)

st.markdown(
    f'<p class="step-label">Photo'
    f'<span class="step-help" title="{_INSPECT_PHOTO_HELP}">?</span></p>',
    unsafe_allow_html=True,
)
st.markdown('<span class="photo-source-picker" aria-hidden="true"></span>', unsafe_allow_html=True)
_ins_pick1, _ins_pick2 = st.columns(2, gap="small")
_ins_photo_source = st.session_state.get("inspect_photo_source", "Upload")
with _ins_pick1:
    if st.button(
        "Upload",
        use_container_width=True,
        type="primary" if _ins_photo_source == "Upload" else "secondary",
        key="inspect_pick_upload",
    ):
        st.session_state["inspect_photo_source"] = "Upload"
        st.rerun()
with _ins_pick2:
    if st.button(
        "Take photo",
        use_container_width=True,
        type="primary" if _ins_photo_source == "Take photo" else "secondary",
        key="inspect_pick_camera",
    ):
        st.session_state["inspect_photo_source"] = "Take photo"
        st.rerun()
inspect_photo_source = st.session_state.get("inspect_photo_source", "Upload")

inspect_photo_bytes = None
if inspect_photo_source == "Upload":
    uploaded_file = st.file_uploader(
        "Photo file",
        type=["jpg", "jpeg", "png", "webp"],
        key="inspect_upload",
        label_visibility="collapsed",
    )
    if uploaded_file is not None:
        inspect_photo_bytes = uploaded_file.getvalue()
else:
    captured = st.session_state.get("inspect_camera_bytes")
    if captured:
        st.image(captured, use_container_width=True)
        if st.button("Retake", key="inspect_retake"):
            st.session_state.pop("inspect_camera_bytes", None)
            st.session_state.pop("inspect_camera", None)
            st.rerun()
        inspect_photo_bytes = captured
    else:
        shot = st.camera_input(
            "Camera",
            key="inspect_camera",
            label_visibility="collapsed",
        )
        if shot is not None:
            st.session_state["inspect_camera_bytes"] = shot.getvalue()
            st.session_state.pop("inspect_camera", None)
            st.rerun()


# -------------------------------------------------
# CACHED PIPELINE FUNCTIONS
# -------------------------------------------------
# Streamlit reruns the full script whenever a widget changes.
# These cached functions prevent expensive operations from rerunning
# unless their inputs actually change.
@st.cache_resource
def get_detector():
    """Load the GroundingDINO detector once per Streamlit process.

    The model is large and may download on first use through Hugging Face.
    Keep this as a resource cache rather than a data cache because the detector
    object is not plain serializable data.
    """
    return load_detector()


@st.cache_data(show_spinner=False)
def cached_detection(image_bytes, threshold, crop_margin_version=2):
    """Run object detection on stable bytes so Streamlit can cache the result."""
    image_for_detection = Image.open(BytesIO(image_bytes)).convert("RGB")

    detector = get_detector()

    return detect_and_crop_tank(
        image=image_for_detection,
        detector=detector,
        threshold=threshold
    )


@st.cache_data(show_spinner=False)
def cached_edge_map(
    crop_rgb,
    blur_kernel,
    canny_low,
    canny_high
):
    """Cache Canny edge extraction for a crop and its preprocessing settings."""
    return generate_edge_map(
        crop_rgb=crop_rgb,
        blur_kernel=blur_kernel,
        canny_low=canny_low,
        canny_high=canny_high
    )


@st.cache_data(show_spinner=False)
def cached_rim_detection(
    edges,
    center_x,
    center_y,
    expected_radius,
    search_band,
    max_step_change,
    num_points,
    window_size
):
    """Cache radial rim detection, which is the most parameter-sensitive step."""
    return detect_rim_multistart(
        edges=edges,
        center_x=center_x,
        center_y=center_y,
        expected_radius=expected_radius,
        search_band=search_band,
        max_step_change=max_step_change,
        num_points=num_points,
        window_size=window_size
    )


def fig_to_streamlit(fig):
    """Render a Matplotlib figure and immediately release its memory."""
    st.pyplot(fig)
    plt.close(fig)


def fig_to_pil(fig):
    """Snapshot a Matplotlib figure to a PIL image without closing it."""
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    buf.seek(0)
    return Image.open(buf).convert("RGB").copy()


def pil_to_jpeg_bytes(img: Image.Image, quality: int = 85) -> bytes:
    buf = BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def ndarray_to_jpeg_bytes(arr, quality: int = 85) -> bytes:
    return pil_to_jpeg_bytes(ai.ndarray_to_pil(arr), quality=quality)


def cached_ai_value(cache_key, generator):
    """Run an AI call once per cache key within the Streamlit session.

    Empty strings / empty dicts are not cached so failed calls can be retried.
    """
    if "ai_cache" not in st.session_state:
        st.session_state.ai_cache = {}
    existing = st.session_state.ai_cache.get(cache_key)
    if isinstance(existing, str) and existing.strip():
        return existing
    if isinstance(existing, dict) and existing:
        return existing
    if cache_key in st.session_state.ai_cache:
        del st.session_state.ai_cache[cache_key]
    value = generator()
    if isinstance(value, str):
        if not value.strip():
            raise RuntimeError("OpenAI returned an empty response. Click again to retry.")
        st.session_state.ai_cache[cache_key] = value.strip()
    elif isinstance(value, dict):
        if not value:
            raise RuntimeError("OpenAI returned an empty response. Click again to retry.")
        st.session_state.ai_cache[cache_key] = value
    else:
        st.session_state.ai_cache[cache_key] = value
    return st.session_state.ai_cache[cache_key]


def cached_ai_text(cache_key, generator):
    """Run an AI call once per cache key and require a non-empty string."""
    return cached_ai_value(cache_key, generator)


# Rim-equation fit helpers live in cv.rim_fit (shared with Quick Run).

# -------------------------------------------------
# SIDEBAR CONTROLS
# -------------------------------------------------
# Apply AI calibration before widgets are created so values stick on rerun.
if "apply_ai_settings" in st.session_state:
    pending = st.session_state.pop("apply_ai_settings")
    for key, value in pending.items():
        st.session_state[key] = value
    st.sidebar.success("Applied AI calibration suggestions.")

with st.sidebar:
    step_label("AI assist")

ai_enabled = st.sidebar.checkbox(
    "Enable OpenAI Assist",
    value=True,
    help="Uses GPT vision for photo QA, operator guidance, troubleshooting, shift notes, and Q&A. Classical CV still does the measuring.",
)

ai_model = st.sidebar.selectbox(
    "Vision Model",
    options=list(ai.FALLBACK_MODELS),
    index=0,
    help="Default is gpt-5.6-terra (vision, balanced cost). Use gpt-5.6 / gpt-5.6-sol for tougher reasoning.",
)

ai_api_key_input = st.sidebar.text_input(
    "Your OpenAI API key (optional)",
    type="password",
    placeholder="Leave blank to use the shop .env key",
    help="If you paste a key, it is used instead of OPENAI_API_KEY in .env.",
    key="user_openai_api_key",
)
openai_api_key = ai.resolve_api_key(ai_api_key_input)
key_source = ai.api_key_source(ai_api_key_input)

if ai_enabled and openai_api_key:
    if key_source == "typed":
        st.sidebar.caption("Using the key you entered · model: " + ai_model)
    else:
        st.sidebar.caption("Using OPENAI_API_KEY from .env · model: " + ai_model)
elif ai_enabled:
    st.sidebar.warning("No OpenAI key. Add one in .env as OPENAI_API_KEY, or paste yours above.")
else:
    st.sidebar.caption("AI assist is off.")

with st.sidebar:
    step_label("Detection")

use_auto_crop = st.sidebar.checkbox(
    "Use Auto-Crop",
    value=True,
    key="setting_use_auto_crop",
    help="Uses AI to find the tank opening and crop to it. Turn off if the crop is wrong and analyze the full image instead.",
)

detection_threshold = st.sidebar.slider(
    "Detection Threshold",
    0.05,
    0.90,
    0.25,
    0.05,
    key="setting_detection_threshold",
    help="Minimum AI confidence to accept a detection. Lower finds more candidates (including false ones); higher is stricter.",
)

canny_low = st.sidebar.slider(
    "Low Gradient Threshold",
    0,
    255,
    40,
    key="setting_canny_low",
    help="Lower Canny edge threshold. Lower values keep weaker edges (more detail, more noise).",
)
canny_high = st.sidebar.slider(
    "High Gradient Threshold",
    0,
    255,
    120,
    key="setting_canny_high",
    help="Upper Canny edge threshold. Higher values keep only strong edges (cleaner, may miss a faint rim).",
)

blur_kernel = st.sidebar.selectbox(
    "Blur Kernel Size",
    [3, 5, 7, 9, 11, 13],
    index=3,
    key="setting_blur_kernel",
    help="Softens the image before edge detection. Larger blur reduces noise but can blur out a thin rim.",
)

with st.sidebar:
    step_label("Rim search")

num_points = st.sidebar.slider(
    "Angular Samples",
    180,
    1440,
    720,
    180,
    key="setting_num_points",
    help="How many points to sample around the circumference. More points = finer detail, slightly slower.",
)

search_band = st.sidebar.slider(
    "Search Band [pixels]",
    20,
    300,
    120,
    10,
    key="setting_search_band",
    help="How far inside/outside the expected circle to search for the rim edge. Widen if the rim is missing.",
)

max_step_change = st.sidebar.slider(
    "Max Step Change [pixels]",
    5,
    100,
    30,
    5,
    key="setting_max_step_change",
    help="Largest allowed radius jump between neighboring samples. Lower stops wild jumps onto wrong edges.",
)

window_size = st.sidebar.slider(
    "Smoothing Window",
    3,
    75,
    21,
    2,
    key="setting_window_size",
    help="Circular moving-average window on the rim profile. Higher = smoother trend, less local detail.",
)

with st.sidebar:
    step_label("Curvature")

curvature_tolerance = st.sidebar.number_input(
    "Curvature Tolerance [%]",
    value=3.0,
    step=0.5,
    key="setting_curvature_tolerance",
    help="How far from the target curvature still counts as OK (green). Smaller % marks more zones as too flat/tight.",
)

target_mode = st.sidebar.radio(
    "Target Radius Source",
    [
        "Smooth bend profile",
        "Median detected radius",
        "Expected/manual radius"
    ],
    help=(
        "Smooth bend profile: ignore gradual ovality and flag local flats/kinks. "
        "Median: compare each spot to this part's average shape. "
        "Expected/manual: compare to the Expected Radius you set below."
    ),
)

real_radius_inches = st.sidebar.number_input(
    "Known Actual Radius [in]",
    value=45.0,
    step=1.0,
    help="Real-world radius of the opening in inches. Used to convert pixels to inches for reporting and exports.",
)

# -------------------------------------------------
# LOAD IMAGE
# -------------------------------------------------
if inspect_photo_bytes is None:
    st.caption("Upload or take a photo to begin.")
    st.stop()

uploaded_bytes = inspect_photo_bytes
image = Image.open(BytesIO(uploaded_bytes)).convert("RGB")

with st.expander("Uploaded image", expanded=False):
    st.image(image, use_container_width=True)

# -------------------------------------------------
# OPENAI PHOTO QUALITY + CALIBRATION
# -------------------------------------------------
current_calibration = {
    "use_auto_crop": bool(use_auto_crop),
    "detection_threshold": float(detection_threshold),
    "canny_low": int(canny_low),
    "canny_high": int(canny_high),
    "blur_kernel": int(blur_kernel),
    "num_points": int(num_points),
    "search_band": int(search_band),
    "max_step_change": int(max_step_change),
    "window_size": int(window_size),
    "curvature_tolerance": float(curvature_tolerance),
}

# Keep a copy for busy-job handlers (click handlers only queue work, then rerun).
st.session_state["uploaded_bytes"] = uploaded_bytes
st.session_state["current_calibration"] = current_calibration
st.session_state["ai_model"] = ai_model
st.session_state["openai_api_key"] = openai_api_key
st.session_state["ai_enabled"] = ai_enabled
st.session_state["real_radius_inches"] = float(real_radius_inches)
st.session_state["target_mode"] = target_mode

image_id = ai.content_hash(uploaded_bytes)
settings_id = ai.content_hash(current_calibration, float(real_radius_inches), target_mode)
photo_display_key = "photo_cal_img_" + ai.content_hash(uploaded_bytes, ai_model)

# -------------------------------------------------
# BUSY JOB HANDLER (full-screen lock, no competing clicks)
# -------------------------------------------------
busy_job = st.session_state.get("ui_busy")
if busy_job:
    message = busy_job.get("message") or "Working…"
    detail = busy_job.get("detail") or (
        "Please wait — don't change settings or click other buttons."
    )
    ui_busy.render_busy_screen(message, detail)
    ui_busy.lock_ui(message, detail)
    action = busy_job.get("action")
    payload = busy_job.get("payload") or {}
    try:
        if action == "photo_calibrate":
            img = Image.open(BytesIO(st.session_state["uploaded_bytes"])).convert("RGB")
            result = ai.check_photo_and_calibrate(
                st.session_state["openai_api_key"],
                img,
                current_settings=st.session_state.get("current_calibration") or {},
                model=st.session_state.get("ai_model"),
            )
            st.session_state.setdefault("ai_cache", {})[payload["cache_key"]] = result
            st.session_state["latest_photo_calibration"] = result

        elif action == "run_analysis":
            # Kept for compatibility; Run analysis now executes inline (no extra reruns).
            st.session_state.analysis_run = True
            st.session_state.analysis_image_id = payload["image_id"]
            st.session_state.analysis_settings_id = payload["settings_id"]

        elif action == "ai_summary":
            metrics = payload["metrics"]
            zone = Image.open(BytesIO(payload["zone_bytes"])).convert("RGB")
            original = Image.open(BytesIO(st.session_state["uploaded_bytes"])).convert("RGB")
            text = ai.operator_summary(
                st.session_state["openai_api_key"],
                metrics=metrics,
                zone_image=zone,
                original=original,
                model=st.session_state.get("ai_model"),
            )
            st.session_state.setdefault("ai_cache", {})[payload["cache_key"]] = text

        elif action == "ai_opinion":
            metrics = payload["metrics"]
            zone = Image.open(BytesIO(payload["zone_bytes"])).convert("RGB")
            text = ai.zone_second_opinion(
                st.session_state["openai_api_key"],
                metrics=metrics,
                zone_image=zone,
                model=st.session_state.get("ai_model"),
            )
            st.session_state.setdefault("ai_cache", {})[payload["cache_key"]] = text

        elif action == "ai_report":
            metrics = payload["metrics"]
            prior = st.session_state.get("ai_cache", {}).get(payload.get("summary_key"))
            text = ai.shift_report(
                st.session_state["openai_api_key"],
                metrics=metrics,
                operator_guidance=prior,
                model=st.session_state.get("ai_model"),
            )
            st.session_state.setdefault("ai_cache", {})[payload["cache_key"]] = text

        elif action == "ai_all_guidance":
            metrics = payload["metrics"]
            zone = Image.open(BytesIO(payload["zone_bytes"])).convert("RGB")
            original = Image.open(BytesIO(st.session_state["uploaded_bytes"])).convert("RGB")
            cache = st.session_state.setdefault("ai_cache", {})
            for key in (
                payload["summary_key"],
                payload["opinion_key"],
                payload["report_key"],
            ):
                cache.pop(key, None)
            cache[payload["summary_key"]] = ai.operator_summary(
                st.session_state["openai_api_key"],
                metrics=metrics,
                zone_image=zone,
                original=original,
                model=st.session_state.get("ai_model"),
            )
            cache[payload["opinion_key"]] = ai.zone_second_opinion(
                st.session_state["openai_api_key"],
                metrics=metrics,
                zone_image=zone,
                model=st.session_state.get("ai_model"),
            )
            cache[payload["report_key"]] = ai.shift_report(
                st.session_state["openai_api_key"],
                metrics=metrics,
                operator_guidance=cache[payload["summary_key"]],
                model=st.session_state.get("ai_model"),
            )

        elif action == "ai_chat":
            metrics = payload["metrics"]
            zone = Image.open(BytesIO(payload["zone_bytes"])).convert("RGB")
            original = Image.open(BytesIO(st.session_state["uploaded_bytes"])).convert("RGB")
            answer = ai.answer_question(
                st.session_state["openai_api_key"],
                payload["question"],
                metrics=metrics,
                images=[zone, original],
                history=payload.get("history") or [],
                model=st.session_state.get("ai_model"),
            )
            st.session_state.ai_chat_messages.append(
                {"role": "assistant", "content": answer}
            )

        elif action == "ai_edges":
            img = Image.open(BytesIO(st.session_state["uploaded_bytes"])).convert("RGB")
            crop = Image.open(BytesIO(payload["crop_bytes"])).convert("RGB")
            edge_img = Image.open(BytesIO(payload["edge_bytes"])).convert("RGB")
            tip = ai.troubleshoot_failure(
                st.session_state["openai_api_key"],
                original=img,
                crop=crop,
                edges=edge_img,
                issue=payload["issue"],
                settings=payload.get("settings") or {},
                model=st.session_state.get("ai_model"),
            )
            st.session_state.setdefault("ai_cache", {})[payload["cache_key"]] = tip

        elif action == "ai_detect_fail":
            img = Image.open(BytesIO(st.session_state["uploaded_bytes"])).convert("RGB")
            tip = ai.troubleshoot_failure(
                st.session_state["openai_api_key"],
                original=img,
                issue=payload["issue"],
                settings=payload.get("settings") or {},
                model=st.session_state.get("ai_model"),
            )
            st.session_state.setdefault("ai_cache", {})[payload["cache_key"]] = tip

    except Exception as exc:
        st.session_state["busy_error"] = str(exc)
    finally:
        ui_busy.clear_busy()
        ui_busy.unlock_ui()
        st.session_state.hold_lock_for_analysis = False
    st.rerun()

_busy_err = st.session_state.pop("busy_error", None)
if _busy_err:
    st.error(f"Last action failed: {_busy_err}")

if ai_enabled and openai_api_key:
    step_label("AI photo check")
    qa_col1, qa_col2 = st.columns([1.2, 3.8])
    with qa_col1:
        run_photo_qa = st.button("Check photo", type="primary")
    with qa_col2:
        st.caption(
            "Reviews glare, framing, blur, and angle — then suggests sidebar "
            "calibration you can apply in one click."
        )

    if run_photo_qa:
        st.session_state.setdefault("ai_cache", {}).pop(photo_display_key, None)
        with ui_busy.busy_overlay(
            "Checking photo & suggesting calibration…",
            "Please wait — don't change settings or click other buttons.",
        ):
            photo_cal_result = ai.check_photo_and_calibrate(
                openai_api_key,
                image,
                current_settings=current_calibration,
                model=ai_model,
            )
        st.session_state.setdefault("ai_cache", {})[photo_display_key] = photo_cal_result
        st.session_state["latest_photo_calibration"] = photo_cal_result

    photo_cal = st.session_state.get("ai_cache", {}).get(photo_display_key)
    if photo_cal:
        st.markdown(photo_cal.get("quality_markdown") or "")
        if photo_cal.get("notes"):
            st.info(photo_cal["notes"])

        suggestions = ai.sanitize_suggestions(
            photo_cal.get("suggestions"),
            current_calibration,
        )
        reasons = photo_cal.get("reasons") or {}

        rows = []
        changed = 0
        for key in ai.CALIBRATION_SPECS:
            cur = current_calibration[key]
            sug = suggestions[key]
            is_changed = cur != sug
            if is_changed:
                changed += 1
            rows.append(
                {
                    "Setting": ai.SETTING_LABELS[key],
                    "Current": cur,
                    "AI suggestion": sug,
                    "Changed": "Yes" if is_changed else "No",
                    "Why": reasons.get(key, "—"),
                }
            )

        step_label("Suggested calibration")
        st.caption(
            f"{changed} setting(s) differ from your current sidebar values. "
            "Manual geometry (center / expected radius) stays under your control "
            "after the crop."
        )
        st.dataframe(rows, use_container_width=True, hide_index=True)

        apply_col1, apply_col2, apply_col3 = st.columns([1.4, 1.4, 2])
        with apply_col1:
            if st.button(
                "Apply all AI suggestions",
                type="primary",
                disabled=(changed == 0),
                help="Writes every suggested value into the sidebar.",
            ):
                st.session_state["apply_ai_settings"] = ai.suggestions_to_widget_state(
                    suggestions
                )
                st.rerun()
        with apply_col2:
            if st.button(
                "Apply changed only",
                disabled=(changed == 0),
                help="Only updates settings that differ from what you have now.",
            ):
                changed_only = {
                    k: v
                    for k, v in suggestions.items()
                    if current_calibration.get(k) != v
                }
                st.session_state["apply_ai_settings"] = ai.suggestions_to_widget_state(
                    changed_only
                )
                st.rerun()
        with apply_col3:
            st.caption(
                "After applying, click **Run analysis**, then check Edge Detection "
                "and tweak center/radius if the rim dots are off."
            )
elif ai_enabled:
    st.info("Add an OpenAI API key in the sidebar to enable photo quality checks and operator guidance.")

# -------------------------------------------------
# RUN ANALYSIS GATE
# -------------------------------------------------
# Heavy CV work waits until the user clicks Run, so they can check the photo,
# apply AI calibration, then analyze with the chosen settings.
if st.session_state.get("analysis_image_id") != image_id:
    st.session_state.analysis_image_id = image_id
    st.session_state.analysis_run = False
    st.session_state.analysis_settings_id = None

st.divider()
step_label("Run analysis")
run_col1, run_col2 = st.columns([1.2, 3.8])
with run_col1:
    run_clicked = st.button(
        "Run analysis",
        type="primary",
        use_container_width=True,
        help="Runs tank detection, rim search, curvature, and correction plots using the current sidebar settings.",
    )
with run_col2:
    st.caption(
        "Suggested flow: Check photo → Apply AI suggestions → Run analysis. "
        "Changing settings or uploading a new image requires Run again."
    )

if run_clicked:
    st.session_state.analysis_run = True
    st.session_state.analysis_image_id = image_id
    st.session_state.analysis_settings_id = settings_id

analysis_ready = (
    st.session_state.get("analysis_run")
    and st.session_state.get("analysis_image_id") == image_id
    and st.session_state.get("analysis_settings_id") == settings_id
)

if not analysis_ready:
    if st.session_state.get("analysis_run") and st.session_state.get("analysis_settings_id") != settings_id:
        st.warning("Settings changed since the last run. Click **Run analysis** again.")
    else:
        st.info(
            "Image loaded. Adjust sidebar settings or use AI calibration above, "
            "then click **Run analysis**."
        )
    st.stop()

# Show a clear wait state once, then run CV in this same script pass (no extra reruns).
if run_clicked:
    ui_busy.lock_ui(
        "Running analysis…",
        "Auto-crop (GroundingDINO) is the slow step on CPU. "
        "Tip: turn off Use Auto-Crop for a faster run if the rim already fills the frame.",
    )
    st.warning(
        "Running analysis… Auto-crop can take a while on CPU the first time. "
        "Please wait — don't click other controls."
    )

# -------------------------------------------------
# AUTO CROP USING src/detection.py
# -------------------------------------------------

if use_auto_crop:
    with st.spinner("Detecting tank opening (GroundingDINO) — often the slowest step…"):
        detection_output = cached_detection(
            uploaded_bytes,
            detection_threshold
        )

    results = detection_output["results"]
    annotated_image = detection_output["annotated_image"]
    crop = detection_output["crop"]
    best_detection = detection_output["best_detection"]
    inner_size = detection_output.get("inner_size")

    if best_detection is None:
        # Analysis can still proceed on the whole image; the manual geometry
        # controls become more important when auto-crop fails.
        st.warning("No tank region detected. Using full image.")
        crop = image
        inner_size = None

        if ai_enabled and openai_api_key:
            detect_fail_key = "detect_fail_" + ai.content_hash(
                uploaded_bytes,
                detection_threshold,
                ai_model,
            )
            with st.expander("AI Troubleshooting (detection miss)", expanded=True):
                tip = st.session_state.get("ai_cache", {}).get(detect_fail_key)
                if tip:
                    st.markdown(tip)
                if st.button("Ask AI how to recover"):
                    ui_busy.request_busy(
                        "ai_detect_fail",
                        "Asking AI how to recover…",
                        "Please wait — don't change settings or click other buttons.",
                        cache_key=detect_fail_key,
                        issue="Auto-crop found no tank / rim region.",
                        settings={
                            "use_auto_crop": True,
                            "detection_threshold": detection_threshold,
                            "canny_low": canny_low,
                            "canny_high": canny_high,
                            "blur_kernel": blur_kernel,
                        },
                    )
    else:
        with st.expander("Detected Tank Region", expanded=False):
            st.image(annotated_image, width=800)

else:
    crop = image
    results = []
    best_detection = None
    inner_size = None

crop_rgb = np.array(crop)

with st.expander("Analysis Crop", expanded=False):
    st.image(crop_rgb, width=800)

# -------------------------------------------------
# EDGE DETECTION using src/preprocessing.py
# -------------------------------------------------

edge_output = cached_edge_map(
    crop_rgb,
    blur_kernel,
    canny_low,
    canny_high
)

crop_gray = edge_output["gray"]
crop_blur = edge_output["blurred"]
edges = edge_output["edges"]

with st.expander("Edge Detection", expanded=False):
    st.image(edges, clamp=True, width=800)
    if ai_enabled and openai_api_key:
        edges_key = "edges_" + ai.content_hash(
            uploaded_bytes, canny_low, canny_high, blur_kernel, ai_model
        )
        tip = st.session_state.get("ai_cache", {}).get(edges_key)
        if tip:
            st.markdown(tip)
        if st.button("Ask AI about this edge map"):
            ui_busy.request_busy(
                "ai_edges",
                "Reviewing edge map…",
                "Please wait — don't change settings or click other buttons.",
                cache_key=edges_key,
                crop_bytes=ndarray_to_jpeg_bytes(crop_rgb),
                edge_bytes=ndarray_to_jpeg_bytes(edges),
                issue=(
                    "Review whether the Canny edge map clearly shows a continuous "
                    "tank rim suitable for radial search."
                ),
                settings={
                    "canny_low": canny_low,
                    "canny_high": canny_high,
                    "blur_kernel": blur_kernel,
                    "search_band": search_band,
                },
            )

# -------------------------------------------------
# APPROXIMATE GEOMETRY using src/rim_analysis.py
# -------------------------------------------------

height, width = edges.shape

default_center_x = width // 2
default_center_y = height // 2
if inner_size:
    default_radius = int(0.5 * min(inner_size[0], inner_size[1]))
else:
    default_radius = int(0.5 * min(width, height))

with st.sidebar:
    step_label("Manual override")

center_x = st.sidebar.number_input(
    "Center X [pixels]",
    value=int(default_center_x),
    step=10,
    help="Horizontal center of the opening in the analysis crop. Adjust if the rim search is off to the left or right.",
)

center_y = st.sidebar.number_input(
    "Center Y [pixels]",
    value=int(default_center_y),
    step=10,
    help="Vertical center of the opening in the analysis crop. Adjust if the rim search is too high or too low.",
)

expected_radius = st.sidebar.number_input(
    "Expected Radius [pixels]",
    value=int(default_radius),
    step=10,
    help="Starting guess for rim size in pixels. The search looks near this circle; also used when Target Radius Source is Expected/manual.",
)

center_x = int(center_x)
center_y = int(center_y)
expected_radius = int(expected_radius)

# -------------------------------------------------
# MULTI-START RADIAL RIM DETECTION using src/rim_analysis.py
# -------------------------------------------------

rim_output = cached_rim_detection(
    edges,
    center_x,
    center_y,
    expected_radius,
    search_band,
    max_step_change,
    num_points,
    window_size
)

theta_uniform = rim_output["theta_uniform"]
radius_uniform_pixels = rim_output["radius_uniform_pixels"]

x_rim = rim_output["x_rim"]
y_rim = rim_output["y_rim"]

circle_x = rim_output["circle_x"]
circle_y = rim_output["circle_y"]

all_radius_results = rim_output["all_radius_results"]

# -------------------------------------------------
# CURVATURE ERROR + FORCE CORRECTION using src/correction.py
# -------------------------------------------------

correction_output = compute_curvature_correction(
    radius_uniform_pixels=radius_uniform_pixels,
    theta_uniform=theta_uniform,
    expected_radius=expected_radius,
    real_radius_inches=real_radius_inches,
    curvature_tolerance=curvature_tolerance,
    target_mode=target_mode
)

pixels_per_inch = correction_output["pixels_per_inch"]

target_radius_pixels = correction_output["target_radius_pixels"]
target_radius_inches = correction_output["target_radius_inches"]

# The lower-level correction helper uses the mathematical curvature sign.
# The dashboard flips signs so positive values line up with operator-facing
# "increase force / too flat" guidance. Preserve this convention when changing
# labels, legends, or exported correction maps.
curvature_error_percent = -correction_output["curvature_error_percent"]
force_correction_percent = -correction_output["force_correction_percent"]

too_flat = correction_output["too_flat"]
too_tight = correction_output["too_tight"]
acceptable = correction_output["acceptable"]

rim_fit = fit_rim_equation(
    x_rim=x_rim,
    y_rim=y_rim,
    initial_center_x=center_x,
    initial_center_y=center_y,
    target_radius_pixels=target_radius_pixels,
    theta_plot=theta_uniform
)

third_cos_pixels = rim_fit["third_cos"]
third_sin_pixels = rim_fit["third_sin"]
ovality_cos_pixels = rim_fit["ovality_cos"]
ovality_sin_pixels = rim_fit["ovality_sin"]
egg_cos_pixels = rim_fit["egg_cos"]
egg_sin_pixels = rim_fit["egg_sin"]
seam_amp_pixels = rim_fit["seam_amp"]
third_amp_pixels = rim_fit["third_amp"]
ovality_amp_pixels = rim_fit["ovality_amp"]
egg_amp_pixels = rim_fit["egg_amp"]
third_phase = rim_fit["third_phase"]
ovality_phase = rim_fit["ovality_phase"]
egg_phase = rim_fit["egg_phase"]

rim_equation_pixels = (
    f"R(θ) = {target_radius_pixels:.2f} "
    f"{format_signed_term(third_cos_pixels, 'cos(3θ)')} "
    f"{format_signed_term(third_sin_pixels, 'sin(3θ)')} "
    f"{format_signed_term(ovality_cos_pixels, 'cos(2θ)')} "
    f"{format_signed_term(ovality_sin_pixels, 'sin(2θ)')} "
    f"{format_signed_term(egg_cos_pixels, 'cos(θ)')} "
    f"{format_signed_term(egg_sin_pixels, 'sin(θ)')} "
    f"{format_signed_term(seam_amp_pixels, '')}"
)

derived_x_rim = rim_fit["x_plot"]
derived_y_rim = rim_fit["y_plot"]
equation_center_x = rim_fit["center_x"]
equation_center_y = rim_fit["center_y"]

rim_equation_export = build_rim_equation_export(
    rim_fit,
    target_radius_pixels=float(target_radius_pixels),
    target_radius_inches=float(target_radius_inches),
    pixels_per_inch=float(pixels_per_inch),
)

rim_equation_json = publish_rim_equation(
    rim_equation_export,
    target_radius_inches=float(target_radius_inches),
    source="inspect",
    meta={
        "pixels_per_inch": float(pixels_per_inch),
        "within_tolerance_percent": float(correction_output["within_tolerance_percent"]),
        "too_flat_percent": float(correction_output["too_flat_percent"]),
        "too_tight_percent": float(correction_output["too_tight_percent"]),
    },
)
rim_equation_csv = build_rim_equation_csv(
    rim_fit,
    target_radius_inches=float(target_radius_inches),
    pixels_per_inch=float(pixels_per_inch),
)

# -------------------------------------------------
# SUMMARY
# -------------------------------------------------

step_label("Summary")

col1, col2, col3, col4, col5, col6 = st.columns(6)

col1.metric("Target Radius", f"{target_radius_inches:.2f} in")
col2.metric("Target Radius", f"{target_radius_pixels:.1f} px")
col3.metric("Within Tolerance", f"{correction_output['within_tolerance_percent']:.1f}%")
col4.metric("Too Tight", f"{correction_output['too_flat_percent']:.1f}%")
col5.metric("Too Flat", f"{correction_output['too_tight_percent']:.1f}%")
col6.metric("Pixels/Inch", f"{pixels_per_inch:.2f}")

force_col1, force_col2 = st.columns(2)

with force_col1:
    st.markdown(
        f"""
        <div class="info-card">
        <strong>Largest Force Decrease</strong><br>
        <span class="small-note">Too tight / over-bent region</span><br><br>
        <span class="info-val info-val-tight">
        {-correction_output['max_force_increase']:.2f}% at θ = {correction_output['max_force_increase_angle']:.3f} rad
        </span>
        </div>
        """,
        unsafe_allow_html=True
    )

with force_col2:
    st.markdown(
        f"""
        <div class="info-card">
        <strong>Largest Force Increase</strong><br>
        <span class="small-note">Too flat / needs more bending</span><br><br>
        <span class="info-val info-val-flat">
        {-correction_output['max_force_decrease']:.2f}% at θ = {correction_output['max_force_decrease_angle']:.3f} rad
        </span>
        </div>
        """,
        unsafe_allow_html=True
    )

# -------------------------------------------------
# DASHBOARD PLOTS
# -------------------------------------------------

def draw_correction_zones(ax, background, *, green_alpha=0.35):
    """Overlay too-flat / too-tight / OK rim points on a background image."""
    if background.ndim == 2:
        ax.imshow(background, cmap="gray", vmin=0, vmax=255)
    else:
        ax.imshow(background)

    ax.scatter(
        x_rim[acceptable],
        y_rim[acceptable],
        s=5,
        color="lime",
        alpha=green_alpha,
        label=f"Within ±{curvature_tolerance:.1f}%",
    )
    ax.scatter(
        x_rim[too_tight],
        y_rim[too_tight],
        s=7,
        color="blue",
        alpha=0.9,
        label="Too flat",
    )
    ax.scatter(
        x_rim[too_flat],
        y_rim[too_flat],
        s=7,
        color="red",
        alpha=0.9,
        label="Too tight",
    )
    ax.axis("equal")


main_left, main_right = st.columns([1.35, 1])

with main_left:
    step_label("Expected circle")
    st.caption(
        "Where the app searches for the rim (Center X/Y + Expected Radius). "
        "Different from Correction Zones and from Derived Rim Equation below."
    )

    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.imshow(crop_rgb)
    ax.plot(
        circle_x,
        circle_y,
        color="red",
        linestyle="--",
        linewidth=2,
        label="Expected circle",
    )
    ax.scatter(
        [center_x],
        [center_y],
        color="red",
        s=40,
        zorder=5,
        label="Expected center",
    )
    ax.scatter(
        x_rim,
        y_rim,
        s=4,
        color="lime",
        alpha=0.45,
        label="Detected rim",
    )
    ax.axis("equal")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_title("Expected Circle on Crop")
    fig_to_streamlit(fig)

    step_label("Correction zones")
    st.caption("Where the rim is too flat (blue) or too tight (red) vs within tolerance (green).")

    fig_zones, ax_zones = plt.subplots(figsize=(5.5, 5.5))
    draw_correction_zones(ax_zones, crop_rgb, green_alpha=0.35)
    ax_zones.legend(loc="upper right", fontsize=8)
    ax_zones.set_title("Correction Zones (photo)")
    zone_overlay_image = fig_to_pil(fig_zones)
    fig_to_streamlit(fig_zones)

with main_right:
    st.markdown(
        """
        <div class="info-card">
        <h4>Chart guide</h4>
        <p><strong>Expected Circle on Crop</strong> — red dashed search target on the photo.</p>
        <p><strong>Correction Zones</strong> (photo)</p>
        <p>🟢 Within Tolerance</p>
        <p>🔵 Too Flat: Increase Force</p>
        <p>🔴 Too Tight: Decrease Force</p>
        <p class="small-note">
        <strong>Derived Rim Equation</strong> (bottom row) fits a smooth math curve
        to the detected rim — not the same as the expected circle.
        </p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.success(
        "Rim equation saved to this session. Continue to Correct for springback "
        "and roll-position guidance — no file download required."
    )
    if st.button(
        "Continue to Correct →",
        type="primary",
        use_container_width=True,
        key="inspect_continue_to_correct",
    ):
        st.switch_page("pages/2_Correct.py")

    export_col1, export_col2 = st.columns(2)

    with export_col1:
        st.download_button(
            label="Download Equation JSON",
            data=rim_equation_json,
            file_name="derived_rim_equation.json",
            mime="application/json"
        )

    with export_col2:
        st.download_button(
            label="Download Coefficients CSV",
            data=rim_equation_csv,
            file_name="derived_rim_coefficients.csv",
            mime="text/csv"
        )

    st.markdown(
        f"""
        <div class="info-card">
        <h4>Derived Rim Equation</h4>
        <p><strong>R(θ) = Rₜ + A₃c cos(3θ) + A₃s sin(3θ) + A₀c cos(2θ) + A₀s sin(2θ) + Aₑc cos(θ) + Aₑs sin(θ) + Aₛ</strong></p>
        <p class="small-note">
        Fitted from detected rim points:
        Rₜ = {target_radius_pixels:.2f} px,
        A₃ = {third_amp_pixels:.2f} px at φ₃ = {third_phase:.3f} rad,
        A₀ = {ovality_amp_pixels:.2f} px at φ₀ = {ovality_phase:.3f} rad,
        Aₑ = {egg_amp_pixels:.2f} px at φₑ = {egg_phase:.3f} rad,
        Aₛ = {seam_amp_pixels:.2f} px.
        </p>
        <p class="small-note">
        Fit error: RMSE = {rim_fit["rmse"]:.2f} px,
        max = {rim_fit["max_error"]:.2f} px,
        center adjustment = {rim_fit["center_offset"]:.2f} px.
        </p>
        <p class="small-note">{rim_equation_pixels}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="info-card">
        <h4>Notes</h4>
        <p class="small-note">
        Rim detected using multi-start radial edge search with circular smoothing.
        Curvature tolerance is ±{curvature_tolerance:.1f}%.
        Force correction is estimated from local curvature error.
        </p>
        </div>
        """,
        unsafe_allow_html=True
    )

plot1, plot2, plot3 = st.columns(3)

with plot1:
    step_label("Curvature error")

    fig, ax = plt.subplots(figsize=(5, 4))

    ax.plot(
        theta_uniform,
        curvature_error_percent,
        color="lime",
        label="Curvature Error"
    )

    ax.axhline(
        curvature_tolerance,
        linestyle="--",
        color="red",
        label=f"+{curvature_tolerance:.1f}%"
    )

    ax.axhline(
        -curvature_tolerance,
        linestyle="--",
        color="red",
        label=f"-{curvature_tolerance:.1f}%"
    )

    ax.axhline(
        0,
        linestyle="--",
        color="gray",
        label="0%"
    )

    ax.set_xlabel("Angle θ [rad]")
    ax.set_ylabel("Error [%]")
    ax.set_title("Curvature Error Around Shell")
    ax.grid(True)
    ax.legend(fontsize=8)

    fig_to_streamlit(fig)

with plot2:
    step_label("Force correction")

    fig, ax = plt.subplots(figsize=(5, 4))

    ax.plot(
        theta_uniform,
        force_correction_percent,
        label="Force Correction"
    )

    ax.axhline(
        0,
        linestyle="--",
        color="gray",
        label="0%"
    )

    ax.set_xlabel("Angle θ [rad]")
    ax.set_ylabel("Correction [%]")
    ax.set_title("Estimated Force Correction")
    ax.grid(True)
    ax.legend(fontsize=8)

    fig_to_streamlit(fig)

with plot3:
    step_label("Rim equation")
    st.caption(
        "Fitted math curve through the detected rim — not the expected search circle above."
    )

    fig, ax = plt.subplots(figsize=(5, 4))

    ax.imshow(crop_rgb)
    ax.scatter(
        x_rim,
        y_rim,
        s=4,
        color="red",
        label="Detected Rim"
    )
    ax.plot(
        derived_x_rim,
        derived_y_rim,
        color="lime",
        linewidth=2,
        label="Derived Rim Equation"
    )
    ax.scatter(
        equation_center_x,
        equation_center_y,
        color="lime",
        s=35,
        label="Equation Center"
    )

    ax.axis("equal")
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=3,
        fontsize=8
    )
    ax.set_title("Derived Rim Equation")
    fig.tight_layout()

    fig_to_streamlit(fig)

# -------------------------------------------------
# OPENAI OPERATOR GUIDANCE / REPORT / CHAT
# -------------------------------------------------

ai_result_metrics = ai.build_result_metrics(
    target_radius_inches=target_radius_inches,
    target_radius_pixels=target_radius_pixels,
    within_tolerance_percent=correction_output["within_tolerance_percent"],
    too_flat_percent=correction_output["too_flat_percent"],
    too_tight_percent=correction_output["too_tight_percent"],
    pixels_per_inch=pixels_per_inch,
    curvature_tolerance=curvature_tolerance,
    target_mode=target_mode,
    max_force_increase=-correction_output["max_force_decrease"],
    max_force_increase_angle=correction_output["max_force_decrease_angle"],
    max_force_decrease=-correction_output["max_force_increase"],
    max_force_decrease_angle=correction_output["max_force_increase_angle"],
    rim_rmse_px=rim_fit["rmse"],
)

metrics_hash = ai.content_hash(ai_result_metrics, uploaded_bytes, ai_model)

if ai_enabled and openai_api_key:
    st.divider()
    step_label("Operator guidance")
    st.caption(
        f"Powered by `{ai_model}`. Measurements still come from the CV pipeline — "
        "the model only explains them."
    )

    summary_key = "summary_" + metrics_hash
    gen_summary = st.button("Generate operator summary", type="primary")

    if gen_summary:
        with ui_busy.busy_overlay(
            "Writing operator summary…",
            "Please wait — don't change settings or click other buttons.",
        ):
            st.session_state.setdefault("ai_cache", {})[summary_key] = ai.operator_summary(
                openai_api_key,
                metrics=ai_result_metrics,
                zone_image=zone_overlay_image,
                original=image,
                model=ai_model,
            )

    summary_text = st.session_state.get("ai_cache", {}).get(summary_key)
    if isinstance(summary_text, str) and summary_text.strip():
        with st.expander("Operator summary", expanded=True):
            st.markdown(summary_text)

    step_label("Ask AI")
    if "ai_chat_messages" not in st.session_state:
        st.session_state.ai_chat_messages = []
    if "ai_chat_metrics_hash" not in st.session_state:
        st.session_state.ai_chat_metrics_hash = None

    # Reset chat when the analyzed result changes.
    if st.session_state.ai_chat_metrics_hash != metrics_hash:
        st.session_state.ai_chat_messages = []
        st.session_state.ai_chat_metrics_hash = metrics_hash

    for msg in st.session_state.ai_chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    chat_prompt = st.chat_input("e.g. Why is the lower-right blue? What should I adjust first?")
    if chat_prompt:
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.ai_chat_messages
        ]
        st.session_state.ai_chat_messages.append({"role": "user", "content": chat_prompt})
        with ui_busy.busy_overlay(
            "Thinking…",
            "Please wait — don't change settings or click other buttons.",
        ):
            answer = ai.answer_question(
                openai_api_key,
                chat_prompt,
                metrics=ai_result_metrics,
                images=[zone_overlay_image, image],
                history=history,
                model=ai_model,
            )
        st.session_state.ai_chat_messages.append({"role": "assistant", "content": answer})

# -------------------------------------------------
# FOOTNOTE + RELEASE ANALYSIS LOCK
# -------------------------------------------------

st.caption(
    "Force correction is estimated from local curvature error. "
    "This is a guidance tool, not a calibrated roll-forming force prediction. "
    "OpenAI assist explains CV results; it does not replace the measurements."
)

ui_busy.unlock_ui()
