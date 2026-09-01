import numpy as np


def calculate_side_roll_position(pivot_x, pivot_y, travel_distance, travel_angle_deg):
    """Project a side-roll travel value from its pivot/origin onto its guide axis."""
    angle_rad = np.deg2rad(travel_angle_deg)
    return (
        pivot_x + travel_distance * np.cos(angle_rad),
        pivot_y + travel_distance * np.sin(angle_rad),
    )


def parabola_coefficient_from_radius(radius):
    """Convert a local sheet radius to the coefficient for y = a*x^2.

    Near the top roll contact the desired circular arc is approximated as a
    parabola. For a parabola at its vertex, curvature is 2a, so radius = 1/(2a).
    """
    if radius <= 0:
        raise ValueError("Sheet radius must be greater than zero.")

    return 1 / (2 * radius)


def calculate_parabola_contact_geometry(contact_x, top_contact, sheet_radius, side_radius):
    """Calculate the sheet contact point and matching side-roll center.

    The side roll is tangent to the outside of the parabolic sheet profile.
    Moving from the sheet contact point along the surface normal by one side
    roll radius gives the roll center that would create that contact.
    """
    top_x, top_y = top_contact
    a = parabola_coefficient_from_radius(sheet_radius)

    contact_y = a * (contact_x - top_x) ** 2 + top_y
    slope = 2 * a * (contact_x - top_x)

    normal = np.array([-slope, 1.0])
    normal = normal / np.linalg.norm(normal)

    contact = np.array([contact_x, contact_y])
    center = contact - side_radius * normal

    return contact, center, slope


def solve_side_roll_position_for_sheet_radius(
    pivot,
    travel_angle_deg,
    side_radius,
    top_center,
    top_radius,
    sheet_radius,
    side,
    min_travel=0.0,
    max_travel=24.0,
    sample_count=16000,
    axis_direction=1.0,
):
    """Find the side-roll travel that best matches a target loaded sheet radius.

    There is no closed-form solve in this implementation. Instead, the function
    samples possible contact x-locations on the left or right side of the top
    roll, computes the side-roll center implied by each tangent contact, then
    chooses the candidate nearest to the configured guide rail.

    `axis_direction` handles the convention that positive operator travel is
    measured away from the top roll while the guide angle points toward it.
    """
    top_contact = np.array([top_center[0], top_center[1] - top_radius], dtype=float)
    angle_rad = np.deg2rad(travel_angle_deg)
    guide_unit = np.array([np.cos(angle_rad), np.sin(angle_rad)], dtype=float)
    pivot = np.asarray(pivot, dtype=float)

    guide_start = pivot + axis_direction * min_travel * guide_unit
    guide_end = pivot + axis_direction * max_travel * guide_unit
    guide_x_min = min(guide_start[0], guide_end[0]) - 3 * side_radius
    guide_x_max = max(guide_start[0], guide_end[0]) + 3 * side_radius

    if side == "left":
        x_values = np.linspace(guide_x_min, top_contact[0] - 1e-4, sample_count)
    else:
        x_values = np.linspace(top_contact[0] + 1e-4, guide_x_max, sample_count)

    # Vectorized tangent contacts (same math as calculate_parabola_contact_geometry).
    top_x, top_y = float(top_contact[0]), float(top_contact[1])
    a = parabola_coefficient_from_radius(sheet_radius)
    contact_y = a * (x_values - top_x) ** 2 + top_y
    slope = 2.0 * a * (x_values - top_x)
    norm = np.sqrt(slope * slope + 1.0)
    nx = -slope / norm
    ny = 1.0 / norm
    centers = np.column_stack(
        (
            x_values - side_radius * nx,
            contact_y - side_radius * ny,
        )
    )
    contacts = np.column_stack((x_values, contact_y))
    slopes = slope

    center_vectors = centers - pivot
    travel_values = (center_vectors @ guide_unit) / axis_direction
    cross_track_error = np.abs(
        center_vectors[:, 0] * guide_unit[1] - center_vectors[:, 1] * guide_unit[0]
    )
    in_range = (min_travel <= travel_values) & (travel_values <= max_travel)
    # Prefer physically reachable travel. If the requested radius is outside the
    # configured travel window, return the nearest infeasible solution and flag it
    # so the UI can warn the operator.
    if np.any(in_range):
        candidate_indexes = np.flatnonzero(in_range)
        best_index = candidate_indexes[np.argmin(cross_track_error[candidate_indexes])]
    else:
        travel_penalty = np.maximum(min_travel - travel_values, 0) + np.maximum(
            travel_values - max_travel,
            0,
        )
        score = cross_track_error + 10 * travel_penalty
        best_index = int(np.argmin(score))
    best_travel = float(travel_values[best_index])
    best_center = pivot + axis_direction * best_travel * guide_unit

    return {
        "center": tuple(best_center),
        "contact": contacts[best_index],
        "travel": best_travel,
        "slope": float(slopes[best_index]),
        "cross_track_error": float(cross_track_error[best_index]),
        "travel_in_range": min_travel <= best_travel <= max_travel,
    }


