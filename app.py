"""Operator check: is this roll ready to send for full weld?"""

from __future__ import annotations

import copy
from io import BytesIO

import streamlit as st
from PIL import Image

from advanced_nav import render_top_menu
from bertsch_chart import (
    resolve_start_lr,
    render_shop_job_inputs,
    stash_job_for_correct,
)
from cv import openai_assist as ai
from cv.paste_image import listen_for_pasted_image
from operator_display import (
    build_lr_fix_plan,
    draw_rim_overlay,
    draw_target_vs_actual,
    roll_is_borderline,
    roll_is_ready,
)
from springback.defaults import get_default_setup, setup_to_json
from springback.ui import apply_theme
from workflow import ensure_workflow_state, publish_rim_equation

st.set_page_config(
    page_title="Check roll",
    layout="centered",
    initial_sidebar_state="collapsed",
)
apply_theme()

def _lr_hero(l_mm: float, r_mm: float, *, highlight: bool = False) -> str:
    cls = "lr-hero-tile highlight" if highlight else "lr-hero-tile"
    return f"""
    <div class="lr-hero">
      <div class="{cls}"><div class="lab">L</div><div class="val">{l_mm:.0f}</div></div>
      <div class="{cls}"><div class="lab">R</div><div class="val">{r_mm:.0f}</div></div>
    </div>
    """


def _start_badge(start_lr: dict) -> str:
    if start_lr.get("verified"):
        return '<span class="badge badge-verified">Verified</span>'
    if start_lr.get("source") in ("chart_anchor", "chart_calibrated"):
        return '<span class="badge badge-fill">Chart</span>'
    return '<span class="badge badge-estimate">Estimate</span>'


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


@st.cache_resource
def get_quick_detector():
    from cv.detection import load_detector

    return load_detector()


def _zone_overlay_image(result: dict) -> Image.Image:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.6, 4.6))
    draw_rim_overlay(ax, result, outside=False)
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


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
    title_html='<div class="app-title">Check roll</div>',
)

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
        f'<p class="step-label">Start L / R (mm) {_start_badge(start_lr)}</p>',
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

st.markdown('<p class="step-label">Photo</p>', unsafe_allow_html=True)
photo_source = st.radio(
    "Photo source",
    ("Upload", "Take photo"),
    horizontal=True,
    key="quick_photo_source_v2",
    label_visibility="collapsed",
)

photo_bytes = None
if photo_source == "Upload":
    uploaded = st.file_uploader(
        "Upload or paste one photo",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=False,
        key="quick_upload",
        help="Pick a file, or copy a screenshot and press Ctrl+V / Cmd+V.",
    )
    if isinstance(uploaded, list):
        uploaded = uploaded[0] if uploaded else None
    pasted = listen_for_pasted_image(key="quick_paste")
    if pasted and pasted != st.session_state.get("quick_paste_bytes"):
        st.session_state["quick_paste_bytes"] = pasted
        st.session_state["quick_photo_pick"] = "paste"
    upload_id = None
    if uploaded is not None:
        upload_id = f"{getattr(uploaded, 'name', 'file')}:{getattr(uploaded, 'size', len(uploaded.getvalue()))}"
        if upload_id != st.session_state.get("quick_upload_id"):
            st.session_state["quick_upload_id"] = upload_id
            st.session_state["quick_photo_pick"] = "upload"
    if st.session_state.get("quick_photo_pick") == "paste" and st.session_state.get("quick_paste_bytes"):
        photo_bytes = st.session_state["quick_paste_bytes"]
    elif uploaded is not None:
        photo_bytes = uploaded.getvalue()
    elif st.session_state.get("quick_paste_bytes"):
        photo_bytes = st.session_state["quick_paste_bytes"]
else:
    captured = st.session_state.get("quick_camera_bytes")
    if captured:
        st.image(captured, use_container_width=True)
        if st.button("Retake"):
            st.session_state.quick_camera_bytes = None
            st.session_state.pop("quick_camera", None)
            st.rerun()
        photo_bytes = captured
    else:
        shot = st.camera_input(
            "Take one photo of the opening",
            key="quick_camera",
        )
        if shot is not None:
            st.session_state.quick_camera_bytes = shot.getvalue()
            st.session_state.pop("quick_camera", None)
            st.rerun()

run = st.button(
    "Check roll",
    type="primary",
    use_container_width=True,
    disabled=photo_bytes is None or bool(job_missing),
)
if job_missing:
    st.caption("Select " + ", ".join(job_missing).lower() + " first.")

