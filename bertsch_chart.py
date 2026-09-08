"""Bertsch chart language helpers — same fields operators use on the floor.

Calculator geometry stays in inches internally. Display and job cards use:
Desired Diameter, Thickness, Material, Plate Width, L Axis (mm), R Axis (mm).
"""

from __future__ import annotations

from typing import Any

from starting_setpoints import run_starting_setpoints

# Typical shop presets. Yield can be overridden with custom psi.
# Keys must be unique; labels show as ``Name (xx,xxx psi)``.
MATERIAL_PRESETS: dict[str, dict[str, Any]] = {
    "A36 Carbon Steel": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 36.0,
        "yield_psi": 36000.0,
    },
    "Mild Steel / Hot Rolled": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 36.0,
        "yield_psi": 36000.0,
    },
    "A572-50": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 50.0,
        "yield_psi": 50000.0,
    },
    "A516 Gr 70": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 38.0,
        "yield_psi": 38000.0,
    },
    "A588 (Corten)": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 50.0,
        "yield_psi": 50000.0,
    },
    "Carbon Steel (50 ksi)": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 50.0,
        "yield_psi": 50000.0,
    },
    "304 Stainless (annealed)": {
        "elastic_modulus_ksi": 28000.0,
        "yield_strength_ksi": 30.0,
        "yield_psi": 30000.0,
    },
    "304 Stainless (1/4 hard)": {
        "elastic_modulus_ksi": 28000.0,
        "yield_strength_ksi": 75.0,
        "yield_psi": 75000.0,
    },
    "316 / 316L Stainless": {
        "elastic_modulus_ksi": 28000.0,
        "yield_strength_ksi": 30.0,
        "yield_psi": 30000.0,
    },
    "301 Stainless": {
        "elastic_modulus_ksi": 28000.0,
        "yield_strength_ksi": 40.0,
        "yield_psi": 40000.0,
    },
    "2205 Duplex": {
        "elastic_modulus_ksi": 29000.0,
        "yield_strength_ksi": 65.0,
        "yield_psi": 65000.0,
    },
    "Aluminum 5052-H32": {
        "elastic_modulus_ksi": 10000.0,
        "yield_strength_ksi": 28.0,
        "yield_psi": 28000.0,
    },
    "Aluminum 6061-T6": {
        "elastic_modulus_ksi": 10000.0,
        "yield_strength_ksi": 40.0,
        "yield_psi": 40000.0,
    },
}

# Chart recipes still say "Carbon Steel" / "304 Stainless" — map those names.
MATERIAL_ALIASES: dict[str, str] = {
    "Carbon Steel": "A36 Carbon Steel",
    "304 Stainless": "304 Stainless (annealed)",
}

THICKNESS_CHOICES: tuple[str, ...] = (
    '16 ga (0.060")',
    '14 ga (0.075")',
    '12 ga (0.105")',
    '11 ga (0.120")',
    '10 ga (0.135")',
    '7 ga (0.179")',
    '1/16"',
    '3/32"',
    '1/8"',
    '5/32"',
    '3/16"',
    '7/32"',
    '1/4"',
    '5/16"',
    '3/8"',
    '7/16"',
    '1/2"',
    '5/8"',
    '3/4"',
    '1"',
    "Other…",
)

_THICKNESS_IN: dict[str, float] = {
    '16 ga (0.060")': 0.060,
    '14 ga (0.075")': 0.075,
    '12 ga (0.105")': 0.105,
    '11 ga (0.120")': 0.120,
    '10 ga (0.135")': 0.135,
    '7 ga (0.179")': 0.1793,
    '1/16"': 0.0625,
    '3/32"': 0.09375,
    '1/8"': 0.125,
    '5/32"': 0.15625,
    '3/16"': 0.1875,
    '7/32"': 0.21875,
    '1/4"': 0.25,
    '5/16"': 0.3125,
    '3/8"': 0.375,
    '7/16"': 0.4375,
    '1/2"': 0.5,
    '5/8"': 0.625,
    '3/4"': 0.75,
    '1"': 1.0,
}


