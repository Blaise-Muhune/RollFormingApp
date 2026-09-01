import json

import numpy as np

from springback.calculations import KSI_TO_PSI


# Accepted JSON key spellings for rim equation coefficients. Keep this mapping
# broad because measurement/export tools often use slightly different labels.
RIM_ALIASES = {
    "Rt": ("Rt", "R_t", "target_radius", "base_radius", "radius"),
    "A3c": ("A3c", "A_3c", "third_cos", "cos3", "cos_3"),
    "A3s": ("A3s", "A_3s", "third_sin", "sin3", "sin_3"),
    "A0c": ("A0c", "A_0c", "oval_cos", "cos2", "cos_2"),
    "A0s": ("A0s", "A_0s", "oval_sin", "sin2", "sin_2"),
    "Aec": ("Aec", "Ae_c", "A_ec", "egg_cos", "cos1", "cos_1"),
    "Aes": ("Aes", "Ae_s", "A_es", "egg_sin", "sin1", "sin_1"),
    "As": ("As", "A_s", "offset", "constant"),
}

SCALE_ALIASES = ("pixels_per_in", "px_per_in", "scale_px_per_in", "pixelsPerIn")


AMPLITUDE_PHASE_ALIASES = {
    "A3": ("A3", "A_3"),
    "phi3": ("phi3", "phi_3"),
    "A0": ("A0", "A_0"),
    "phi0": ("phi0", "phi_0"),
    "Ae": ("Ae", "A_e"),
    "phie": ("phie", "phi_e", "phiE"),
}


def _coerce_float(value, label):
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Rim coefficient {label} must be numeric.") from exc


def _find_value(source, aliases):
    for alias in aliases:
        if alias in source:
            return source[alias]
    return None


def _read_coefficient(source, label, default=None):
    value = _find_value(source, RIM_ALIASES[label])
    if value is None:
        if default is None:
            raise ValueError(f"Missing rim coefficient: {label}.")
        return default
    return _coerce_float(value, label)


def _read_amplitude_phase(source, amplitude_label, phase_label):
    amplitude = _find_value(source, AMPLITUDE_PHASE_ALIASES[amplitude_label])
    phase = _find_value(source, AMPLITUDE_PHASE_ALIASES[phase_label])
    if amplitude is None or phase is None:
        return None

    return (
        _coerce_float(amplitude, amplitude_label),
        _coerce_float(phase, phase_label),
    )


def _phase_pair_to_cos_sin(amplitude, phase_rad):
    return amplitude * np.cos(phase_rad), amplitude * np.sin(phase_rad)


def parse_ellipse_coefficients(raw_json):
    """Parse a measured rim equation JSON file into canonical inch coefficients.

    Supported inputs can provide either cosine/sine terms directly or
    amplitude/phase pairs. If `pixels_per_in` is supplied, all radius-like terms
    are converted from pixels to inches so downstream calculations stay unit
    consistent with the rest of the app.
    """
    payload = json.loads(raw_json)
    if not isinstance(payload, dict):
        raise ValueError("Rim equation file must contain a JSON object.")

    source = payload.get("coefficients", payload)
    if not isinstance(source, dict):
        raise ValueError("Rim equation coefficients must be a JSON object.")

    units = payload.get("units", {})
    radius_units = units.get("radius", "inches") if isinstance(units, dict) else "inches"
    pixels_per_in = _find_value(source, SCALE_ALIASES)
    if pixels_per_in is not None:
        pixels_per_in = _coerce_float(pixels_per_in, "pixels_per_in")
        if pixels_per_in <= 0:
            raise ValueError("pixels_per_in must be greater than zero.")

    length_scale = 1 / pixels_per_in if pixels_per_in else 1.0

    coefficients = {
        "Rt": _read_coefficient(source, "Rt") * length_scale,
        "As": _read_coefficient(source, "As", default=0.0) * length_scale,
        "pixels_per_in": pixels_per_in,
        "radius_units": "inches" if pixels_per_in else radius_units,
    }

    # The app uses a harmonic radius model:
    # R(theta) = Rt + 3-lobed terms + ovality terms + egg-shape terms + offset.
    # Direct cos/sin coefficients take precedence over amplitude/phase inputs.
    harmonic_specs = [
        ("A3c", "A3s", "A3", "phi3"),
        ("A0c", "A0s", "A0", "phi0"),
        ("Aec", "Aes", "Ae", "phie"),
    ]
    for cos_label, sin_label, amplitude_label, phase_label in harmonic_specs:
        cos_value = _find_value(source, RIM_ALIASES[cos_label])
        sin_value = _find_value(source, RIM_ALIASES[sin_label])
        amplitude_phase = _read_amplitude_phase(source, amplitude_label, phase_label)

        if cos_value is not None or sin_value is not None:
            coefficients[cos_label] = _coerce_float(cos_value or 0.0, cos_label) * length_scale
            coefficients[sin_label] = _coerce_float(sin_value or 0.0, sin_label) * length_scale
        elif amplitude_phase is not None:
            coefficients[cos_label], coefficients[sin_label] = _phase_pair_to_cos_sin(
                amplitude_phase[0] * length_scale,
                amplitude_phase[1],
            )
        else:
            coefficients[cos_label] = 0.0
            coefficients[sin_label] = 0.0

    return coefficients


