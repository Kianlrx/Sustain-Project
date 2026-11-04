# Dashboard that shows:
# Macro progress bar
# Meal slots (Breakfast, Lunch, Dinner, Snacks)
# Logged items.
from datetime import date

import streamlit as st

from services import db, targets as targets_service

MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]

# (label, key in the targets dict, unit) for each progress bar
NUTRIENTS = [
    ("Calories", "calories", "kcal"),
    ("Protein", "protein_g", "g"),
    ("Carbs", "carbs_g", "g"),
    ("Fat", "fat_g", "g"),
]


def render_diary_page():
    user = st.session_state.user
    st.title(f"Welcome back, {user['username']}")
    st.caption(date.today().strftime("%A, %d %B %Y"))

    # Same call as settings page
    targets = targets_service.recalibrate(user["id"])
    if targets is None:
        st.info("No targets yet. Complete the onboarding questionnaire first.")
        return

    entries = db.get_food_entries(user["id"], date.today().isoformat())
    totals = {key: sum(entry[key] for entry in entries) for _, key, _ in NUTRIENTS}
    _render_progress(targets, totals)

    st.subheader("Meals")
    slot_cols = st.columns(2)
    for i, slot in enumerate(MEAL_SLOTS):
        with slot_cols[i % 2]:  # two slots per row
            slot_entries = [entry for entry in entries if entry["meal_slot"] == slot]
            _render_meal_slot(user["id"], slot, slot_entries)


def _render_progress(targets, totals):
    st.subheader("Today's progress")
    cols = st.columns(4)
    for col, (label, key, unit) in zip(cols, NUTRIENTS):
        eaten, target = totals[key], targets[key]
        col.metric(label, f"{eaten} / {target} {unit}")
        col.progress(min(eaten / target, 1.0) if target else 0.0)
        left = target - eaten
        col.caption(f"{left} {unit} left" if left >= 0 else f"{-left} {unit} over")



def _render_meal_slot(user_id, slot, entries):
    with st.container(border=True):
        st.markdown(f"##### {slot}")
        if not entries:
            st.caption("Nothing logged yet.")
        for entry in entries:
            st.write(
                f"**{entry['food_name']}** · {entry['calories']} kcal · "
                f"P {entry['protein_g']}g · C {entry['carbs_g']}g · F {entry['fat_g']}g"
            )
        with st.popover("Log food"):
            _render_log_form(user_id, slot)


def _render_log_form(user_id, slot):
    # Manual entry for now but a food database search could replace this later.
    with st.form(f"log_{slot}", clear_on_submit=True):
        name = st.text_input("Food", key=f"{slot}_name")
        calories = st.number_input("Calories (kcal)", 0, 5000, 0, key=f"{slot}_calories")
        protein = st.number_input("Protein (g)", 0, 500, 0, key=f"{slot}_protein")
        carbs = st.number_input("Carbs (g)", 0, 500, 0, key=f"{slot}_carbs")
        fat = st.number_input("Fat (g)", 0, 500, 0, key=f"{slot}_fat")
        if st.form_submit_button("Add"):
            if not name.strip():
                st.error("Enter a food name.")
            else:
                db.add_food_entry(
                    user_id, date.today().isoformat(), slot, name.strip(),
                    calories, protein, carbs, fat,
                )
                st.rerun()