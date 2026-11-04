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

    # A meal request replaces the diary until the user goes back.
    if st.session_state.get("meal_request"):
        _render_meal_request(st.session_state.meal_request)
        return

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

    remaining = {key: max(targets[key] - totals[key], 0) for _, key, _ in NUTRIENTS}

    st.subheader("Meals")
    with st.popover("Quick Log"):
        _render_quick_log()
    slot_cols = st.columns(2)
    for i, slot in enumerate(MEAL_SLOTS):
        with slot_cols[i % 2]:  # two slots per row
            slot_entries = [entry for entry in entries if entry["meal_slot"] == slot]
            _render_meal_slot(slot, slot_entries, remaining)


def _render_progress(targets, totals):
    st.subheader("Today's progress")
    cols = st.columns(4)
    for col, (label, key, unit) in zip(cols, NUTRIENTS):
        eaten, target = totals[key], targets[key]
        col.metric(label, f"{eaten} / {target} {unit}")
        col.progress(min(eaten / target, 1.0) if target else 0.0)
        left = target - eaten
        col.caption(f"{left} {unit} left" if left >= 0 else f"{-left} {unit} over")



def _render_meal_slot(slot, entries, remaining):
    with st.container(border=True):
        st.markdown(f"##### {slot}")
        if not entries:
            st.caption("Nothing logged yet.")
        for entry in entries:
            st.write(
                f"**{entry['food_name']}** · {entry['calories']} kcal · "
                f"P {entry['protein_g']}g · C {entry['carbs_g']}g · F {entry['fat_g']}g"
            )

        # Opens the meal prompt for this slot, passing on what's left of today's budget.
        if st.button("Request a meal", key=f"request_{slot}"):
            st.session_state.meal_request = {"slot": slot, "remaining": remaining}
            st.rerun()

def _render_quick_log():
    # Log a food item that was not suggested by the app. If box is empty it comes back as None.
    with st.form("quick_log"):
        name = st.text_input("Food name")
        slot = st.selectbox("Meal slot", MEAL_SLOTS)
        calories = st.number_input("Calories (kcal)", value=None, step=1)
        protein = st.number_input("Protein (g)", value=None, step=1)
        carbs = st.number_input("Carbs (g)", value=None, step=1)
        fat = st.number_input("Fat (g)", value=None, step=1)
        if st.form_submit_button("Log food"):
            numbers = [calories, protein, carbs, fat]
            if not name.strip() or None in numbers:
                st.error("Fill in every field.")
            elif min(numbers) < 0:
                st.error("Values can't be negative.")
            else:
                st.success(f"{name.strip()} is ready to log.")


def _render_meal_request(request):
    # Meal prompt flow placeholder.
    # The prompt can read the slot and remaining budget from st.session_state.meal_request.
    slot = request["slot"]
    st.title(f"{slot} request")
    st.subheader("Remaining budget for today")
    cols = st.columns(4)
    for col, (label, key, unit) in zip(cols, NUTRIENTS):
        col.metric(label, f"{request['remaining'][key]} {unit}")
    st.info("Meal suggestions will appear here once the meal prompt is built.")
    if st.button("Back to diary"):
        del st.session_state.meal_request
        st.rerun()