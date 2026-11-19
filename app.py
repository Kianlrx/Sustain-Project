import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import streamlit as st
from PIL import Image

from services import db
from views.auth import render_login_page, render_logout_button
from views.onboarding import render_onboarding_page
from views.dashboard import render_dashboard_page
from views.diary import render_diary_page
from views.settings import render_settings_page

st.set_page_config(
    page_title="Sustain", layout="wide", initial_sidebar_state="expanded"
)

# Menu icons copied from the design prototype (24x24 stroke icons).
# They are drawn with a CSS mask so they take the button's text colour.
_ICON_PATHS = {
    "dashboard": (
        '<rect x="3" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1.5"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1.5"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1.5"/>'
    ),
    "diary": (
        '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>'
        '<line x1="16" y1="2" x2="16" y2="6"/>'
        '<line x1="8" y1="2" x2="8" y2="6"/>'
        '<line x1="3" y1="10" x2="21" y2="10"/>'
    ),
    "weight": (
        '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>'
        '<polyline points="16 7 22 7 22 13"/>'
    ),
    "settings": (
        '<circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 '
        "0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 "
        "2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 "
        "0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 "
        "0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 "
        "1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 "
        "0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 "
        "0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 "
        "1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 "
        "0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 "
        '2h-.09a1.65 1.65 0 0 0-1.51 1z"/>'
    ),
    "logout": (
        '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
        '<polyline points="16 17 21 12 16 7"/>'
        '<line x1="21" y1="12" x2="9" y2="12"/>'
    ),
}

# (page, label, button key) for the main menu
NAV_ITEMS = (
    ("Dashboard", "Dashboard", "nav_dashboard"),
    ("Diary", "Diary", "nav_diary"),
    ("Weight", "Weight", "nav_weight"),
)
NAV_KEYS = {
    "Dashboard": "nav_dashboard",
    "Diary": "nav_diary",
    "Weight": "nav_weight",
    "Settings": "nav_settings",
}
# button key -> icon name
BUTTON_ICONS = {
    "nav_dashboard": "dashboard",
    "nav_diary": "diary",
    "nav_weight": "weight",
    "nav_settings": "settings",
    "sidebar_logout_button": "logout",
}
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "sustain_logo.png"


def _icon_url(name):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="black" stroke-width="1.9" stroke-linecap="round" '
        f'stroke-linejoin="round">{_ICON_PATHS[name]}</svg>'
    )
    return f'url("data:image/svg+xml,{quote(svg)}")'


