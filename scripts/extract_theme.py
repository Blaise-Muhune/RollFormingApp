"""One-off helper to rebuild springback/theme.css from ui.py (dev utility)."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "springback" / "ui.py"
OUT = ROOT / "springback" / "theme.css"

INSPECT = """
/* --- Inspect page (wide layout) --- */
body[data-page="inspect"] .block-container,
body[data-page="inspect"] [data-testid="stMainBlockContainer"] {
    max-width: 1500px !important;
}

body[data-page="inspect"] div[data-testid="stMetric"] {
    background-color: #FFFFFF !important;
    border: 2px solid #111111 !important;
    border-radius: 0 !important;
    padding: 14px !important;
    box-shadow: none !important;
}

body[data-page="inspect"] div[data-testid="stMetricLabel"] {
    font-family: "JetBrains Mono", Consolas, monospace !important;
    font-size: 0.68rem !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: #5c5c58 !important;
}

body[data-page="inspect"] div[data-testid="stMetricValue"] {
    font-family: "Archivo Black", Arial, sans-serif !important;
    font-size: 1.35rem !important;
    line-height: 1.05 !important;
    letter-spacing: -0.03em !important;
}

body[data-page="inspect"] .info-card {
    background-color: #FFFFFF;
    border: 2px solid #111111;
    padding: 18px;
    border-radius: 0;
    margin-bottom: 16px;
}

body[data-page="inspect"] .small-note {
    color: #5c5c58;
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 0.78rem;
    letter-spacing: 0.04em;
}

@media (max-width: 768px) {
    body[data-page="inspect"] div[data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
    }

    body[data-page="inspect"] .info-card {
        padding: 14px !important;
    }
}
"""

text = UI.read_text(encoding="utf-8")
match = re.search(r"<style>\n(.*)\n        </style>", text, re.DOTALL)
if not match:
    raise SystemExit("Could not find <style> block in ui.py")

lines = []
for line in match.group(1).splitlines():
    lines.append(line[8:] if line.startswith("        ") else line)

nav_hide = """
/* --- Hide default Streamlit sidebar page list --- */
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
    display: none !important;
}
"""

font = '@import url("https://fonts.googleapis.com/css2?family=Archivo+Black&family=JetBrains+Mono:wght@500;700&display=swap");\n\n'
OUT.write_text(font + nav_hide + "\n".join(lines) + INSPECT + "\n", encoding="utf-8")
print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