def material_grade_options() -> list[str]:
    """Labels like ``Carbon Steel (36000 psi)`` for the operator picker."""
    options = [
        f"{name} ({int(preset['yield_psi']):,} psi)"
        for name, preset in MATERIAL_PRESETS.items()
    ]
    options.append("Other…")
    return options


def parse_material_grade_label(label: str) -> tuple[str, float | None]:
    """Return (material_name, yield_psi_or_None for Other)."""
    if label == "Other…" or label.startswith("Other"):
        return "Other…", None
    # Prefer longest name match so "304 Stainless (annealed)" wins over shorter keys.
    for name in sorted(MATERIAL_PRESETS.keys(), key=len, reverse=True):
        if label == name or label.startswith(name + " ("):
            return name, float(MATERIAL_PRESETS[name]["yield_psi"])
    # Chart / old labels.
    alias = MATERIAL_ALIASES.get(label.strip())
    if alias and alias in MATERIAL_PRESETS:
        return alias, float(MATERIAL_PRESETS[alias]["yield_psi"])
    return "Other…", None


def resolve_chart_material_name(chart_name: str | None) -> str | None:
    """Map a handwritten chart material string onto a preset key."""
    if not chart_name:
        return None
    if chart_name in MATERIAL_PRESETS:
        return chart_name
    return MATERIAL_ALIASES.get(chart_name)


def thickness_label_from_inches(thickness_in: float, *, tol: float = 0.002) -> str:
    """Best matching dropdown label for a thickness in inches."""
    for label, inches in _THICKNESS_IN.items():
        if abs(inches - float(thickness_in)) <= tol:
            return label
    return "Other…"


def material_grade_label_for_name(material_name: str) -> str:
    options = material_grade_options()
    for opt in options:
        if opt.startswith(material_name):
            return opt
    return options[0]


