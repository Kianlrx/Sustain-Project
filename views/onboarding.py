# Onboarding questionnaire: a guided 3-step flow (Body Metrics, Lifestyle &
# Goals, Allergies & Diet) with a live TDEE preview docked at the bottom.
import re
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from html import escape
from urllib.parse import quote

import streamlit as st
from models.profile import DIETARY_PREFERENCES, UserProfile
from services import db, targets as targets_service
from services.branding import logo_data_uri
from services.tdee_engine import (
    DEFAULT_OCCUPATION_DAYS_PER_WEEK,
    DEFAULT_OCCUPATION_HOURS_PER_WORKDAY,
    OCCUPATION_METS,
    TRAINING_TYPE_METS,
    calculate_tdee,
)

STEPS = (
    ("Body Metrics", "Age, sex, height & weight"),
    ("Lifestyle & Goals", "Training, steps & skill"),
    ("Allergies & Diet", "Exclusions & diet style"),
)
MAX_SESSIONS_PER_WEEK = 14

GOALS = {
    "Fat Loss": ("20% deficit", "Steady, sustainable fat loss while preserving lean muscle."),
    "Muscle Gain": ("10% surplus", "A controlled surplus to fuel muscle growth and strength."),
    "Recomposition": ("Maintenance", "Lose fat and build muscle at maintenance calories."),
    "GLP-1 Support": ("15% deficit", "Protein-first nutrition to protect lean mass on reduced appetite."),
}
OCCUPATIONS = {
    "Desk Job": ("Sedentary", "Mostly seated office, study or remote computer work."),
    "Standing": ("Standing", "Standing with light movement: teaching, retail, errands."),
    "Active Work": ("Active Work", "Frequent walking: hospitality, nursing, floor work."),
    "Heavy Labor": ("Heavy Labor", "Heavy lifting, construction or demanding manual work."),
}
SKILLS = {
    "Beginner": "Simple 15–25 min recipes with minimal prep.",
    "Intermediate": "Comfortable with multiple burners, marinades and spices.",
    "Advanced": "Enjoys scratch sauces, complex techniques and batch prep.",
}
TRAINING_LABELS = {
    "Weight training (low intensity)": "Weight Training",
    "Endurance training (medium intensity)": "Endurance",
    "Interval training (high intensity)": "Interval Training",
}
STEP_OPTIONS = (
    "Less than 2,500",
    "2,500 - 5,000",
    "5,000 - 7,500",
    "7,500 - 10,000",
    "More than 10,000",
    "Custom amount",
)
ALLERGEN_OPTIONS = (
    "Peanuts", "Tree Nuts", "Dairy", "Eggs", "Gluten",
    "Shellfish", "Soy", "Fish", "Sesame", "Pork",
)

# Every answer lives in session state under these keys. Re-assigning them at
# the start of each run keeps answers from steps that are not on screen.
DEFAULTS = {
    "ob_step": 1,
    "ob_errors": [],
    "measurement_units": "Metric",
    "measurement_units_previous": "Metric",
    "ob_age": 25,
    "ob_sex": "Male",
    "ob_sex__last": "Male",
    "height_cm": "175",
    "weight_kg": "75",
    "ob_use_body_fat": False,
    "body_fat_pct_input": "",
    "fitness_goal": "Fat Loss",
    "training_sessions_per_week": 3,
    "training_type": next(iter(TRAINING_TYPE_METS)),
    "training_duration_minutes": 60,
    "occupation_movement": "Desk Job",
    "daily_steps_option": STEP_OPTIONS[0],
    "daily_steps_option__last": STEP_OPTIONS[0],
    "custom_daily_steps_input": "",
    "cooking_skill": "Beginner",
    "allergens": [],
    "other_allergen": "",
    "dietary_preferences": [],
}

