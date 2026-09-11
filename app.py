"""Operator check: is this roll ready to send for full weld?"""

from __future__ import annotations

import copy
import hashlib
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from advanced_nav import render_top_menu
from branding import PAGE_ICON
from bertsch_chart import (
    resolve_start_lr,
    render_shop_job_inputs,
    stash_job_for_correct,
)
from cv import openai_assist as ai
from operator_display import (
    SPOT_TOLERANCE_PCT,
    build_lr_fix_plan,
    circle_is_borderline,
    circle_is_round,
    circularity_stats,
    draw_rim_overlay,
    draw_target_vs_actual,
    primary_guidance_spot,
    roll_is_borderline,
    roll_is_ready,
)
from springback.defaults import get_default_setup, setup_to_json
from springback.ui import apply_theme, lr_hero, start_badge, step_label, step_label_row
from workflow import ensure_workflow_state, publish_rim_equation

st.set_page_config(
    page_title="Check roll",
    page_icon=PAGE_ICON,
    layout="centered",
    initial_sidebar_state="collapsed",
)
apply_theme()

def _lr_hero(l_mm: float, r_mm: float, *, highlight: bool = False) -> str:
    return lr_hero(l_mm, r_mm, highlight=highlight)


def _start_badge(start_lr: dict) -> str:
    return start_badge(start_lr)


@st.cache_data(show_spinner=False)
def _cached_start_lr(
    setup_json: str,
    diameter_in: float,
    thickness_in: float,
    thickness_choice: str,
    material_name: str,
    yield_psi: float | None,
) -> dict | None:
    from springback.defaults import setup_from_json

    try:
        setup_copy = setup_from_json(setup_json)
        return resolve_start_lr(
            setup_copy,
            diameter_in=diameter_in,
            thickness_in=thickness_in,
            thickness_choice=thickness_choice,
            material_name=material_name,
            yield_psi=yield_psi,
        )
    except Exception:
        return None


def _zone_overlay_image(result: dict) -> Image.Image:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.6, 4.6))
    draw_rim_overlay(ax, result, outside=False)
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=200)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _show_check_roll_overlay(slot) -> None:
    slot.markdown(
        """
        <div class="check-roll-overlay" role="status" aria-live="polite">
          <div class="check-roll-loader">
            <div class="check-roll-loader__topline">
              <span>Roll formation check</span>
              <span class="check-roll-loader__live">Live</span>
            </div>
            <h2>Checking roll</h2>
            <p>
              Reading the photo, tracing the rim, and checking for smooth bends,
              flats, or tight spots. First check can take 30+ seconds.
            </p>
            <div class="check-roll-loader__track" aria-hidden="true"></div>
            <div class="check-roll-loader__steps" aria-hidden="true">
              <div class="check-roll-loader__step">Photo calibration</div>
              <div class="check-roll-loader__step">Rim detection</div>
              <div class="check-roll-loader__step">Correction map</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _scroll_to_check_roll_result() -> None:
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            const target = doc.getElementById("check-roll-result");
            if (!target) return;
            window.setTimeout(function () {
                target.scrollIntoView({ behavior: "smooth", block: "start" });
            }, 120);
        })();
        </script>
        """,
        height=0,
    )


ensure_workflow_state()
ai.load_project_dotenv()

if "quick_setup" not in st.session_state:
    st.session_state.quick_setup = copy.deepcopy(
        st.session_state.get("setup") or get_default_setup()
    )
setup = st.session_state.quick_setup
material = setup["material"]

render_top_menu(
    active="check",
    title_html=(
        '<div class="app-title">Check roll</div>'
        
    ),
)

st.markdown('<p class="step-label">Job</p>', unsafe_allow_html=True)
job = render_shop_job_inputs(setup, compact=True)
job_diameter_in = job["diameter_in"]
thickness_in = job["thickness_in"]
material_name = job["material_name"]
yield_psi = job["yield_psi"]
job_missing = job["missing"]
real_radius_inches = material["target_final_radius_in"]
chart_matches = job["chart_matches"]
thickness_choice = job["thickness_choice"]

