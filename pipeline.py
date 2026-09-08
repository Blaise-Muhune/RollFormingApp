"""End-to-end Quick Run pipeline: image + setup → guidance results.

Pure computation (no Streamlit widgets). Callers handle UI, caching, and
session handoff via ``workflow.publish_rim_equation``.
"""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import numpy as np
from PIL import Image

from cv.correction import compute_curvature_correction
from cv.detection import detect_and_crop_tank, load_detector
from cv.preprocessing import generate_edge_map
from cv.rim_analysis import detect_rim_multistart
from cv.rim_fit import build_rim_equation_export, fit_rim_equation
from operator_display import (
    SMOOTH_PASS_MIN_PCT,
    SPOT_TOLERANCE_PCT,
)
from springback.calculations import (
    calculate_required_loaded_radius,
    estimate_final_radius_from_loaded,
)
from springback.defaults import setup_to_json
from springback.ellipse import parse_ellipse_coefficients, sample_ellipse_compensation
from springback.geometry import solve_machine_positions
from springback.schedule import (
    CORRECTION_SOLVER_SAMPLE_COUNT,
    calculate_side_roll_adjustment_schedule,
)
from starting_setpoints import run_starting_setpoints

__all__ = [
    "DEFAULT_CV_SETTINGS",
    "PipelineError",
    "run_quick_pipeline",
    "run_starting_setpoints",
]

DEFAULT_CV_SETTINGS = {
    "use_auto_crop": True,
    "detection_threshold": 0.25,
    "canny_low": 50,
    "canny_high": 150,
    "blur_kernel": 5,
    "num_points": 180,
    "search_band": 120,
    "max_step_change": 30,
    "window_size": 21,
    "curvature_tolerance": SPOT_TOLERANCE_PCT,
    "target_mode": "Smooth bend profile",
}


class PipelineError(Exception):
    """Raised when the Quick Run CV or springback chain cannot finish."""


def _merge_cv_settings(overrides: dict[str, Any] | None) -> dict[str, Any]:
    settings = dict(DEFAULT_CV_SETTINGS)
    if overrides:
        settings.update(overrides)
    # Canny blur kernel must be odd.
    blur = int(settings["blur_kernel"])
    if blur % 2 == 0:
        blur += 1
    settings["blur_kernel"] = max(3, blur)
    return settings


