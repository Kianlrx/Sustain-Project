# Manages personal metrics, allergen blocklists, macro target recalibration, and saved favorite recipes.
import streamlit as st

from services import db, targets as targets_service

ACTIVITY_LEVELS = ["Sedentary", "Lightly Active", "Moderately Active", "Very Active", "Athlete"]
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
    with st.form("profile_form"):
        weight = st.number_input("Weight (kg)", 30.0, 300.0, float(profile["weight_kg"]), step=0.5)
        activity = st.selectbox(
            "Weekly Exercise Activity",
            ACTIVITY_LEVELS,
            index=ACTIVITY_LEVELS.index(profile["activity_level"]),
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
                activity_level=activity,
                fitness_goal=goal,
                allergens=allergens + [o.strip() for o in other.split(",") if o.strip()],
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