start_lr = None
if not job_missing and thickness_in is not None:
    start_lr = _cached_start_lr(
        setup_to_json(setup),
        float(job_diameter_in),
        float(thickness_in),
        thickness_choice or "",
        material_name or "",
        float(yield_psi) if yield_psi is not None else None,
    )

if start_lr:
    st.markdown(
        f'<div class="step-label-row">'
        f'<p class="step-label">Start L/R mm</p>{_start_badge(start_lr)}'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        _lr_hero(start_lr["l_axis_mm"], start_lr["r_axis_mm"]),
        unsafe_allow_html=True,
    )
elif chart_matches and not job_missing:
    tip = chart_matches[0]
    st.caption(
        f"Chart line for {job_diameter_in:.0f}\" — "
        f"L {float(tip['l_axis_mm']):.0f} / R {float(tip['r_axis_mm']):.0f} mm"
    )

_PHOTO_HELP = (
    "Clear photo of the rolled opening, centered in frame. "
    "Good lighting helps — avoid heavy glare on the rim."
)

st.markdown(
    f'<p class="step-label">Photo'
    f'<span class="step-help" title="{_PHOTO_HELP}">?</span></p>',
    unsafe_allow_html=True,
)
st.markdown('<span class="photo-source-picker" aria-hidden="true"></span>', unsafe_allow_html=True)
_pick1, _pick2 = st.columns(2, gap="small")
_photo_source = st.session_state.get("quick_photo_source_v2", "Upload")
with _pick1:
    if st.button(
        "Upload",
        use_container_width=True,
        type="primary" if _photo_source == "Upload" else "secondary",
        key="pick_upload",
    ):
        st.session_state["quick_photo_source_v2"] = "Upload"
        st.rerun()
with _pick2:
    if st.button(
        "Take photo",
        use_container_width=True,
        type="primary" if _photo_source == "Take photo" else "secondary",
        key="pick_camera",
    ):
        st.session_state["quick_photo_source_v2"] = "Take photo"
        st.rerun()
photo_source = st.session_state.get("quick_photo_source_v2", "Upload")

photo_bytes = None
if photo_source == "Upload":
    uploaded = st.file_uploader(
        "Photo file",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False,
        key="quick_upload",
        label_visibility="collapsed",
    )
    if isinstance(uploaded, list):
        uploaded = uploaded[0] if uploaded else None
    if uploaded is not None:
        photo_bytes = uploaded.getvalue()
else:
    captured = st.session_state.get("quick_camera_bytes")
    if captured:
        st.image(captured, use_container_width=True)
        if st.button("Retake"):
            st.session_state.quick_camera_bytes = None
            st.session_state.pop("quick_camera", None)
            st.session_state.pop("quick_photo_token", None)
            for _k in (
                "quick_result",
                "quick_error",
                "quick_ai_status",
                "quick_overlay_png",
                "quick_compare_png",
                "quick_plot_token",
                "quick_load_photo_overlays",
            ):
                st.session_state.pop(_k, None)
            st.rerun()
        photo_bytes = captured
    else:
        shot = st.camera_input(
            "Camera",
            key="quick_camera",
            label_visibility="collapsed",
        )
        if shot is not None:
            st.session_state.quick_camera_bytes = shot.getvalue()
            st.session_state.pop("quick_camera", None)
            st.rerun()

