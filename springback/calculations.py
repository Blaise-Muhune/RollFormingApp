"""Springback equations used by the Streamlit calculator.

The calculator keeps user-facing material inputs in ksi because that is the
unit operators and engineers typically use for steel properties. The formulas
below convert to psi before applying the curvature model so thickness and
radius can remain in inches.
"""

KSI_TO_PSI = 1000.0


def calculate_required_loaded_radius(
    elastic_modulus_ksi,
    yield_strength_ksi,
    thickness_in,
    target_radius_in,
):
    """Return the overbend radius required to hit a final radius after springback.

    Model summary:
    - final_curvature is the desired released-shell curvature, 1 / target radius.
    - springback_curvature estimates the elastic curvature lost after unloading.
    - loaded_curvature adds that loss back in, giving the curvature the roll
      former must create while the sheet is still under load.

    The returned dict is intentionally verbose because the UI displays several
    intermediate values for engineering review.
    """
    if elastic_modulus_ksi <= 0:
        raise ValueError("Elastic modulus must be greater than zero.")
    if yield_strength_ksi <= 0:
        raise ValueError("Yield strength must be greater than zero.")
    if thickness_in <= 0:
        raise ValueError("Sheet thickness must be greater than zero.")
    if target_radius_in <= 0:
        raise ValueError("Target radius must be greater than zero.")

    elastic_modulus_psi = elastic_modulus_ksi * KSI_TO_PSI
    yield_strength_psi = yield_strength_ksi * KSI_TO_PSI

    final_curvature = 1 / target_radius_in
    springback_curvature = (3 * yield_strength_psi) / (elastic_modulus_psi * thickness_in)
    loaded_curvature = final_curvature + springback_curvature
    loaded_radius = 1 / loaded_curvature
    radius_difference = target_radius_in - loaded_radius
    springback_percent = radius_difference / target_radius_in * 100

    return {
        "target_final_curvature": final_curvature,
        "springback_curvature": springback_curvature,
        "required_loaded_curvature": loaded_curvature,
        "required_loaded_radius": loaded_radius,
        "springback_radius_change": radius_difference,
        "springback_percent": springback_percent,
    }


def estimate_final_radius_from_loaded(
    loaded_radius_in,
    elastic_modulus_ksi,
    yield_strength_ksi,
    thickness_in,
):
    """Invert the springback model for a loaded radius.

    This is used as a sanity check in the UI: applying this inverse to the
    calculated loaded radius should recover the requested final radius, apart
    from floating-point roundoff.
    """
    if loaded_radius_in <= 0:
        raise ValueError("Loaded radius must be greater than zero.")

    elastic_modulus_psi = elastic_modulus_ksi * KSI_TO_PSI
    yield_strength_psi = yield_strength_ksi * KSI_TO_PSI

    loaded_curvature = 1 / loaded_radius_in
    springback_curvature = (3 * yield_strength_psi) / (elastic_modulus_psi * thickness_in)
    final_curvature = max(loaded_curvature - springback_curvature, 1e-9)

    return 1 / final_curvature
