import re
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

import streamlit as st
from models.profile import UserProfile
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

</style>
"""


def _parse_measurement(value: str, label: str, minimum: int, maximum: int) -> float | None:
    value = value.strip()
    if not re.fullmatch(r"(?:\d+(?:\.\d{0,2})?|\.\d{1,2})", value):
        st.error(f"{label} must be a number with no more than 2 decimal places.")
        return None

    measurement = Decimal(value)
    if not minimum <= measurement <= maximum:
        st.error(f"{label} must be between {minimum} and {maximum}.")
        return None

    return float(measurement)


def _normalize_measurement_inputs() -> None:
    for key in ("height_cm", "weight_kg"):
        value = st.session_state.get(key, "").strip()
        if re.fullmatch(r"(?:\d+(?:\.\d{0,2})?|\.\d{1,2})", value):
            st.session_state[key] = format(Decimal(value).normalize(), "f")


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
    st.session_state.setdefault("height_cm", "175")
    st.session_state.setdefault("weight_kg", "75")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 🧬 Body Metrics")
        age = st.number_input("Age", min_value=15, max_value=100, value=25)
        sex = st.selectbox("Biological Sex", ["Male", "Female"])
        height_cm = st.text_input("Height (cm)", key="height_cm")
        weight_kg = st.text_input("Weight (kg)", key="weight_kg")

        use_body_fat = st.checkbox("I know my Body Fat %")
        body_fat_pct = None
        if use_body_fat:
            body_fat_pct = st.number_input(
                "Body Fat %",
                min_value=3.0,
                max_value=60.0,
                value=18.0,
                format="%.15g",
            )

        st.markdown("##### ❌ Allergies & Dietary Restrictions")
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
            "Select any allergens or dietary exclusions to block from recipes:"
        )
        allergens = st.multiselect(
            allergen_label,
            allergen_options,
            key="allergens",
        )
        other_allergen = ""
        if "Other" in allergens:
            other_allergen = st.text_input(
                "Other allergen or dietary restriction",
                placeholder="Enter your restriction",
                key="other_allergen",
            )

    with col2:
        st.markdown("##### 🏃 Lifestyle & Fitness Goals")
        session_columns = (
            st.columns(2)
            if st.session_state.get("training_sessions_per_week", 3) > 0
            else [st.container()]
        )
        with session_columns[0]:
            sessions_per_week = st.slider(
                "Training sessions per week",
                min_value=0,
                max_value=14,
                value=3,
                step=1,
                help="Count the workouts you typically complete in a week.",
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
                        "These are broad calorie-expenditure categories. The calculator "
                        "uses representative MET estimates (weight training 3.5, "
                        "endurance 6.8, interval training 8.0); actual expenditure "
                        "depends on body weight, pace, and effort."
                    ),
                    key="training_type",
                )
            session_duration = st.number_input(
                "Average time per workout (minutes)",
                min_value=10,
                max_value=240,
                value=60,
                step=5,
                key="training_duration_minutes",
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
            help=(
                "**Desk Job:** Mostly seated computer work (about 1.3 MET).\n\n"
                "**Standing:** Standing with light tasks (about 1.8 MET).\n\n"
                "**Active Work:** Moderate walking at work (about 3.8 MET).\n\n"
                "**Heavy Labor:** Heavy manual work (about 6.5 MET)."
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
                st.selectbox(
                    "Estimated Daily Step Count",
                    step_count_options,
                    help=(
                        "**Less than 2,500:** Fewer than 2,500 steps per day.\n\n"
                        "**2,500 - 5,000:** Between 2,500 and 5,000 steps per day.\n\n"
                        "**5,000 - 7,500:** Between 5,000 and 7,500 steps per day.\n\n"
                        "**7,500 - 10,000:** Between 7,500 and 10,000 steps per day.\n\n"
                        "**More than 10,000:** More than 10,000 steps per day.\n\n"
                        "**Custom amount:** Enter your own daily step count."
                    ),
                    key="daily_steps_option",
                )
            with custom_steps_col:
                custom_daily_steps = st.number_input(
                    "Custom amount",
                    min_value=0,
                    max_value=50000,
                    step=1,
                    value=None,
                    key="custom_daily_steps",
                    placeholder="Steps per day",
                )
            daily_steps = custom_daily_steps
        else:
            daily_steps_option = st.selectbox(
                "Estimated Daily Step Count",
                step_count_options,
                help=(
                    "**Less than 2,500:** Fewer than 2,500 steps per day.\n\n"
                    "**2,500 - 5,000:** Between 2,500 and 5,000 steps per day.\n\n"
                    "**5,000 - 7,500:** Between 5,000 and 7,500 steps per day.\n\n"
                    "**7,500 - 10,000:** Between 7,500 and 10,000 steps per day.\n\n"
                    "**More than 10,000:** More than 10,000 steps per day.\n\n"
                    "**Custom amount:** Enter your own daily step count."
                ),
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

    _, submit_col = st.columns([3, 1])
    with submit_col:
        submitted = st.button(
            "Submit Questionnaire",
            on_click=_normalize_measurement_inputs,
            use_container_width=True,
        )

    if submitted:
        parsed_height_cm = _parse_measurement(height_cm, "Height (cm)", 100, 250)
        parsed_weight_kg = _parse_measurement(weight_kg, "Weight (kg)", 30, 300)
        if parsed_height_cm is None or parsed_weight_kg is None:
            return
        if daily_steps is None:
            st.error("Enter your custom daily step count.")
            return
        if "Other" in allergens and not other_allergen.strip():
            st.error("Enter your other allergen or dietary restriction.")
            return

        profile = UserProfile(
            age=age,
            sex=sex,
            height_cm=parsed_height_cm,
            weight_kg=parsed_weight_kg,
            body_fat_pct=body_fat_pct,
            occupation_type=occupation_type,
            daily_steps=daily_steps,
            exercise_sessions=exercise_sessions,
            occupation_hours_per_workday=occupation_hours,
            occupation_days_per_week=occupation_days,
            cooking_skill=cooking_skill,
            allergens=[
                allergen
                for allergen in allergens
                if allergen != "Other"
            ]
            + ([other_allergen.strip()] if "Other" in allergens else []),
            fitness_goal=fitness_goal,
        )
        user_id = st.session_state.user["id"]
        db.save_profile(user_id, asdict(profile))
        db.mark_onboarding_complete(user_id)
        st.session_state.user["onboarding_complete"] = True
        st.rerun()  # the router in app.py now shows the diary
