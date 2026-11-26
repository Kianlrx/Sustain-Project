# Manages personal metrics, allergen blocklists, macro target recalibration, and saved favorite recipes.
import streamlit as st

from models.profile import DIETARY_PREFERENCES
from services import db, targets as targets_service
from services.validation import (
    WEIGHT_MAX_KG,
    WEIGHT_MIN_KG,
    validate_manual_targets,
    validate_profile_settings,
)
from services.tdee_engine import (
    DEFAULT_OCCUPATION_DAYS_PER_WEEK,
    DEFAULT_OCCUPATION_HOURS_PER_WORKDAY,
    OCCUPATION_METS,
    TRAINING_TYPE_METS,
    WORK_STEPS_WARNING,
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
    _render_target_explanation(db.get_profile(user_id), manual)

    with st.expander("Fine-tune targets by hand"):
        calories = st.number_input("Calories (kcal)", 1200, 6000, current["calories"], step=50)
        protein = st.number_input("Protein (g)", 0, 400, current["protein_g"])
        carbs = st.number_input("Carbs (g)", 0, 800, current["carbs_g"])
        fat = st.number_input("Fat (g)", 0, 300, current["fat_g"])
        left, right = st.columns(2)
        if left.button("Save my targets"):
            chosen = {"calories": calories, "protein_g": protein, "carbs_g": carbs, "fat_g": fat}
            errors = validate_manual_targets(chosen)
            for error in errors:
                st.error(error)
            if not errors:
                db.save_targets(user_id, chosen, manual=True)
                st.rerun()
        if manual and right.button("Go back to automatic targets"):
            db.save_targets(user_id, current, manual=False)
            targets_service.recalibrate(user_id)
            st.rerun()


def _render_target_explanation(profile, manual):
    """Show how the automatic targets are worked out, one step at a time."""
    steps = targets_service.explain_targets(profile)
    targets = steps["targets"]
    with st.expander("How your targets are calculated"):
        if manual:
            st.info(
                "You set your targets by hand, so the app uses those. "
                "Below is what the automatic calculation would give."
            )
        if steps["bmr_method"] == "Katch-McArdle":
            bmr_formula = "Katch-McArdle: 370 + 21.6 x lean body mass (kg), because you gave a body-fat %"
        else:
            bmr_formula = (
                "Mifflin-St Jeor: 10 x weight (kg) + 6.25 x height (cm) - 5 x age, "
                "+5 for men or -161 for women"
            )
        st.markdown(
            f"**1. Resting burn (BMR): {steps['bmr_kcal']:,} kcal**  \n"
            f"The energy your body uses at rest. Formula: {bmr_formula}."
        )
        st.markdown(
            f"**2. Activity: {steps['tdee_kcal']:,} kcal a day (maintenance)**  \n"
            f"BMR {steps['bmr_kcal']:,} + daily movement {steps['neat_kcal']:,} "
            f"+ exercise {steps['eat_kcal']:,} + digesting food {steps['tef_kcal']:,} "
            f"= {steps['tdee_kcal']:,} kcal. "
            f"That is an activity multiplier of about x{steps['activity_multiplier']} on your BMR. "
            "Exercise is averaged over seven days."
        )
        change = round((steps["goal_modifier"] - 1) * 100)
        change_text = "no change" if change == 0 else f"{change:+d}%"
        goal_line = (
            f"**3. Goal adjustment ({steps['goal']}): {targets['calories']:,} kcal**  \n"
            f"{steps['tdee_kcal']:,} x {steps['goal_modifier']:.2f} ({change_text}) "
            f"= {steps['goal_adjusted_kcal']:,} kcal."
        )
        if steps["calorie_floor_applied"]:
            goal_line += (
                f" This is below the safe minimum, so it is raised to "
                f"{steps['calorie_floor']:,} kcal."
            )
        st.markdown(goal_line)
        st.markdown(
            "**4. Macros**  \n"
            f"Protein: 1.8 g per kg of body weight = {targets['protein_g']} g.  \n"
            f"Fat: 25% of calories / 9 kcal per g = {targets['fat_g']} g.  \n"
            f"Carbs: the calories left over / 4 kcal per g = {targets['carbs_g']} g."
        )
        components = calculate_tdee(profile)
        for warning in components["warnings"]:
            # Settings no longer asks for work steps, so don't warn about them.
            if warning != WORK_STEPS_WARNING:
                st.warning(warning)
        st.caption("These are estimates from standard formulas, not measurements or medical advice.")


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
        weight = st.number_input(
            "Weight (kg)",
            WEIGHT_MIN_KG,
            WEIGHT_MAX_KG,
            min(WEIGHT_MAX_KG, max(WEIGHT_MIN_KG, float(profile["weight_kg"]))),
            step=0.5,
        )
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
        occupation = st.selectbox(
            "Daily occupation movement",
            occupation_types,
            index=occupation_index,
        )
        goal = st.selectbox(
            "Primary Fitness Goal", FITNESS_GOALS, index=FITNESS_GOALS.index(profile["fitness_goal"])
        )
        measurement_units = st.selectbox(
            "Preferred measurement units",
            ["Metric", "Imperial"],
            index=0 if profile.get("measurement_units", "Metric") == "Metric" else 1,
        )
        known = [a for a in profile["allergens"] if a in ALLERGENS]
        others = [a for a in profile["allergens"] if a not in ALLERGENS]
        allergens = st.multiselect("Allergens and exclusions", ALLERGENS, default=known)
        other = st.text_input("Other exclusions (comma separated)", ", ".join(others))
        diets = st.multiselect(
            "Dietary preferences",
            DIETARY_PREFERENCES,
            default=profile.get("diets", []),
        )
        if st.form_submit_button("Save changes"):
            errors = validate_profile_settings(
                weight,
                sessions_per_week,
                session_duration if sessions_per_week else None,
                occupation,
                goal,
                measurement_units,
                other,
                occupations=occupation_types,
                goals=FITNESS_GOALS,
            )
            for error in errors:
                st.error(error)
            if errors:
                return
            profile.update(
                weight_kg=weight,
                measurement_units=measurement_units,
                fitness_goal=goal,
                occupation_type=occupation,
                occupation_hours_per_workday=DEFAULT_OCCUPATION_HOURS_PER_WORKDAY[
                    occupation
                ],
                occupation_days_per_week=DEFAULT_OCCUPATION_DAYS_PER_WEEK,
                # Work steps are no longer asked for; clear any old saved value.
                occupational_steps_per_workday=None,
                allergens=allergens + [o.strip() for o in other.split(",") if o.strip()],
                diets=diets,
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
