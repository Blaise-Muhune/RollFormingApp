"""Shop Bertsch L/R recipes from the handwritten operator chart.

Values are live machine L Axis / R Axis in millimeters (M-11106 Jog screen).
These lines are the shop table — treated as verified start numbers.
"""

from __future__ import annotations

from typing import Any

# Handwritten chart transcribed into the app (operator table).
SHOP_RECIPES: tuple[dict[str, Any], ...] = (
    {
        "diameter_in": 28,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 105.0,
        "r_axis_mm": 37.0,
        "notes": "Start 105 / last 37",
        "verified": True,
    },
    {
        "diameter_in": 30,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 110.0,
        "r_axis_mm": 48.0,
        "notes": "Start / first roll",
        "verified": True,
    },
    {
        "diameter_in": 36,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 120.0,
        "r_axis_mm": 80.0,
        "notes": "Older reference",
        "verified": True,
    },
    {
        "diameter_in": 36,
        "thickness": "3/16\"",
        "material": "Carbon Steel",
        "plate_width_in": None,
        "l_axis_mm": 123.0,
        "r_axis_mm": 75.0,
        "notes": "Finish cut noted as 60",
        "verified": True,
    },
    {
        "diameter_in": 36,
        "thickness": "5/16\"",
        "material": "304 Stainless",
        "plate_width_in": None,
        "l_axis_mm": 135.0,
        "r_axis_mm": 74.0,
        "notes": "From green reference note",
        "verified": True,
    },
    {
        "diameter_in": 36,
        "thickness": "1/2\"",
        "material": None,
        "plate_width_in": 46.0,
        "l_axis_mm": 145.0,
        "r_axis_mm": 114.0,
        "notes": None,
        "verified": True,
    },
    {
        "diameter_in": 42,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 128.0,
        "r_axis_mm": 95.0,
        "notes": "First bend 128 / first full roll 95",
        "verified": True,
    },
    {
        "diameter_in": 46,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 137.0,
        "r_axis_mm": 95.0,
        "notes": "105 appears crossed out",
        "verified": True,
    },
    {
        "diameter_in": 54,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 145.0,
        "r_axis_mm": 100.0,
        "notes": "Separate reference sheet",
        "verified": True,
    },
    {
        "diameter_in": 60,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 150.0,
        "r_axis_mm": 115.0,
        "notes": "Separate reference sheet",
        "verified": True,
    },
    {
        "diameter_in": 70,
        "thickness": "3/8\"",
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 160.0,
        "r_axis_mm": 147.0,
        "notes": None,
        "verified": True,
    },
    {
        "diameter_in": 70,
        "thickness": "1/4\"",
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 170.0,
        "r_axis_mm": 137.0,
        "notes": None,
        "verified": True,
    },
    {
        "diameter_in": 72,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 165.0,
        "r_axis_mm": 135.0,
        "notes": "Separate reference sheet",
        "verified": True,
    },
    {
        "diameter_in": 84,
        "thickness": None,
        "material": None,
        "plate_width_in": None,
        "l_axis_mm": 180.0,
        "r_axis_mm": 137.0,
        "notes": "Separate reference sheet",
        "verified": True,
    },
)


def recipe_diameters() -> list[int]:
    return sorted({int(r["diameter_in"]) for r in SHOP_RECIPES})


def recipes_for_diameter(diameter_in: float, *, tol: float = 0.6) -> list[dict[str, Any]]:
    d = float(diameter_in)
    return [dict(r) for r in SHOP_RECIPES if abs(float(r["diameter_in"]) - d) <= tol]


def recipe_option_label(recipe: dict[str, Any]) -> str:
    parts: list[str] = []
    if recipe.get("thickness"):
        parts.append(str(recipe["thickness"]))
    if recipe.get("material"):
        parts.append(str(recipe["material"]))
    if recipe.get("plate_width_in"):
        parts.append(f'{recipe["plate_width_in"]:.0f}" wide')
    if not parts:
        parts.append("General")
    return " · ".join(parts)


def mm_to_in(mm: float) -> float:
    return float(mm) / 25.4


