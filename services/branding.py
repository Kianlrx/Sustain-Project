import base64
from functools import lru_cache
from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "sustain_logo_svg.svg"


@lru_cache(maxsize=1)
def logo_data_uri():
    svg = LOGO_PATH.read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode()


# Colour tokens for the light and dark themes in .streamlit/config.toml.
# Page styles use them as var(--sustain-<name>). Each one is written as
# light-dark(), which picks the value for the colour scheme Streamlit sets on
# the app, so styles switch at once when a viewer changes the theme in the
# top-right menu (Streamlit does not rerun the script for that).
THEME_TOKENS = {
    "dark": {
        "bg": "#141415",
        "surface": "#1c1c1e",
        "raised": "#232325",
        "hover": "#232325",
        "hover-strong": "#2a2a2d",
        "border": "rgba(237, 237, 237, .08)",
        "border-strong": "rgba(237, 237, 237, .16)",
        "grid": "rgba(237, 237, 237, .06)",
        "text": "#ededed",
        "secondary": "#a1a1a6",
        "muted": "#8a8a90",
        "sidebar": "#0f0f10",
        "sidebar-hover": "#19191b",
        "sidebar-active": "#232325",
        "highlight-color": "rgba(255, 255, 255, .04)",
        "dock": "#19191b",
        "shadow-color": "rgba(0, 0, 0, .3)",
        "positive": "#4cc38a",
        "negative": "#e5484d",
        "negative-soft": "rgba(229, 72, 77, .12)",
        "caution": "#e2a640",
        "info": "#5aa9d6",
    },
    "light": {
        "bg": "#fafafa",
        "surface": "#ffffff",
        "raised": "#f4f4f5",
        "hover": "#f4f4f5",
        "hover-strong": "#ebebec",
        "border": "rgba(23, 23, 23, .08)",
        "border-strong": "rgba(23, 23, 23, .16)",
        "grid": "rgba(23, 23, 23, .06)",
        "text": "#171717",
        "secondary": "#525252",
        "muted": "#737373",
        "sidebar": "#f4f4f5",
        "sidebar-hover": "#ebebec",
        "sidebar-active": "#ffffff",
        "highlight-color": "rgba(0, 0, 0, .05)",
        "dock": "#ffffff",
        "shadow-color": "rgba(0, 0, 0, .08)",
        "positive": "#16a34a",
        "negative": "#dc2626",
        "negative-soft": "rgba(220, 38, 38, .08)",
        "caution": "#b45309",
        "info": "#2b6f99",
    },
}
SHARED_TOKENS = {
    "accent": "#dc2a46",
    "accent-hover": "#c4223c",
    "mono": '"JetBrains Mono", ui-monospace, SFMono-Regular, Consolas, monospace',
}


def theme_tokens_css():
    light, dark = THEME_TOKENS["light"], THEME_TOKENS["dark"]
    tokens = {name: f"light-dark({light[name]}, {dark[name]})" for name in dark}
    tokens.update(SHARED_TOKENS)
    tokens["highlight"] = "0 1px 1px var(--sustain-highlight-color)"
    tokens["popover-shadow"] = "0 8px 24px var(--sustain-shadow-color)"
    lines = "".join(f"--sustain-{name}: {value};" for name, value in tokens.items())
    return f":root {{ {lines} }}"
