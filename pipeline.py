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
from cv.rim_seed import seed_rim_geometry
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
    # Stable rim lock: crop-center + DINO size (SAM refine optional in Inspect).
    "num_points": 180,
    "search_band": 120,
    "max_step_change": 30,
    "window_size": 21,
    "curvature_tolerance": SPOT_TOLERANCE_PCT,
    "target_mode": "Smooth bend profile",
    # Off by default — mask seeds were pulling the rim off the opening.
    "use_sam_refine": False,
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


def _assess_tracking_failure(
    *,
    crop_h: int,
    crop_w: int,
    x_rim,
    y_rim,
    radius_uniform_pixels,
    rim_seed: dict[str, Any],
    auto_crop: bool,
    best_detection: Any,
) -> str | None:
    """Return a retake message when crop/rim tracking looks unusable, else None."""
    if auto_crop and best_detection is None:
        return (
            "Crop failed — no tank opening found. "
            "Retake: rotate upright, center the rim, fill most of the frame."
        )

    radii = np.asarray(radius_uniform_pixels, dtype=float)
    xs = np.asarray(x_rim, dtype=float)
    ys = np.asarray(y_rim, dtype=float)
    if radii.size < 8:
        return "Rim tracking failed — too few points. Retake a clearer photo."

    med_r = float(np.median(radii))
    min_side = float(min(crop_h, crop_w))
    cx = float(np.mean(xs))
    cy = float(np.mean(ys))

    margin = max(6.0, 0.03 * min_side)
    near_edge = (
        (xs < margin)
        | (ys < margin)
        | (xs > (crop_w - 1 - margin))
        | (ys > (crop_h - 1 - margin))
    )
    edge_frac = float(np.mean(near_edge))

    # Good close-ups often fill most of a tight crop — that is OK.
    # Fail only when a large circle is also clipped / off-center (floor fit).
    center_dx = abs(cx - 0.5 * crop_w) / max(crop_w, 1.0)
    center_dy = abs(cy - 0.5 * crop_h) / max(crop_h, 1.0)
    off_center = (center_dx > 0.18) or (center_dy > 0.18)
    fills_frame = med_r > 0.42 * min_side
    if fills_frame and (edge_frac > 0.22 or (off_center and edge_frac > 0.12)):
        return (
            "Crop / rim tracking failed — detected circle is clipped or off-center. "
            "Retake: upright photo, opening centered, less floor and racks."
        )

    if edge_frac > 0.35:
        return (
            "Crop failed — rim runs off the image edge. "
            "Retake: zoom out slightly and keep the full opening in frame."
        )

    # Wild radius scatter = tracker jumped between wrong edges / background.
    peak = float(np.max(radii) - np.min(radii))
    if med_r > 1e-6 and (peak / med_r) > 0.55:
        return (
            "Rim tracking failed — outline is unstable. "
            "Retake: even light, no glare, opening fills the frame."
        )

    coverage = float(rim_seed.get("coverage") or 0.0)
    source = str(rim_seed.get("mask_source") or "")
    if (
        auto_crop
        and source == "fallback"
        and coverage < 0.04
        and fills_frame
        and (off_center or edge_frac > 0.18)
    ):
        return (
            "Crop failed — could not lock onto the opening. "
            "Retake: center the rim, rotate upright, avoid busy backgrounds."
        )

    return None


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

    When ``include_schedule`` is True, side-roll L/R work runs only if the roll
    is not Ready. Ready checks skip machine solves and the station schedule.
    """
    if real_radius_inches <= 0:
        raise PipelineError("Known actual radius must be greater than zero.")

    settings = _merge_cv_settings(cv_settings)
    # Bound Check roll density (AI can suggest higher; 180 is the shop default).
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
            detection_warning = "No tank region detected."
            # Check roll should not invent a rim on the full messy frame.
            raise PipelineError(
                "Crop failed — no tank opening found. "
                "Retake: rotate upright, center the rim, fill most of the frame."
            )
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

    # Proven Check roll seed: crop center + DINO inner size (not mask ellipse).
    # Mask/SAM refine is optional and only adopted when it agrees with DINO.
    center_x = width // 2
    center_y = height // 2
    if inner_size:
        expected_radius = int(0.5 * min(inner_size[0], inner_size[1]))
    else:
        expected_radius = int(0.5 * min(width, height))
    rim_seed: dict[str, Any] = {
        "center_x": float(center_x),
        "center_y": float(center_y),
        "expected_radius": float(expected_radius),
        "mask_source": "dino",
        "coverage": 0.0,
    }
    search_band = int(settings["search_band"])

    if bool(settings.get("use_sam_refine", False)):
        try:
            refined = seed_rim_geometry(
                crop_rgb,
                edges=edges,
                inner_size=tuple(inner_size) if inner_size is not None else None,
                use_sam=True,
            )
            seed_r = float(refined.get("expected_radius") or 0.0)
            if (
                seed_r >= 10
                and expected_radius > 0
                and abs(seed_r - expected_radius) / expected_radius <= 0.18
            ):
                center_x = int(round(float(refined["center_x"])))
                center_y = int(round(float(refined["center_y"])))
                expected_radius = int(round(seed_r))
                rim_seed = refined
        except Exception:
            pass

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
            search_band=search_band,
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

    tracking_fail = _assess_tracking_failure(
        crop_h=int(height),
        crop_w=int(width),
        x_rim=x_rim,
        y_rim=y_rim,
        radius_uniform_pixels=radius_uniform_pixels,
        rim_seed=rim_seed,
        auto_crop=bool(settings["use_auto_crop"]),
        best_detection=best_detection,
    )
    if tracking_fail:
        raise PipelineError(tracking_fail)

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
    # Separate score vs a perfect circle (median radius). Smooth can pass an oval;
    # circularity tells how round the opening actually is.
    circularity_output = compute_curvature_correction(
        radius_uniform_pixels=radius_uniform_pixels,
        theta_uniform=theta_uniform,
        expected_radius=expected_radius,
        real_radius_inches=float(real_radius_inches),
        curvature_tolerance=float(settings["curvature_tolerance"]),
        target_mode="Median detected radius",
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
    circle_ok = (
        float(circularity_output["within_tolerance_percent"]) >= float(ready_ok_percent)
        and float(circularity_output["max_abs_smooth_error_percent"]) <= SPOT_TOLERANCE_PCT
    )
    # L/R fix math runs when Smooth or Round fails (not only Smooth).
    needs_fix_solve = not roll_ready or not circle_ok

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

    # --- Springback + machine (skip heavy solves when Ready) ---
    sample_n = max(400, min(int(solver_sample_count), 2000))
    calculation = calculate_required_loaded_radius(
        material["elastic_modulus_ksi"],
        material["yield_strength_ksi"],
        material["sheet_thickness_in"],
        material["target_final_radius_in"],
    )
    loaded_radius = calculation["required_loaded_radius"]
    estimated_final_radius = estimate_final_radius_from_loaded(
        loaded_radius,
        material["elastic_modulus_ksi"],
        material["yield_strength_ksi"],
        material["sheet_thickness_in"],
    )

    positions = None
    compensation = None
    adjusted_stations: list = []
    dominant_stations: list = []
    # Ready on both Smooth and Round skips heavy L/R work.
    if needs_fix_solve:
        positions = solve_machine_positions(
            setup,
            loaded_radius,
            sample_count=sample_n,
        )
        if include_schedule:
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

    if positions is not None:
        left_ok = positions["left_solution"]["travel_in_range"]
        right_ok = positions["right_solution"]["travel_in_range"]
    else:
        left_ok = right_ok = True

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
        "circularity": {
            "within_tolerance_percent": float(circularity_output["within_tolerance_percent"]),
            "max_abs_error_percent": float(circularity_output["max_abs_smooth_error_percent"]),
            "worst_error_percent": float(circularity_output["worst_smooth_error_percent"]),
            "worst_angle": float(circularity_output["worst_smooth_angle"]),
            "worst_idx": int(circularity_output["worst_smooth_idx"]),
            "worst_action": circularity_output["worst_smooth_action"],
            "too_flat": circularity_output["too_flat"],
            "too_tight": circularity_output["too_tight"],
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
        "rim_seed": {
            "center_x": float(rim_seed["center_x"]),
            "center_y": float(rim_seed["center_y"]),
            "expected_radius": float(rim_seed["expected_radius"]),
            "mask_source": rim_seed.get("mask_source"),
            "coverage": float(rim_seed.get("coverage") or 0.0),
            "prompt_box": list(rim_seed.get("prompt_box") or []),
        },
    }
