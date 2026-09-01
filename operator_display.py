"""Operator-facing Quick Run display helpers (plain shop-floor language)."""

from __future__ import annotations


def _operator_action(direction: str) -> str:
    """Map internal curvature language to floor-facing instructions."""
    key = (direction or "").strip().lower()
    if "increase" in key:
        return "Add bend (too flat)"
    if "decrease" in key:
        return "Ease off (too tight)"
    return "Hold"


def _operator_action_short(direction: str) -> str:
    key = (direction or "").strip().lower()
    if "increase" in key:
        return "Add bend"
    if "decrease" in key:
        return "Ease off"
    return "Hold"


def angle_to_clock(angle_deg: float) -> str:
    """θ = 0 at 3 o'clock, counterclockwise — shop clock face."""
    hour = int(round(((90.0 - float(angle_deg)) % 360.0) / 30.0)) % 12
    label = 12 if hour == 0 else hour
    return f"{label} o'clock"


def roll_is_ready(result: dict, min_ok_percent: float = 85.0) -> bool:
    ok = float(result.get("correction", {}).get("within_tolerance_percent") or 0.0)
    return ok >= min_ok_percent


def roll_is_borderline(result: dict, *, min_ok_percent: float = 85.0, floor: float = 75.0) -> bool:
    """Close enough that template judgment should win over machine moves."""
    ok = float(result.get("correction", {}).get("within_tolerance_percent") or 0.0)
    return floor <= ok < min_ok_percent


def _mm(inches: float) -> float:
    return float(inches) * 25.4


def _fmt_mm(value: float) -> str:
    return f"{value:.0f}"


def _axis_nudge_line(axis: str, start_mm: float, delta_mm: float) -> str:
    """e.g. L +8 mm (145 -> 153) or L hold (~145)."""
    if abs(delta_mm) < 1.0:
        return f"{axis} hold (~{_fmt_mm(start_mm)} mm)"
    try_mm = start_mm + delta_mm
    sign = "+" if delta_mm > 0 else ""
    return (
        f"{axis} {sign}{_fmt_mm(delta_mm)} mm "
        f"({_fmt_mm(start_mm)} -> {_fmt_mm(try_mm)})"
    )


def _significant_stations(result: dict, *, max_stations: int = 6) -> list[dict]:
    stations = list(result.get("dominant_stations") or [])
    stations = [
        row
        for row in stations
        if _operator_action(row.get("direction", "")) != "Hold"
        and abs(float(row.get("curvature_adjustment_pct") or 0.0)) >= 1.0
    ]
    stations.sort(
        key=lambda row: abs(float(row.get("curvature_adjustment_pct") or 0.0)),
        reverse=True,
    )
    picked: list[dict] = []
    seen_clock: set[str] = set()
    for row in stations:
        clock = angle_to_clock(row["angle_deg"])
        if clock in seen_clock:
            continue
        seen_clock.add(clock)
        picked.append(row)
        if len(picked) >= max_stations:
            break
    return picked


def _signs_agree(values: list[float], *, tiny: float = 1.0) -> bool:
    """True if non-tiny values share a sign (or there are none)."""
    big = [v for v in values if abs(v) >= tiny]
    if len(big) <= 1:
        return True
    return min(big) * max(big) >= 0


