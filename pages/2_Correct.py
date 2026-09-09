import streamlit as st

from springback.calculations import calculate_required_loaded_radius
from springback.defaults import get_default_setup, setup_from_json, setup_to_json
from springback.ellipse import parse_ellipse_coefficients, sample_ellipse_compensation
from springback.geometry import solve_machine_positions
from springback.plotting import plot_ellipse_compensation, plot_roll_former_geometry
from springback.ui import (
    apply_theme,
    lr_hero,
    metric_row,
    number_input,
    start_badge,
    step_label,
    step_label_row,
)
from springback.schedule import (
    CORRECTION_SOLVER_SAMPLE_COUNT,
    calculate_side_roll_adjustment_schedule,
    station_table_rows,
)
from bertsch_chart import (
    apply_pending_job_dropdowns,
    positions_to_chart_axes,
    render_shop_job_inputs,
)
from advanced_nav import render_top_menu
from branding import PAGE_ICON
from workflow import (
    get_inspect_target_radius,
    get_rim_equation_json,
    rim_equation_ready,
)


# Single source of truth for binding Streamlit widget keys to the nested setup
# dictionary. When adding a new editable setup field, add it here and to
# DEFAULT_SETUP so load/save/reset/session-state behavior stays consistent.
WIDGET_PATHS = {
    "machine_layout": ("machine_layout",),
    "units": ("units",),
    "elastic_modulus_ksi": ("material", "elastic_modulus_ksi"),
    "yield_strength_ksi": ("material", "yield_strength_ksi"),
    "sheet_thickness_in": ("material", "sheet_thickness_in"),
    "target_final_radius_in": ("material", "target_final_radius_in"),
    "top_roll_radius_in": ("geometry", "top_roll_radius_in"),
    "bottom_roll_radius_in": ("geometry", "bottom_roll_radius_in"),
    "side_roll_radius_in": ("geometry", "side_roll_radius_in"),
    "top_center_x_in": ("geometry", "top_center_x_in"),
    "top_center_y_in": ("geometry", "top_center_y_in"),
    "bottom_center_x_in": ("geometry", "bottom_center_x_in"),
    "bottom_center_y_in": ("geometry", "bottom_center_y_in"),
    "left_pivot_x_in": ("geometry", "left_pivot_x_in"),
    "left_pivot_y_in": ("geometry", "left_pivot_y_in"),
    "right_pivot_x_in": ("geometry", "right_pivot_x_in"),
    "right_pivot_y_in": ("geometry", "right_pivot_y_in"),
    "left_angle_deg": ("travel", "left_angle_deg"),
    "right_angle_deg": ("travel", "right_angle_deg"),
    "min_side_travel_in": ("travel", "min_side_travel_in"),
    "max_side_travel_in": ("travel", "max_side_travel_in"),
}


def get_nested_value(data, path):
    """Read a nested setup value using a tuple path from WIDGET_PATHS."""
    value = data
    for key in path:
        value = value[key]
    return value


def set_nested_value(data, path, value):
    """Write a nested setup value using a tuple path from WIDGET_PATHS."""
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def sync_widget_state(setup, overwrite=False):
    """Copy setup values into Streamlit session state.

    Streamlit widgets own their own state once created. This function keeps the
    widget state synchronized after load/reset while avoiding overwriting active
    user edits on ordinary reruns.
    """
    for widget_key, path in WIDGET_PATHS.items():
        if overwrite or widget_key not in st.session_state:
            st.session_state[widget_key] = get_nested_value(setup, path)