ONBOARDING_CSS = """
<style>
    [data-testid="stAppViewContainer"] { background:#0e1117; color:#f8fafc; }
    [data-testid="stHeader"] { background:rgba(14,17,23,.94); }
    .block-container { max-width:860px; padding:4.5rem 1.25rem 9rem; }
    .ob-brand { display:flex; align-items:center; gap:.75rem; flex-wrap:wrap; }
    .ob-brand img { width:40px; height:40px; border-radius:11px; }
    .ob-wordmark { font-size:1.25rem; font-weight:700; letter-spacing:-.025em; color:#f8fafc; }
    .ob-status { display:inline-flex; align-items:center; gap:.4rem; padding:.25rem .7rem;
        border-radius:999px; background:rgba(255,75,75,.14); border:1px solid rgba(255,75,75,.32);
        color:#ff8585; font-size:.72rem; font-weight:600; }
    .ob-status i { width:6px; height:6px; border-radius:50%; background:#ff4b4b; }
    .ob-title { margin:.9rem 0 .3rem; font-size:1.75rem; font-weight:700; letter-spacing:-.03em;
        line-height:1.2; color:#f8fafc; }
    .ob-sub { color:#94a3b8; font-size:.9rem; line-height:1.55; margin-bottom:1.3rem; }

    .ob-stepper { padding:1rem 1.25rem; border:1px solid #262c3a; border-radius:14px;
        background:#161b26; }
    .ob-tabs { display:grid; grid-template-columns:repeat(3,1fr); gap:.6rem; margin-bottom:.75rem; }
    .ob-tab { display:flex; align-items:center; gap:.6rem; padding:.6rem .75rem; border-radius:10px;
        background:#1e222d; border:1px solid #2d3242; }
    .ob-tab.active { border-color:#ff4b4b; background:rgba(255,75,75,.1); }
    .ob-tab.done { border-color:rgba(52,211,153,.4); }
    .ob-num { flex-shrink:0; width:24px; height:24px; display:grid; place-items:center;
        border-radius:50%; background:#161b26; border:1px solid #3c4459;
        color:#94a3b8; font-size:.72rem; font-weight:700; }
    .ob-tab.active .ob-num { background:#ff4b4b; border-color:#ff4b4b; color:#fff; }
    .ob-tab.done .ob-num { background:#34d399; border-color:#34d399; color:#0e1117; }
    .ob-tab-title { font-size:.8rem; font-weight:600; color:#f8fafc; }
    .ob-tab-sub { font-size:.7rem; color:#64748b; }
    .ob-track { height:5px; border-radius:999px; background:#1e222d; overflow:hidden; }
    .ob-fill { height:100%; border-radius:999px; background:linear-gradient(90deg,#ff4b4b,#ff7a59); }
    @media (max-width:640px) { .ob-tabs { grid-template-columns:1fr; } }

    .st-key-ob_card { padding:1.35rem; border:1px solid #262c3a; border-radius:14px;
        background:#161b26; }
    .ob-card-head { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap;
        gap:.75rem; padding-bottom:1rem; border-bottom:1px solid #262c3a; }
    .ob-card-title { display:flex; align-items:center; gap:.7rem; }
    .ob-card-title h2 { margin:0; padding:0; font-size:1.05rem; font-weight:700;
        letter-spacing:-.015em; color:#f8fafc; }
    .ob-icon { width:34px; height:34px; display:grid; place-items:center; border-radius:9px;
        background:#1e222d; border:1px solid #2d3242; }
    .ob-icon img { width:18px; height:18px; }
    .ob-tip { width:17px; height:17px; display:inline-grid; place-items:center; border-radius:50%;
        background:#1e222d; border:1px solid #3c4459; color:#94a3b8; font-size:.65rem;
        font-weight:700; cursor:help; }
    .ob-pill { display:inline-flex; align-items:center; padding:.25rem .7rem; border-radius:999px;
        font-size:.72rem; font-weight:600; border:1px solid; }
    .ob-pill.green { color:#34d399; background:rgba(52,211,153,.14); border-color:rgba(52,211,153,.32); }
    .ob-pill.amber { color:#fbbf24; background:rgba(251,191,36,.14); border-color:rgba(251,191,36,.34); }
    .ob-pill.blue { color:#38bdf8; background:rgba(56,189,248,.14); border-color:rgba(56,189,248,.38); }
    .ob-pill.grey { color:#94a3b8; background:#1e222d; border-color:#3c4459; }
    .ob-label { display:flex; justify-content:space-between; align-items:center; gap:.5rem;
        margin:.2rem 0 -.35rem; font-size:.82rem; font-weight:600; color:#f8fafc; }
    .ob-label span { color:#94a3b8; font-size:.75rem; font-weight:500; }
    .ob-label .hot { color:#ff4b4b; font-weight:700; }

    .st-key-ob_bodyfat { padding:.85rem 1rem; border:1px solid #2d3242; border-radius:12px;
        background:#1e222d; }

    /* Selected segmented controls and pills fill solid, as in the design */
    .st-key-ob_card button[data-testid="stBaseButton-segmented_controlActive"],
    .st-key-ob_card button[data-testid="stBaseButton-pillsActive"] {
        background:#ff4b4b; border-color:#ff4b4b; color:#fff; }
    .st-key-ob_card button[data-testid="stBaseButton-segmented_controlActive"] p,
    .st-key-ob_card button[data-testid="stBaseButton-pillsActive"] p { color:#fff; }
    .st-key-ob_diets button[data-testid="stBaseButton-pillsActive"] {
        background:rgba(52,211,153,.16); border-color:#34d399; }

    /* Radio groups rendered as selectable cards */
    [class*="st-key-ob_cards"] [data-testid="stElementContainer"],
    [class*="st-key-ob_cards"] [data-testid="stRadio"],
    [class*="st-key-ob_cards"] [data-testid="stRadio"] > div { width:100% !important; }
    [class*="st-key-ob_cards"] div[role="radiogroup"] { display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr)); gap:.6rem; width:100%; }
    .st-key-ob_cards3_skill div[role="radiogroup"] { grid-template-columns:repeat(3,minmax(0,1fr)); }
    @media (max-width:640px) {
        [class*="st-key-ob_cards"] div[role="radiogroup"] { grid-template-columns:1fr; } }
    [class*="st-key-ob_cards"] label[data-baseweb="radio"] { margin:0; padding:.75rem .9rem;
        border:1px solid #2d3242; border-radius:12px; background:#1e222d;
        align-items:flex-start; transition:border-color .15s, background .15s; }
    [class*="st-key-ob_cards"] label[data-baseweb="radio"]:hover { border-color:#3c4459;
        background:#252a38; }
    [class*="st-key-ob_cards"] label[data-baseweb="radio"]:has(input:checked) {
        border-color:#ff4b4b; background:rgba(255,75,75,.11);
        box-shadow:inset 0 0 0 1px rgba(255,75,75,.35); }
    [class*="st-key-ob_cards"] label[data-baseweb="radio"] > div:first-child { display:none; }
    [class*="st-key-ob_cards"] label[data-baseweb="radio"] p { font-size:.85rem; }
    [class*="st-key-ob_cards"] [data-testid="stCaptionContainer"] p { font-size:.74rem;
        color:#94a3b8; line-height:1.4; }

    /* Bottom dock with the live TDEE preview and navigation */
    .st-key-ob_dock { position:fixed; left:0; right:0; bottom:0; z-index:100;
        padding:.8rem max(1.25rem, calc((100vw - 860px) / 2 + 1.25rem));
        background:rgba(22,27,38,.95); backdrop-filter:blur(12px);
        border-top:1px solid #262c3a; box-shadow:0 -10px 30px rgba(0,0,0,.48); }
    .ob-preview { display:flex; flex-wrap:wrap; align-items:center; gap:1rem; }
    .ob-metric { display:flex; flex-direction:column; }
    .ob-metric small { color:#64748b; font-size:.62rem; font-weight:600; text-transform:uppercase;
        letter-spacing:.05em; }
    .ob-metric b { color:#f8fafc; font-size:.98rem; font-variant-numeric:tabular-nums; }
    .ob-divider { width:1px; height:28px; background:#2d3242; }
    .ob-macros { display:flex; gap:.4rem; flex-wrap:wrap; }
    .ob-macro { display:inline-flex; align-items:center; gap:.35rem; padding:.25rem .55rem;
        border-radius:8px; background:#1e222d; border:1px solid #2d3242; font-size:.75rem;
        font-weight:700; font-variant-numeric:tabular-nums; }
    .ob-macro i { width:8px; height:8px; border-radius:50%; }
    .st-key-ob_dock button { min-height:42px; border-radius:10px; font-weight:650; }
    .st-key-ob_back button { background:#1e222d; border:1px solid #2d3242; color:#f8fafc; }
    .st-key-ob_back button:hover { background:#252a38; border-color:#3c4459; color:#fff; }
    .st-key-ob_next button, .st-key-ob_submit button { background:#ff4b4b; border:0; color:#fff;
        box-shadow:0 4px 16px rgba(255,75,75,.34); }
    .st-key-ob_next button:hover, .st-key-ob_submit button:hover { background:#ff6161; color:#fff; }
</style>
"""