# New / changed / cleared photo → drop the previous pass/fail result immediately.
_photo_token = (
    hashlib.sha1(photo_bytes).hexdigest() if photo_bytes is not None else None
)
_prev_photo_token = st.session_state.get("quick_photo_token")
if _photo_token != _prev_photo_token:
    st.session_state["quick_photo_token"] = _photo_token
    for _k in (
        "quick_result",
        "quick_error",
        "quick_ai_status",
        "quick_overlay_png",
        "quick_compare_png",
        "quick_plot_token",
        "quick_scroll_to_result",
        "quick_load_photo_overlays",
    ):
        st.session_state.pop(_k, None)
    if _photo_token is not None:
        st.session_state["quick_pending_check"] = True
    else:
        st.session_state.pop("quick_pending_check", None)

_can_check = photo_bytes is not None and not bool(job_missing)
_auto_check = bool(st.session_state.get("quick_pending_check")) and _can_check
run_clicked = st.button(
    "Check again" if st.session_state.get("quick_result") or st.session_state.get("quick_error") else "Check roll",
    type="primary",
    use_container_width=True,
    disabled=not _can_check,
    key="quick_check_roll_btn",
)
if job_missing and photo_bytes is not None:
    st.caption("Select " + ", ".join(job_missing).lower() + " — check starts when the job is set.")
elif job_missing:
    st.caption("Select " + ", ".join(job_missing).lower() + " first.")
elif photo_bytes is None:
    st.caption("Upload or take a photo — check starts automatically.")

run = bool(run_clicked) or _auto_check

if run and photo_bytes is not None and not job_missing:
    from pipeline import DEFAULT_CV_SETTINGS, PipelineError, run_quick_pipeline

    st.session_state.pop("quick_pending_check", None)
    improve_rim = bool(st.session_state.get("quick_improve_rim", False))
    auto_crop = True
    st.session_state.setup = copy.deepcopy(setup)
    loading_overlay = st.empty()
    _show_check_roll_overlay(loading_overlay)
    try:
        st.session_state.pop("quick_error", None)
        st.session_state.pop("quick_overlay_png", None)
        st.session_state.pop("quick_compare_png", None)
        st.session_state.pop("quick_plot_token", None)
        st.session_state.pop("quick_load_photo_overlays", None)
        image_bytes = photo_bytes
        cv_settings = dict(DEFAULT_CV_SETTINGS)
        cv_settings["use_auto_crop"] = auto_crop
        ai_status = {
            "used": False,
            "verdict": None,
            "notes": "",
            "retried": False,
            "error": None,
        }
        api_key = ai.resolve_api_key() if improve_rim else None
        photo = Image.open(BytesIO(image_bytes)).convert("RGB")
        if improve_rim and api_key:
            try:
                photo_cal = ai.check_photo_and_calibrate(
                    api_key,
                    photo,
                    current_settings=cv_settings,
                )
                cv_settings = ai.merge_check_roll_settings(
                    cv_settings, photo_cal.get("suggestions")
                )
                ai_status["used"] = True
                ai_status["verdict"] = photo_cal.get("verdict")
                ai_status["notes"] = photo_cal.get("notes") or ""
            except Exception as exc:
                ai_status["error"] = str(exc)
        elif improve_rim:
            ai_status["error"] = "no_key"

        result = run_quick_pipeline(
            image_bytes,
            setup,
            real_radius_inches=float(real_radius_inches),
            cv_settings=cv_settings,
            detector=None,
            solver_sample_count=1500,
            include_schedule=True,
        )

        # Optional second OpenAI pass only when improve is on and first check failed.
        if (
            improve_rim
            and api_key
            and not roll_is_ready(result)
        ):
            try:
                review = ai.review_rim_tracking(
                    api_key,
                    original=photo,
                    overlay=_zone_overlay_image(result),
                    current_settings=cv_settings,
                )
                if not review.get("rim_ok"):
                    retry_settings = ai.merge_check_roll_settings(
                        cv_settings, review.get("suggestions")
                    )
                    if retry_settings != cv_settings:
                        cv_settings = retry_settings
                        result = run_quick_pipeline(
                            image_bytes,
                            setup,
                            real_radius_inches=float(real_radius_inches),
                            cv_settings=cv_settings,
                            detector=None,
                            solver_sample_count=1500,
                            include_schedule=True,
                        )
                        ai_status["retried"] = True
                        if review.get("issue"):
                            ai_status["notes"] = review["issue"]
            except Exception:
                pass

        st.session_state["quick_result"] = result
        st.session_state["quick_ai_status"] = ai_status
        publish_rim_equation(
            result["rim_equation_export"],
            target_radius_inches=float(material["target_final_radius_in"]),
            source="check_roll",
            meta={"pixels_per_inch": result["correction"]["pixels_per_inch"]},
        )
        st.session_state["quick_scroll_to_result"] = True
    except PipelineError as exc:
        st.session_state["quick_result"] = None
        st.session_state["quick_error"] = str(exc)
    except Exception as exc:
        st.session_state["quick_result"] = None
        st.session_state["quick_error"] = f"Could not check this photo: {exc}"
    finally:
        loading_overlay.empty()

