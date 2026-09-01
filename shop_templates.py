"""Shop hanging radius templates used for the first-curve check.

The board uses finished **inside diameter** in inches (24, 30, 36, 42, 48, 54, 60, 102).
Radius for springback / Bertsch set points is diameter / 2.
"""

from __future__ import annotations

# Pegs on the shop board (48 is often off the board because it is in use).
SHOP_TEMPLATE_DIAMETERS_IN: tuple[int, ...] = (24, 30, 36, 42, 48, 54, 60, 102)

OTHER_SIZE_LABEL = "Other size…"


def diameter_to_radius_in(diameter_in: float) -> float:
    return float(diameter_in) / 2.0


def radius_to_nearest_template(radius_in: float) -> int | None:
    diameter = float(radius_in) * 2.0
    best = min(SHOP_TEMPLATE_DIAMETERS_IN, key=lambda d: abs(d - diameter))
    if abs(best - diameter) <= 0.6:
        return int(best)
    return None


def all_job_diameters() -> tuple[int, ...]:
    """Hanging templates plus diameters that appear on the Bertsch recipe chart."""
    from shop_recipes import recipe_diameters

    return tuple(sorted(set(SHOP_TEMPLATE_DIAMETERS_IN) | set(recipe_diameters())))


def template_options() -> list[str]:
    return [str(d) for d in all_job_diameters()] + [OTHER_SIZE_LABEL]