_ICONS = {
    "body": '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "lifestyle": (
        '<path d="M18 8h1a4 4 0 0 1 0 8h-1"/><path d="M6 8H5a4 4 0 0 0 0 8h1"/>'
        '<line x1="6" y1="12" x2="18" y2="12"/><line x1="8" y1="6" x2="8" y2="18"/>'
        '<line x1="16" y1="6" x2="16" y2="18"/>'
    ),
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
}


def _truncate_to_two_decimals(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _parse_measurement(
    value: str, label: str, minimum: float, maximum: float
) -> float:
    value = value.strip()
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value):
        raise ValueError(f"{label} must be a number.")

    try:
        measurement = _truncate_to_two_decimals(Decimal(value))
    except InvalidOperation as error:
        raise ValueError(f"{label} must be a number.") from error
    if not minimum <= measurement <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")

    return float(measurement)


def _convert_measurement_value(
    value: str, measurement: str, from_units: str, to_units: str
) -> str:
    numeric_value = Decimal(value.strip())
    if from_units == to_units:
        converted = numeric_value
    elif measurement == "height" and from_units == "Metric":
        converted = numeric_value / Decimal("2.54")
    elif measurement == "height" and from_units == "Imperial":
        converted = numeric_value * Decimal("2.54")
    elif measurement == "weight" and from_units == "Metric":
        converted = numeric_value * Decimal("2.2046226218")
    elif measurement == "weight" and from_units == "Imperial":
        converted = numeric_value / Decimal("2.2046226218")
    else:
        raise ValueError("Unsupported measurement unit conversion.")
    return format(_truncate_to_two_decimals(converted), "f")


