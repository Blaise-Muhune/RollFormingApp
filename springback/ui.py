import streamlit as st


def apply_theme():
    """Force a light shop-floor look (overrides Streamlit dark / system theme)."""
    st.markdown(
        """
        <style>
        :root {
            --panel: #ffffff !important;
            --line: #e2e8f0 !important;
            --blue: #1d4ed8 !important;
            --green: #15803d !important;
            --ink: #0f172a !important;
            --muted: #64748b !important;
        }

        html, body, .stApp, [data-testid="stAppViewContainer"],
        [data-testid="stAppViewBlockContainer"],
        .main, .block-container {
            background: #f8fafc !important;
            background-color: #f8fafc !important;
            color: #0f172a !important;
        }

        .stApp {
            background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%) !important;
        }

        [data-testid="stHeader"] {
            background: #f8fafc !important;
        }

        /* Keep nav buttons below the Streamlit top chrome (they were clipping). */
        section.main > div,
        [data-testid="stMain"] > div {
            overflow: visible !important;
        }

        .block-container,
        [data-testid="stMainBlockContainer"] {
            max-width: 720px !important;
            padding-top: 3.5rem !important;
            padding-bottom: 2rem !important;
            overflow: visible !important;
        }

        div[data-testid="stHorizontalBlock"] {
            overflow: visible !important;
            align-items: stretch !important;
        }

        div[data-testid="stHorizontalBlock"] .stButton {
            overflow: visible !important;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius: 10px !important;
            border: 1px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #0f172a !important;
            min-height: 2.75rem !important;
            height: auto !important;
            font-weight: 650 !important;
            overflow: visible !important;
            white-space: normal !important;
            line-height: 1.25 !important;
            padding-top: 0.55rem !important;
            padding-bottom: 0.55rem !important;
        }

        /* Secondary / default: dark ink on white */
        .stButton > button[kind="secondary"],
        .stButton > button[data-testid="baseButton-secondary"],
        .stButton > button[data-testid="stBaseButton-secondary"],
        .stDownloadButton > button {
            background: #ffffff !important;
            border-color: #cbd5e1 !important;
            color: #0f172a !important;
        }

        .stButton > button[kind="secondary"] *,
        .stButton > button[data-testid="baseButton-secondary"] *,
        .stButton > button[data-testid="stBaseButton-secondary"] *,
        .stDownloadButton > button * {
            color: #0f172a !important;
        }

        .stButton > button[kind="secondary"]:hover,
        .stButton > button[data-testid="baseButton-secondary"]:hover,
        .stButton > button[data-testid="stBaseButton-secondary"]:hover,
        .stDownloadButton > button:hover {
            border-color: #93c5fd !important;
            background: #f8fbff !important;
            color: #0f172a !important;
        }

        .stButton > button[kind="secondary"]:hover *,
        .stButton > button[data-testid="baseButton-secondary"]:hover *,
        .stButton > button[data-testid="stBaseButton-secondary"]:hover *,
        .stDownloadButton > button:hover * {
            color: #0f172a !important;
        }

        /* Primary: white label on blue */
        .stButton > button[kind="primary"],
        .stButton > button[data-testid="baseButton-primary"],
        .stButton > button[data-testid="stBaseButton-primary"],
        button[data-testid="stBaseButton-primary"],
        .stButton > button[kind="primary"]:hover,
        .stButton > button[data-testid="baseButton-primary"]:hover,
        .stButton > button[data-testid="stBaseButton-primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {
            background: #1d4ed8 !important;
            border-color: #1e40af !important;
            color: #ffffff !important;
        }

        .stButton > button[kind="primary"] *,
        .stButton > button[data-testid="baseButton-primary"] *,
        .stButton > button[data-testid="stBaseButton-primary"] *,
        button[data-testid="stBaseButton-primary"] *,
        .stButton > button[kind="primary"]:hover *,
        .stButton > button[data-testid="baseButton-primary"]:hover *,
        .stButton > button[data-testid="stBaseButton-primary"]:hover *,
        button[data-testid="stBaseButton-primary"]:hover * {
            color: #ffffff !important;
        }

        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            background: transparent !important;
        }

        [data-testid="stSidebar"] {
            background: #ffffff !important;
            border-right: 1px solid #e2e8f0 !important;
        }

        [data-testid="stSidebar"] [data-testid="stExpander"] {
            border: 1px solid #e2e8f0 !important;
            border-radius: 10px !important;
            background: #f8fafc !important;
        }

        h1, h2, h3, h4, p, label, li, .stMarkdown, .stCaption,
        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"] {
            color: #0f172a !important;
        }

        .stCaption, [data-testid="stCaptionContainer"] {
            color: #64748b !important;
        }

        .app-title {
            font-size: 1.65rem !important;
            font-weight: 750 !important;
            line-height: 1.15 !important;
            margin: 0.15rem 0 0.35rem !important;
            color: #0f172a !important;
            letter-spacing: -0.02em !important;
        }

        .app-sub {
            color: #64748b !important;
            font-size: 1.02rem !important;
            margin: 0 0 1rem 0 !important;
        }

        .do-card {
            border: 1px solid #e2e8f0 !important;
            border-radius: 16px !important;
            background: #ffffff !important;
            padding: 1.15rem 1.25rem 1.25rem !important;
            margin: 0.5rem 0 1rem 0 !important;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06) !important;
            color: #0f172a !important;
        }

        .do-card h2 {
            margin: 0 0 0.35rem 0 !important;
            font-size: 1.35rem !important;
            color: #0f172a !important;
        }

        .do-meta {
            color: #64748b !important;
            font-size: 0.98rem !important;
            margin: 0 0 1rem 0 !important;
        }

        .axis-grid {
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 0.75rem !important;
            margin: 0 0 1rem 0 !important;
        }

        .axis-tile {
            border-radius: 14px !important;
            padding: 1rem 1.05rem !important;
            background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%) !important;
            border: 1px solid #93c5fd !important;
        }

        .axis-tile.r {
            background: linear-gradient(180deg, #f0fdf4 0%, #dcfce7 100%) !important;
            border-color: #86efac !important;
        }

        .axis-tile .label {
            font-size: 0.85rem !important;
            font-weight: 650 !important;
            color: #64748b !important;
            text-transform: uppercase !important;
            letter-spacing: 0.04em !important;
        }

        .axis-tile .value {
            font-size: 2.15rem !important;
            font-weight: 800 !important;
            line-height: 1.1 !important;
            color: #0f172a !important;
            margin-top: 0.25rem !important;
        }

        .do-steps {
            font-size: 1.08rem !important;
            line-height: 1.55 !important;
            color: #0f172a !important;
            margin: 0 !important;
            padding-left: 1.15rem !important;
        }

        .do-steps li { margin: 0.35rem 0 !important; color: #0f172a !important; }

        .panel-title, .panel-title-purple {
            color: #1d4ed8 !important;
            font-size: 0.9rem !important;
            font-weight: 750 !important;
            text-transform: uppercase !important;
            margin-bottom: 0.8rem !important;
        }

        .panel-title-purple { color: #6d28d9 !important; }

        .metric-big { color: #0f172a !important; font-size: 1.8rem !important; font-weight: 800 !important; }
        .metric-label { color: #64748b !important; }
        .metric-value { color: #0f172a !important; font-weight: 650 !important; }
        .ok-value { color: #15803d !important; font-weight: 800 !important; }
        .muted-note { color: #64748b !important; }
        .travel-value { color: #15803d !important; font-weight: 750 !important; }

        div[data-testid="stVerticalBlock"] > div:has(> .panel-anchor) {
            border: 1px solid #e2e8f0 !important;
            border-radius: 12px !important;
            background: #ffffff !important;
            padding: 1rem !important;
            margin-bottom: 0.75rem !important;
        }

        [data-testid="stAlert"] {
            background: #ffffff !important;
        }

        [data-testid="stExpander"] {
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 10px !important;
        }

        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] p,
        [data-testid="stExpander"] span {
            color: #0f172a !important;
        }

        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextInput"] input,
        div[data-baseweb="select"] > div {
            background-color: #ffffff !important;
            color: #0f172a !important;
            border-color: #cbd5e1 !important;
        }

        hr { border-color: #e2e8f0 !important; }

        /* --- Check roll operator screen --- */
        .verdict-pass, .verdict-fail {
            border-radius: 16px;
            padding: 1.25rem 1.35rem;
            margin: 0.5rem 0 1rem 0;
            text-align: center;
        }
        .verdict-pass { background: #14532d; color: #ecfdf5; }
        .verdict-fail { background: #7f1d1d; color: #fef2f2; }
        .verdict-borderline { background: #78350f; color: #fffbeb; }
        .verdict-pass h2, .verdict-fail h2, .verdict-borderline h2 {
            margin: 0;
            font-size: 1.75rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }
        .verdict-pass p, .verdict-fail p, .verdict-borderline p {
            margin: 0.45rem 0 0 0;
            font-size: 1.05rem;
            opacity: 0.95;
        }

        .step-label {
            font-size: 0.78rem !important;
            font-weight: 750 !important;
            letter-spacing: 0.06em !important;
            text-transform: uppercase !important;
            color: #64748b !important;
            margin: 1rem 0 0.35rem 0 !important;
        }

        .lr-hero {
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 0.75rem !important;
            margin: 0.5rem 0 0.75rem 0 !important;
        }
        .lr-hero-tile {
            border-radius: 14px !important;
            padding: 1rem 1.1rem !important;
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            text-align: center !important;
        }
        .lr-hero-tile.highlight {
            border: 2px solid #1d4ed8 !important;
            background: #eff6ff !important;
        }
        .lr-hero-tile .lab {
            font-size: 0.82rem !important;
            font-weight: 700 !important;
            color: #64748b !important;
            text-transform: uppercase !important;
            letter-spacing: 0.05em !important;
        }
        .lr-hero-tile .val {
            font-size: 2.25rem !important;
            font-weight: 800 !important;
            color: #0f172a !important;
            line-height: 1.1 !important;
            margin-top: 0.2rem !important;
        }
        .lr-hero-tile.highlight .val { color: #1e40af !important; }

        .action-card {
            border-radius: 14px !important;
            padding: 1rem 1.15rem !important;
            margin: 0.5rem 0 1rem 0 !important;
            background: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
        }
        .action-card.primary {
            border: 2px solid #1d4ed8 !important;
            background: #eff6ff !important;
        }
        .action-card.warn {
            border: 2px solid #f59e0b !important;
            background: #fffbeb !important;
        }
        .action-card h3 {
            margin: 0 0 0.5rem 0 !important;
            font-size: 1.15rem !important;
            color: #0f172a !important;
        }
        .action-steps {
            margin: 0 !important;
            padding-left: 1.15rem !important;
            font-size: 1.08rem !important;
            line-height: 1.5 !important;
            color: #0f172a !important;
        }
        .action-steps li { margin: 0.3rem 0 !important; }

        .badge {
            display: inline-block;
            padding: 0.15rem 0.55rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            vertical-align: middle;
            margin-left: 0.35rem;
        }
        .badge-verified { background: #dcfce7; color: #166534; }
        .badge-estimate { background: #e2e8f0; color: #475569; }
        .badge-fill { background: #dbeafe; color: #1d4ed8; }

        .section-move {
            font-size: 1.12rem !important;
            line-height: 1.45 !important;
            margin: 0.5rem 0 !important;
            padding: 0.75rem 0.9rem !important;
            border-radius: 10px !important;
            background: #ffffff !important;
            border: 1px solid #fecaca !important;
            color: #0f172a !important;
        }
        .section-move strong { color: #991b1b; }

        div[data-testid="stFileUploader"] section {
            min-height: 3.25rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def panel_start(title, purple=False):
    """Create the visual start of a panel used by the main page layout."""
    title_class = "panel-title-purple" if purple else "panel-title"
    st.markdown('<div class="panel-anchor"></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="{title_class}">{title}</div>', unsafe_allow_html=True)


def metric_row(label, value):
    """Render a two-column label/value row with shared app styling."""
    st.markdown(
        f"""
        <div class="metric-row">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def big_metric(label, value):
    """Render the large headline metric used in result panels."""
    st.markdown(
        f"""
        <div class="metric-label">{label}</div>
        <div class="metric-big">{value}</div>
        """,
        unsafe_allow_html=True,
    )


def number_input(label, value, min_value=None, max_value=None, step=0.1, fmt="%.3f", key=None):
    """Wrapper that normalizes numeric defaults before passing them to Streamlit."""
    return st.number_input(
        label,
        value=float(value),
        min_value=min_value,
        max_value=max_value,
        step=step,
        format=fmt,
        key=key,
    )