@lru_cache(maxsize=1)
def _logo_data_uri():
    # The source PNG is ~650KB; embed a 64px copy (2x for a sharp 32px logo).
    with Image.open(LOGO_PATH) as image:
        image = image.convert("RGBA")
        image.thumbnail((64, 64), Image.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def _buttons(suffix=""):
    return ",\n    ".join(f".st-key-{key} button{suffix}" for key in BUTTON_ICONS)


ICON_STYLES = "\n".join(
    f"    .st-key-{key} button::before {{ "
    f"-webkit-mask-image: {_icon_url(icon)}; mask-image: {_icon_url(icon)}; }}"
    for key, icon in BUTTON_ICONS.items()
)

SIDEBAR_STYLES = f"""
<style>
    /* ---- Fixed, non-collapsible 240px sidebar (desktop) ----
       On phones Streamlit hides the sidebar off-canvas, so its open/close
       controls stay available there or navigation would be unreachable. */
    @media (min-width: 768px) {{
        [data-testid="stSidebarHeader"],
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stExpandSidebarButton"] {{
            display: none !important;
        }}
        section[data-testid="stSidebar"] {{
            width: 240px !important;
            min-width: 240px !important;
            max-width: 240px !important;
            transform: none !important;
        }}
        /* The drag-to-resize handle is the only child without a test id. */
        section[data-testid="stSidebar"] > div:not([data-testid]) {{
            display: none !important;
        }}
    }}
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div:first-child {{
        background: #131720;
    }}
    section[data-testid="stSidebar"] {{
        border-right: 1px solid #222733;
    }}

    /* ---- Full-height column so Settings / Log out sit at the bottom ---- */
    [data-testid="stSidebarContent"] {{
        display: flex;
        flex-direction: column;
        height: 100%;
        padding: 0 !important;
        scrollbar-gutter: auto !important;
    }}
    /* Streamlit pulls markdown blocks up by 1rem; undo that in the sidebar. */
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
        margin-bottom: 0 !important;
    }}
    [data-testid="stSidebarUserContent"] {{
        flex: 1 1 auto;
        display: flex;
        flex-direction: column;
        padding: 0 !important;
    }}
    [data-testid="stSidebarUserContent"] div:has(.st-key-sidebar_footer) {{
        flex: 1 1 auto;
        display: flex;
        flex-direction: column;
    }}
    [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {{
        gap: 0;
    }}
    /* Streamlit gives keyed containers flex: 1 1 0%, which would stretch
       them; keep each section at its natural height instead. */
    .st-key-sidebar_brand,
    .st-key-sidebar_nav,
    .st-key-sidebar_footer {{
        flex: 0 0 auto !important;
    }}
    .st-key-sidebar_footer {{
        margin-top: auto !important;
    }}

    /* ---- Brand header: 60px tall, 16px side padding, 32px logo ---- */
    .st-key-sidebar_brand {{
        height: 60px !important;
        min-height: 60px;
        padding: 0 16px;
        border-bottom: 1px solid rgba(34, 39, 51, .8);
        justify-content: center;
    }}
    .sustain-brand {{
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .sustain-brand img {{
        width: 32px;
        height: 32px;
        flex-shrink: 0;
        border-radius: 9px;
    }}
    .sustain-brand span {{
        color: #f8fafc;
        font-size: 15px;
        font-weight: 700;
        line-height: 1;
        letter-spacing: -.025em;
    }}

    /* ---- Menu section: 16px top margin, 10px side padding, 4px gaps ---- */
    .st-key-sidebar_nav {{
        margin-top: 16px !important;
        padding: 0 10px;
    }}
    .st-key-sidebar_nav,
    .st-key-sidebar_nav [data-testid="stVerticalBlock"],
    .st-key-sidebar_footer,
    .st-key-sidebar_footer [data-testid="stVerticalBlock"] {{
        gap: 4px !important;
    }}
    .sustain-menu-label {{
        margin: 0 0 4px !important;
        padding: 0 10px;
        color: #5c6677;
        font-size: 10px !important;
        font-weight: 600;
        line-height: 15px;
        letter-spacing: .08em;
        text-transform: uppercase;
    }}

    /* ---- Footer: 1px divider, 14px vertical / 10px side padding ---- */
    .st-key-sidebar_footer {{
        padding: 14px 10px;
        border-top: 1px solid #222733;
    }}

    /* ---- Nav buttons: 40px tall, 12px padding, 18px icon, 12px gap ---- */
    {_buttons()} {{
        position: relative;
        display: flex;
        align-items: center;
        justify-content: flex-start;
        gap: 12px;
        width: 100%;
        height: 40px;
        min-height: 40px;
        padding: 0 12px;
        border: 0;
        border-radius: 10px;
        background: transparent;
        color: #8b949e;
        box-shadow: none;
        transition: background-color .15s, color .15s;
    }}
    {_buttons("::before")} {{
        content: "";
        width: 18px;
        height: 18px;
        flex-shrink: 0;
        background-color: currentColor;
        -webkit-mask: no-repeat center / 18px 18px;
        mask: no-repeat center / 18px 18px;
    }}
{ICON_STYLES}
    {_buttons(" > div")} {{
        justify-content: flex-start;
    }}
    {_buttons(" p")} {{
        margin: 0;
        font-size: 13.5px;
        font-weight: 500;
        line-height: 1;
        white-space: nowrap;
    }}
    {_buttons(":hover")} {{
        border: 0;
        background: #1a202e;
        color: #f8fafc;
    }}
    {_buttons(":focus:not(:active)")} {{
        border: 0;
        box-shadow: none;
    }}
    .st-key-sidebar_logout_button button:hover {{
        background: rgba(255, 75, 75, .1);
        color: #ff4b4b;
    }}
</style>
"""


def _active_nav_styles(key):
    # Highlighted row: lighter background, white text, red icon and a
    # 3px x 16px red pill 4px from the left edge, as in the prototype.
    button = f".st-key-{key} button"
    return f"""
    <style>
        {button}, {button}:hover, {button}:focus:not(:active) {{
            background: #1e2433;
            color: #f8fafc;
        }}
        {button} p {{ font-weight: 600; }}
        {button}::before {{ background-color: #ff4b4b; }}
        {button}::after {{
            content: "";
            position: absolute;
            top: 50%;
            left: 4px;
            width: 3px;
            height: 16px;
            border-radius: 999px;
            background: #ff4b4b;
            transform: translateY(-50%);
        }}
    </style>
    """


def _go_to(page):
    st.session_state.main_navigation = page
    st.rerun()


def render_sidebar():
    st.markdown(SIDEBAR_STYLES, unsafe_allow_html=True)
    active_key = NAV_KEYS.get(st.session_state.main_navigation)
    if active_key:
        st.markdown(_active_nav_styles(active_key), unsafe_allow_html=True)

    # Use st.button inside `with st.sidebar:` rather than st.sidebar.button:
    # st.sidebar.button ignores the surrounding container, so the Settings and
    # Log out buttons would not land in the bottom-pinned footer.
    with st.sidebar:
        with st.container(key="sidebar_brand"):
            st.markdown(
                f'<div class="sustain-brand"><img src="{_logo_data_uri()}" '
                'alt="Sustain logo"><span>Sustain</span></div>',
                unsafe_allow_html=True,
            )

        with st.container(key="sidebar_nav"):
            st.markdown(
                '<p class="sustain-menu-label">Menu</p>', unsafe_allow_html=True
            )
            for page, label, key in NAV_ITEMS:
                if st.button(label, key=key, use_container_width=True):
                    _go_to(page)

        with st.container(key="sidebar_footer"):
            if st.button("Settings", key="nav_settings", use_container_width=True):
                _go_to("Settings")
            render_logout_button()


db.init_db()
st.session_state.setdefault("user", None)

user = st.session_state.user
if user is None:
    render_login_page()
else:
    if not user["onboarding_complete"]:
        render_onboarding_page()
    else:
        if "navigation_target" in st.session_state:
            st.session_state["main_navigation"] = st.session_state.pop(
                "navigation_target"
            )
        st.session_state.setdefault("main_navigation", "Dashboard")
        if st.session_state.main_navigation not in NAV_KEYS:
            st.session_state.main_navigation = "Dashboard"
        render_sidebar()
        page = st.session_state.main_navigation
        if page == "Dashboard":
            render_dashboard_page()
        elif page == "Diary":
            render_diary_page()
        elif page == "Weight":
            render_dashboard_page()
        else:
            render_settings_page()