def _convert_measurement_inputs() -> None:
    from_units = st.session_state.get("measurement_units_previous", "Metric")
    to_units = st.session_state["measurement_units"]
    if from_units == to_units:
        return

    try:
        converted_inputs = {
            key: _convert_measurement_value(
                st.session_state[key], measurement, from_units, to_units
            )
            for key, measurement in (
                ("height_cm", "height"),
                ("weight_kg", "weight"),
            )
        }
    except (InvalidOperation, ValueError):
        st.session_state["measurement_units"] = from_units
        st.session_state["unit_conversion_warning"] = (
            "Enter numeric height and weight values before changing units."
        )
        return

    st.session_state.update(converted_inputs)
    st.session_state["measurement_units_previous"] = to_units


def _normalize_allergens(selected: list[str], custom: str) -> list[str]:
    return [
        allergen for allergen in selected if allergen != "Other"
    ] + [value.strip() for value in custom.split(",") if value.strip()]


def _truncate_input_value(value: str) -> str:
    if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", value.strip()):
        return value
    try:
        truncated = format(_truncate_to_two_decimals(Decimal(value.strip())), "f")
        return truncated.rstrip("0").rstrip(".") if "." in truncated else truncated
    except InvalidOperation:
        return value


def _measurement_warning(
    value: str, label: str, minimum: float, maximum: float
) -> str | None:
    if not value.strip():
        return None
    try:
        _parse_measurement(value, label, minimum, maximum)
    except ValueError as error:
        return str(error)
    return None


def _parse_integer_input(
    value: str, label: str, minimum: int, maximum: int
) -> int:
    value = value.strip()
    if not re.fullmatch(r"[+-]?\d+", value):
        raise ValueError(f"{label} must be a whole number.")

    number = int(value)
    if not minimum <= number <= maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}.")
    return number


def _integer_input_warning(
    value: str, label: str, minimum: int, maximum: int
) -> str | None:
    if not value.strip():
        return None
    try:
        _parse_integer_input(value, label, minimum, maximum)
    except ValueError as error:
        return str(error)
    return None


def _normalize_measurement_input(key: str) -> None:
    st.session_state[key] = _truncate_input_value(st.session_state[key])


def _normalize_measurement_inputs() -> None:
    for key in ("height_cm", "weight_kg", "body_fat_pct_input"):
        st.session_state[key] = _truncate_input_value(
            st.session_state.get(key, "")
        )