def initialize_state():
    """Initialize or normalize all session-state values used by the app."""
    if "setup" not in st.session_state:
        st.session_state.setup = get_default_setup()
    else:
        # Round-trip through JSON/default merging so older sessions pick up any
        # newly added setup keys without mutating DEFAULT_SETUP.
        st.session_state.setup = setup_from_json(setup_to_json(st.session_state.setup))
    if "animation_running" not in st.session_state:
        st.session_state.animation_running = False
    if "animation_frame" not in st.session_state:
        st.session_state.animation_frame = 0
    if "ellipse_coefficients" not in st.session_state:
        st.session_state.ellipse_coefficients = None

    # Job handed off from Check roll: diameter / thickness / yield already chosen.
    pending = st.session_state.pop("pending_correct_job", None)
    applied_job = False
    if isinstance(pending, dict):
        mat = st.session_state.setup["material"]
        mat["target_final_radius_in"] = float(pending["diameter_in"]) / 2.0
        mat["sheet_thickness_in"] = float(pending["thickness_in"])
        mat["yield_strength_ksi"] = float(pending["yield_strength_ksi"])
        mat["elastic_modulus_ksi"] = float(pending["elastic_modulus_ksi"])
        st.session_state.pop("correct_target_radius_locked", None)
        applied_job = True
        st.session_state["_correct_job_banner"] = (
            "Loaded from Check roll — job settings applied."
        )
        # Must run before render_shop_job_inputs creates the selectboxes.
        apply_pending_job_dropdowns(pending)
        st.session_state["target_final_radius_in"] = float(pending["diameter_in"]) / 2.0
        st.session_state["sheet_thickness_in"] = float(pending["thickness_in"])
        st.session_state["yield_strength_ksi"] = float(pending["yield_strength_ksi"])
        st.session_state["elastic_modulus_ksi"] = float(pending["elastic_modulus_ksi"])

    # Prefer the Inspect-stage target radius when the operator continues the
    # unified workflow, unless they already customized material settings.
    inspect_target = get_inspect_target_radius()
    applied_inspect_target = False
    if (
        not applied_job
        and inspect_target is not None
        and not st.session_state.get("correct_target_radius_locked")
    ):
        st.session_state.setup["material"]["target_final_radius_in"] = inspect_target
        applied_inspect_target = True

    sync_widget_state(
        st.session_state.setup,
        overwrite=applied_job or applied_inspect_target,
    )
    autoload_rim_equation_from_inspect()


def autoload_rim_equation_from_inspect():
    """Parse the in-session Inspect payload into Correct-stage coefficients."""
    rim_json = get_rim_equation_json()
    if not rim_json:
        return

    token = st.session_state.get("ellipse_autoload_token")
    # Respect an explicit file upload until Inspect publishes a newer equation.
    if st.session_state.get("ellipse_source") == "upload" and token == rim_json:
        return
    if st.session_state.get("ellipse_coefficients") is not None and token == rim_json:
        return

    try:
        st.session_state.ellipse_coefficients = parse_ellipse_coefficients(rim_json)
        st.session_state.ellipse_autoload_token = rim_json
        st.session_state.ellipse_source = "inspect"
        st.session_state.pop("_ellipse_autoload_error", None)
    except Exception as exc:
        st.session_state.ellipse_coefficients = None
        st.session_state.ellipse_source = None
        st.session_state["_ellipse_autoload_error"] = str(exc)


def update_setup_from_inputs(setup):
    """Persist current widget values back into the nested setup dictionary."""
    for widget_key, path in WIDGET_PATHS.items():
        set_nested_value(setup, path, st.session_state[widget_key])


@st.cache_data(show_spinner=False)
def calculate_model_state(setup_json):
    """Calculate springback and machine positions from a JSON cache key.

    Streamlit cache keys are more reliable with immutable/simple inputs, so the
    setup dictionary is serialized before entering this function.
    """
    setup = setup_from_json(setup_json)
    material = setup["material"]
    calculation = calculate_required_loaded_radius(
        material["elastic_modulus_ksi"],
        material["yield_strength_ksi"],
        material["sheet_thickness_in"],
        material["target_final_radius_in"],
    )
    loaded_radius = calculation["required_loaded_radius"]
    positions = solve_machine_positions(setup, loaded_radius)
    return calculation, positions


