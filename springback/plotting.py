import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from matplotlib.patches import Circle

from springback.geometry import calculate_parabola_contact_geometry, parabola_coefficient_from_radius


def draw_metallic_roller(ax, center, radius, label, label_y_offset=1.0, rotation_angle=0.0):
    """Draw one roll as a styled circle with witness marks for animation."""
    x0, y0 = center

    circle = Circle(
        center,
        radius,
        facecolor="#d9d9d9",
        edgecolor="black",
        linewidth=2.2,
        zorder=3,
    )
    ax.add_patch(circle)

    for scale, alpha in zip([0.85, 0.65, 0.45, 0.25], [0.25, 0.20, 0.15, 0.10]):
        ax.add_patch(
            Circle(
                center,
                radius * scale,
                facecolor="none",
                edgecolor="white",
                linewidth=1.5,
                alpha=alpha,
                zorder=4,
            )
        )

    for angle in np.linspace(0, 2 * np.pi, 12, endpoint=False) + rotation_angle:
        x1 = x0 + 0.12 * radius * np.cos(angle)
        y1 = y0 + 0.12 * radius * np.sin(angle)
        x2 = x0 + 0.92 * radius * np.cos(angle)
        y2 = y0 + 0.92 * radius * np.sin(angle)
        ax.plot([x1, x2], [y1, y2], color="white", alpha=0.28, linewidth=1, zorder=5)

    for angle in np.linspace(0, 2 * np.pi, 48) + rotation_angle:
        highlight = 0.16 * np.cos(angle - rotation_angle - np.pi / 4) + 0.08
        x1 = x0 + 0.05 * radius * np.cos(angle)
        y1 = y0 + 0.05 * radius * np.sin(angle)
        x2 = x0 + 0.98 * radius * np.cos(angle)
        y2 = y0 + 0.98 * radius * np.sin(angle)
        ax.plot([x1, x2], [y1, y2], color="white", alpha=max(highlight, 0), linewidth=0.7, zorder=5)

    witness_angle = rotation_angle + 0.55
    witness_x = x0 + 0.68 * radius * np.cos(witness_angle)
    witness_y = y0 + 0.68 * radius * np.sin(witness_angle)
    ax.plot(
        [x0, witness_x],
        [y0, witness_y],
        color="#2563eb",
        alpha=0.72,
        linewidth=2.0,
        zorder=7,
    )
    ax.add_patch(
        Circle(
            (witness_x, witness_y),
            radius * 0.08,
            facecolor="#60a5fa",
            edgecolor="#dbeafe",
            linewidth=0.8,
            zorder=8,
        )
    )

    ax.add_patch(
        Circle(
            center,
            radius * 0.23,
            facecolor="#444444",
            edgecolor="white",
            linewidth=2,
            zorder=6,
        )
    )
    ax.add_patch(
        Circle(
            center,
            radius * 0.11,
            facecolor="#111111",
            edgecolor="white",
            linewidth=1.5,
            zorder=7,
        )
    )

    ax.plot(
        [x0 - radius * 1.15, x0 + radius * 1.15],
        [y0, y0],
        color="white",
        linestyle="--",
        linewidth=1,
        alpha=0.5,
        zorder=2,
    )
    ax.plot(
        [x0, x0],
        [y0 - radius * 1.15, y0 + radius * 1.15],
        color="white",
        linestyle="--",
        linewidth=1,
        alpha=0.5,
        zorder=2,
    )

    ax.text(
        x0,
        y0 + radius + label_y_offset,
        label,
        color="#58a6ff",
        fontsize=9,
        fontweight="bold",
        ha="center",
        va="bottom",
        zorder=10,
    )


def draw_dimension_line(ax, start, end, text, text_offset=(0, 0)):
    """Draw a bidirectional measurement arrow with a label."""
    x1, y1 = start
    x2, y2 = end

    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(arrowstyle="<->", color="white", linewidth=1.3, shrinkA=0, shrinkB=0),
        zorder=8,
    )

    ax.text(
        (x1 + x2) / 2 + text_offset[0],
        (y1 + y2) / 2 + text_offset[1],
        text,
        color="white",
        fontsize=9,
        ha="center",
        va="center",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#111827", edgecolor="#374151", alpha=0.95),
        zorder=9,
    )