def _measurement_ranges(units):
    """(height label, min, max, weight label, min, max) for the chosen units."""
    if units == "Imperial":
        return "Height (inches)", 39.38, 98.42, "Weight (lbs)", 66.15, 661.38
    return "Height (cm)", 100, 250, "Weight (kg)", 30, 300


def _collect_profile(state):
    """Build the saved profile from the answers in `state`.

    Returns (profile dict or None, {step number: [error messages]}).
    """
    errors = {1: [], 2: [], 3: []}
    units = state["measurement_units"]
    height_label, height_min, height_max, weight_label, weight_min, weight_max = (
        _measurement_ranges(units)
    )
    height = weight = body_fat = None
    try:
        height = _parse_measurement(state["height_cm"], height_label, height_min, height_max)
    except ValueError as error:
        errors[1].append(str(error))
    try:
        weight = _parse_measurement(state["weight_kg"], weight_label, weight_min, weight_max)
    except ValueError as error:
        errors[1].append(str(error))
    if state["ob_use_body_fat"]:
        try:
            body_fat = _parse_measurement(state["body_fat_pct_input"], "Body Fat %", 3, 80)
        except ValueError as error:
            errors[1].append(str(error))

    sessions = int(state["training_sessions_per_week"])
    if not 0 <= sessions <= MAX_SESSIONS_PER_WEEK:
        errors[2].append(f"Training sessions must be between 0 and {MAX_SESSIONS_PER_WEEK}.")
    exercise_sessions = []
    if sessions > 0:
        training_type = state["training_type"]
        exercise_sessions = [
            {
                "type": training_type,
                "met": TRAINING_TYPE_METS[training_type],
                "duration_minutes": int(state["training_duration_minutes"]),
                "sessions_per_week": sessions,
            }
        ]
    daily_steps = state["daily_steps_option"]
    if daily_steps == "Custom amount":
        try:
            daily_steps = _parse_integer_input(
                state["custom_daily_steps_input"], "Custom daily steps", 0, 50000
            )
        except ValueError as error:
            errors[2].append(str(error))

    if any(errors.values()):
        return None, errors

    if units == "Imperial":
        height = float(_truncate_to_two_decimals(Decimal(str(height)) * Decimal("2.54")))
        weight = float(
            _truncate_to_two_decimals(Decimal(str(weight)) / Decimal("2.2046226218"))
        )
    occupation = state["occupation_movement"]
    profile = asdict(
        UserProfile(
            age=int(state["ob_age"]),
            sex=state["ob_sex"],
            height_cm=height,
            weight_kg=weight,
            body_fat_pct=body_fat,
            occupation_type=occupation,
            daily_steps=daily_steps,
            exercise_sessions=exercise_sessions,
            occupation_hours_per_workday=DEFAULT_OCCUPATION_HOURS_PER_WORKDAY[occupation],
            occupation_days_per_week=DEFAULT_OCCUPATION_DAYS_PER_WEEK,
            cooking_skill=state["cooking_skill"],
            allergens=_normalize_allergens(
                list(state["allergens"]), state["other_allergen"]
            ),
            diets=list(state["dietary_preferences"]),
            fitness_goal=state["fitness_goal"],
        )
    )
    profile["measurement_units"] = units
    return profile, errors


# ---- Session-state callbacks -------------------------------------------------

def _keep_choice(key):
    """Segmented controls and pills can be clicked off; keep the last choice."""
    if st.session_state[key] is None:
        st.session_state[key] = st.session_state[f"{key}__last"]
    else:
        st.session_state[f"{key}__last"] = st.session_state[key]


def _change_units():
    if st.session_state["measurement_units"] is None:
        st.session_state["measurement_units"] = st.session_state["measurement_units_previous"]
        return
    _convert_measurement_inputs()


def _go_back():
    st.session_state["ob_step"] = max(1, st.session_state["ob_step"] - 1)
    st.session_state["ob_errors"] = []


def _go_next():
    step = st.session_state["ob_step"]
    _normalize_measurement_inputs()
    _, errors = _collect_profile(st.session_state)
    st.session_state["ob_errors"] = errors[step]
    if not errors[step]:
        st.session_state["ob_step"] = min(len(STEPS), step + 1)


