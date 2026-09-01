"""Rim extraction from a binary edge map.

This module assumes the caller already knows an approximate center and radius.
It searches along radial rays, selects a continuous edge candidate around the
opening, then smooths the closed radius profile. The output is intentionally
pixel-based; physical unit conversion happens later in ``correction.py``.
"""

import numpy as np


def detect_rim_multistart(
    edges,
    center_x,
    center_y,
    expected_radius,
    search_band=120,
    max_step_change=30,
    num_points=720,
    window_size=21,
):
    """Detect a closed rim profile by scanning from multiple start angles.

    A single radial walk can lock onto the wrong edge after a noisy section.
    Running the same continuity-constrained search from several start angles
    and taking the median makes the final profile less dependent on where the
    scan began.
    """
    base_theta = np.linspace(
        0,
        2 * np.pi,
        num_points,
        endpoint=False
    )

    # Eight evenly spaced starts provide good robustness without making the UI
    # feel sluggish. Increase this only if photos have frequent occlusions.
    start_angles = [
        0,
        np.pi / 4,
        np.pi / 2,
        3 * np.pi / 4,
        np.pi,
        5 * np.pi / 4,
        3 * np.pi / 2,
        7 * np.pi / 4,
    ]

    # Search only near the expected radius so unrelated background edges are
    # less likely to be selected as the rim.
    inner_radius = expected_radius - search_band
    outer_radius = expected_radius + search_band

    all_radius_results = []

    for start_angle in start_angles:
        theta_scan = np.linspace(
            start_angle,
            start_angle + 2 * np.pi,
            num_points,
            endpoint=False
        )

        theta_wrapped_all = np.mod(theta_scan, 2 * np.pi)

        detected_radii = []
        previous_radius = expected_radius

        for theta in theta_scan:
            theta_wrapped = np.mod(theta, 2 * np.pi)

            # Sample integer pixel radii along the current ray.
            radii = np.arange(inner_radius, outer_radius)

            xs = (
                center_x + radii * np.cos(theta_wrapped)
            ).astype(int)

            ys = (
                center_y + radii * np.sin(theta_wrapped)
            ).astype(int)

            valid = (
                (xs >= 0)
                & (xs < edges.shape[1])
                & (ys >= 0)
                & (ys < edges.shape[0])
            )

            xs = xs[valid]
            ys = ys[valid]
            radii_valid = radii[valid]

            edge_values = edges[ys, xs]
            edge_indices = np.where(edge_values > 0)[0]

            if len(edge_indices) > 0:
                candidate_radii = radii_valid[edge_indices]

                # Choose the edge that keeps the profile continuous. Tank rims
                # often create multiple nearby Canny edges due to lighting,
                # thickness, or bevels.
                selected_radius = candidate_radii[
                    np.argmin(
                        np.abs(candidate_radii - previous_radius)
                    )
                ]

                if abs(selected_radius - previous_radius) <= max_step_change:
                    detected_radii.append(selected_radius)
                    previous_radius = selected_radius
                else:
                    # Reject abrupt jumps; carrying the previous radius is less
                    # damaging than allowing one bad edge to derail the walk.
                    detected_radii.append(previous_radius)
            else:
                # Missing edges are expected in glare, shadows, or occlusion.
                detected_radii.append(previous_radius)

        detected_radii = np.array(detected_radii)

        sort_index = np.argsort(theta_wrapped_all)

        detected_sorted = detected_radii[sort_index]

        all_radius_results.append(detected_sorted)

    all_radius_results = np.array(all_radius_results)

    # Median voting removes start-angle-specific failures while preserving the
    # angular sample grid expected by downstream plotting and correction code.
    radius_uniform_pixels = np.median(
        all_radius_results,
        axis=0
    )

    theta_uniform = base_theta

    radius_uniform_pixels = circular_smooth(
        radius_uniform_pixels,
        window_size=window_size
    )

    x_rim, y_rim = generate_rim_coordinates(
        center_x=center_x,
        center_y=center_y,
        radius_uniform_pixels=radius_uniform_pixels,
        theta_uniform=theta_uniform
    )

    circle_x, circle_y = generate_circle_coordinates(
        center_x=center_x,
        center_y=center_y,
        radius=expected_radius,
        theta_uniform=theta_uniform
    )

    return {
        "theta_uniform": theta_uniform,
        "radius_uniform_pixels": radius_uniform_pixels,
        "x_rim": x_rim,
        "y_rim": y_rim,
        "circle_x": circle_x,
        "circle_y": circle_y,
        "all_radius_results": all_radius_results,
    }


def circular_smooth(radius_values, window_size=21):
    """Smooth a closed radius profile with wraparound at 0/2pi."""
    if window_size % 2 == 0:
        # Force an odd window so each output point has a symmetric neighborhood.
        window_size += 1

    kernel = np.ones(window_size) / window_size
    pad = window_size // 2

    radius_padded = np.pad(
        radius_values,
        pad_width=pad,
        mode="wrap"
    )

    smoothed = np.convolve(
        radius_padded,
        kernel,
        mode="valid"
    )

    return smoothed


def generate_rim_coordinates(
    center_x,
    center_y,
    radius_uniform_pixels,
    theta_uniform
):
    """Convert polar rim samples back to image x/y coordinates."""
    x_rim = (
        center_x
        + radius_uniform_pixels * np.cos(theta_uniform)
    )

    y_rim = (
        center_y
        + radius_uniform_pixels * np.sin(theta_uniform)
    )

    return x_rim, y_rim


def generate_circle_coordinates(
    center_x,
    center_y,
    radius,
    theta_uniform
):
    """Generate the expected/manual reference circle in image coordinates."""
    circle_x = center_x + radius * np.cos(theta_uniform)
    circle_y = center_y + radius * np.sin(theta_uniform)

    return circle_x, circle_y
