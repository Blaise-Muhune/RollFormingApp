"""Curvature and force-correction calculations.

Inputs and most intermediate values are pixel radii from rim detection. The
known real radius provides the pixel-to-inch scale used for reporting and
exports. The force-correction formula is a guidance heuristic; calibration
against machine/process data should happen before treating it as a prediction.
"""

import numpy as np


def _odd_window_size(size, fraction=0.18):
    """Choose a broad circular smoothing window for the local bend trend."""
    n = int(size)
    if n < 3:
        return 1
    window = max(9, int(round(n * fraction)))
    if window % 2 == 0:
        window += 1
    if window >= n:
        window = n - 1 if n % 2 == 0 else n
    return max(1, window)


def _circular_smooth(values, window_size):
    values = np.asarray(values, dtype=float)
    window_size = int(window_size)
    if window_size <= 1 or values.size < 3:
        return values.copy()
    if window_size % 2 == 0:
        window_size += 1
    half = window_size // 2
    padded = np.concatenate([values[-half:], values, values[:half]])
    kernel = np.ones(window_size, dtype=float) / window_size
    return np.convolve(padded, kernel, mode="valid")


def compute_curvature_correction(
    radius_uniform_pixels,
    theta_uniform,
    expected_radius,
    real_radius_inches,
    curvature_tolerance=3.0,
    target_mode="Smooth bend profile",
):
    """Classify rim sections and estimate local force correction.

    ``target_mode`` controls the baseline:
    - ``Smooth bend profile`` compares each section against a broad local
      curvature trend. This is the operator check: it tolerates a smooth oval
      but flags flats, kinks, and tight spots.
    - ``Median detected radius`` measures local variation around the observed
      rim and is useful when the absolute target is uncertain.
    - ``Expected/manual radius`` compares directly with the operator-entered
      expected radius.
    """
    pixels_per_inch = expected_radius / real_radius_inches

    if target_mode in ("Smooth bend profile", "Median detected radius"):
        target_radius_pixels = np.median(radius_uniform_pixels)
    elif target_mode == "Expected/manual radius":
        target_radius_pixels = expected_radius
    else:
        raise ValueError(f"Unknown target_mode: {target_mode}")

    target_radius_inches = target_radius_pixels / pixels_per_inch
    actual_radius_inches = radius_uniform_pixels / pixels_per_inch

    # Curvature is computed in pixel space because relative curvature error is
    # scale-invariant. Inch values are still returned for readable reporting.
    target_curvature = 1 / target_radius_pixels
    actual_curvature = 1 / radius_uniform_pixels
    if target_mode == "Smooth bend profile":
        trend_window = _odd_window_size(len(actual_curvature))
        target_curvature_for_sections = _circular_smooth(actual_curvature, trend_window)
    else:
        trend_window = None
        target_curvature_for_sections = target_curvature

    curvature_error_percent = (
        (actual_curvature - target_curvature_for_sections)
        / target_curvature_for_sections
    ) * 100

    # Positive here means the target curvature is higher than the detected
    # curvature, i.e. the section is flatter and needs more bend. ``main.py``
    # flips some arrays for display, so check both files before changing signs.
    force_correction_percent = (
        (target_curvature_for_sections - actual_curvature)
        / actual_curvature
    ) * 100

    # Lower curvature means larger radius / flatter section.
    too_flat = actual_curvature < target_curvature_for_sections * (1 - curvature_tolerance / 100)

    # Higher curvature means smaller radius / tighter section.
    too_tight = actual_curvature > target_curvature_for_sections * (1 + curvature_tolerance / 100)

    acceptable = ~(too_flat | too_tight)
    worst_smooth_idx = int(np.argmax(np.abs(curvature_error_percent)))
    max_abs_smooth_error_percent = float(np.abs(curvature_error_percent[worst_smooth_idx]))
    worst_smooth_error_percent = float(curvature_error_percent[worst_smooth_idx])
    worst_smooth_action = "Ease off" if worst_smooth_error_percent > 0 else "Add bend"

    # Store indices as well as values so the UI can report the angle where the
    # largest increase/decrease occurs without recomputing argmax/argmin.
    max_increase_idx = np.argmax(force_correction_percent)
    max_decrease_idx = np.argmin(force_correction_percent)

    return {
        "pixels_per_inch": pixels_per_inch,
        "target_radius_pixels": target_radius_pixels,
        "target_radius_inches": target_radius_inches,
        "actual_radius_inches": actual_radius_inches,
        "target_curvature": target_curvature,
        "target_curvature_for_sections": target_curvature_for_sections,
        "smooth_trend_window": trend_window,
        "actual_curvature": actual_curvature,
        "curvature_error_percent": curvature_error_percent,
        "force_correction_percent": force_correction_percent,
        "too_flat": too_flat,
        "too_tight": too_tight,
        "acceptable": acceptable,
        "within_tolerance_percent": 100 * np.mean(acceptable),
        "too_flat_percent": 100 * np.mean(too_flat),
        "too_tight_percent": 100 * np.mean(too_tight),
        "worst_smooth_idx": worst_smooth_idx,
        "worst_smooth_error_percent": worst_smooth_error_percent,
        "worst_smooth_action": worst_smooth_action,
        "worst_smooth_angle": theta_uniform[worst_smooth_idx],
        "max_abs_smooth_error_percent": max_abs_smooth_error_percent,
        "max_increase_idx": max_increase_idx,
        "max_decrease_idx": max_decrease_idx,
        "max_force_increase": force_correction_percent[max_increase_idx],
        "max_force_decrease": force_correction_percent[max_decrease_idx],
        "max_force_increase_angle": theta_uniform[max_increase_idx],
        "max_force_decrease_angle": theta_uniform[max_decrease_idx],
    }