def _submit():
    _normalize_measurement_inputs()
    profile, errors = _collect_profile(st.session_state)
    if profile is None:
        first_step = next(step for step, messages in errors.items() if messages)
        st.session_state["ob_step"] = first_step
        st.session_state["ob_errors"] = errors[first_step]
        return
    user_id = st.session_state.user["id"]
    db.save_profile(user_id, profile)
    db.mark_onboarding_complete(user_id)
    st.session_state.user["onboarding_complete"] = True
    st.session_state["main_navigation"] = "Dashboard"


# ---- Rendering ---------------------------------------------------------------

def _icon(name, color="#ff4b4b"):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round">{_ICONS[name]}</svg>'
    )
    # st.html strips inline <svg>, so icons are embedded as images.
    return f'<span class="ob-icon"><img alt="" src="data:image/svg+xml,{quote(svg)}"></span>'


def _card_header(icon, title, tip, badge="", icon_color="#ff4b4b"):
    st.html(
        '<div class="ob-card-head"><div class="ob-card-title">'
        f"{_icon(icon, icon_color)}<h2>{escape(title)}</h2>"
        f'<span class="ob-tip" title="{escape(tip)}">?</span></div>{badge}</div>'
    )


def _label(text, hint="", hot=False):
    st.html(
        f'<div class="ob-label">{escape(text)}'
        f'<span class="{"hot" if hot else ""}">{escape(hint)}</span></div>'
    )


def _header():
    st.html(
        f'<div class="ob-brand"><img src="{logo_data_uri()}" alt="Sustain logo">'
        '<span class="ob-wordmark">Sustain</span>'
        '<span class="ob-status"><i></i>Profile &amp; TDEE Calibration</span></div>'
        '<h1 class="ob-title">Welcome to Sustain</h1>'
        '<p class="ob-sub">Complete your profile so we can tailor your daily calories, '
        "macros and recipe recommendations.</p>"
    )


def _stepper(current):
    tabs = "".join(
        f'<div class="ob-tab {"active" if number == current else "done" if number < current else ""}">'
        f'<span class="ob-num">{"✓" if number < current else number}</span>'
        f'<div><div class="ob-tab-title">{escape(title)}</div>'
        f'<div class="ob-tab-sub">{escape(sub)}</div></div></div>'
        for number, (title, sub) in enumerate(STEPS, start=1)
    )
    st.html(
        f'<div class="ob-stepper"><div class="ob-tabs">{tabs}</div>'
        f'<div class="ob-track"><div class="ob-fill" style="width:{current / len(STEPS) * 100:.2f}%">'
        "</div></div></div>"
    )


def _bmi_badge():
    units = st.session_state["measurement_units"]
    height_label, hmin, hmax, weight_label, wmin, wmax = _measurement_ranges(units)
    try:
        height = _parse_measurement(st.session_state["height_cm"], height_label, hmin, hmax)
        weight = _parse_measurement(st.session_state["weight_kg"], weight_label, wmin, wmax)
    except ValueError:
        return '<span class="ob-pill grey">BMI —</span>'
    if units == "Imperial":
        height, weight = height * 2.54, weight / 2.2046226218
    bmi = weight / (height / 100) ** 2
    if bmi < 18.5:
        label, tone = "Underweight", "blue"
    elif bmi < 25:
        label, tone = "Healthy Range", "green"
    elif bmi < 30:
        label, tone = "Overweight", "amber"
    else:
        label, tone = "Higher BMI", "amber"
    return f'<span class="ob-pill {tone}">BMI {bmi:.1f} · {label}</span>'


