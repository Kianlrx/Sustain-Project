# Manages personal metrics, allergen blocklists, macro target recalibration, and saved favorite recipes.
import streamlit as st

from services import db, targets as targets_service
from services.tdee_engine import (
    DEFAULT_OCCUPATION_DAYS_PER_WEEK,
    DEFAULT_OCCUPATION_HOURS_PER_WORKDAY,
    OCCUPATION_METS,
    TRAINING_TYPE_METS,
    calculate_tdee,
)

FITNESS_GOALS = ["Fat Loss", "Muscle Gain", "Recomposition", "GLP-1 Support"]
ALLERGENS = ["Peanuts", "Tree Nuts", "Dairy", "Eggs", "Gluten", "Shellfish", "Soy", "Pork"]


def render_settings_page():
    user = st.session_state.user
    st.title("Profile & Settings")

    profile = db.get_profile(user["id"])
    if profile is None:
        st.info("No saved profile yet. Complete the onboarding questionnaire first.")
    else:
        _render_targets(user["id"])
        _render_profile_form(user["id"], profile)
    _render_change_password(user["id"])


def _render_targets(user_id):
    # Recalculate on every visit so targets always match the saved profile (SCRUM-95).
    current = targets_service.recalibrate(user_id)
    _, manual = db.get_targets(user_id)

    st.subheader("Daily targets")
    cols = st.columns(4)
    cols[0].metric("Calories", f"{current['calories']} kcal")
    cols[1].metric("Protein", f"{current['protein_g']} g")
    cols[2].metric("Carbs", f"{current['carbs_g']} g")
    cols[3].metric("Fat", f"{current['fat_g']} g")
    st.caption("Set by you." if manual else "Calculated from your profile. Not medical advice.")
    components = calculate_tdee(db.get_profile(user_id))
    st.subheader("Estimated TDEE breakdown")
    component_cols = st.columns(7)
    for column, label, key in zip(
        component_cols,
        (
            "BMR",
            "Work NEAT",
            "Step NEAT",
            "Total NEAT",
            "EAT",
            "TEF",
            "Maintenance TDEE",
        ),
        (
            "bmr_kcal",
            "occupation_non_step_neat_kcal",
            "step_neat_kcal",
            "neat_kcal",
            "eat_kcal",
            "tef_kcal",
            "tdee_kcal",
        ),
    ):
        column.metric(label, f"{components[key]} kcal")
    st.caption(
        "BMR uses body-fat % when provided; otherwise Mifflin-St Jeor. "
        "Occupational NEAT is based on work MET and time; step NEAT excludes "
        "reported work and exercise steps. "
        "EAT is the net-MET exercise estimate averaged over seven days. "
        "Maintenance TDEE uses maintenance macros for TEF; your calorie goal "
        "above may be adjusted for your selected goal. "
        f"The estimate used {components['step_count_used']:,} "
        "steps shown are the representative count used for your selected step range. "
        "Calories are estimates and may overlap if work steps are not reported."
    )
    for warning in components["warnings"]:
        st.warning(warning)

    with st.expander("Fine-tune targets by hand"):
        calories = st.number_input("Calories (kcal)", 1200, 6000, current["calories"], step=50)
        protein = st.number_input("Protein (g)", 0, 400, current["protein_g"])
        carbs = st.number_input("Carbs (g)", 0, 800, current["carbs_g"])
        fat = st.number_input("Fat (g)", 0, 300, current["fat_g"])
        left, right = st.columns(2)
        if left.button("Save my targets"):
            db.save_targets(
                user_id,
                {"calories": calories, "protein_g": protein, "carbs_g": carbs, "fat_g": fat},
                manual=True,
            )
            st.rerun()
        if manual and right.button("Go back to automatic targets"):
            db.save_targets(user_id, current, manual=False)
            targets_service.recalibrate(user_id)
            st.rerun()


