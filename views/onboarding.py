# Onboarding questionnaire: a guided 3-step flow (Body Metrics, Lifestyle &
# Goals, Allergies & Diet) with navigation docked at the bottom.
import re
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from html import escape
from pathlib import Path
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
    .block-container { max-width:860px; padding:4.5rem 1.25rem 9rem; }
    .ob-brand { display:flex; align-items:center; gap:.75rem; flex-wrap:wrap; }
    .ob-brand img { width:40px; height:40px; border-radius:11px; }
    .ob-wordmark { font-size:1.125rem; font-weight:600; color:var(--sustain-text); }
    .ob-status { display:inline-flex; align-items:center; gap:.4rem; padding:.25rem .7rem;
        border-radius:4px; border:1px solid var(--sustain-border);
        color:var(--sustain-secondary); font-size:.75rem; font-weight:400; }
    .ob-status i { width:6px; height:6px; border-radius:50%; background:var(--sustain-accent); }
    .ob-title { margin:16px 0 4px; font-size:2rem; font-weight:500;
        line-height:1.2; color:var(--sustain-text); }
    .ob-sub { color:var(--sustain-secondary); font-size:.9rem; line-height:1.55; margin-bottom:1.3rem; }

    .ob-stepper { padding:1rem 1.25rem; border:1px solid var(--sustain-border); border-radius:14px;
        background:var(--sustain-surface); }
    .ob-tabs { display:grid; grid-template-columns:repeat(3,1fr); gap:.6rem; margin-bottom:.75rem; }
    .ob-tab { display:flex; align-items:center; gap:.6rem; padding:.6rem .75rem; border-radius:10px;
        background:var(--sustain-raised); border:1px solid var(--sustain-border); }
    .ob-tab.active { border-color:var(--sustain-border-strong); background:var(--sustain-hover-strong); }
    .ob-tab.done { border-color:var(--sustain-border); }
    .ob-num { flex-shrink:0; width:24px; height:24px; display:grid; place-items:center;
        border-radius:50%; background:var(--sustain-surface); border:1px solid var(--sustain-border-strong);
        color:var(--sustain-secondary); font-size:.75rem; font-weight:500; }
    .ob-tab.active .ob-num { background:var(--sustain-accent); border-color:var(--sustain-accent); color:#fff; }
    .ob-tab.done .ob-num { background:var(--sustain-raised); border-color:var(--sustain-border); color:var(--sustain-positive); }
    .ob-tab-title { font-size:.8125rem; font-weight:500; color:var(--sustain-text); }
    .ob-tab-sub { font-size:.7rem; color:var(--sustain-muted); }
    .ob-track { height:5px; border-radius:999px; background:var(--sustain-raised); overflow:hidden; }
    .ob-fill { height:100%; border-radius:999px; background:var(--sustain-accent); }
    @media (max-width:640px) { .ob-tabs { grid-template-columns:1fr; } }

    .st-key-ob_card { padding:1.35rem; border:1px solid var(--sustain-border); border-radius:14px;
        background:var(--sustain-surface); }
    .ob-card-head { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap;
        gap:.75rem; padding-bottom:1rem; border-bottom:1px solid var(--sustain-border); }
    .ob-card-title { display:flex; align-items:center; gap:.7rem; }
    .ob-card-title h2 { margin:0; padding:0; font-size:1.125rem; font-weight:500; color:var(--sustain-text); }
    .ob-icon { width:34px; height:34px; display:grid; place-items:center; border-radius:9px;
        background:var(--sustain-raised); border:1px solid var(--sustain-border); }
    .ob-icon img { width:18px; height:18px; }
    .ob-tip { width:17px; height:17px; display:inline-grid; place-items:center; border-radius:50%;
        background:var(--sustain-raised); border:1px solid var(--sustain-border-strong); color:var(--sustain-secondary); font-size:.6875rem;
        font-weight:500; cursor:help; }
    .ob-pill { display:inline-flex; align-items:center; padding:2px 8px; border-radius:4px;
        font-size:.75rem; font-weight:400; border:1px solid var(--sustain-border); background:transparent; }
    .ob-pill.green { color:var(--sustain-positive); }
    .ob-pill.amber { color:var(--sustain-caution); }
    .ob-pill.blue { color:var(--sustain-info); }
    .ob-pill.grey { color:var(--sustain-secondary); }
    .ob-label { display:flex; justify-content:space-between; align-items:center; gap:.5rem;
        margin:.2rem 0 -.35rem; font-size:.875rem; font-weight:500; color:var(--sustain-text); }
    .ob-label span { color:var(--sustain-secondary); font-size:.75rem; font-weight:500; }
    .ob-label .hot { color:var(--sustain-negative); font-weight:500; }

    .st-key-ob_bodyfat { padding:.85rem 1rem; border:1px solid var(--sustain-border); border-radius:12px;
        background:var(--sustain-raised); }

    /* Bottom dock with step navigation */
    .st-key-ob_dock { position:fixed; left:0; right:0; bottom:0; z-index:100;
        padding:.8rem max(1.25rem, calc((100vw - 860px) / 2 + 1.25rem));
        background:var(--sustain-dock);
        border-top:1px solid var(--sustain-border); }
    .st-key-ob_dock button { min-height:40px; border-radius:8px; font-weight:500; }
    .st-key-ob_back button { background:var(--sustain-raised); border:1px solid var(--sustain-border); color:var(--sustain-text); }
    .st-key-ob_back button:hover { background:var(--sustain-hover-strong); border-color:var(--sustain-border-strong); color:var(--sustain-text); }
    .st-key-ob_next button, .st-key-ob_submit button { background:var(--sustain-accent); border:0; color:#fff;
        box-shadow:none; }
    .st-key-ob_next button:hover, .st-key-ob_submit button:hover { background:var(--sustain-accent-hover); color:#fff; }
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
    # Compare as decimals: as floats, 39.38 is slightly more than the typed
    # "39.38", so the minimum shown on screen would be rejected.
    if not Decimal(str(minimum)) <= measurement <= Decimal(str(maximum)):
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
    try:
        # Never save a profile that the target calculation can't handle,
        # or every page after onboarding would fail for this user.
        targets_service.calculate_targets(profile)
    except ValueError as error:
        errors[1].append(f"We couldn't calculate targets from these details: {error}")
        return None, errors
    return profile, errors


def _icon(name, color="#8a8a90"):
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round">{_ICONS[name]}</svg>'
    )
    # st.html strips inline <svg>, so icons are embedded as images.
    return f'<span class="ob-icon"><img alt="" src="data:image/svg+xml,{quote(svg)}"></span>'


def _header():
    st.html(
        f'<div class="ob-brand"><img src="{logo_data_uri()}" alt="Sustain logo">'
        '<span class="ob-wordmark">Sustain</span>'
        '</div>'
        '<h1 class="ob-title">Set up your profile</h1>'
        '<p class="ob-sub">Complete your profile so we can tailor your daily calories, '
        "macros and recipe recommendations.</p>"
    )



def _card_header(icon, title, tip, badge=""):
    return (
        '<div class="ob-card-head"><div class="ob-card-title">'
        f"{_icon(icon)}<h2 tabindex='-1'>{escape(title)}</h2>"
        f'<span class="ob-tip" title="{escape(tip)}">?</span></div>{badge}</div>'
    )


def _label(text, hint="", target=""):
    tag = "label" if target else "div"
    linked = f' for="{target}"' if target else ""
    return f'<{tag}{linked} class="ob-label">{escape(text)}<span>{escape(hint)}</span></{tag}>'


def _field(name, label, attrs="", hint=""):
    value = escape(str(DEFAULTS[name]), quote=True)
    return _label(label, hint, name) + f'<input id="{name}" name="{name}" value="{value}" {attrs}>'


def _group(name, label, options, style="pills", multiple=False):
    kind = "checkbox" if multiple else "radio"
    selected = DEFAULTS[name] if multiple else (DEFAULTS[name],)
    items = "".join(
        f'<label><input name="{name}" type="{kind}" value="{escape(value)}"'
        f'{" checked" if value in selected else ""}>'
        f'<span>{escape(title)}<small>{escape(detail)}</small></span></label>'
        for value, (title, detail) in options.items()
    )
    return f'<div class="{style}" role="group" aria-label="{escape(label)}">{items}</div>'


def _choices(items):
    return {item: (item, "") for item in items}


def _onboarding_html():
    tabs = "".join(
        f'<div class="ob-tab"><span class="ob-num">{number}</span>'
        f'<div class="ob-tab-title"><span class="ob-tab-name">{escape(title)}</span><div class="ob-tab-sub">{escape(sub)}</div></div></div>'
        for number, (title, sub) in enumerate(STEPS, 1)
    )
    training = "".join(
        f'<option value="{escape(key)}">{escape(TRAINING_LABELS[key])}</option>' for key in TRAINING_TYPE_METS
    )
    default_height = float(DEFAULTS["height_cm"]) / 100
    default_bmi = float(DEFAULTS["weight_kg"]) / default_height ** 2
    bmi_badge = f'<output class="ob-pill green" id="bmi" aria-live="polite">BMI {default_bmi:.1f} &middot; Healthy Range</output>'
    return f"""
    <form novalidate>
        <div class="ob-stepper"><div class="ob-tabs">{tabs}</div>
          <div class="ob-track"><div class="ob-fill"></div></div></div>
        <div class="st-key-ob_card">
          <div class="errors" role="alert" hidden></div>
          <section>
            {_card_header("body", "Body Metrics", "Used to compute your Basal Metabolic Rate (BMR), the calories your body burns at rest.", bmi_badge)}
            {_label("Measurement Units")}
            {_group("measurement_units", "Measurement units", {"Metric": ("Metric (cm / kg)", ""), "Imperial": ("Imperial (in / lbs)", "")}, "segments")}
            <div class="grid">
              <div>{_field("ob_age", "Age", 'type="number" min="15" max="100" required')}</div>
              <div>{_label("Biological Sex", "For BMR constant")}
              {_group("ob_sex", "Biological Sex", _choices(("Male", "Female")), "segments")}</div>
              <div>{_field("height_cm", "Height (cm)", 'inputmode="decimal"')}</div>
              <div>{_field("weight_kg", "Weight (kg)", 'inputmode="decimal"')}</div>
            </div>
            <div class="st-key-ob_bodyfat">
              <div class="toggle-row"><label><input type="checkbox" role="switch" name="ob_use_body_fat" aria-controls="body-fat-detail"> I know my Body Fat %</label>
              <span class="ob-pill grey" id="formula"></span></div>
              <div id="body-fat-detail">{_field("body_fat_pct_input", "Body Fat Percentage", 'inputmode="decimal" placeholder="e.g. 18"', "3 - 80%")}</div>
            </div>
          </section>
          <section hidden>
            {_card_header("lifestyle", "Lifestyle & Fitness Goals", "Sets your exercise (EAT) and everyday movement (NEAT) energy, and your calorie target.")}
            {_label("Primary Fitness Goal")}
            {_group("fitness_goal", "Primary Fitness Goal", {k: (k, detail) for k, (_, detail) in GOALS.items()}, "cards")}
            {_field("training_sessions_per_week", "Training Sessions per Week", f'type="range" min="0" max="{MAX_SESSIONS_PER_WEEK}"')}
            <div id="training-detail" class="grid">
              <div>{_label("Main Exercise Type", target="training_type")}
                <select id="training_type" name="training_type">{training}</select></div>
              <div>{_field("training_duration_minutes", "Avg Time per Workout", 'type="number" min="10" max="240" step="5" required', "minutes")}</div>
            </div>
            {_label("Daily Occupation Movement", "Non-exercise activity (NEAT)")}
            {_group("occupation_movement", "Daily Occupation Movement", OCCUPATIONS, "cards")}
            {_label("Estimated Daily Step Count")}
            {_group("daily_steps_option", "Estimated Daily Step Count", _choices(STEP_OPTIONS))}
            <div id="steps-detail">{_field("custom_daily_steps_input", "Custom daily steps", 'inputmode="numeric" placeholder="Steps per day, e.g. 8200"')}</div>
            {_label("Cooking Skill Level")}
            {_group("cooking_skill", "Cooking Skill Level", {k: (k, detail) for k, detail in SKILLS.items()}, "cards skill")}
          </section>
          <section hidden>
            {_card_header("shield", "Allergies & Dietary Restrictions", "Excluded foods are kept out of recipe searches and meal suggestions.", '<span class="ob-pill grey">Optional</span>')}
            {_label("Allergens / Dietary Exclusions")}
            {_group("allergens", "Allergens", _choices(ALLERGEN_OPTIONS), multiple=True)}
            {_field("other_allergen", "Other exclusions", 'placeholder="Other ingredients to exclude, comma-separated (e.g. cilantro, mushrooms)"')}
            {_label("Diet Types")}
            {_group("dietary_preferences", "Diet Types", _choices(DIETARY_PREFERENCES), "pills diets", True)}
          </section>
        </div>
        <footer class="st-key-ob_dock">
          <div class="ob-dock-progress">
            <span id="ob-progress-label">Step 1 of {len(STEPS)} &bull; {escape(STEPS[0][0])}</span>
            <progress id="ob-progress" value="1" max="{len(STEPS)}" aria-labelledby="ob-progress-label"></progress>
          </div>
          <div class="st-key-ob_back"><button type="button" id="back" hidden>&larr; Back</button></div>
          <div class="st-key-ob_submit"><button type="submit" id="next">Next Step &rarr;</button></div>
        </footer>
    </form>
    """


_ANSWER_DEFAULTS = {key: value for key, value in DEFAULTS.items() if key not in {
    "ob_step", "ob_errors", "measurement_units_previous", "ob_sex__last", "daily_steps_option__last",
}}
_PATH = Path(__file__).resolve().parents[1] / "components" / "onboarding"
_questionnaire = st.components.v2.component(
    "sustain_onboarding",
    html=_onboarding_html(),
    css=ONBOARDING_CSS.split("<style>", 1)[1].split("</style>", 1)[0]
    + (_PATH / "questionnaire.css").read_text(encoding="utf-8"),
    js=(_PATH / "questionnaire.js").read_text(encoding="utf-8"),
)


def _save_questionnaire():
    answers = st.session_state.onboarding_questionnaire.submit
    if not isinstance(answers, dict):
        return
    try:
        if set(answers) != set(_ANSWER_DEFAULTS):
            raise ValueError("Incomplete answers")
        if any(
            type(answers[key]) is not type(default)
            for key, default in _ANSWER_DEFAULTS.items()
        ):
            raise ValueError("Invalid answer type")
        choices = {
            "measurement_units": ("Metric", "Imperial"), "ob_sex": ("Male", "Female"),
            "fitness_goal": GOALS, "occupation_movement": OCCUPATIONS, "cooking_skill": SKILLS,
            "training_type": TRAINING_TYPE_METS, "daily_steps_option": STEP_OPTIONS,
        }
        if any(answers[key] not in options for key, options in choices.items()):
            raise ValueError("Invalid choice")
        if any(item not in ALLERGEN_OPTIONS for item in answers["allergens"]) or any(
            item not in DIETARY_PREFERENCES for item in answers["dietary_preferences"]
        ):
            raise ValueError("Invalid exclusions")
        if not 15 <= answers["ob_age"] <= 100 or not 10 <= answers["training_duration_minutes"] <= 240:
            raise ValueError("Age or workout duration is out of range")
        profile, errors = _collect_profile(answers)
    except (TypeError, ValueError):
        profile, errors = None, {1: ["Check your answers and try again."]}
        answers = None

    if profile is None:
        step, messages = next((step, messages) for step, messages in errors.items() if messages)
        attempt = st.session_state.get("onboarding_feedback", {}).get("attempt", 0) + 1
        st.session_state.onboarding_feedback = {
            "step": step - 1, "errors": messages, "answers": answers, "attempt": attempt,
        }
        return

    user = st.session_state.user
    db.save_profile(user["id"], profile, complete_onboarding=True)
    user["onboarding_complete"] = True
    st.session_state.main_navigation = "Dashboard"
    st.session_state.pop("onboarding_feedback", None)


def render_onboarding_page():
    st.html(ONBOARDING_CSS)
    _header()
    _questionnaire(
        key="onboarding_questionnaire",
        data={
            "defaults": _ANSWER_DEFAULTS,
            "feedback": st.session_state.get("onboarding_feedback"),
            "ranges": {unit: _measurement_ranges(unit) for unit in ("Metric", "Imperial")},
            "goalHints": {key: hint for key, (hint, _) in GOALS.items()},
        },
        on_submit_change=_save_questionnaire,
    )