def render_operator_do_this(setup, positions):
    """Minimal shop-floor card: only what to set on the Bertsch."""
    from bertsch_chart import resolve_start_lr, thickness_label_from_inches

    material = setup["material"]
    diameter_in = float(material["target_final_radius_in"]) * 2.0
    thickness_in = float(material["sheet_thickness_in"])
    yield_psi = float(material["yield_strength_ksi"]) * 1000.0
    thickness_choice = thickness_label_from_inches(thickness_in)
    material_name = st.session_state.get("job_material_grade") or ""
    try:
        from bertsch_chart import parse_material_grade_label

        if material_name:
            material_name, _ = parse_material_grade_label(material_name)
    except Exception:
        material_name = "A36 Carbon Steel"

    start = resolve_start_lr(
        setup,
        diameter_in=diameter_in,
        thickness_in=thickness_in,
        thickness_choice=thickness_choice,
        material_name=material_name or "A36 Carbon Steel",
        yield_psi=yield_psi,
        positions=positions,
    )
    l_mm = float(start["l_axis_mm"])
    r_mm = float(start["r_axis_mm"])
    if start.get("verified"):
        footer = "From your shop chart for this diameter, thickness, and material."
    elif start.get("source") == "chart_calibrated":
        footer = start.get("notes") or "Estimate aligned to a nearby chart size."
    else:
        footer = "Estimate only — confirm on the hanging template before you rely on it."

    step_label_row("Set on jog", start_badge(start))
    st.markdown(lr_hero(l_mm, r_mm, highlight=True), unsafe_allow_html=True)
    st.markdown(
        """
        <div class="action-card primary">
          <h3>On the Bertsch</h3>
          <ol class="action-steps">
            <li>On Jog, set <strong>L Axis</strong> and <strong>R Axis</strong> to the values above.</li>
            <li>Roll, check the hanging template, then photo on Check roll if needed.</li>
          </ol>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(footer)

    if not (
        positions["left_solution"]["travel_in_range"]
        and positions["right_solution"]["travel_in_range"]
    ):
        st.warning("These travels may be outside the machine’s configured limits — confirm on the console.")

    return {"l_mm": l_mm, "r_mm": r_mm, "start": start}


def render_header():
    """Render title row — matches Check roll header."""
    render_top_menu(
        active="correct",
        title_html='<div class="app-title">Correct adjustment</div>',
    )


def render_sidebar_inputs(setup):
    """Machine geometry — collapsed in sidebar for engineers."""
    with st.sidebar:
        with st.expander("Machine setup", expanded=False):
            setup["machine_layout"] = st.selectbox(
                "Machine / Roll Layout",
                ["4-Roll Pyramid"],
                index=0,
                key="machine_layout",
            )
            setup["units"] = st.selectbox("Units", ["Inches"], index=0, key="units")
            render_roll_geometry_inputs(setup)
            render_side_roll_guide_inputs(setup)
            render_pivot_position_inputs(setup)
            st.download_button(
                "Save setup JSON",
                data=setup_to_json(setup),
                file_name="roll_former_setup.json",
                mime="application/json",
                use_container_width=True,
            )
            if st.button("Reset to defaults", use_container_width=True):
                st.session_state.setup = get_default_setup()
                sync_widget_state(st.session_state.setup, overwrite=True)
                st.rerun()


def render_job_inputs_main(setup):
    """Same diameter / thickness / grade dropdowns as Check roll."""
    return render_shop_job_inputs(setup, compact=True)


def render_roll_geometry_inputs(setup):
    """Render fixed roll radii and top/bottom origin controls."""
    geometry = setup["geometry"]
    geometry["top_roll_radius_in"] = number_input(
        "Top Roll Radius",
        geometry["top_roll_radius_in"],
        min_value=0.001,
        step=0.25,
        key="top_roll_radius_in",
    )
    geometry["bottom_roll_radius_in"] = number_input(
        "Bottom Roll Radius",
        geometry["bottom_roll_radius_in"],
        min_value=0.001,
        step=0.25,
        key="bottom_roll_radius_in",
    )
    geometry["side_roll_radius_in"] = number_input(
        "Side Roll Radius",
        geometry["side_roll_radius_in"],
        min_value=0.001,
        step=0.25,
        key="side_roll_radius_in",
    )

    top_col, bottom_col = st.columns(2)
    with top_col:
        geometry["top_center_y_in"] = number_input(
            "Top Center Y",
            geometry["top_center_y_in"],
            step=0.5,
            key="top_center_y_in",
        )
        geometry["bottom_center_y_in"] = number_input(
            "Bottom Roll Origin Y",
            geometry["bottom_center_y_in"],
            step=0.5,
            key="bottom_center_y_in",
        )
    with bottom_col:
        geometry["top_center_x_in"] = number_input(
            "Top Center X",
            geometry["top_center_x_in"],
            step=0.5,
            key="top_center_x_in",
        )
        geometry["bottom_center_x_in"] = number_input(
            "Bottom Roll Origin X",
            geometry["bottom_center_x_in"],
            step=0.5,
            key="bottom_center_x_in",
        )


def render_side_roll_guide_inputs(setup):
    """Render side-roll guide axis angles and travel limits."""
    travel = setup["travel"]
    travel["left_angle_deg"] = number_input(
        "Left Guide Angle",
        travel["left_angle_deg"],
        min_value=-180.0,
        max_value=180.0,
        step=1.0,
        fmt="%.1f",
        key="left_angle_deg",
    )
    travel["right_angle_deg"] = number_input(
        "Right Guide Angle",
        travel["right_angle_deg"],
        min_value=-180.0,
        max_value=180.0,
        step=1.0,
        fmt="%.1f",
        key="right_angle_deg",
    )
    travel["min_side_travel_in"] = number_input(
        "Minimum Travel",
        travel["min_side_travel_in"],
        step=0.5,
        key="min_side_travel_in",
    )
    travel["max_side_travel_in"] = number_input(
        "Maximum Travel",
        travel["max_side_travel_in"],
        step=0.5,
        key="max_side_travel_in",
    )


def render_pivot_position_inputs(setup):
    """Render side-roll pivot/origin controls for each rail."""
    geometry = setup["geometry"]
    left_col, right_col = st.columns(2)
    with left_col:
        geometry["left_pivot_x_in"] = number_input(
            "Left Side Roll Origin X",
            geometry["left_pivot_x_in"],
            step=0.5,
            key="left_pivot_x_in",
        )
        geometry["left_pivot_y_in"] = number_input(
            "Left Side Roll Origin Y",
            geometry["left_pivot_y_in"],
            step=0.5,
            key="left_pivot_y_in",
        )
    with right_col:
        geometry["right_pivot_x_in"] = number_input(
            "Right Side Roll Origin X",
            geometry["right_pivot_x_in"],
            step=0.5,
            key="right_pivot_x_in",
        )
        geometry["right_pivot_y_in"] = number_input(
            "Right Side Roll Origin Y",
            geometry["right_pivot_y_in"],
            step=0.5,
            key="right_pivot_y_in",
        )


def render_geometry_summary(setup, positions):
    """Display fixed geometry and solved span metrics."""
    step_label("Machine geometry")
    geometry = setup["geometry"]
    metric_row("Top Roll Radius (R1)", f"{geometry['top_roll_radius_in']:.3f} in")
    metric_row("Bottom Roll Radius (R2)", f"{geometry['bottom_roll_radius_in']:.3f} in")
    metric_row("Side Roll Radius", f"{geometry['side_roll_radius_in']:.3f} in")
    metric_row("Roll Center Span", f"{positions['roll_center_span']:.3f} in")
    metric_row("Top Roll Center Height", f"{positions['top_center'][1] - positions['left_center'][1]:.3f} in")


def render_calculator_comparison(setup, positions, operator_lr):
    """Show model L/R only when it disagrees with Set on jog."""
    axes = positions_to_chart_axes(positions)
    l_calc = float(axes["l_axis_mm"])
    r_calc = float(axes["r_axis_mm"])
    l_set = float(operator_lr["l_mm"])
    r_set = float(operator_lr["r_mm"])
    if abs(l_calc - l_set) < 1.0 and abs(r_calc - r_set) < 1.0:
        return

    step_label("Calculator differs")
    st.caption(
        "The springback model does not match Set on jog above. "
        "Use Set on jog on the floor; this row is for engineering review."
    )
    metric_row("Model L axis", f"{l_calc:.0f} mm")
    metric_row("Model R axis", f"{r_calc:.0f} mm")


def render_results(calculation, positions, target_radius):
    """One-line springback summary for engineers."""
    loaded_radius = calculation["required_loaded_radius"]
    springback_pct = float(calculation["springback_percent"])

    step_label("Springback model")
    st.caption(
        f"Roll to about {loaded_radius:.1f}\" loaded radius "
        f"({springback_pct:.0f}% springback) to land near {target_radius:.1f}\" final."
    )

    left_ok = positions["left_solution"]["travel_in_range"]
    right_ok = positions["right_solution"]["travel_in_range"]
    if not (left_ok and right_ok):
        st.warning("Model side-roll travel is outside configured limits.")


# Side-roll schedule helpers live in springback.schedule (shared with Quick Run).


@st.cache_data(show_spinner=False)
def cached_side_roll_adjustment_schedule(
    setup_json,
    nominal_loaded_radius,
    stations,
    sample_count=CORRECTION_SOLVER_SAMPLE_COUNT,
):
    return calculate_side_roll_adjustment_schedule(
        setup_json,
        nominal_loaded_radius,
        stations,
        sample_count=sample_count,
    )


def render_ellipse_upload(nominal_loaded_radius):
    """Render measured-rim correction from Inspect handoff or file upload."""
    step_label("Rim equation")

    if st.session_state.pop("_ellipse_autoload_error", None):
        st.error(
            "Could not load the Inspect-stage rim equation from session. "
            "Upload a JSON file below, or re-run Inspect."
        )

    if rim_equation_ready() and st.session_state.get("ellipse_source") == "inspect":
        st.caption("Loaded from Inspect this session.")
    elif st.session_state.ellipse_coefficients is not None:
        st.caption("Loaded from uploaded JSON.")

    uploaded = st.file_uploader(
        "Upload rim equation JSON",
        type=["json"],
        key="ellipse_upload",
        label_visibility="collapsed",
    )

    if uploaded is not None:
        try:
            st.session_state.ellipse_coefficients = parse_ellipse_coefficients(
                uploaded.getvalue().decode("utf-8")
            )
            st.session_state.ellipse_source = "upload"
            st.session_state.ellipse_autoload_token = get_rim_equation_json()
            st.rerun()
        except Exception as exc:
            st.session_state.ellipse_coefficients = None
            st.session_state.ellipse_source = None
            st.error(f"Could not load rim equation: {exc}")

    if st.session_state.ellipse_coefficients is None:
        st.caption("Optional — only if you ran Inspect or have a rim-equation file.")
        return

    setup = st.session_state.setup
    material = setup["material"]
    try:
        compensation = sample_ellipse_compensation(
            st.session_state.ellipse_coefficients,
            material["target_final_radius_in"],
            material["elastic_modulus_ksi"],
            material["yield_strength_ksi"],
            material["sheet_thickness_in"],
        )
    except Exception as exc:
        st.error(f"Could not calculate rim correction: {exc}")
        return

    params = compensation["parameters"]
    st.caption(
        f"Max rim adjustment {compensation['max_abs_adjustment_pct']:.1f}% · "
        f"peak-to-peak {params['peak_to_peak_radius']:.2f}"
    )

    adjusted_stations = cached_side_roll_adjustment_schedule(
        setup_to_json(setup),
        nominal_loaded_radius,
        tuple(compensation["stations"]),
    )
    dominant_keys = {row["angle_deg"] for row in compensation["dominant_stations"]}
    dominant_stations_by_distance = [
        row for row in adjusted_stations if row["angle_deg"] in dominant_keys
    ]
    dominant_stations_by_distance = sorted(
        dominant_stations_by_distance,
        key=lambda row: row["drive_distance_in"],
    )

    fig = plot_ellipse_compensation(
        compensation,
        adjusted_stations=adjusted_stations,
        dominant_stations=compensation["dominant_stations"],
    )

    with st.expander("Rim compensation plot & stations", expanded=False):
        st.plotly_chart(fig, use_container_width=True)
        step_label("Largest corrections")
        st.dataframe(
            station_table_rows(dominant_stations_by_distance),
            use_container_width=True,
            hide_index=True,
        )

        with st.expander("All angular stations", expanded=False):
            st.dataframe(
                station_table_rows(adjusted_stations),
                use_container_width=True,
                hide_index=True,
            )


def main():
    """Operator-first calculator: L/R to set, engineering details collapsed."""
    st.set_page_config(
        page_title="Correct adjustment",
        page_icon=PAGE_ICON,
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    apply_theme()
    initialize_state()

    banner = st.session_state.pop("_correct_job_banner", None)
    if banner:
        st.success(banner)

    setup = st.session_state.setup
    render_header()
    render_sidebar_inputs(setup)

    step_label("Job")
    render_job_inputs_main(setup)

    update_setup_from_inputs(setup)
    st.session_state.correct_target_radius_locked = True

    material = setup["material"]
    calculation, positions = calculate_model_state(setup_to_json(setup))
    loaded_radius = calculation["required_loaded_radius"]

    operator_lr = render_operator_do_this(setup, positions)

    with st.expander("Engineering details", expanded=False):
        render_calculator_comparison(setup, positions, operator_lr)
        render_results(calculation, positions, material["target_final_radius_in"])
        with st.expander("Machine geometry & diagram", expanded=False):
            render_geometry_summary(setup, positions)
            fig = plot_roll_former_geometry(
                setup,
                positions,
                loaded_radius,
                roller_phase=0.0,
            )
            st.pyplot(fig, use_container_width=True)
        render_ellipse_upload(loaded_radius)

    st.session_state.animation_running = False


if __name__ == "__main__":
    main()