def solve_machine_positions(setup, sheet_radius, sample_count=16000):
    """Solve all roll centers for the loaded sheet radius requested by the model.

    The top roll is fixed at the configured top center. The bottom roll is kept
    vertically aligned with the top roll and spaced by roll radii plus sheet
    thickness. Left and right side rolls are solved independently against their
    guide axes.
    """
    geometry = setup["geometry"]
    travel = setup["travel"]
    material = setup["material"]

    top_center = (
        geometry["top_center_x_in"],
        geometry["top_center_y_in"],
    )
    bottom_origin = (
        geometry["bottom_center_x_in"],
        geometry["bottom_center_y_in"],
    )
    top_to_bottom_center_distance = (
        geometry["top_roll_radius_in"]
        + geometry["bottom_roll_radius_in"]
        + material["sheet_thickness_in"]
    )
    bottom_center = (
        top_center[0],
        top_center[1] - top_to_bottom_center_distance,
    )
    bottom_travel = bottom_origin[1] - bottom_center[1]
    left_pivot = (
        geometry["left_pivot_x_in"],
        geometry["left_pivot_y_in"],
    )
    right_pivot = (
        geometry["right_pivot_x_in"],
        geometry["right_pivot_y_in"],
    )

    left_solution = solve_side_roll_position_for_sheet_radius(
        pivot=left_pivot,
        travel_angle_deg=travel["left_angle_deg"],
        side_radius=geometry["side_roll_radius_in"],
        top_center=top_center,
        top_radius=geometry["top_roll_radius_in"],
        sheet_radius=sheet_radius,
        side="left",
        min_travel=travel["min_side_travel_in"],
        max_travel=travel["max_side_travel_in"],
        sample_count=sample_count,
        axis_direction=-1.0,
    )
    right_solution = solve_side_roll_position_for_sheet_radius(
        pivot=right_pivot,
        travel_angle_deg=travel["right_angle_deg"],
        side_radius=geometry["side_roll_radius_in"],
        top_center=top_center,
        top_radius=geometry["top_roll_radius_in"],
        sheet_radius=sheet_radius,
        side="right",
        min_travel=travel["min_side_travel_in"],
        max_travel=travel["max_side_travel_in"],
        sample_count=sample_count,
        axis_direction=-1.0,
    )

    return {
        "top_center": top_center,
        "bottom_center": bottom_center,
        "bottom_origin": bottom_origin,
        "bottom_travel": bottom_travel,
        "top_to_bottom_center_distance": top_to_bottom_center_distance,
        "left_pivot": left_pivot,
        "right_pivot": right_pivot,
        "left_solution": left_solution,
        "right_solution": right_solution,
        "left_center": left_solution["center"],
        "right_center": right_solution["center"],
        "roll_center_span": abs(right_solution["center"][0] - left_solution["center"][0]),
    }