def run_quick_pipeline(
    image_bytes: bytes,
    setup: dict[str, Any],
    *,
    real_radius_inches: float,
    cv_settings: dict[str, Any] | None = None,
    detector=None,
    solver_sample_count: int = CORRECTION_SOLVER_SAMPLE_COUNT,
    include_schedule: bool = True,
    ready_ok_percent: float = SMOOTH_PASS_MIN_PCT,
) -> dict[str, Any]:
    """Run CV analysis then springback correction for one uploaded image.

    Returns a result dict with rim equation payload, springback metrics,
    machine positions, and station tables. Raises ``PipelineError`` on failure.

    When ``include_schedule`` is True, side-roll L/R deltas are only computed if
    the roll is not Ready (pass/fail). Ready checks skip that expensive path.
    """
    if real_radius_inches <= 0:
        raise PipelineError("Known actual radius must be greater than zero.")

    settings = _merge_cv_settings(cv_settings)
    # Keep Check roll rim density bounded even if callers merge AI suggestions.
    settings["num_points"] = min(int(settings.get("num_points") or 180), 180)
    material = setup["material"]

    try:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise PipelineError(f"Could not open uploaded image: {exc}") from exc

    # --- Detect / crop ---
    detection_warning = None
    best_detection = None
    annotated_image = None
    inner_size = None
    if settings["use_auto_crop"]:
        try:
            from cv.detection import detect_and_crop_tank_cached

            detection_output = detect_and_crop_tank_cached(
                image_bytes,
                threshold=float(settings["detection_threshold"]),
            )
        except Exception:
            if detector is None:
                detector = load_detector()
            detection_output = detect_and_crop_tank(
                image=image,
                detector=detector,
                threshold=float(settings["detection_threshold"]),
            )
        crop = detection_output["crop"]
        best_detection = detection_output["best_detection"]
        annotated_image = detection_output["annotated_image"]
        inner_size = detection_output.get("inner_size")
        if best_detection is None:
            detection_warning = "No tank region detected. Using full image."
            crop = image
            inner_size = None
    else:
        crop = image

    crop_rgb = np.array(crop)

    # --- Edges + rim ---
    edge_output = generate_edge_map(
        crop_rgb=crop_rgb,
        blur_kernel=int(settings["blur_kernel"]),
        canny_low=int(settings["canny_low"]),
        canny_high=int(settings["canny_high"]),
    )
    edges = edge_output["edges"]
    height, width = edges.shape
    center_x = width // 2
    center_y = height // 2
    if inner_size:
        expected_radius = int(0.5 * min(inner_size[0], inner_size[1]))
    else:
        expected_radius = int(0.5 * min(width, height))
    if expected_radius < 10:
        raise PipelineError(
            "Analysis crop is too small for rim detection. "
            "Try Advanced Inspect with a clearer photo."
        )

    try:
        rim_output = detect_rim_multistart(
            edges=edges,
            center_x=center_x,
            center_y=center_y,
            expected_radius=expected_radius,
            search_band=int(settings["search_band"]),
            max_step_change=int(settings["max_step_change"]),
            num_points=int(settings["num_points"]),
            window_size=int(settings["window_size"]),
        )
    except Exception as exc:
        raise PipelineError(f"Rim detection failed: {exc}") from exc

    theta_uniform = rim_output["theta_uniform"]
    radius_uniform_pixels = rim_output["radius_uniform_pixels"]
    x_rim = rim_output["x_rim"]
    y_rim = rim_output["y_rim"]

    if radius_uniform_pixels is None or len(radius_uniform_pixels) < 8:
        raise PipelineError(
            "Rim detection returned too few points. Open Advanced Inspect to tune."
        )

    # Prefer job target radius for springback; CV pass/fail follows the configured
    # target_mode (smooth bend profile by default for unattended Quick Run).
    correction_output = compute_curvature_correction(
        radius_uniform_pixels=radius_uniform_pixels,
        theta_uniform=theta_uniform,
        expected_radius=expected_radius,
        real_radius_inches=float(real_radius_inches),
        curvature_tolerance=float(settings["curvature_tolerance"]),
        target_mode=settings["target_mode"],
    )

    pixels_per_inch = float(correction_output["pixels_per_inch"])
    target_radius_pixels = float(correction_output["target_radius_pixels"])
    # Springback uses the operator job target; rim export Rt follows the CV
    # target (inches) so Correct stays consistent with the fitted equation.
    cv_target_radius_inches = float(correction_output["target_radius_inches"])
    within_tol = float(correction_output["within_tolerance_percent"])
    max_smooth_error = float(correction_output["max_abs_smooth_error_percent"])
    roll_ready = (
        within_tol >= float(ready_ok_percent)
        and max_smooth_error <= SPOT_TOLERANCE_PCT
    )

    rim_fit = fit_rim_equation(
        x_rim=x_rim,
        y_rim=y_rim,
        initial_center_x=center_x,
        initial_center_y=center_y,
        target_radius_pixels=target_radius_pixels,
        theta_plot=theta_uniform,
    )

    rim_equation_export = build_rim_equation_export(
        rim_fit,
        target_radius_pixels=target_radius_pixels,
        target_radius_inches=cv_target_radius_inches,
        pixels_per_inch=pixels_per_inch,
    )

    # --- Springback + machine (lighter samples for shop check) ---
    sample_n = max(400, min(int(solver_sample_count), 2000))
    calculation = calculate_required_loaded_radius(
        material["elastic_modulus_ksi"],
        material["yield_strength_ksi"],
        material["sheet_thickness_in"],
        material["target_final_radius_in"],
    )
    loaded_radius = calculation["required_loaded_radius"]
    positions = solve_machine_positions(
        setup,
        loaded_radius,
        sample_count=sample_n,
    )
    estimated_final_radius = estimate_final_radius_from_loaded(
        loaded_radius,
        material["elastic_modulus_ksi"],
        material["yield_strength_ksi"],
        material["sheet_thickness_in"],
    )

    compensation = None
    adjusted_stations: list = []
    dominant_stations: list = []
    # Pass/fail does not need L/R schedule. Fail only solves dominant stations.
    if include_schedule and not roll_ready:
        coefficients = parse_ellipse_coefficients(json.dumps(rim_equation_export))
        compensation = sample_ellipse_compensation(
            coefficients,
            material["target_final_radius_in"],
            material["elastic_modulus_ksi"],
            material["yield_strength_ksi"],
            material["sheet_thickness_in"],
        )
        dominant_only = tuple(compensation["dominant_stations"])
        adjusted_stations = calculate_side_roll_adjustment_schedule(
            setup_to_json(setup),
            loaded_radius,
            dominant_only,
            sample_count=sample_n,
        )
        dominant_stations = sorted(
            adjusted_stations,
            key=lambda row: row["drive_distance_in"],
        )

    left_ok = positions["left_solution"]["travel_in_range"]
    right_ok = positions["right_solution"]["travel_in_range"]

    return {
        "ok": True,
        "detection_warning": detection_warning,
        "best_detection": best_detection is not None,
        "annotated_image": annotated_image,
        "crop_rgb": crop_rgb,
        "edges": edges,
        "x_rim": x_rim,
        "y_rim": y_rim,
        "theta_uniform": theta_uniform,
        "radius_uniform_pixels": radius_uniform_pixels,
        "rim_center_x": float(rim_fit.get("center_x", center_x)),
        "rim_center_y": float(rim_fit.get("center_y", center_y)),
        "target_radius_pixels": float(target_radius_pixels),
        # Perfect circle for the job hanging-template size (desired radius).
        "job_target_radius_pixels": float(real_radius_inches) * pixels_per_inch,
        "too_flat": correction_output["too_flat"],
        "too_tight": correction_output["too_tight"],
        "acceptable": correction_output["acceptable"],
        "curvature_tolerance": float(settings["curvature_tolerance"]),
        "correction": {
            "within_tolerance_percent": within_tol,
            "too_flat_percent": float(correction_output["too_flat_percent"]),
            "too_tight_percent": float(correction_output["too_tight_percent"]),
            "max_abs_smooth_error_percent": max_smooth_error,
            "worst_smooth_idx": int(correction_output["worst_smooth_idx"]),
            "worst_smooth_error_percent": float(correction_output["worst_smooth_error_percent"]),
            "worst_smooth_action": correction_output["worst_smooth_action"],
            "worst_smooth_angle": float(correction_output["worst_smooth_angle"]),
            "pixels_per_inch": pixels_per_inch,
            "cv_target_radius_inches": cv_target_radius_inches,
        },
        "rim_fit": rim_fit,
        "rim_equation_export": rim_equation_export,
        "calculation": calculation,
        "loaded_radius": float(loaded_radius),
        "estimated_final_radius": float(estimated_final_radius),
        "positions": positions,
        "travel_in_range": bool(left_ok and right_ok),
        "compensation": compensation,
        "adjusted_stations": adjusted_stations,
        "dominant_stations": dominant_stations,
        "cv_settings_used": settings,
        "real_radius_inches": float(real_radius_inches),
    }
