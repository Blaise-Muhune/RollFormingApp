import copy
import json


# Default machine and material values used for first launch and for filling in
# missing keys from older saved setup files. Keep this schema in sync with
# `WIDGET_PATHS` in main.py so every editable field can round-trip through JSON.
DEFAULT_SETUP = {
    "machine_layout": "4-Roll Pyramid",
    "units": "Inches",
    "material": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 50.0,
        "sheet_thickness_in": 0.134,
        "target_final_radius_in": 44.0,
    },
    "geometry": {
        "top_roll_radius_in": 7.43,
        "bottom_roll_radius_in": 7.43,
        "side_roll_radius_in": 6.02,
        "top_center_x_in": 0.0,
        "top_center_y_in": 0.0,
        "bottom_center_x_in": 0.0,
        "bottom_center_y_in": -14.795,
        "left_pivot_x_in": -12.798,
        "left_pivot_y_in": -4.553,
        "right_pivot_x_in": 12.868,
        "right_pivot_y_in": -4.674,
    },
    "travel": {
        "left_angle_deg": 60.0,
        "right_angle_deg": 120.0,
        "min_side_travel_in": 0.0,
        "max_side_travel_in": 24.0,
    },
}


def get_default_setup():
    """Return a mutable setup without exposing the module-level defaults."""
    return copy.deepcopy(DEFAULT_SETUP)


def merge_setup(base, incoming):
    """Recursively overlay a saved setup onto defaults.

    This lets new default fields be added later without breaking older setup
    JSON files that do not yet contain those keys.
    """
    merged = copy.deepcopy(base)

    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_setup(merged[key], value)
        else:
            merged[key] = value

    return merged


def setup_to_json(setup):
    """Serialize setup dictionaries in a stable, human-readable form."""
    return json.dumps(setup, indent=2, sort_keys=True)


def setup_from_json(raw_json):
    """Load a setup JSON string and backfill any missing default values."""
    loaded = json.loads(raw_json)
    if not isinstance(loaded, dict):
        raise ValueError("Setup file must contain a JSON object.")

    return merge_setup(get_default_setup(), loaded)