def _lerp(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if abs(x1 - x0) < 1e-9:
        return float(y0)
    t = (x - x0) / (x1 - x0)
    return float(y0 + t * (y1 - y0))


def estimate_lr_from_chart_anchors(
    *,
    diameter_in: float,
    thickness_choice: str | None = None,
) -> dict[str, Any] | None:
    """Estimate L/R by interpolating confirmed shop-chart diameters.

    Prefers a thickness-matched series when the chart has enough points;
    otherwise uses the general (size-only) chart lines. Not marked verified —
    those numbers are filled from nearby confirmed sizes.
    """
    d = float(diameter_in)

    # Thickness-specific series (need at least 2 diameters with that thickness).
    thick_series: list[dict[str, Any]] = []
    if thickness_choice:
        by_d: dict[float, dict[str, Any]] = {}
        for row in SHOP_RECIPES:
            if row.get("thickness") != thickness_choice:
                continue
            key = float(row["diameter_in"])
            # Prefer a row that also names material when duplicates exist.
            prev = by_d.get(key)
            if prev is None or (row.get("material") and not prev.get("material")):
                by_d[key] = dict(row)
        thick_series = [by_d[k] for k in sorted(by_d)]

    # General size-only trend (no thickness listed).
    general_by_d: dict[float, dict[str, Any]] = {}
    for row in SHOP_RECIPES:
        if row.get("thickness"):
            continue
        key = float(row["diameter_in"])
        general_by_d[key] = dict(row)
    general_series = [general_by_d[k] for k in sorted(general_by_d)]

    series = thick_series if len(thick_series) >= 2 else general_series
    if len(series) < 2:
        # Single nearest chart point — use as-is only if very close.
        pool = thick_series or general_series or [dict(r) for r in SHOP_RECIPES]
        if not pool:
            return None
        nearest = min(pool, key=lambda r: abs(float(r["diameter_in"]) - d))
        if abs(float(nearest["diameter_in"]) - d) > 2.0:
            return None
        return {
            "l_axis_mm": float(nearest["l_axis_mm"]),
            "r_axis_mm": float(nearest["r_axis_mm"]),
            "source": "chart_anchor",
            "source_label": "Chart-based estimate",
            "notes": (
                f"Nearest chart size {float(nearest['diameter_in']):.0f}\" "
                f"(L {float(nearest['l_axis_mm']):.0f} / R {float(nearest['r_axis_mm']):.0f})."
            ),
            "verified": False,
            "anchor_low_in": float(nearest["diameter_in"]),
            "anchor_high_in": float(nearest["diameter_in"]),
        }

    diameters = [float(r["diameter_in"]) for r in series]
    # Exact hit on this series.
    for row in series:
        if abs(float(row["diameter_in"]) - d) <= 0.6:
            kind = "thickness series" if series is thick_series else "size chart"
            return {
                "l_axis_mm": float(row["l_axis_mm"]),
                "r_axis_mm": float(row["r_axis_mm"]),
                "source": "chart_anchor",
                "source_label": "Chart-based estimate",
                "notes": f"From {kind} at {float(row['diameter_in']):.0f}\".",
                "verified": False,
                "anchor_low_in": float(row["diameter_in"]),
                "anchor_high_in": float(row["diameter_in"]),
            }

    # Interpolate / mild extrapolate between neighboring confirmed sizes.
    if d <= diameters[0]:
        lo, hi = series[0], series[1]
    elif d >= diameters[-1]:
        lo, hi = series[-2], series[-1]
    else:
        hi = next(r for r in series if float(r["diameter_in"]) >= d)
        hi_i = series.index(hi)
        lo = series[hi_i - 1]

    d0, d1 = float(lo["diameter_in"]), float(hi["diameter_in"])
    l_mm = _lerp(d, d0, d1, float(lo["l_axis_mm"]), float(hi["l_axis_mm"]))
    r_mm = _lerp(d, d0, d1, float(lo["r_axis_mm"]), float(hi["r_axis_mm"]))
    kind = "thickness series" if series is thick_series else "size chart"
    return {
        "l_axis_mm": l_mm,
        "r_axis_mm": r_mm,
        "source": "chart_anchor",
        "source_label": "Chart-based estimate",
        "notes": (
            f"Filled from confirmed {kind} between {d0:.0f}\" "
            f"(L {float(lo['l_axis_mm']):.0f}/R {float(lo['r_axis_mm']):.0f}) and "
            f"{d1:.0f}\" (L {float(hi['l_axis_mm']):.0f}/R {float(hi['r_axis_mm']):.0f})."
        ),
        "verified": False,
        "anchor_low_in": d0,
        "anchor_high_in": d1,
    }