def build_lr_fix_plan(
    result: dict,
    start: dict,
    *,
    max_moves: int = 3,
) -> dict:
    """Turn CV stations + start L/R into operator guidance.

    When photo errors agree (same way to nudge), return one next L / R pair.
    When they fight each other, return short section moves instead.
    """
    start_l = float(start["l_axis_mm"])
    start_r = float(start["r_axis_mm"])
    source_label = start.get("source_label") or start.get("source") or "Start"
    verified = bool(start.get("verified"))

    stations = _significant_stations(result, max_stations=max(max_moves, 6))
    moves: list[dict] = []
    for row in stations:
        action = _operator_action(row.get("direction", ""))
        l_delta = _mm(float(row.get("left_travel_delta_in") or 0.0))
        r_delta = _mm(float(row.get("right_travel_delta_in") or 0.0))
        primary = "L" if abs(l_delta) >= abs(r_delta) else "R"
        l_line = _axis_nudge_line("L", start_l, l_delta)
        r_line = _axis_nudge_line("R", start_r, r_delta)
        primary_line = l_line if primary == "L" else r_line
        secondary_line = r_line if primary == "L" else l_line
        short = (
            f"{angle_to_clock(row['angle_deg'])} — "
            f"{_operator_action_short(row.get('direction', ''))}. "
            f"Set L {start_l + l_delta:.0f} / R {start_r + r_delta:.0f} mm."
        )
        line = (
            f"{angle_to_clock(row['angle_deg'])}: {action}. On Jog, try {primary_line}"
            + (f"; {secondary_line}" if "hold" not in secondary_line.lower() else "")
            + ". MAIN DRIVE that section, then check the hanging template."
        )
        moves.append(
            {
                "clock": angle_to_clock(row["angle_deg"]),
                "action": action,
                "action_short": _operator_action_short(row.get("direction", "")),
                "primary_axis": primary,
                "l_delta_mm": l_delta,
                "r_delta_mm": r_delta,
                "l_try_mm": start_l + l_delta,
                "r_try_mm": start_r + r_delta,
                "adj_pct": abs(float(row.get("curvature_adjustment_pct") or 0.0)),
                "line": line,
                "short_line": short,
            }
        )

    base = {
        "start_l_mm": start_l,
        "start_r_mm": start_r,
        "source_label": source_label,
        "verified": verified,
        "moves": moves[:max_moves],
    }

    if not moves:
        return {**base, "mode": "none", "next_l_mm": start_l, "next_r_mm": start_r}

    actions = {m["action"] for m in moves}
    l_deltas = [m["l_delta_mm"] for m in moves]
    r_deltas = [m["r_delta_mm"] for m in moves]
    consistent = (
        len(actions) == 1
        and _signs_agree(l_deltas)
        and _signs_agree(r_deltas)
    )

    if consistent:
        # Weight by how wrong each station is so the worst spots pull harder.
        weights = [max(m["adj_pct"], 1.0) for m in moves]
        wsum = sum(weights) or 1.0
        next_l = sum(m["l_try_mm"] * w for m, w in zip(moves, weights)) / wsum
        next_r = sum(m["r_try_mm"] * w for m, w in zip(moves, weights)) / wsum
        action = next(iter(actions))
        return {
            **base,
            "mode": "single",
            "action": action,
            "next_l_mm": float(next_l),
            "next_r_mm": float(next_r),
            "l_delta_mm": float(next_l - start_l),
            "r_delta_mm": float(next_r - start_r),
        }

    return {
        **base,
        "mode": "sections",
        "next_l_mm": None,
        "next_r_mm": None,
    }


def correction_instructions(result: dict, *, max_moves: int = 3) -> list[str]:
    """Short Bertsch moves only — skip Hold and tiny deltas."""
    lines: list[str] = []
    for row in _significant_stations(result, max_stations=max_moves):
        clock = angle_to_clock(row["angle_deg"])
        action = _operator_action(row.get("direction", ""))
        left = float(row.get("left_travel_delta_in") or 0.0)
        right = float(row.get("right_travel_delta_in") or 0.0)
        if abs(left) >= abs(right):
            axis = "LEFT rocker (L Axis)"
        else:
            axis = "RIGHT rocker (R Axis)"
        adj = abs(float(row.get("curvature_adjustment_pct") or 0.0))
        if adj < 3:
            amount = "a small jog"
        elif adj < 8:
            amount = "a clear jog"
        else:
            amount = "a stronger jog"
        way = "UP" if (left if abs(left) >= abs(right) else right) > 0 else "DOWN"
        lines.append(
            f"{clock}: {action}. Neutral MAIN DRIVE, {amount} on {axis} {way}, "
            "MAIN DRIVE that section, then check the hanging template. Do not treat this as an exact inch setting."
        )
    return lines


def operator_move_rows(stations):
    """Operator-facing move sheet: drive -> action -> roll changes."""
    rows = []
    for row in stations:
        left_delta = float(row.get("left_travel_delta_in", 0.0))
        right_delta = float(row.get("right_travel_delta_in", 0.0))
        rows.append(
            {
                "MAIN DRIVE (in)": f"{row.get('drive_distance_in', 0.0):.2f}",
                "Angle (deg)": f"{row['angle_deg']:.0f}",
                "Action": _operator_action(row.get("direction", "")),
                "L Axis change": f"{left_delta:+.3f}",
                "R Axis change": f"{right_delta:+.3f}",
                "Loaded radius (in)": f"{row['recommended_loaded_radius_in']:.2f}",
                "L Axis": f"{row['left_travel_in']:+.3f}",
                "R Axis": f"{row['right_travel_in']:+.3f}",
            }
        )
    return rows


