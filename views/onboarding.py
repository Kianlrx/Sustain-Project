import re
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path

import streamlit as st
from models.profile import DIETARY_PREFERENCES, UserProfile
from services import db
from services.tdee_engine import (
    DEFAULT_OCCUPATION_DAYS_PER_WEEK,
    DEFAULT_OCCUPATION_HOURS_PER_WORKDAY,
    OCCUPATION_METS,
    TRAINING_TYPE_METS,
)


INPUT_STYLES = """
<style>
[data-testid="stNumberInputContainer"],
[data-testid="stTextInputRootElement"],
[data-testid="stSelectbox"] [role="group"],
[data-testid="stMultiSelect"] [role="group"] {
    box-sizing: border-box;
    height: 42px;
    min-height: 42px;
    border-radius: 8px;
}

[data-testid="stMultiSelect"] [role="group"] {
    height: auto;
}

[data-testid="stSelectbox"] [data-testid="stTooltipIcon"] {
    transform: translateX(-12px);
}

.st-key-height_measurement_field,
.st-key-weight_measurement_field,
.st-key-body_fat_measurement_field,
.st-key-custom_steps_field,
.st-key-workout_duration_field {
    position: relative;
}

.st-key-height_measurement_field > [data-testid="stElementContainer"]:has([data-testid="stAlert"]),
.st-key-weight_measurement_field > [data-testid="stElementContainer"]:has([data-testid="stAlert"]),
.st-key-custom_steps_field > [data-testid="stElementContainer"]:has([data-testid="stAlert"]),
.st-key-workout_duration_field > [data-testid="stElementContainer"]:has([data-testid="stAlert"]) {
    position: absolute;
    top: 100%;
    left: 0;
    width: max-content;
    max-width: 100%;
    height: auto;
    box-sizing: border-box;
    min-height: 0;
    margin: 0;
    pointer-events: none;
    padding: 0;
    z-index: 1000;
}

.st-key-body_fat_measurement_field > [data-testid="stElementContainer"]:has([data-testid="stAlert"]) {
    position: absolute;
    top: 100%;
    right: 0;
    left: auto;
    width: max-content;
    max-width: 100%;
    height: auto;
    box-sizing: border-box;
    min-height: 0;
    margin: 0;
    pointer-events: none;
    padding: 0;
    z-index: 1000;
}

.st-key-height_measurement_field [data-testid="stAlert"],
.st-key-weight_measurement_field [data-testid="stAlert"],
.st-key-body_fat_measurement_field [data-testid="stAlert"],
.st-key-custom_steps_field [data-testid="stAlert"],
.st-key-workout_duration_field [data-testid="stAlert"] {
    width: max-content;
    max-width: 100%;
    height: auto;
    box-sizing: border-box;
    min-height: 0;
    margin: 0;
    padding: 0;
}

.st-key-height_measurement_field [data-testid="stAlertContainer"],
.st-key-weight_measurement_field [data-testid="stAlertContainer"],
.st-key-body_fat_measurement_field [data-testid="stAlertContainer"],
.st-key-custom_steps_field [data-testid="stAlertContainer"],
.st-key-workout_duration_field [data-testid="stAlertContainer"] {
    padding: 0.5rem 1rem;
}

.st-key-height_measurement_field [data-testid="stAlertContentError"],
.st-key-weight_measurement_field [data-testid="stAlertContentError"],
.st-key-body_fat_measurement_field [data-testid="stAlertContentError"],
.st-key-custom_steps_field [data-testid="stAlertContentError"],
.st-key-workout_duration_field [data-testid="stAlertContentError"],
.st-key-height_measurement_field [data-testid="stMarkdownContainer"],
.st-key-weight_measurement_field [data-testid="stMarkdownContainer"],
.st-key-body_fat_measurement_field [data-testid="stMarkdownContainer"],
.st-key-custom_steps_field [data-testid="stMarkdownContainer"],
.st-key-workout_duration_field [data-testid="stMarkdownContainer"] {
    height: auto;
    margin-bottom: 0;
}

.st-key-height_measurement_field [data-testid="stAlert"] p,
.st-key-weight_measurement_field [data-testid="stAlert"] p,
.st-key-body_fat_measurement_field [data-testid="stAlert"] p,
.st-key-custom_steps_field [data-testid="stAlert"] p,
.st-key-workout_duration_field [data-testid="stAlert"] p {
    margin: 0;
}

</style>
"""


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


