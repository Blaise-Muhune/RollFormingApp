"""Harmonic rim-equation fitting shared by Inspect and Quick Run.

Fits a compact Fourier model to a detected rim profile and builds the JSON
payload consumed by the springback / Correct stage.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def format_signed_term(value, label):
    """Format equation terms without producing awkward '+ -' text."""
    sign = "+" if value >= 0 else "-"
    return f"{sign} {abs(value):.2f}{label}"


def solve_rim_equation(theta_values, radius_values, target_radius_pixels):
    """Fit a compact harmonic model to the radius error around the rim.

    The model decomposes the rim into terms that are meaningful to downstream
    manufacturing discussions:
    - 3theta terms: three-lobed / roll-process variation.
    - 2theta terms: ovality.
    - 1theta terms: off-round, egg-shaped, or remaining center bias.
    - constant term: overall radius offset from the target.

    The fit is linear once the center is fixed, so least squares is sufficient.
    Center refinement happens in ``fit_rim_equation`` below.
    """
    design_matrix = np.column_stack(
        [
            np.cos(3 * theta_values),
            np.sin(3 * theta_values),
            np.cos(2 * theta_values),
            np.sin(2 * theta_values),
            np.cos(theta_values),
            np.sin(theta_values),
            np.ones_like(theta_values),
        ]
    )

    radius_residual = radius_values - target_radius_pixels
    third_cos, third_sin, ovality_cos, ovality_sin, egg_cos, egg_sin, seam_amp = np.linalg.lstsq(
        design_matrix,
        radius_residual,
        rcond=None,
    )[0]

    fitted_residual = design_matrix @ np.array(
        [
            third_cos,
            third_sin,
            ovality_cos,
            ovality_sin,
            egg_cos,
            egg_sin,
            seam_amp,
        ]
    )
    fit_error = radius_residual - fitted_residual

    return {
        "third_cos": third_cos,
        "third_sin": third_sin,
        "ovality_cos": ovality_cos,
        "ovality_sin": ovality_sin,
        "egg_cos": egg_cos,
        "egg_sin": egg_sin,
        "seam_amp": seam_amp,
        "third_amp": np.hypot(third_cos, third_sin),
        "ovality_amp": np.hypot(ovality_cos, ovality_sin),
        "egg_amp": np.hypot(egg_cos, egg_sin),
        "third_phase": np.arctan2(third_sin, third_cos) / 3,
        "ovality_phase": np.arctan2(ovality_sin, ovality_cos) / 2,
        "egg_phase": np.arctan2(egg_sin, egg_cos),
        "rmse": np.sqrt(np.mean(fit_error ** 2)),
        "max_error": np.max(np.abs(fit_error)),
    }


def fit_rim_equation(
    x_rim,
    y_rim,
    initial_center_x,
    initial_center_y,
    target_radius_pixels,
    theta_plot,
):
    """Refine the center and produce plottable/exportable rim-equation data.

    ``detect_rim_multistart`` starts from the user/manual center. Small center
    errors can masquerade as first-harmonic shape error, so this function tries
    nearby centers and keeps the one with the lowest fit RMSE.
    """

    def fit_for_center(test_center_x, test_center_y):
        dx = x_rim - test_center_x
        dy = y_rim - test_center_y
        theta_values = np.mod(np.arctan2(dy, dx), 2 * np.pi)
        radius_values = np.hypot(dx, dy)

        fit = solve_rim_equation(
            theta_values=theta_values,
            radius_values=radius_values,
            target_radius_pixels=target_radius_pixels,
        )
        fit["center_x"] = test_center_x
        fit["center_y"] = test_center_y
        return fit

    # Search only a local neighborhood. A wider search may fit noise or the
    # wrong edge instead of correcting modest manual/detection center error.
    search_radius = max(20.0, target_radius_pixels * 0.04)
    step = max(4.0, search_radius / 4)
    best_fit = fit_for_center(initial_center_x, initial_center_y)

    # Coarse-to-fine grid search keeps this deterministic and dependency-free.
    while step >= 0.5:
        offsets = np.arange(-2, 3) * step

        for offset_y in offsets:
            for offset_x in offsets:
                candidate_center_x = best_fit["center_x"] + offset_x
                candidate_center_y = best_fit["center_y"] + offset_y
                candidate_offset = np.hypot(
                    candidate_center_x - initial_center_x,
                    candidate_center_y - initial_center_y,
                )

                if candidate_offset > search_radius:
                    continue

                candidate_fit = fit_for_center(
                    candidate_center_x,
                    candidate_center_y,
                )

                if candidate_fit["rmse"] < best_fit["rmse"]:
                    best_fit = candidate_fit

        step /= 2

    best_fit["center_offset"] = np.hypot(
        best_fit["center_x"] - initial_center_x,
        best_fit["center_y"] - initial_center_y,
    )

    best_fit["radius_plot"] = (
        target_radius_pixels
        + best_fit["third_cos"] * np.cos(3 * theta_plot)
        + best_fit["third_sin"] * np.sin(3 * theta_plot)
        + best_fit["ovality_cos"] * np.cos(2 * theta_plot)
        + best_fit["ovality_sin"] * np.sin(2 * theta_plot)
        + best_fit["egg_cos"] * np.cos(theta_plot)
        + best_fit["egg_sin"] * np.sin(theta_plot)
        + best_fit["seam_amp"]
    )
    best_fit["x_plot"] = best_fit["center_x"] + best_fit["radius_plot"] * np.cos(theta_plot)
    best_fit["y_plot"] = best_fit["center_y"] + best_fit["radius_plot"] * np.sin(theta_plot)

    return best_fit


def build_rim_equation_export(
    rim_fit: dict[str, Any],
    *,
    target_radius_pixels: float,
    target_radius_inches: float,
    pixels_per_inch: float,
) -> dict[str, Any]:
    """Build the JSON payload Correct / Quick Run springback stages consume."""
    ppi = float(pixels_per_inch)
    return {
        "equation_name": "Derived Rim Equation",
        "equation_form": (
            "R(theta) = Rt + A3c*cos(3*theta) + A3s*sin(3*theta) "
            "+ A0c*cos(2*theta) + A0s*sin(2*theta) "
            "+ Aec*cos(theta) + Aes*sin(theta) + As"
        ),
        "correction_form": "correction(theta) = Rt - R(theta)",
        "units": {
            "radius": "inches",
            "theta": "radians",
        },
        "coefficients": {
            "Rt": float(target_radius_inches),
            "A3c": float(rim_fit["third_cos"] / ppi),
            "A3s": float(rim_fit["third_sin"] / ppi),
            "A0c": float(rim_fit["ovality_cos"] / ppi),
            "A0s": float(rim_fit["ovality_sin"] / ppi),
            "Aec": float(rim_fit["egg_cos"] / ppi),
            "Aes": float(rim_fit["egg_sin"] / ppi),
            "As": float(rim_fit["seam_amp"] / ppi),
        },
        "amplitude_phase": {
            "A3": float(rim_fit["third_amp"] / ppi),
            "phi3": float(rim_fit["third_phase"]),
            "A0": float(rim_fit["ovality_amp"] / ppi),
            "phi0": float(rim_fit["ovality_phase"]),
            "Ae": float(rim_fit["egg_amp"] / ppi),
            "phie": float(rim_fit["egg_phase"]),
        },
        "fit_quality": {
            "rmse": float(rim_fit["rmse"] / ppi),
            "max_error": float(rim_fit["max_error"] / ppi),
        },
        "target_radius_pixels": float(target_radius_pixels),
        "pixels_per_inch": ppi,
    }


def rim_equation_csv(rim_fit: dict[str, Any], *, target_radius_inches: float, pixels_per_inch: float) -> str:
    """CSV companion export for the fitted coefficients (inches)."""
    ppi = float(pixels_per_inch)
    return "\n".join(
        [
            "name,value,units",
            f"Rt,{target_radius_inches:.10g},inches",
            f"A3c,{rim_fit['third_cos'] / ppi:.10g},inches",
            f"A3s,{rim_fit['third_sin'] / ppi:.10g},inches",
            f"A0c,{rim_fit['ovality_cos'] / ppi:.10g},inches",
            f"A0s,{rim_fit['ovality_sin'] / ppi:.10g},inches",
            f"Aec,{rim_fit['egg_cos'] / ppi:.10g},inches",
            f"Aes,{rim_fit['egg_sin'] / ppi:.10g},inches",
            f"As,{rim_fit['seam_amp'] / ppi:.10g},inches",
            f"rmse,{rim_fit['rmse'] / ppi:.10g},inches",
            f"max_error,{rim_fit['max_error'] / ppi:.10g},inches",
        ]
    )