def _step_body_metrics():
    _card_header(
        "body", "Body Metrics",
        "Used to compute your Basal Metabolic Rate (BMR), the calories your body burns at rest.",
        _bmi_badge(),
    )
    units = st.session_state["measurement_units"]
    _label("Measurement Units", f"Using {units} System")
    st.segmented_control(
        "Measurement units",
        ["Metric", "Imperial"],
        format_func=lambda value: "Metric (cm / kg)" if value == "Metric" else "Imperial (in / lbs)",
        key="measurement_units",
        on_change=_change_units,
        label_visibility="collapsed",
        width="stretch",
    )
    height_label, hmin, hmax, weight_label, wmin, wmax = _measurement_ranges(units)

    age_col, sex_col = st.columns(2)
    with age_col:
        _label("Age", "15 – 100 yrs")
        st.number_input("Age", min_value=15, max_value=100, key="ob_age",
                        label_visibility="collapsed")
    with sex_col:
        _label("Biological Sex", "For BMR constant")
        st.segmented_control(
            "Biological Sex", ["Male", "Female"], key="ob_sex",
            on_change=_keep_choice, args=("ob_sex",),
            label_visibility="collapsed", width="stretch",
        )

    height_col, weight_col = st.columns(2)
    for column, key, label, low, high in (
        (height_col, "height_cm", height_label, hmin, hmax),
        (weight_col, "weight_kg", weight_label, wmin, wmax),
    ):
        with column:
            _label(label, f"{low:g} – {high:g}")
            value = st.text_input(
                label, key=key, on_change=_normalize_measurement_input, args=(key,),
                label_visibility="collapsed",
            )
            if warning := _measurement_warning(value, label, low, high):
                st.caption(f":red[{warning}]")

    with st.container(key="ob_bodyfat"):
        toggle_col, badge_col = st.columns([3, 2], vertical_alignment="center")
        with toggle_col:
            use_body_fat = st.toggle("I know my Body Fat %", key="ob_use_body_fat")
        badge_col.html(
            '<div style="text-align:right">'
            + (
                '<span class="ob-pill blue">Formula: Katch-McArdle</span>'
                if use_body_fat
                else '<span class="ob-pill grey">Formula: Mifflin-St Jeor</span>'
            )
            + "</div>"
        )
        if use_body_fat:
            _label("Body Fat Percentage", "3 – 80%")
            value = st.text_input(
                "Body Fat %", key="body_fat_pct_input", placeholder="e.g. 18",
                on_change=_normalize_measurement_input, args=("body_fat_pct_input",),
                label_visibility="collapsed",
            )
            if warning := _measurement_warning(value, "Body Fat %", 3, 80):
                st.caption(f":red[{warning}]")


def _step_lifestyle():
    _card_header(
        "lifestyle", "Lifestyle & Fitness Goals",
        "Sets your exercise (EAT) and everyday movement (NEAT) energy, and your calorie target.",
    )
    _label("Primary Fitness Goal", GOALS[st.session_state["fitness_goal"]][0])
    with st.container(key="ob_cards_goal"):
        st.radio(
            "Primary Fitness Goal", list(GOALS), key="fitness_goal",
            format_func=lambda goal: f"**{goal}**",
            captions=[description for _, description in GOALS.values()],
            label_visibility="collapsed",
        )

    sessions = st.session_state["training_sessions_per_week"]
    minutes = st.session_state["training_duration_minutes"]
    _label(
        "Training Sessions per Week",
        f"{sessions} session{'' if sessions == 1 else 's'} · {sessions * minutes} min/wk",
        hot=True,
    )
    st.slider(
        "Training sessions per week", min_value=0, max_value=MAX_SESSIONS_PER_WEEK,
        step=1, key="training_sessions_per_week", label_visibility="collapsed",
    )
    if sessions > 0:
        type_col, minutes_col = st.columns(2)
        with type_col:
            _label("Main Exercise Type")
            st.selectbox(
                "Main exercise type", list(TRAINING_TYPE_METS), key="training_type",
                format_func=TRAINING_LABELS.get, label_visibility="collapsed",
            )
        with minutes_col:
            _label("Avg Time per Workout", "minutes")
            st.number_input(
                "Average time per workout", min_value=10, max_value=240, step=5,
                key="training_duration_minutes", label_visibility="collapsed",
            )

    _label("Daily Occupation Movement", "Non-exercise activity (NEAT)")
    with st.container(key="ob_cards_occupation"):
        st.radio(
            "Daily Occupation Movement", list(OCCUPATION_METS), key="occupation_movement",
            format_func=lambda value: f"**{OCCUPATIONS[value][0]}**",
            captions=[OCCUPATIONS[value][1] for value in OCCUPATION_METS],
            label_visibility="collapsed",
        )

    _label("Estimated Daily Step Count")
    st.pills(
        "Estimated daily step count", STEP_OPTIONS, key="daily_steps_option",
        on_change=_keep_choice, args=("daily_steps_option",),
        label_visibility="collapsed",
    )
    if st.session_state["daily_steps_option"] == "Custom amount":
        value = st.text_input(
            "Custom daily steps", key="custom_daily_steps_input",
            placeholder="Steps per day, e.g. 8200", label_visibility="collapsed",
        )
        if warning := _integer_input_warning(value, "Custom daily steps", 0, 50000):
            st.caption(f":red[{warning}]")

    _label("Cooking Skill Level")
    with st.container(key="ob_cards3_skill"):
        st.radio(
            "Cooking Skill Level", list(SKILLS), key="cooking_skill",
            format_func=lambda value: f"**{value}**",
            captions=list(SKILLS.values()),
            label_visibility="collapsed",
        )