def springback_curvature(elastic_modulus_ksi, yield_strength_ksi, thickness_in):
    """Return the elastic springback curvature used for each local station."""
    if elastic_modulus_ksi <= 0 or yield_strength_ksi <= 0 or thickness_in <= 0:
        raise ValueError("Material properties and sheet thickness must be greater than zero.")

    elastic_modulus_psi = elastic_modulus_ksi * KSI_TO_PSI
    yield_strength_psi = yield_strength_ksi * KSI_TO_PSI
    return (3 * yield_strength_psi) / (elastic_modulus_psi * thickness_in)


def evaluate_rim_radius(theta, coefficients):
    """Evaluate the fitted polar radius R(theta) for scalar or vector angles."""
    return (
        coefficients["Rt"]
        + coefficients["A3c"] * np.cos(3 * theta)
        + coefficients["A3s"] * np.sin(3 * theta)
        + coefficients["A0c"] * np.cos(2 * theta)
        + coefficients["A0s"] * np.sin(2 * theta)
        + coefficients["Aec"] * np.cos(theta)
        + coefficients["Aes"] * np.sin(theta)
        + coefficients["As"]
    )


def evaluate_rim_derivatives(theta, coefficients):
    """Return first and second derivatives of the fitted polar radius.

    These derivatives feed the polar-curve curvature equation used in
    `sample_ellipse_compensation`.
    """
    dr = (
        -3 * coefficients["A3c"] * np.sin(3 * theta)
        + 3 * coefficients["A3s"] * np.cos(3 * theta)
        - 2 * coefficients["A0c"] * np.sin(2 * theta)
        + 2 * coefficients["A0s"] * np.cos(2 * theta)
        - coefficients["Aec"] * np.sin(theta)
        + coefficients["Aes"] * np.cos(theta)
    )
    d2r = (
        -9 * coefficients["A3c"] * np.cos(3 * theta)
        - 9 * coefficients["A3s"] * np.sin(3 * theta)
        - 4 * coefficients["A0c"] * np.cos(2 * theta)
        - 4 * coefficients["A0s"] * np.sin(2 * theta)
        - coefficients["Aec"] * np.cos(theta)
        - coefficients["Aes"] * np.sin(theta)
    )
    return dr, d2r