def render_onboarding_page():
    st.html(INPUT_STYLES)
    st.image(
        Path(__file__).resolve().parents[1] / "assets" / "sustain_logo.png",
        width=56,
    )
    st.title("Welcome to Sustain")
    st.caption(
        "Please complete the questionnaire below to personalize your nutrition targets and meal recommendations."
    )
    st.session_state.setdefault("measurement_units", "Metric")
    st.session_state.setdefault("measurement_units_previous", "Metric")
    st.session_state.setdefault("height_cm", "175")
    st.session_state.setdefault("weight_kg", "75")
    st.session_state.setdefault("body_fat_pct_input", "")
    st.session_state.setdefault("custom_daily_steps_input", "")
    st.session_state.setdefault("training_duration_minutes_input", "60")
    if warning := st.session_state.pop("unit_conversion_warning", None):
        st.toast(warning, icon="⚠️")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 💪 Body Metrics")
        measurement_units = st.radio(
            "Measurement units",
            ["Metric", "Imperial"],
            horizontal=True,
            key="measurement_units",
            on_change=_convert_measurement_inputs,
            help="Imperial measurements are converted to cm and kg before calculations and saving.",
        )
        if measurement_units == "Metric":
            height_label, weight_label = "Height (cm)", "Weight (kg)"
            height_min, height_max = 100, 250
            weight_min, weight_max = 30, 300
        else:
            height_label, weight_label = "Height (inches)", "Weight (lbs)"
            height_min, height_max = 39.38, 98.42
            weight_min, weight_max = 66.15, 661.38
        age_col, sex_col = st.columns(2)
        with age_col:
            age = st.number_input("Age", min_value=15, max_value=100, value=25)
        with sex_col:
            sex = st.selectbox("Biological Sex", ["Male", "Female"])
        height_col, weight_col = st.columns(2)
        with height_col:
            with st.container(key="height_measurement_field"):
                height_input = st.text_input(
                    height_label,
                    key="height_cm",
                    on_change=_normalize_measurement_input,
                    args=("height_cm",),
                )
                if warning := _measurement_warning(
                    height_input, height_label, height_min, height_max
                ):
                    st.error(warning)
        with weight_col:
            with st.container(key="weight_measurement_field"):
                weight_input = st.text_input(
                    weight_label,
                    key="weight_kg",
                    on_change=_normalize_measurement_input,
                    args=("weight_kg",),
                )
                if warning := _measurement_warning(
                    weight_input, weight_label, weight_min, weight_max
                ):
                    st.error(warning)

        body_fat_col, body_fat_input_col = st.columns([1, 2])
        with body_fat_col:
            use_body_fat = st.checkbox("I know my Body Fat %")
        body_fat_pct = None
        if use_body_fat:
            with body_fat_input_col:
                with st.container(key="body_fat_measurement_field"):
                    body_fat_pct = st.text_input(
                        "Body Fat %",
                        key="body_fat_pct_input",
                        placeholder="Enter body fat %",
                        label_visibility="collapsed",
                        on_change=_normalize_measurement_input,
                        args=("body_fat_pct_input",),
                    )
                    if warning := _measurement_warning(
                        body_fat_pct, "Body Fat %", 3, 80
                    ):
                        st.error(warning)

        st.markdown("##### 🥦 Allergies & Dietary Restrictions (optional)")
        allergen_options = [
            "Peanuts",
            "Tree Nuts",
            "Dairy",
            "Eggs",
            "Gluten",
            "Shellfish",
            "Soy",
            "Pork",
            "Other",
        ]
        allergen_label = (
            "Allergens / Dietary Restrictions:"
        )
        allergens = st.multiselect(
            allergen_label,
            allergen_options,
            key="allergens",
            help="Select any allergens or foods that you don't want included in your meal recommendations.",
        )
        diets = st.multiselect(
            "Diet Types",
            DIETARY_PREFERENCES,
            key="dietary_preferences",
            help="Select any dietary preferences that you have. These will be used when generating meal recommendations.",
        )
        other_allergen = ""
        if "Other" in allergens:
            other_allergen = st.text_input(
                "Other exclusions (optional, comma-separated)",
                placeholder="For example: sesame, mushrooms",
                key="other_allergen",
            )

    with col2:
        st.markdown("##### 🏋️ Lifestyle & Fitness Goals")
        session_columns = st.columns(3)
        with session_columns[0]:
            sessions_per_week = st.slider(
                "Training sessions per week",
                min_value=0,
                max_value=14,
                value=3,
                step=1,
                help="Set to 0 if you don't exercise regularly.",
                key="training_sessions_per_week",
            )
        exercise_sessions = []
        if sessions_per_week > 0:
            with session_columns[1]:
                session_type = st.selectbox(
                    "Main exercise type",
                    list(TRAINING_TYPE_METS),
                    format_func=lambda value: {
                        "Weight training (low intensity)": "Weight Training",
                        "Endurance training (medium intensity)": "Endurance",
                        "Interval training (high intensity)": "Interval Training",
                    }[value],
                    help=(
                        "**Weight Training:** Short duration exercises—not cardiovascularly demanding \n\n"
                        "**Endurance:** Long duration, moderate intensity exercise (running, cycling, etc.)\n\n"
                        "**Interval Training:** High-intensity interval sessions (VO2 max, Threshold, etc.)"
                    ),
                    key="training_type",
                )
            with session_columns[2]:
                with st.container(key="workout_duration_field"):
                    session_duration_input = st.text_input(
                        "Average time per workout (minutes)",
                        key="training_duration_minutes_input",
                    )
                    duration_warning = _integer_input_warning(
                        session_duration_input,
                        "Average time per workout",
                        10,
                        240,
                    )
                    if duration_warning:
                        st.error(duration_warning)
                session_duration = (
                    _parse_integer_input(
                        session_duration_input, "Average time per workout", 10, 240
                    )
                    if not duration_warning and session_duration_input.strip()
                    else 60
                )
            exercise_sessions = [
                {
                    "type": session_type,
                    "met": TRAINING_TYPE_METS[session_type],
                    "duration_minutes": session_duration,
                    "sessions_per_week": sessions_per_week,
                }
            ]

        occupation_type = st.selectbox(
            "Daily Occupation Movement",
            list(OCCUPATION_METS),
            format_func=lambda value: (
                "Sedentary" if value == "Desk Job" else value
            ),
            help=(
                "**Sedentary:** Mostly seated, minimal movement.\n\n"
                "**Standing:** Standing with light movement.\n\n"
                "**Active Work:** Moderate walking.\n\n"
                "**Heavy Labor:** Heavy manual work."
            ),
            key="occupation_movement",
        )
        occupation_hours = DEFAULT_OCCUPATION_HOURS_PER_WORKDAY[occupation_type]
        occupation_days = DEFAULT_OCCUPATION_DAYS_PER_WEEK
        if occupation_type in {"Active Work", "Heavy Labor"} and occupation_hours == 0:
            st.warning(
                "Enter the time spent doing active work to include its occupational energy."
            )
        step_count_options = [
            "Less than 2,500",
            "2,500 - 5,000",
            "5,000 - 7,500",
            "7,500 - 10,000",
            "More than 10,000",
            "Custom amount",
        ]
        if st.session_state.get("daily_steps_option", step_count_options[0]) == "Custom amount":
            step_count_col, custom_steps_col = st.columns([1, 1])
            with step_count_col:
                daily_steps_option = st.selectbox(
                    "Estimated Daily Step Count",
                    step_count_options,
                    key="daily_steps_option",
                )
            with custom_steps_col:
                with st.container(key="custom_steps_field"):
                    custom_daily_steps = st.text_input(
                        "Custom amount",
                        key="custom_daily_steps_input",
                        placeholder="Steps per day",
                    )
                    custom_steps_warning = _integer_input_warning(
                        custom_daily_steps, "Custom daily steps", 0, 50000
                    )
                    if custom_steps_warning:
                        st.error(custom_steps_warning)
            daily_steps = (
                _parse_integer_input(
                    custom_daily_steps, "Custom daily steps", 0, 50000
                )
                if not custom_steps_warning and custom_daily_steps.strip()
                else None
            )
        else:
            daily_steps_option = st.selectbox(
                "Estimated Daily Step Count",
                step_count_options,
                key="daily_steps_option",
            )
            daily_steps = daily_steps_option
        cooking_skill = st.selectbox(
            "Cooking Skill Level",
            ["Beginner", "Intermediate", "Advanced"],
            help=(
                "**Beginner:** New to cooking or most comfortable with simple recipes.\n\n"
                "**Intermediate:** Comfortable preparing familiar meals and using basic techniques.\n\n"
                "**Advanced:** Confident with a wide range of techniques and more complex recipes."
            ),
            key="cooking_skill",
        )
        fitness_goal = st.selectbox(
            "Primary Fitness Goal",
            ["Fat Loss", "Muscle Gain", "Recomposition", "GLP-1 Support"],
            help=(
                "**Fat Loss:** Focus on reducing body fat with sustainable nutrition habits.\n\n"
                "**Muscle Gain:** Focus on supporting muscle growth and strength.\n\n"
                "**Recomposition:** Aim to build muscle while reducing body fat.\n\n"
                "**GLP-1 Support:** Focus on nutrition needs while using GLP-1 medication."
            ),
            key="fitness_goal",
        )
        st.html("<div style='height: 19px'></div>")
        _, submit_col, _ = st.columns([1, 1, 1])
        with submit_col:
            submitted = st.button(
                "Submit Questionnaire",
                type="primary",
                on_click=_normalize_measurement_inputs,
                use_container_width=False,
            )

    if submitted:
        warnings = []
        parsed_height = None
        parsed_weight = None
        try:
            parsed_height = _parse_measurement(
                height_input, height_label, height_min, height_max
            )
        except ValueError as error:
            warnings.append(str(error))
        try:
            parsed_weight = _parse_measurement(
                weight_input, weight_label, weight_min, weight_max
            )
        except ValueError as error:
            warnings.append(str(error))
        if body_fat_pct is not None:
            try:
                body_fat_pct = _parse_measurement(
                    str(body_fat_pct), "Body Fat %", 3, 80
                )
            except ValueError as error:
                warnings.append(str(error))
        if sessions_per_week > 0 and duration_warning:
            warnings.append(duration_warning)
        if (
            sessions_per_week > 0
            and not duration_warning
            and not session_duration_input.strip()
        ):
            warnings.append("Average time per workout must be a whole number.")
        if daily_steps_option == "Custom amount" and custom_steps_warning:
            warnings.append(custom_steps_warning)
        if daily_steps is None and not (
            daily_steps_option == "Custom amount" and custom_daily_steps.strip()
        ):
            warnings.append("Enter your custom daily step count.")
        if warnings:
            for warning in warnings:
                st.toast(warning, icon="⚠️")
            return

        if measurement_units == "Metric":
            height_cm = parsed_height
            weight_kg = parsed_weight
        else:
            height_cm = float(
                _truncate_to_two_decimals(Decimal(str(parsed_height)) * Decimal("2.54"))
            )
            weight_kg = float(
                _truncate_to_two_decimals(
                    Decimal(str(parsed_weight)) / Decimal("2.2046226218")
                )
            )

        profile = UserProfile(
            age=age,
            sex=sex,
            height_cm=height_cm,
            weight_kg=weight_kg,
            body_fat_pct=body_fat_pct,
            occupation_type=occupation_type,
            daily_steps=daily_steps,
            exercise_sessions=exercise_sessions,
            occupation_hours_per_workday=occupation_hours,
            occupation_days_per_week=occupation_days,
            cooking_skill=cooking_skill,
            allergens=_normalize_allergens(allergens, other_allergen),
            diets=diets,
            fitness_goal=fitness_goal,
        )
        user_id = st.session_state.user["id"]
        db.save_profile(user_id, asdict(profile))
        db.mark_onboarding_complete(user_id)
        st.session_state.user["onboarding_complete"] = True
        st.rerun()  # the router in app.py now shows the diary