def render_shop_job_inputs(
    setup: dict[str, Any],
    *,
    compact: bool = False,
) -> dict[str, Any]:
    """Same diameter / thickness / grade dropdowns used on Check roll and Correct.

    Elastic modulus is set from the grade automatically (not shown).
    Returns diameter_in, thickness_in, material_name, yield_psi, missing.
    """
    import streamlit as st

    from shop_recipes import recipes_for_diameter
    from shop_templates import (
        OTHER_SIZE_LABEL,
        diameter_to_radius_in,
        radius_to_nearest_template,
        template_options,
    )

    material = setup["material"]
    nearest = radius_to_nearest_template(material["target_final_radius_in"])
    default_size = str(nearest if nearest is not None else 48)
    options = template_options()
    if "quick_template_size" not in st.session_state:
        st.session_state.quick_template_size = (
            default_size if default_size in options else "48"
        )

    diameter_label = "Diameter" if compact else "Desired diameter (hanging template size)"
    thickness_label = "Thickness"
    material_label = "Material" if compact else "Material grade"
    material_help = None if compact else (
        "Yield strength is shown in parentheses. Elastic modulus is set from the grade."
    )

    # Prefill thickness/material from chart when diameter is already selected.
    _size_for_pref = st.session_state.get("quick_template_size", default_size)
    if _size_for_pref == OTHER_SIZE_LABEL:
        _pref_d = float(material["target_final_radius_in"] * 2.0)
    elif _size_for_pref in options:
        _pref_d = float(_size_for_pref)
    else:
        _pref_d = float(default_size)
    _pref_matches = recipes_for_diameter(_pref_d)
    pref_thick = None
    pref_mat = None
    for row in _pref_matches:
        if row.get("thickness") in THICKNESS_CHOICES and pref_thick is None:
            pref_thick = row["thickness"]
        resolved = resolve_chart_material_name(row.get("material"))
        if resolved and pref_mat is None:
            pref_mat = resolved

    thick_options = list(THICKNESS_CHOICES)
    if "job_thickness_choice" not in st.session_state:
        st.session_state.job_thickness_choice = (
            pref_thick if pref_thick in thick_options else '1/4"'
        )
    grade_options = material_grade_options()
    if "job_material_grade" not in st.session_state:
        grade_default = grade_options[0]
        for opt in grade_options:
            if pref_mat and opt.startswith(pref_mat):
                grade_default = opt
                break
        st.session_state.job_material_grade = grade_default

    if compact:
        st.markdown('<span class="job-inputs-row-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([2, 2, 5], gap="small")
        with c1:
            size_choice = st.selectbox(
                diameter_label,
                options=options,
                key="quick_template_size",
            )
        with c2:
            thickness_choice = st.selectbox(
                thickness_label,
                options=thick_options,
                key="job_thickness_choice",
            )
        with c3:
            material_grade = st.selectbox(
                material_label,
                options=grade_options,
                key="job_material_grade",
                help=material_help,
            )
    else:
        size_choice = st.selectbox(
            diameter_label,
            options=options,
            key="quick_template_size",
        )
        thickness_choice = st.selectbox(
            thickness_label,
            options=thick_options,
            key="job_thickness_choice",
        )
        material_grade = st.selectbox(
            material_label,
            options=grade_options,
            key="job_material_grade",
            help=material_help,
        )

    if size_choice == OTHER_SIZE_LABEL:
        job_diameter_in = st.number_input(
            "Inside diameter [in]",
            value=float(material["target_final_radius_in"] * 2.0),
            min_value=1.0,
            step=1.0,
            key="quick_custom_id",
        )
    else:
        job_diameter_in = float(size_choice)
    material["target_final_radius_in"] = diameter_to_radius_in(job_diameter_in)

    custom_thickness_in = None
    if thickness_choice == "Other…":
        custom_thickness_in = st.number_input(
            "Thickness [in]",
            min_value=0.001,
            value=float(material.get("sheet_thickness_in") or 0.25),
            step=0.001,
            format="%.3f",
            key="job_thickness_custom",
        )
    thickness_in = thickness_to_inches(thickness_choice, custom_thickness_in)
    material_name, preset_yield_psi = parse_material_grade_label(material_grade)
    yield_psi = preset_yield_psi
    if material_name == "Other…":
        yield_psi = st.number_input(
            "Yield strength [psi]",
            min_value=1000.0,
            value=float(st.session_state.get("job_yield_psi") or 36000.0),
            step=1000.0,
            key="job_yield_psi",
        )

    missing = missing_job_inputs(
        thickness_in=thickness_in,
        material_name=material_name,
        yield_psi=yield_psi,
    )
    if not missing and thickness_in is not None:
        material["sheet_thickness_in"] = float(thickness_in)
        apply_material_preset(
            setup,
            material_name,
            yield_psi=float(yield_psi) if yield_psi is not None else None,
        )
        # Keep widget-backed keys in sync for Correct's update_setup_from_inputs.
        st.session_state["target_final_radius_in"] = material["target_final_radius_in"]
        st.session_state["sheet_thickness_in"] = material["sheet_thickness_in"]
        st.session_state["yield_strength_ksi"] = material["yield_strength_ksi"]
        st.session_state["elastic_modulus_ksi"] = material["elastic_modulus_ksi"]

    chart_matches = recipes_for_diameter(job_diameter_in)

    return {
        "diameter_in": float(job_diameter_in),
        "thickness_in": float(thickness_in) if thickness_in else None,
        "thickness_choice": thickness_choice,
        "material_name": material_name,
        "yield_psi": float(yield_psi) if yield_psi is not None else None,
        "missing": missing,
        "chart_matches": chart_matches,
    }


def thickness_to_inches(label: str | None, custom_in: float | None = None) -> float | None:
    if label is None or label == "" or label == "Other…":
        if custom_in is not None and custom_in > 0:
            return float(custom_in)
        return None
    if label in _THICKNESS_IN:
        return _THICKNESS_IN[label]
    return None


def inches_to_mm(inches: float) -> float:
    return float(inches) * 25.4


def mm_to_inches(mm: float) -> float:
    return float(mm) / 25.4


def resolve_start_lr(
    setup: dict[str, Any],
    *,
    diameter_in: float,
    thickness_in: float,
    thickness_choice: str | None,
    material_name: str,
    yield_psi: float | None = None,
    positions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Starting L/R: verified chart → chart-filled sizes → calculator.

    1. Verified: diameter + thickness + material all match a chart line.
    2. Chart-based: interpolate/fill from confirmed chart sizes (same thickness
       series when possible).
    3. Calculator: springback estimate, optionally shifted so it matches the
       nearest chart anchor (machine-calibrated fill).
    """
    from shop_recipes import estimate_lr_from_chart_anchors, recipes_for_diameter

    chart_matches = recipes_for_diameter(diameter_in)
    # Strict: chart row must name thickness + material, and both must match job.
    full_matches = [
        r
        for r in chart_matches
        if r.get("thickness")
        and r.get("material")
        and r.get("thickness") == thickness_choice
        and (
            resolve_chart_material_name(r.get("material")) == material_name
            or r.get("material") == material_name
        )
    ]
    if full_matches:
        tip = full_matches[0]
        return {
            "l_axis_mm": float(tip["l_axis_mm"]),
            "r_axis_mm": float(tip["r_axis_mm"]),
            "source": "shop_chart",
            "source_label": "Shop chart",
            "notes": tip.get("notes") or "",
            "verified": True,
        }

    # Fill other sizes from confirmed chart diameters (shop truth trend).
    chart_fill = estimate_lr_from_chart_anchors(
        diameter_in=diameter_in,
        thickness_choice=thickness_choice,
    )
    if chart_fill is not None:
        return chart_fill

    # Fall back to springback; bias to nearest chart point when we can.
    if positions is not None:
        axes = positions_to_chart_axes(positions)
    else:
        recipe = calculate_chart_recipe(
            setup,
            diameter_in=diameter_in,
            thickness_in=thickness_in,
            material_name=material_name,
            yield_psi=yield_psi,
        )
        axes = {
            "l_axis_mm": float(recipe["l_axis_mm"]),
            "r_axis_mm": float(recipe["r_axis_mm"]),
        }

    calibrated = _calibrate_axes_to_nearest_chart(
        setup,
        diameter_in=diameter_in,
        thickness_in=thickness_in,
        thickness_choice=thickness_choice,
        material_name=material_name,
        yield_psi=yield_psi,
        axes=axes,
    )
    if calibrated is not None:
        return calibrated

    return {
        "l_axis_mm": float(axes["l_axis_mm"]),
        "r_axis_mm": float(axes["r_axis_mm"]),
        "source": "calculator",
        "source_label": "Calculator estimate",
        "notes": "Same springback model as Calculate adjustment.",
        "verified": False,
    }


def _calibrate_axes_to_nearest_chart(
    setup: dict[str, Any],
    *,
    diameter_in: float,
    thickness_in: float,
    thickness_choice: str | None,
    material_name: str,
    yield_psi: float | None,
    axes: dict[str, float],
) -> dict[str, Any] | None:
    """Shift calculator L/R so it agrees with the nearest confirmed chart size."""
    from shop_recipes import SHOP_RECIPES

    # Prefer general (size-only) anchors; they form the clean diameter trend.
    anchors = [dict(r) for r in SHOP_RECIPES if not r.get("thickness")]
    if not anchors:
        anchors = [dict(r) for r in SHOP_RECIPES]
    if not anchors:
        return None

    anchor = min(anchors, key=lambda r: abs(float(r["diameter_in"]) - float(diameter_in)))
    anchor_d = float(anchor["diameter_in"])
    try:
        at_anchor = calculate_chart_recipe(
            setup,
            diameter_in=anchor_d,
            thickness_in=thickness_in,
            material_name=material_name,
            yield_psi=yield_psi,
        )
    except Exception:
        return None

    bias_l = float(anchor["l_axis_mm"]) - float(at_anchor["l_axis_mm"])
    bias_r = float(anchor["r_axis_mm"]) - float(at_anchor["r_axis_mm"])
    return {
        "l_axis_mm": float(axes["l_axis_mm"]) + bias_l,
        "r_axis_mm": float(axes["r_axis_mm"]) + bias_r,
        "source": "chart_calibrated",
        "source_label": "Chart-calibrated estimate",
        "notes": (
            f"Calculator shifted to match confirmed chart at {anchor_d:.0f}\" "
            f"(L {float(anchor['l_axis_mm']):.0f} / R {float(anchor['r_axis_mm']):.0f})."
        ),
        "verified": False,
    }


def apply_material_preset(setup: dict[str, Any], material_name: str, *, yield_psi: float | None = None) -> None:
    """Write E / Sy into setup from a named preset or custom yield (psi)."""
    material = setup["material"]
    preset = MATERIAL_PRESETS.get(material_name)
    if preset:
        material["elastic_modulus_ksi"] = float(preset["elastic_modulus_ksi"])
        if yield_psi is None:
            material["yield_strength_ksi"] = float(preset["yield_strength_ksi"])
        else:
            material["yield_strength_ksi"] = float(yield_psi) / 1000.0
    else:
        # Unknown alloy: keep E at steel default unless already set reasonably.
        e = float(material.get("elastic_modulus_ksi") or 29000.0)
        if e > 100000:
            e = 29000.0
        material["elastic_modulus_ksi"] = e
        if yield_psi is not None and yield_psi > 0:
            material["yield_strength_ksi"] = float(yield_psi) / 1000.0


def positions_to_chart_axes(positions: dict[str, Any]) -> dict[str, float]:
    """Map solver travel (inches) to Jog-screen style L/R Axis mm."""
    left_in = float(positions["left_solution"]["travel"])
    right_in = float(positions["right_solution"]["travel"])
    return {
        "l_axis_mm": inches_to_mm(left_in),
        "r_axis_mm": inches_to_mm(right_in),
        "l_axis_in": left_in,
        "r_axis_in": right_in,
    }


def calculate_chart_recipe(
    setup: dict[str, Any],
    *,
    diameter_in: float,
    thickness_in: float,
    material_name: str,
    yield_psi: float | None = None,
    plate_width_in: float | None = None,
) -> dict[str, Any]:
    """Run the springback calculator and return a chart-shaped recipe row."""
    if diameter_in <= 0:
        raise ValueError("Desired diameter must be greater than zero.")
    if thickness_in <= 0:
        raise ValueError("Thickness must be greater than zero.")
    if material_name == "Other…" and (yield_psi is None or yield_psi <= 0):
        raise ValueError("Enter yield strength (psi) for Other material.")

    job = dict(setup)
    job["material"] = dict(setup["material"])
    job["material"]["target_final_radius_in"] = float(diameter_in) / 2.0
    job["material"]["sheet_thickness_in"] = float(thickness_in)
    apply_material_preset(job, material_name, yield_psi=yield_psi)

    out = run_starting_setpoints(job)
    axes = positions_to_chart_axes(out["positions"])
    thickness_label = next(
        (k for k, v in _THICKNESS_IN.items() if abs(v - thickness_in) < 1e-6),
        f'{thickness_in:.3f}"',
    )
    return {
        "diameter_in": float(diameter_in),
        "thickness": thickness_label,
        "thickness_in": float(thickness_in),
        "material": material_name if material_name != "Other…" else f"Custom ({yield_psi:.0f} psi)",
        "plate_width_in": float(plate_width_in) if plate_width_in else None,
        "l_axis_mm": axes["l_axis_mm"],
        "r_axis_mm": axes["r_axis_mm"],
        "l_axis_in": axes["l_axis_in"],
        "r_axis_in": axes["r_axis_in"],
        "notes": (
            "Calculator estimate — same language as the shop chart. "
            "Confirm on the hanging template / Jog screen before treating as verified."
        ),
        "verified": False,
        "source": "calculator",
        "yield_strength_ksi": float(job["material"]["yield_strength_ksi"]),
        "elastic_modulus_ksi": float(job["material"]["elastic_modulus_ksi"]),
        "loaded_radius_in": float(out["loaded_radius"]),
        "travel_in_range": bool(out["travel_in_range"]),
        "setup_used": job,
    }


def missing_job_inputs(
    *,
    thickness_in: float | None,
    material_name: str | None,
    yield_psi: float | None,
) -> list[str]:
    missing: list[str] = []
    if thickness_in is None or thickness_in <= 0:
        missing.append("Thickness")
    if not material_name:
        missing.append("Material grade")
    elif material_name == "Other…" and (yield_psi is None or yield_psi <= 0):
        missing.append("Yield strength (psi)")
    return missing


def stash_job_for_correct(
    *,
    diameter_in: float,
    thickness_in: float,
    material_name: str,
    yield_psi: float | None = None,
    plate_width_in: float | None = None,
) -> None:
    """Save Check-roll job inputs so Correct opens already filled.

    Do not write shared selectbox keys here — Check roll already instantiated
    those widgets in this run. Correct applies ``pending_correct_job`` before
    its widgets render.
    """
    import streamlit as st

    from springback.defaults import get_default_setup

    setup = st.session_state.get("setup") or get_default_setup()
    setup = dict(setup)
    setup["material"] = dict(setup["material"])
    setup["material"]["target_final_radius_in"] = float(diameter_in) / 2.0
    setup["material"]["sheet_thickness_in"] = float(thickness_in)
    apply_material_preset(setup, material_name, yield_psi=yield_psi)
    st.session_state.setup = setup
    st.session_state.quick_setup = setup
    st.session_state["pending_correct_job"] = {
        "diameter_in": float(diameter_in),
        "thickness_in": float(thickness_in),
        "material_name": material_name,
        "yield_psi": float(yield_psi)
        if yield_psi is not None
        else float(setup["material"]["yield_strength_ksi"]) * 1000.0,
        "plate_width_in": float(plate_width_in) if plate_width_in else None,
        "elastic_modulus_ksi": float(setup["material"]["elastic_modulus_ksi"]),
        "yield_strength_ksi": float(setup["material"]["yield_strength_ksi"]),
    }
    st.session_state.pop("correct_target_radius_locked", None)
    for key in (
        "desired_diameter_in",
        "yield_strength_psi",
    ):
        st.session_state.pop(key, None)


def apply_pending_job_dropdowns(pending: dict[str, Any]) -> None:
    """Set shared job selectbox keys before those widgets are created."""
    import streamlit as st

    from shop_templates import OTHER_SIZE_LABEL, template_options

    diameter_in = float(pending["diameter_in"])
    thickness_in = float(pending["thickness_in"])
    material_name = str(pending.get("material_name") or "A36 Carbon Steel")
    yield_psi = pending.get("yield_psi")

    size_str = str(int(round(diameter_in)))
    if size_str in template_options():
        st.session_state["quick_template_size"] = size_str
    else:
        st.session_state["quick_template_size"] = OTHER_SIZE_LABEL
        st.session_state["quick_custom_id"] = diameter_in
    st.session_state["job_thickness_choice"] = thickness_label_from_inches(thickness_in)
    if st.session_state["job_thickness_choice"] == "Other…":
        st.session_state["job_thickness_custom"] = thickness_in
    st.session_state["job_material_grade"] = material_grade_label_for_name(material_name)
    if material_name == "Other…" and yield_psi is not None:
        st.session_state["job_yield_psi"] = float(yield_psi)
