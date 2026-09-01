"""Start-of-job Bertsch set points from size/thickness (no photo)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from springback.calculations import (
    calculate_required_loaded_radius,
    estimate_final_radius_from_loaded,
)
from springback.defaults import setup_from_json, setup_to_json
from springback.geometry import solve_machine_positions


def run_starting_setpoints(setup: dict[str, Any], sample_count: int = 1500) -> dict[str, Any]:
    """Bertsch start-of-job set points from material + machine only."""
    return _run_starting_setpoints_cached(setup_to_json(setup), int(sample_count))


@lru_cache(maxsize=128)
def _run_starting_setpoints_cached(setup_json: str, sample_count: int) -> dict[str, Any]:
    setup = setup_from_json(setup_json)
    material = setup["material"]
    calculation = calculate_required_loaded_radius(
        material["elastic_modulus_ksi"],
        material["yield_strength_ksi"],
        material["sheet_thickness_in"],
        material["target_final_radius_in"],
    )
    loaded_radius = calculation["required_loaded_radius"]
    positions = solve_machine_positions(setup, loaded_radius, sample_count=sample_count)
    estimated_final_radius = estimate_final_radius_from_loaded(
        loaded_radius,
        material["elastic_modulus_ksi"],
        material["yield_strength_ksi"],
        material["sheet_thickness_in"],
    )
    left_ok = positions["left_solution"]["travel_in_range"]
    right_ok = positions["right_solution"]["travel_in_range"]
    return {
        "calculation": calculation,
        "loaded_radius": float(loaded_radius),
        "estimated_final_radius": float(estimated_final_radius),
        "positions": json.loads(json.dumps(positions, default=_json_default)),
        "travel_in_range": bool(left_ok and right_ok),
        "target_final_radius_in": float(material["target_final_radius_in"]),
    }


def _json_default(obj):
    import numpy as np

    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, tuple):
        return list(obj)
    raise TypeError(type(obj))