def find_fixed_radius_side_contact(side_center, side_radius, top_contact, sheet_radius, side):
    """Approximate the sheet contact point for a side roll already positioned.

    The position solver works from contact candidates to roll centers. Plotting
    has the inverse problem: a solved roll center is known and the contact point
    is needed so the visible sheet can pass through all rolls.
    """
    cx, _ = side_center
    span = max(abs(cx - top_contact[0]) + 4 * side_radius, 8 * side_radius)

    if side == "left":
        x_values = np.linspace(top_contact[0] - span, top_contact[0] - 1e-4, 7200)
    else:
        x_values = np.linspace(top_contact[0] + 1e-4, top_contact[0] + span, 7200)

    a = parabola_coefficient_from_radius(sheet_radius)
    contact_y = a * (x_values - top_contact[0]) ** 2 + top_contact[1]
    slopes = 2 * a * (x_values - top_contact[0])
    normal_x = -slopes
    normal_y = np.ones_like(slopes)
    normal_length = np.sqrt(normal_x**2 + normal_y**2)
    normal_x = normal_x / normal_length
    normal_y = normal_y / normal_length

    contacts = np.column_stack([x_values, contact_y])
    centers = np.column_stack([
        x_values - side_radius * normal_x,
        contact_y - side_radius * normal_y,
    ])

    center_errors = np.linalg.norm(centers - np.array(side_center), axis=1)
    best_index = np.argmin(center_errors)

    return {
        "contact": contacts[best_index],
        "a": parabola_coefficient_from_radius(sheet_radius),
        "slope": slopes[best_index],
        "center_error": center_errors[best_index],
    }


def draw_curved_sheet(
    ax,
    left_center,
    right_center,
    top_center,
    side_radius,
    top_radius,
    sheet_radius,
    sheet_thickness=0.134,
    visual_linewidth=4.5,
):
    """Draw the loaded sheet profile through the solved contact points.

    The geometric model uses a local parabolic approximation of the sheet arc.
    Straight tangent overhangs are added outside the side rolls so the drawing
    reads like a continuous plate entering and leaving the machine.
    """
    top_contact = np.array([top_center[0], top_center[1] - top_radius])
    left_solution = find_fixed_radius_side_contact(
        left_center,
        side_radius,
        top_contact,
        sheet_radius,
        side="left",
    )
    right_solution = find_fixed_radius_side_contact(
        right_center,
        side_radius,
        top_contact,
        sheet_radius,
        side="right",
    )

    left_contact = left_solution["contact"]
    right_contact = right_solution["contact"]
    span = abs(right_contact[0] - left_contact[0])
    overhang = 0.18 * span

    left_overhang_xs = np.linspace(left_contact[0] - overhang, left_contact[0], 80)
    left_overhang_ys = left_contact[1] + left_solution["slope"] * (left_overhang_xs - left_contact[0])
    left_curve_xs = np.linspace(left_contact[0], top_contact[0], 180)
    left_curve_ys = left_solution["a"] * (left_curve_xs - top_contact[0]) ** 2 + top_contact[1]
    right_curve_xs = np.linspace(top_contact[0], right_contact[0], 180)
    right_curve_ys = right_solution["a"] * (right_curve_xs - top_contact[0]) ** 2 + top_contact[1]
    right_overhang_xs = np.linspace(right_contact[0], right_contact[0] + overhang, 80)
    right_overhang_ys = right_contact[1] + right_solution["slope"] * (
        right_overhang_xs - right_contact[0]
    )

    xs = np.concatenate(
        [
            left_overhang_xs,
            left_curve_xs[1:],
            right_curve_xs[1:],
            right_overhang_xs[1:],
        ]
    )
    ys = np.concatenate(
        [
            left_overhang_ys,
            left_curve_ys[1:],
            right_curve_ys[1:],
            right_overhang_ys[1:],
        ]
    )

    ax.plot(xs, ys, color="#60a5fa", linewidth=visual_linewidth, solid_capstyle="round", zorder=12)
    ax.plot(
        xs,
        ys + sheet_thickness,
        color="#93c5fd",
        linewidth=max(0.8, visual_linewidth * 0.35),
        solid_capstyle="round",
        zorder=13,
    )
    ax.scatter(
        [left_contact[0], top_contact[0], right_contact[0]],
        [left_contact[1], top_contact[1], right_contact[1]],
        s=18,
        color="white",
        zorder=14,
        alpha=0.88,
    )


