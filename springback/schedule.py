"""Side-roll correction schedule shared by Correct and Quick Run."""

from __future__ import annotations

from springback.defaults import setup_from_json
from springback.geometry import solve_machine_positions

CORRECTION_SOLVER_SAMPLE_COUNT = 1500


def calculate_side_roll_adjustment_schedule(
    setup_json,
    nominal_loaded_radius,
    stations,
    sample_count=CORRECTION_SOLVER_SAMPLE_COUNT,
):
    """Convert local loaded-radius recommendations into roll travel deltas.

    The ellipse compensation routine returns curvature/radius stations. Operators
    need machine moves, so this function resolves each recommended loaded radius
    through the same roll-position solver used by the nominal setup.
    """
    setup = setup_from_json(setup_json)
    nominal_positions = solve_machine_positions(
        setup,
        nominal_loaded_radius,
        sample_count=sample_count,
    )
    adjusted = []
    nominal_left_travel = nominal_positions["left_solution"]["travel"]
    nominal_right_travel = nominal_positions["right_solution"]["travel"]

    for station in stations:
        station_positions = solve_machine_positions(
            setup,
            station["recommended_loaded_radius_in"],
            sample_count=sample_count,
        )
        left_travel = station_positions["left_solution"]["travel"]
        right_travel = station_positions["right_solution"]["travel"]

        adjusted.append(
            {
                **station,
                "loaded_radius_delta_in": float(
                    station["recommended_loaded_radius_in"] - nominal_loaded_radius
                ),
                "left_travel_in": float(left_travel),
                "right_travel_in": float(right_travel),
                "left_travel_delta_in": float(left_travel - nominal_left_travel),
                "right_travel_delta_in": float(right_travel - nominal_right_travel),
            }
        )

    return adjusted


def station_table_rows(stations):
    """Format numeric station data for Streamlit dataframe display."""
    return [
        {
            "drive in": f"{row.get('drive_distance_in', 0.0):.3f}",
            "drive mm": f"{row.get('drive_distance_mm', 0.0):.1f}",
            "fraction": f"{row.get('circumference_fraction', 0.0):.3f}",
            "angle deg": f"{row['angle_deg']:.0f}",
            "direction": row["direction"],
            "curvature adj %": f"{row['curvature_adjustment_pct']:+.2f}",
            "loaded radius in": f"{row['recommended_loaded_radius_in']:.3f}",
            "loaded radius delta in": f"{row.get('loaded_radius_delta_in', 0.0):+.3f}",
            "left travel in": f"{row['left_travel_in']:+.3f}",
            "left delta in": f"{row['left_travel_delta_in']:+.3f}",
            "right travel in": f"{row['right_travel_in']:+.3f}",
            "right delta in": f"{row['right_travel_delta_in']:+.3f}",
        }
        for row in stations
    ]