def sample_ellipse_compensation(
    coefficients,
    target_radius_in,
    elastic_modulus_ksi,
    yield_strength_ksi,
    thickness_in,
    sample_count=720,
    station_step_deg=15,
):
    """Sample the measured rim shape and create operator correction stations.

    The measured radius equation is converted to local curvature around the
    shell. Each station compares measured curvature with the target curvature,
    then adjusts the nominal loaded curvature by the same error so springback is
    still accounted for.
    """
    target_radius = target_radius_in
    if target_radius <= 0:
        raise ValueError("Target rim radius must be greater than zero.")

    angles = np.linspace(0, 2 * np.pi, sample_count, endpoint=False)
    angle_deg = np.rad2deg(angles)
    measured_radius = evaluate_rim_radius(angles, coefficients)
    dr, d2r = evaluate_rim_derivatives(angles, coefficients)

    # Polar curve curvature:
    # k = |r^2 + 2(r')^2 - r*r''| / (r^2 + (r')^2)^(3/2)
    curvature_numerator = np.abs(measured_radius**2 + 2 * dr**2 - measured_radius * d2r)
    curvature_denominator = np.power(measured_radius**2 + dr**2, 1.5)
    curvatures = curvature_numerator / curvature_denominator
    curvature_radii = 1 / np.maximum(curvatures, 1e-12)

    target_curvature = 1 / target_radius
    shell_circumference_in = 2 * np.pi * target_radius
    base_loaded_curvature = target_curvature + springback_curvature(
        elastic_modulus_ksi,
        yield_strength_ksi,
        thickness_in,
    )

    angle_wrapped = np.concatenate([angle_deg, angle_deg[:1] + 360])
    radius_wrapped = np.concatenate([measured_radius, measured_radius[:1]])
    curvature_radius_wrapped = np.concatenate([curvature_radii, curvature_radii[:1]])
    curvature_wrapped = np.concatenate([curvatures, curvatures[:1]])

    # Interpolate fixed angular stations so the operator gets a repeatable
    # correction schedule instead of every sampled point from the fitted curve.
    station_angles = np.arange(0, 360, station_step_deg, dtype=float)
    station_radii = np.interp(station_angles, angle_wrapped, radius_wrapped)
    station_curvature_radii = np.interp(station_angles, angle_wrapped, curvature_radius_wrapped)
    station_curvatures = np.interp(station_angles, angle_wrapped, curvature_wrapped)
    correction_curvatures = target_curvature - station_curvatures
    loaded_curvatures = np.maximum(base_loaded_curvature + correction_curvatures, 1e-12)

    stations = []
    for angle, radius, curvature_radius, correction_curvature, loaded_curvature in zip(
        station_angles,
        station_radii,
        station_curvature_radii,
        correction_curvatures,
        loaded_curvatures,
    ):
        if correction_curvature > 0:
            direction = "increase curvature"
        elif correction_curvature < 0:
            direction = "decrease curvature"
        else:
            direction = "hold"

        circumference_fraction = angle / 360
        drive_distance_in = circumference_fraction * shell_circumference_in
        stations.append(
            {
                "angle_deg": float(angle),
                "circumference_fraction": float(circumference_fraction),
                "drive_distance_in": float(drive_distance_in),
                "drive_distance_mm": float(drive_distance_in * 25.4),
                "measured_radius_in": float(radius),
                "curvature_radius_in": float(curvature_radius),
                "radius_error_in": float(radius - target_radius),
                "curvature_error_1_per_in": float(correction_curvature),
                "curvature_adjustment_pct": float(correction_curvature / target_curvature * 100),
                "recommended_loaded_radius_in": float(1 / loaded_curvature),
                "direction": direction,
            }
        )

    ranked = sorted(
        stations,
        key=lambda row: abs(row["curvature_adjustment_pct"]),
        reverse=True,
    )

    return {
        "coefficients": coefficients,
        "parameters": {
            "Rt": coefficients["Rt"],
            "As": coefficients["As"],
            "pixels_per_in": coefficients["pixels_per_in"],
            "radius_units": coefficients["radius_units"],
            "peak_to_peak_radius": float(np.max(measured_radius) - np.min(measured_radius)),
            "shell_circumference_in": float(shell_circumference_in),
            "shell_circumference_mm": float(shell_circumference_in * 25.4),
        },
        "target_curvature": target_curvature,
        "angles": angle_deg,
        "measured_radii": measured_radius,
        "curvature_radii": curvature_radii,
        "curvatures": curvatures,
        "stations": stations,
        "dominant_stations": ranked[:8],
        "max_abs_adjustment_pct": abs(ranked[0]["curvature_adjustment_pct"]) if ranked else 0.0,
    }