def plot_roll_former_geometry(
    setup,
    positions,
    loaded_radius,
    roller_phase=0.0,
):
    """Build the Matplotlib front-view machine plot shown in the main app."""
    geometry = setup["geometry"]
    travel = setup["travel"]

    top_center = positions["top_center"]
    bottom_center = positions["bottom_center"]
    left_center = positions["left_center"]
    right_center = positions["right_center"]

    top_radius = geometry["top_roll_radius_in"]
    bottom_radius = geometry["bottom_roll_radius_in"]
    side_radius = geometry["side_roll_radius_in"]

    fig, ax = plt.subplots(figsize=(10.8, 6.2))
    fig.patch.set_facecolor("#0b1220")
    ax.set_facecolor("#0f172a")

    draw_curved_sheet(
        ax,
        left_center=left_center,
        right_center=right_center,
        top_center=top_center,
        side_radius=side_radius,
        top_radius=top_radius,
        sheet_radius=loaded_radius,
        sheet_thickness=setup["material"]["sheet_thickness_in"],
    )

    draw_metallic_roller(ax, top_center, top_radius, "Top Roll", rotation_angle=-roller_phase)
    draw_metallic_roller(ax, bottom_center, bottom_radius, "Bottom Roll", rotation_angle=roller_phase)
    draw_metallic_roller(
        ax,
        left_center,
        side_radius,
        "Left Roll",
        label_y_offset=2.0,
        rotation_angle=roller_phase,
    )
    draw_metallic_roller(
        ax,
        right_center,
        side_radius,
        "Right Roll",
        label_y_offset=2.0,
        rotation_angle=roller_phase,
    )

    ax.axvline(top_center[0], color="white", linestyle="--", linewidth=1.2, alpha=0.45, zorder=1)
    ax.plot(
        [left_center[0], right_center[0]],
        [left_center[1], right_center[1]],
        color="white",
        linestyle="--",
        linewidth=1.2,
        alpha=0.45,
        zorder=1,
    )

    dimension_y = min(left_center[1], right_center[1], bottom_center[1]) - side_radius - 3.2
    draw_dimension_line(
        ax,
        (left_center[0], dimension_y),
        (right_center[0], dimension_y),
        f"{positions['roll_center_span']:.3f} in",
        text_offset=(0, -1.35),
    )
    ax.text(
        (left_center[0] + right_center[0]) / 2,
        dimension_y - 2.9,
        "Roll Center Span",
        color="white",
        fontsize=9,
        ha="center",
        va="top",
    )

    top_dimension_x = right_center[0] + side_radius + 5.0
    draw_dimension_line(
        ax,
        (top_dimension_x, left_center[1]),
        (top_dimension_x, top_center[1]),
        f"{top_center[1] - left_center[1]:.3f} in",
        text_offset=(2.7, 0),
    )

    left_solution = positions["left_solution"]
    right_solution = positions["right_solution"]
    ax.text(
        left_center[0] - side_radius - 7.0,
        left_center[1] - side_radius - 2.4,
        f"{left_solution['travel']:+.3f} in @ {travel['left_angle_deg']:.0f} deg",
        color="white",
        fontsize=8,
        ha="center",
        va="center",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#111827", edgecolor="#374151", alpha=0.95),
        zorder=9,
    )
    ax.text(
        right_center[0] + side_radius + 7.0,
        right_center[1] - side_radius - 2.4,
        f"{right_solution['travel']:+.3f} in @ {travel['right_angle_deg']:.0f} deg",
        color="white",
        fontsize=8,
        ha="center",
        va="center",
        bbox=dict(boxstyle="round,pad=0.35", facecolor="#111827", edgecolor="#374151", alpha=0.95),
        zorder=9,
    )

    all_x = [top_center[0], bottom_center[0], left_center[0], right_center[0]]
    all_y = [top_center[1], bottom_center[1], left_center[1], right_center[1]]
    max_radius = max(top_radius, bottom_radius, side_radius)

    ax.set_xlim(min(all_x) - 3.4 * max_radius, max(all_x) + 3.4 * max_radius)
    ax.set_ylim(min(all_y) - 3.2 * max_radius, max(all_y) + 3.0 * max_radius)
    ax.set_aspect("equal")
    ax.grid(color="white", alpha=0.10)
    ax.set_title(
        "ROLLER LAYOUT (FRONT VIEW)",
        color="#58a6ff",
        fontsize=12,
        fontweight="bold",
        loc="left",
        pad=10,
    )
    ax.set_xlabel("x position [in]", color="white")
    ax.set_ylabel("y position [in]", color="white")
    ax.tick_params(colors="white")

    for spine in ax.spines.values():
        spine.set_color("#334155")

    fig.tight_layout(pad=1.2)
    return fig