def draw_rim_overlay(ax, result: dict, *, outside: bool = True) -> None:
    """Thin colored ring on the photo. Default sits just outside the metal."""
    import numpy as np
    from matplotlib.collections import LineCollection

    crop = result["crop_rgb"]
    height, width = crop.shape[:2]
    ax.imshow(crop)
    ax.axis("off")
    ax.set_aspect("equal")

    x = np.asarray(result["x_rim"], dtype=float)
    y = np.asarray(result["y_rim"], dtype=float)
    if x.size < 2:
        return

    too_tight = np.asarray(result["too_tight"], dtype=bool)
    too_flat = np.asarray(result["too_flat"], dtype=bool)
    colors = np.repeat([[0.20, 0.90, 0.35, 0.95]], x.size, axis=0)
    colors[too_tight] = (0.23, 0.51, 0.96, 0.95)
    colors[too_flat] = (0.94, 0.27, 0.27, 0.95)

    xo, yo = x, y
    if outside:
        cx, cy = width / 2.0, height / 2.0
        dx, dy = x - cx, y - cy
        radius = np.maximum(np.hypot(dx, dy), 1.0)
        gap = max(10.0, 0.018 * min(width, height))
        xo = cx + dx / radius * (radius + gap)
        yo = cy + dy / radius * (radius + gap)

    pts = np.column_stack([xo, yo])
    segs = np.stack([pts, np.roll(pts, -1, axis=0)], axis=1)
    ax.add_collection(
        LineCollection(
            segs,
            colors=colors,
            linewidths=2.2,
            capstyle="round",
            clip_on=False,
        )
    )
    margin = max(18.0, 0.04 * min(width, height))
    ax.set_xlim(-margin, width + margin)
    ax.set_ylim(height + margin, -margin)


def draw_target_vs_actual(ax, result: dict) -> None:
    """Overlay: dashed perfect circle vs solid actual detected rim.

    Radius comes from the rim, but the dashed circle is **bottom-aligned** to the
    actual opening (not forced to share the rim center). So bottoms match; the
    perfect circle only peels away where the shape is off.
    """
    import numpy as np

    crop = result["crop_rgb"]
    height, width = crop.shape[:2]
    ax.imshow(crop)
    ax.axis("off")
    ax.set_aspect("equal")

    x = np.asarray(result.get("x_rim"), dtype=float)
    y = np.asarray(result.get("y_rim"), dtype=float)
    if x.size < 2:
        return

    rim_fit = result.get("rim_fit") or {}
    # Size only: find a typical radius from the rim's own center.
    cx_fit = float(result.get("rim_center_x", rim_fit.get("center_x", np.mean(x))))
    cy_fit = float(result.get("rim_center_y", rim_fit.get("center_y", np.mean(y))))
    rim_radii = np.hypot(x - cx_fit, y - cy_fit)
    target_r = float(np.median(rim_radii))
    if target_r <= 1e-6:
        # Fallback: half the vertical span of the opening.
        target_r = 0.5 * float(np.max(y) - np.min(y))
    if target_r <= 1e-6:
        return

    # Bottom of the actual roll in image coords (y grows downward).
    bottom_i = int(np.argmax(y))
    bottom_y = float(y[bottom_i])
    # Keep horizontal near the opening center; register vertically from the bottom.
    cx = float(np.mean(x))
    cy = bottom_y - target_r

    theta = np.linspace(0.0, 2.0 * np.pi, 360, endpoint=True)
    ax.plot(
        cx + target_r * np.cos(theta),
        cy + target_r * np.sin(theta),
        color="#e2e8f0",
        linestyle="--",
        linewidth=3.2,
        zorder=3,
    )
    ax.plot(
        cx + target_r * np.cos(theta),
        cy + target_r * np.sin(theta),
        color="#1e293b",
        linestyle="--",
        linewidth=1.8,
        label="Target (perfect circle)",
        zorder=4,
    )

    ax.plot(
        np.r_[x, x[0]],
        np.r_[y, y[0]],
        color="#ea580c",
        linewidth=2.6,
        label="Actual roll",
        zorder=5,
    )

    # Mark the shared bottom origin (not the dashed-circle center).
    ax.plot(
        [cx],
        [bottom_y],
        marker="o",
        markersize=5,
        color="#1e293b",
        zorder=6,
    )
    ax.legend(
        loc="upper right",
        fontsize=8,
        framealpha=0.92,
        facecolor="#ffffff",
        edgecolor="#cbd5e1",
    )
    margin = max(18.0, 0.04 * min(width, height))
    ax.set_xlim(-margin, width + margin)
    ax.set_ylim(height + margin, -margin)
