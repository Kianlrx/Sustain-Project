# Dashboard that shows:
# Macro progress bar
# Meal slots (Breakfast, Lunch, Dinner, Snacks)
# Logged items.
from datetime import date

import streamlit as st

from services import db, targets as targets_service

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


def _render_progress(targets, totals):
    st.subheader("Today's progress")
    cols = st.columns(4)
    for col, (label, key, unit) in zip(cols, NUTRIENTS):
        eaten, target = totals[key], targets[key]
        col.metric(label, f"{eaten} / {target} {unit}")
        col.progress(min(eaten / target, 1.0) if target else 0.0)
        left = target - eaten
        col.caption(f"{left} {unit} left" if left >= 0 else f"{-left} {unit} over")