def plot_ellipse_compensation(compensation, adjusted_stations=None, dominant_stations=None):
    """Build the Plotly chart for measured radius and correction stations."""
    angles = compensation["angles"]
    radii = compensation["measured_radii"]
    curvatures = compensation["curvatures"]
    target_radius = 1 / compensation["target_curvature"]
    target_curvature = compensation["target_curvature"]
    shell_circumference_in = compensation["parameters"].get(
        "shell_circumference_in",
        2 * np.pi * target_radius,
    )
    adjustment_pct = (target_curvature - curvatures) / target_curvature * 100
    drive_distance_in = angles / 360 * shell_circumference_in

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=("Measured Radius", "Curvature Adjustment"),
    )

    fig.add_trace(
        go.Scatter(
            x=drive_distance_in,
            y=radii,
            mode="lines",
            name="Measured radius",
            line=dict(color="#60a5fa", width=2.4),
            hovertemplate=(
                "<b>Drive:</b> %{x:.3f} in<br>"
                "<b>Radius:</b> %{y:.3f} in"
                "<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=[0, shell_circumference_in],
            y=[target_radius, target_radius],
            mode="lines",
            name="Target radius",
            line=dict(color="#4ade80", width=1.5, dash="dash"),
            hoverinfo="skip",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=drive_distance_in,
            y=adjustment_pct,
            mode="lines",
            name="Curvature adjustment",
            line=dict(color="#c084fc", width=2.2),
            fill="tozeroy",
            fillcolor="rgba(192, 132, 252, 0.18)",
            hovertemplate=(
                "<b>Drive:</b> %{x:.3f} in<br>"
                "<b>Curvature adjustment:</b> %{y:.3f}%"
                "<extra></extra>"
            ),
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=[0, shell_circumference_in],
            y=[0, 0],
            mode="lines",
            name="No correction",
            line=dict(color="#cbd5e1", width=1.0),
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    if adjusted_stations:
        dominant_angles = {row["angle_deg"] for row in dominant_stations or []}
        normal_stations = [
            row for row in adjusted_stations if row["angle_deg"] not in dominant_angles
        ]
        largest_stations = [
            row for row in adjusted_stations if row["angle_deg"] in dominant_angles
        ]

        for stations, name, color, size in (
            (normal_stations, "Correction stations", "#94a3b8", 7),
            (largest_stations, "Largest corrections", "#f97316", 12),
        ):
            if not stations:
                continue

            customdata = np.array(
                [
                    [
                        f"{row['drive_distance_mm']:.3f}",
                        f"{row['angle_deg']:.3f}",
                        f"{row['curvature_adjustment_pct']:+.3f}",
                        f"{row['recommended_loaded_radius_in']:.3f}",
                        f"{row.get('loaded_radius_delta_in', 0.0):+.3f}",
                        f"{row['left_travel_in']:+.3f}",
                        f"{row['left_travel_delta_in']:+.3f}",
                        f"{row['right_travel_in']:+.3f}",
                        f"{row['right_travel_delta_in']:+.3f}",
                    ]
                    for row in stations
                ],
                dtype=object,
            )
            fig.add_trace(
                go.Scatter(
                    x=[row["drive_distance_in"] for row in stations],
                    y=[row["curvature_adjustment_pct"] for row in stations],
                    mode="markers",
                    name=name,
                    marker=dict(
                        color=color,
                        size=size,
                        line=dict(color="#f8fafc", width=1.0 if size > 7 else 0),
                    ),
                    customdata=customdata,
                    hovertemplate=(
                        "<b>Drive:</b> %{x:.3f} in / %{customdata[0]} mm<br>"
                        "<b>Angle:</b> %{customdata[1]} deg<br>"
                        "<b>Curvature adjustment:</b> %{customdata[2]}%<br>"
                        "<b>Loaded radius:</b> %{customdata[3]} in "
                        "(%{customdata[4]})<br>"
                        "<b>Left side roll:</b> %{customdata[5]} in "
                        "(%{customdata[6]})<br>"
                        "<b>Right side roll:</b> %{customdata[7]} in "
                        "(%{customdata[8]})"
                        "<extra></extra>"
                    ),
                ),
                row=2,
                col=1,
            )

    fig.update_layout(
        title=dict(
            text="RIM EQUATION CURVATURE COMPENSATION",
            font=dict(color="#58a6ff", size=15),
        ),
        paper_bgcolor="#0b1220",
        plot_bgcolor="#0f172a",
        font=dict(color="#f8fafc"),
        hoverlabel=dict(
            bgcolor="#020617",
            bordercolor="#58a6ff",
            font=dict(size=16, color="#f8fafc"),
            align="left",
        ),
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=18, t=78, b=42),
        height=620,
    )
    fig.update_xaxes(
        title_text="drive distance around shell [in]",
        gridcolor="rgba(255,255,255,0.10)",
        zerolinecolor="rgba(255,255,255,0.18)",
        row=2,
        col=1,
    )
    fig.update_yaxes(
        title_text="local radius [in]",
        gridcolor="rgba(255,255,255,0.10)",
        zerolinecolor="rgba(255,255,255,0.18)",
        row=1,
        col=1,
    )
    fig.update_yaxes(
        title_text="curvature adjustment [%]",
        gridcolor="rgba(255,255,255,0.10)",
        zerolinecolor="rgba(255,255,255,0.18)",
        row=2,
        col=1,
    )
    return fig