def _render_profile_form(user_id, profile):
    st.subheader("Your details")
    exercise_sessions = profile.get("exercise_sessions") or []
    if "exercise_sessions" not in profile and profile.get("activity_level"):
        st.info(
            "Your saved profile uses the previous weekly activity scale. "
            "Add your typical sessions here to include structured exercise "
            "in your updated TDEE estimate."
        )
    session_count = min(
        14,
        round(sum(session.get("sessions_per_week", 0) for session in exercise_sessions)),
    )
    primary_session = exercise_sessions[0] if exercise_sessions else {}
    existing_type = primary_session.get("type")
    training_types = list(TRAINING_TYPE_METS)
    type_index = training_types.index(existing_type) if existing_type in training_types else 0
    occupation_types = list(OCCUPATION_METS)
    occupation_type = profile.get("occupation_type", occupation_types[0])
    occupation_index = (
        occupation_types.index(occupation_type)
        if occupation_type in occupation_types
        else 0
    )
    with st.form("profile_form"):
        weight = st.number_input("Weight (kg)", 30.0, 300.0, float(profile["weight_kg"]), step=0.5)
        sessions_per_week = st.slider(
            "Training sessions per week",
            min_value=0,
            max_value=14,
            value=session_count,
            step=1,
        )
        if sessions_per_week:
            session_type_col, duration_col = st.columns(2)
            with session_type_col:
                session_type = st.selectbox(
                    "Main workout type and intensity",
                    training_types,
                    index=type_index,
                    help=(
                        "Representative MET values: weight training 3.5 (low), "
                        "endurance 6.8 (medium), interval training 8.0 (high)."
                    ),
                )
            with duration_col:
                session_duration = st.number_input(
                    "Average session duration (minutes)",
                    min_value=10,
                    max_value=240,
                    value=max(
                        10,
                        min(240, int(primary_session.get("duration_minutes", 60))),
                    ),
                    step=5,
                )
        occupation =         st.selectbox(
            "Daily occupation movement",
            occupation_types,
            index=occupation_index,
        )
        goal = st.selectbox(
            "Primary Fitness Goal", FITNESS_GOALS, index=FITNESS_GOALS.index(profile["fitness_goal"])
        )
        known = [a for a in profile["allergens"] if a in ALLERGENS]
        others = [a for a in profile["allergens"] if a not in ALLERGENS]
        allergens = st.multiselect("Allergens and exclusions", ALLERGENS, default=known)
        other = st.text_input("Other exclusions (comma separated)", ", ".join(others))
        if st.form_submit_button("Save changes"):
            profile.update(
                weight_kg=weight,
                fitness_goal=goal,
                occupation_type=occupation,
                occupation_hours_per_workday=DEFAULT_OCCUPATION_HOURS_PER_WORKDAY[
                    occupation
                ],
                occupation_days_per_week=DEFAULT_OCCUPATION_DAYS_PER_WEEK,
                occupational_steps_per_workday=None,
                allergens=allergens + [o.strip() for o in other.split(",") if o.strip()],
                exercise_sessions=[
                    {
                        "type": session_type,
                        "met": TRAINING_TYPE_METS[session_type],
                        "duration_minutes": session_duration,
                        "sessions_per_week": sessions_per_week,
                    }
                ]
                if sessions_per_week
                else [],
            )
            db.save_profile(user_id, profile)
            targets_service.recalibrate(user_id)  # SCRUM-95: targets follow the new details
            st.success("Saved. Your targets have been updated.")
            st.rerun()


def _render_change_password(user_id):
    with st.expander("Change password"):
        current = st.text_input("Current password", type="password", key="pw_current")
        new = st.text_input("New password", type="password", key="pw_new")
        if st.button("Change password"):
            if len(new) < 6:
                st.error("The new password must be at least 6 characters.")
            elif db.change_password(user_id, current, new):
                st.success("Password changed.")
            else:
                st.error("Current password is wrong.")