if run and photo_bytes is not None and not job_missing:
    from pipeline import DEFAULT_CV_SETTINGS, PipelineError, run_quick_pipeline

    improve_rim = True
    auto_crop = True
    st.session_state.setup = copy.deepcopy(setup)
    with st.spinner("Checking photo — first check may take 30+ seconds…"):
        try:
            st.session_state.pop("quick_error", None)
            st.session_state.pop("quick_overlay_png", None)
            st.session_state.pop("quick_compare_png", None)
            st.session_state.pop("quick_plot_token", None)
            image_bytes = photo_bytes
            cv_settings = dict(DEFAULT_CV_SETTINGS)
            cv_settings["num_points"] = 180
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
                    cv_settings["num_points"] = 180
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
                        retry_settings["num_points"] = 180
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
        except PipelineError as exc:
            st.session_state["quick_result"] = None
            st.session_state["quick_error"] = str(exc)
        except Exception as exc:
            st.session_state["quick_result"] = None
            st.session_state["quick_error"] = f"Could not check this photo: {exc}"

if st.session_state.get("quick_error") and not st.session_state.get("quick_result"):
    st.error(st.session_state["quick_error"])
    st.caption("Retake: center the opening, even light, no glare.")

result = st.session_state.get("quick_result")
if result:
    st.session_state.pop("quick_error", None)
    ready = roll_is_ready(result)
    borderline = roll_is_borderline(result)
    within_pct = float(result["correction"]["within_tolerance_percent"])
    tol_pct = float(result.get("curvature_tolerance") or 5.0)
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

    st.markdown("---")
    if ready:
        st.markdown(
            f"""
            <div class="verdict-pass">
              <h2>Ready</h2>
              <p>{size_label}&quot; — {within_pct:.0f}% of rim within ±{tol_pct:.0f}% · OK to weld</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif borderline:
        st.markdown(
            f"""
            <div class="verdict-borderline">
              <h2>Borderline</h2>
              <p>{size_label}&quot; — {within_pct:.0f}% round · trust the hanging template</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="action-card warn">
              <p style="margin:0">Photo sees minor oval spots — often glare, angle, or post-weld shape.
              If the template fits, proceed. Photo again before roll if you are still forming.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div class="verdict-fail">
              <h2>Not ready</h2>
              <p>{size_label}&quot; — {within_pct:.0f}% round · fix on Bertsch, then photo again</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        plan = (
            build_lr_fix_plan(result, fix_start)
            if fix_start
            else {"mode": "none", "moves": []}
        )
        mode = plan.get("mode") or "none"

        if mode == "single":
            st.markdown(
                '<p class="step-label">Set on Jog (mm)</p>',
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
                '<p class="step-label">Fix this spot first</p>',
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
                """
                <div class="action-card">
                  <p style="margin:0">Shape is off — check the template and take another photo.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Cache overlay PNGs so widget reruns don't redraw Matplotlib.
    x_rim = result.get("x_rim")
    try:
        rim_n = int(len(x_rim)) if x_rim is not None else 0
    except TypeError:
        rim_n = 0
    plot_token = (
        f"v4:{float(result['correction']['within_tolerance_percent']):.2f}:"
        f"{rim_n}:"
        f"{float(result.get('real_radius_inches') or 0):.4f}"
    )
    if st.session_state.get("quick_plot_token") != plot_token:
        import matplotlib.pyplot as plt

        buf1 = BytesIO()
        fig, ax = plt.subplots(figsize=(4.6, 4.6))
        draw_rim_overlay(ax, result, outside=True)
        ax.set_title("Red = add bend · Blue = ease off · Green = OK")
        fig.savefig(buf1, format="png", bbox_inches="tight", dpi=100)
        plt.close(fig)
        buf1.seek(0)
        st.session_state["quick_overlay_png"] = buf1.getvalue()

        buf2 = BytesIO()
        fig2, ax2 = plt.subplots(figsize=(4.6, 4.6))
        draw_target_vs_actual(ax2, result)
        ax2.set_title("Dashed = target · Orange = actual")
        fig2.savefig(buf2, format="png", bbox_inches="tight", dpi=100)
        plt.close(fig2)
        buf2.seek(0)
        st.session_state["quick_compare_png"] = buf2.getvalue()
        st.session_state["quick_plot_token"] = plot_token

    with st.expander("Photo detail", expanded=(not ready and not borderline)):
        if st.session_state.get("quick_overlay_png"):
            st.image(st.session_state["quick_overlay_png"], use_container_width=True)
        if st.session_state.get("quick_compare_png"):
            st.image(st.session_state["quick_compare_png"], use_container_width=True)

        ai_status = st.session_state.get("quick_ai_status") or {}
        verdict = str(ai_status.get("verdict") or "")
        if verdict.lower() == "retake":
            st.warning("Poor photo — retake if you can.")
        if result.get("detection_warning"):
            st.caption(result["detection_warning"])

        if not ready and fix_start:
            plan = build_lr_fix_plan(result, fix_start)
            if plan.get("mode") == "single" and plan.get("moves"):
                st.caption("Spots that agreed:")
                for move in plan["moves"]:
                    st.markdown(f"- {move['short_line']}")

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