def _step_allergies():
    _card_header(
        "shield", "Allergies & Dietary Restrictions",
        "Excluded foods are kept out of recipe searches and meal suggestions.",
        '<span class="ob-pill grey">Optional</span>',
        icon_color="#34d399",
    )
    excluded = len(st.session_state["allergens"]) + len(
        [v for v in st.session_state["other_allergen"].split(",") if v.strip()]
    )
    _label("Allergens / Dietary Exclusions", f"{excluded} excluded")
    st.pills(
        "Allergens", ALLERGEN_OPTIONS, selection_mode="multi", key="allergens",
        label_visibility="collapsed",
    )
    st.text_input(
        "Other exclusions", key="other_allergen",
        placeholder="Other ingredients to exclude, comma-separated (e.g. cilantro, mushrooms)",
        label_visibility="collapsed",
    )
    diets = st.session_state["dietary_preferences"]
    _label("Diet Types", ", ".join(diets) if diets else "No restrictions")
    with st.container(key="ob_diets"):
        st.pills(
            "Diet types", DIETARY_PREFERENCES, selection_mode="multi",
            key="dietary_preferences", label_visibility="collapsed",
        )


def _dock(step):
    profile, _ = _collect_profile(st.session_state)
    if profile is None:
        tdee_text = target_text = "—"
        protein = carbs = fat = "—"
    else:
        targets = targets_service.calculate_targets(profile)
        tdee_text = f"{round(calculate_tdee(profile)['tdee_kcal']):,} kcal"
        target_text = f"{targets['calories']:,} kcal"
        protein, carbs, fat = (f"{targets[key]}g" for key in ("protein_g", "carbs_g", "fat_g"))
    goal = escape(st.session_state["fitness_goal"])

    with st.container(key="ob_dock"):
        preview_col, back_col, action_col = st.columns(
            [5, 1.2, 1.9], vertical_alignment="center"
        )
        preview_col.html(
            '<div class="ob-preview">'
            f'<div class="ob-metric"><small>Maintenance TDEE</small><b>{tdee_text}</b></div>'
            '<span class="ob-divider"></span>'
            f'<div class="ob-metric"><small>Target ({goal})</small>'
            f'<b style="color:#ff4b4b">{target_text}</b></div>'
            '<span class="ob-divider"></span><div class="ob-macros">'
            f'<span class="ob-macro"><i style="background:#38bdf8"></i>P {protein}</span>'
            f'<span class="ob-macro"><i style="background:#fbbf24"></i>C {carbs}</span>'
            f'<span class="ob-macro"><i style="background:#a78bfa"></i>F {fat}</span>'
            "</div></div>"
        )
        if step > 1:
            back_col.button("← Back", key="ob_back", on_click=_go_back,
                            use_container_width=True)
        if step < len(STEPS):
            action_col.button("Next Step →", key="ob_next", on_click=_go_next,
                              use_container_width=True)
        else:
            action_col.button("Submit & View Plan →", key="ob_submit", on_click=_submit,
                              use_container_width=True)


def render_onboarding_page():
    for key, default in DEFAULTS.items():
        # Re-assigning keeps answers for widgets on steps that are not shown.
        st.session_state[key] = st.session_state.get(key, default)
    st.html(ONBOARDING_CSS)
    if warning := st.session_state.pop("unit_conversion_warning", None):
        st.toast(warning, icon="⚠️")

    step = st.session_state["ob_step"]
    _header()
    _stepper(step)
    with st.container(key="ob_card"):
        for message in st.session_state["ob_errors"]:
            st.error(message)
        (_step_body_metrics, _step_lifestyle, _step_allergies)[step - 1]()
    _dock(step)