if st.session_state.get("quick_error") and not st.session_state.get("quick_result"):
    err = str(st.session_state["quick_error"])
    _title = "Crop failed — retake" if err.lower().startswith("crop") else "Photo check failed — retake"
    st.markdown(
        f"""
        <div class="verdict-fail">
          <h2>{_title}</h2>
          <p>{err}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="action-card warn">
          <ol class="action-steps">
            <li>Rotate the phone so the opening is upright.</li>
            <li>Center the rim and fill most of the frame (less floor / racks).</li>
            <li>Even light — avoid heavy glare on the rim.</li>
            <li>Upload or take the photo again — check starts automatically.</li>
          </ol>
        </div>
        """,
        unsafe_allow_html=True,
    )

result = st.session_state.get("quick_result")
if result:
    st.session_state.pop("quick_error", None)
    ready = roll_is_ready(result)
    borderline = roll_is_borderline(result)
    smooth_pct = float(result["correction"]["within_tolerance_percent"])
    worst_spot_pct = float(result["correction"].get("max_abs_smooth_error_percent") or 0.0)
    worst_spot = primary_guidance_spot(result)
    tol_pct = float(result.get("curvature_tolerance") or SPOT_TOLERANCE_PCT)
    size_label = f"{job_diameter_in:.0f}"

    fix_start = start_lr
    if fix_start is None and result.get("positions"):
        try:
            fix_start = resolve_start_lr(
                setup,
                diameter_in=float(job_diameter_in),
                thickness_in=float(thickness_in or material.get("sheet_thickness_in") or 0.25),
                thickness_choice=thickness_choice,
                material_name=material_name or "A36 Carbon Steel",
                yield_psi=float(yield_psi) if yield_psi is not None else None,
                positions=result["positions"],
            )
        except Exception:
            fix_start = None

    st.markdown('<div id="check-roll-result" class="result-anchor"></div>', unsafe_allow_html=True)
    if st.session_state.pop("quick_scroll_to_result", False):
        _scroll_to_check_roll_result()
    st.markdown("---")
    if ready:
        st.markdown(
            f"""
            <div class="verdict-pass">
              <div class="verdict-body">
                <h2>Smooth</h2>
                <p>{size_label}&quot; — {smooth_pct:.0f}% smooth bend · worst spot {worst_spot_pct:.0f}% · OK to weld if template fits</p>
              </div>
              <div class="verdict-icon verdict-icon-pass" aria-hidden="true">👍</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif borderline:
        st.markdown(
            f"""
            <div class="verdict-borderline">
              <h2>Mostly smooth</h2>
              <p>{size_label}&quot; — {smooth_pct:.0f}% smooth bend · worst spot {worst_spot_pct:.0f}% · template decides final fit</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="action-card warn">
              <p style="margin:0">Photo sees minor flat/tight spots. Ignore perfect roundness here:
              if the curve is smooth and the template fits, proceed. Photo again if you are still forming.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="verdict-fail">
              <div class="verdict-body">
                <h2>Needs smoothing</h2>
                <p>{size_label}&quot; — {smooth_pct:.0f}% smooth bend · worst spot {worst_spot_pct:.0f}% · fix flats/tight spots, then photo again</p>
              </div>
              <div class="verdict-icon verdict-icon-fail" aria-hidden="true">👎</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    circ = circularity_stats(result)
    circ_round = circle_is_round(result)
    circ_border = circle_is_borderline(result)
    # Red = clear fail on Smooth and/or Round (not the yellow “mostly” band).
    is_red = (not ready and not borderline) or (not circ_round and not circ_border)

    if circ_round:
        st.markdown(
            f"""
            <div class="verdict-pass">
              <div class="verdict-body">
                <h2>Round</h2>
                <p>{size_label}&quot; — {circ['ok_pct']:.0f}% within circle · worst {circ['worst_pct']:.0f}% · close to a perfect circle</p>
              </div>
              <div class="verdict-icon verdict-icon-pass" aria-hidden="true">👍</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif circ_border:
        st.markdown(
            f"""
            <div class="verdict-borderline">
              <h2>Mostly round</h2>
              <p>{size_label}&quot; — {circ['ok_pct']:.0f}% within circle · worst {circ['worst_pct']:.0f}% · slight oval is OK if template fits</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="verdict-fail">
              <div class="verdict-body">
                <h2>Out of round</h2>
                <p>{size_label}&quot; — {circ['ok_pct']:.0f}% within circle · worst {circ['worst_pct']:.0f}% · opening is oval or dented vs a true circle</p>
              </div>
              <div class="verdict-icon verdict-icon-fail" aria-hidden="true">👎</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _render_photo_detail(*, expanded: bool) -> None:
        """Rim overlay expander. Builds plots only when open/needed (keeps Ready fast)."""
        load_key = "quick_load_photo_overlays"
        with st.expander("Photo detail", expanded=expanded):
            should_build = expanded or bool(st.session_state.get(load_key))
            if not should_build:
                if st.button("Show overlays", key="quick_photo_detail_load_btn"):
                    st.session_state[load_key] = True
                    st.rerun()
                return

            x_rim = result.get("x_rim")
            try:
                rim_n = int(len(x_rim)) if x_rim is not None else 0
            except TypeError:
                rim_n = 0
            plot_token = (
                f"v6:{float(result['correction']['within_tolerance_percent']):.2f}:"
                f"{float(result['correction'].get('max_abs_smooth_error_percent') or 0):.2f}:"
                f"{int(result['correction'].get('worst_smooth_idx') or 0)}:"
                f"{rim_n}:"
                f"{float(result.get('real_radius_inches') or 0):.4f}"
            )
            if st.session_state.get("quick_plot_token") != plot_token:
                import matplotlib.pyplot as plt

                buf1 = BytesIO()
                fig, ax = plt.subplots(figsize=(4.6, 4.6))
                draw_rim_overlay(ax, result, outside=True)
                fig.savefig(buf1, format="png", bbox_inches="tight", dpi=200)
                plt.close(fig)
                buf1.seek(0)
                st.session_state["quick_overlay_png"] = buf1.getvalue()

                buf2 = BytesIO()
                fig2, ax2 = plt.subplots(figsize=(4.6, 4.6))
                draw_target_vs_actual(ax2, result)
                fig2.savefig(buf2, format="png", bbox_inches="tight", dpi=200)
                plt.close(fig2)
                buf2.seek(0)
                st.session_state["quick_compare_png"] = buf2.getvalue()
                st.session_state["quick_plot_token"] = plot_token

            if st.session_state.get("quick_overlay_png"):
                st.markdown("**Red = Add Bend · Blue = Ease Off · Green = OK**")
                st.image(st.session_state["quick_overlay_png"], use_container_width=True)
            if st.session_state.get("quick_compare_png"):
                st.markdown("**Dashed = Smooth Reference · Orange = Detected Rim**")
                st.image(st.session_state["quick_compare_png"], use_container_width=True)

            ai_status = st.session_state.get("quick_ai_status") or {}
            verdict = str(ai_status.get("verdict") or "")
            if verdict.lower() == "retake":
                st.warning("Poor photo — retake if you can.")
            if result.get("detection_warning"):
                st.caption(result["detection_warning"])

            if not ready and fix_start:
                detail_plan = build_lr_fix_plan(result, fix_start)
                if detail_plan.get("mode") == "single" and detail_plan.get("moves"):
                    st.caption("Smoothness spots that agreed:")
                    for move in detail_plan["moves"]:
                        st.markdown(f"- {move['short_line']}")

    # On red fail: photo detail first and open. On pass: collapsed later (faster).
    if is_red:
        _render_photo_detail(expanded=True)

    # Always show Add bend / Ease off when Smooth or Round is red.
    if is_red and float(worst_spot.get("error") or 0.0) >= tol_pct:
        st.markdown(
            f"""
            <div class="action-card primary">
              <h3>{worst_spot['clock']} - {worst_spot['action']}</h3>
              <p style="margin:0">Work this area first (red = Add bend · blue = Ease off on the photo).</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    needs_fix_ui = (not ready) or (not circ_round)
    if needs_fix_ui:
        plan = (
            build_lr_fix_plan(result, fix_start)
            if fix_start
            else {"mode": "none", "moves": []}
        )
        mode = plan.get("mode") or "none"

        if mode == "single":
            st.markdown(
                '<p class="step-label">Set on jog</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                _lr_hero(plan["next_l_mm"], plan["next_r_mm"], highlight=True),
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div class="action-card primary">
                  <ol class="action-steps">
                    <li>Set <strong>L {plan['next_l_mm']:.0f}</strong> and
                        <strong>R {plan['next_r_mm']:.0f} mm</strong> on Jog.</li>
                    <li>MAIN DRIVE a pass · check template · photo again.</li>
                  </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )

        elif mode == "sections" and plan.get("moves"):
            first = plan["moves"][0]
            rest = plan["moves"][1:]
            st.markdown(
                '<p class="step-label">Fix first</p>',
                unsafe_allow_html=True,
            )
            st.markdown(
                _lr_hero(first["l_try_mm"], first["r_try_mm"], highlight=True),
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""
                <div class="action-card warn">
                  <h3>{first['clock']} — {first['action_short']}</h3>
                  <ol class="action-steps">
                    <li>MAIN DRIVE to <strong>{first['clock']}</strong>.</li>
                    <li>Set <strong>L {first['l_try_mm']:.0f}</strong> /
                        <strong>R {first['r_try_mm']:.0f} mm</strong> on Jog.</li>
                    <li>Roll that section · photo again.</li>
                  </ol>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if rest:
                with st.expander(f"Other spots ({len(rest)})"):
                    for move in rest:
                        st.markdown(
                            f"<p class='section-move'>{move['short_line']}</p>",
                            unsafe_allow_html=True,
                        )
        else:
            st.markdown(
                f"""
                <div class="action-card">
                  <p style="margin:0">
                    {worst_spot['clock']}: <strong>{worst_spot['action']}</strong>.
                    Check the hanging template, nudge L/R that way, then photo again.
                  </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if not is_red:
        _render_photo_detail(expanded=False)

    if not job_missing and thickness_in is not None:
        if st.button(
            "Open full calculator",
            use_container_width=True,
            key="goto_correct_from_result",
        ):
            stash_job_for_correct(
                diameter_in=float(job_diameter_in),
                thickness_in=float(thickness_in),
                material_name=material_name,
                yield_psi=float(yield_psi) if yield_psi is not None else None,
            )
            st.switch_page("pages/2_Correct.py")
