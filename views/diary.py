# Dashboard that shows:
# Macro progress bar
# Meal slots (Breakfast, Lunch, Dinner, Snacks)
# Logged items.
from datetime import date

import streamlit as st

from services import db, targets as targets_service
from views.food_search import (
    render_find_recipe_dialog,
    render_food_search_dialog,
    render_saved_recipes_dialog,
)

MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]

DIARY_CARD_SHADOWS = """
<style>
    .st-key-diary_summary_card,
    [class*="st-key-diary_meal_"] {
        box-shadow: 0 4px 14px rgba(0, 0, 0, .18);
    }
</style>
"""

# (label, key in the targets dict, unit) for each progress bar
NUTRIENTS = [
    ("Calories", "calories", "kcal"),
    ("Protein", "protein_g", "g"),
    ("Carbs", "carbs_g", "g"),
    ("Fat", "fat_g", "g"),
]


def render_diary_page():
    user = st.session_state.user

    if st.session_state.get("meal_request"):
        _render_meal_request(st.session_state.meal_request)
        return

    _, diary, _ = st.columns([1, 1.4, 1])
    with diary:
        st.markdown(DIARY_CARD_SHADOWS, unsafe_allow_html=True)
        st.title("Today's Diary")
        st.caption(date.today().strftime("%A, %d %B %Y"))
        if message := st.session_state.pop("food_logged_message", None):
            st.success(message)

        targets = targets_service.recalibrate(user["id"])
        if targets is None:
            st.info("No targets yet. Complete the onboarding questionnaire first.")
            return

        entries = db.get_food_entries(user["id"], date.today().isoformat())
        totals = {key: sum(entry[key] for entry in entries) for _, key, _ in NUTRIENTS}
        _render_progress(targets, totals)

        remaining = {
            key: max(targets[key] - totals[key], 0) for _, key, _ in NUTRIENTS
        }

        active_dialog = st.session_state.pop("next_diary_dialog", None)
        if active_dialog == "food":
            render_food_search_dialog(user["id"])
        elif active_dialog == "recipe":
            render_find_recipe_dialog()
        elif active_dialog == "saved":
            render_saved_recipes_dialog(user["id"])

        st.subheader("Meals")
        for slot in MEAL_SLOTS:
            slot_entries = [entry for entry in entries if entry["meal_slot"] == slot]
            _render_meal_slot(slot, slot_entries, remaining, user["id"])


def _render_progress(targets, totals):
    with st.container(border=True, key="diary_summary_card"):
        calories, calorie_target = totals["calories"], targets["calories"]
        summary_title, summary_value = st.columns([1, 1])
        summary_title.subheader("Daily Summary")
        summary_title.caption("Calories")
        summary_value.write(f"{calories} of {calorie_target:,} kcal")
        st.progress(min(calories / calorie_target, 1.0) if calorie_target else 0.0)
        macros = st.columns(3)
        for col, (label, key, unit) in zip(macros, NUTRIENTS[1:]):
            with col:
                col.caption(label)
                col.progress(
                    min(totals[key] / targets[key], 1.0) if targets[key] else 0.0
                )
                col.write(f"{totals[key]} of {targets[key]}{unit}")


def _render_meal_slot(slot, entries, remaining, user_id):
    with st.container(border=True, key=f"diary_meal_{slot.lower()}"):
        meal_calories = sum(entry["calories"] for entry in entries)
        details, controls = st.columns([3, 2], vertical_alignment="center")
        with details:
            st.subheader(slot)
            if not entries:
                st.caption("Nothing logged yet.")
            for entry in entries:
                st.write(
                    f"**{entry['food_name']}** · {entry['calories']} kcal · "
                    f"P {entry['protein_g']}g · C {entry['carbs_g']}g · "
                    f"F {entry['fat_g']}g"
                )

        with controls:
            calories, add = st.columns([1, 1], vertical_alignment="center")
            calories.markdown(
                f"<div style='text-align:center'>{meal_calories} kcal</div>",
                unsafe_allow_html=True,
            )
            with add.popover("＋ Add"):
                for label, icon, dialog in (
                    ("Search Food", "🔍", "food"),
                    ("Find a Recipe", "📖", "recipe"),
                    ("Saved Recipes", "🔖", "saved"),
                ):
                    if st.button(
                        f"{icon}  {label}", key=f"{slot}_{dialog}_action"
                    ):
                        st.session_state.next_diary_dialog = dialog
                        st.session_state.diary_dialog_meal_slot = slot
                        st.rerun()
                with st.expander("Enter custom food"):
                    _render_quick_log(user_id, slot)
                if st.button("Request a meal", key=f"{slot}_request_meal_action"):
                    st.session_state.meal_request = {
                        "slot": slot,
                        "remaining": remaining,
                    }
                    st.rerun()

def _render_quick_log(user_id, meal_slot):
    # Log a food item that was not suggested by the app. If box is empty it comes back as None.
    key_prefix = f"quick_log_{meal_slot.lower()}"

    # Empty boxes after successful save before drawing again.
    if st.session_state.pop(f"{key_prefix}_saved", False):
        st.session_state[f"{key_prefix}_name"] = ""
        for field in ["calories", "protein", "carbs", "fat"]:
            key = f"{key_prefix}_{field}"
            st.session_state[key] = None

    with st.form(f"{key_prefix}_form"):
        name = st.text_input("Food name", key=f"{key_prefix}_name")
        slot = st.selectbox(
            "Meal slot", MEAL_SLOTS, index=MEAL_SLOTS.index(meal_slot),
            key=f"{key_prefix}_meal_slot",
        )
        calories = st.number_input(
            "Calories (kcal)", value=None, step=1, key=f"{key_prefix}_calories"
        )
        protein = st.number_input(
            "Protein (g)", value=None, step=1, key=f"{key_prefix}_protein"
        )
        carbs = st.number_input(
            "Carbs (g)", value=None, step=1, key=f"{key_prefix}_carbs"
        )
        fat = st.number_input(
            "Fat (g)", value=None, step=1, key=f"{key_prefix}_fat"
        )
        if st.form_submit_button("Log food"):
            numbers = [calories, protein, carbs, fat]
            if not name.strip() or None in numbers:
                st.error("Fill in every field.")
            elif min(numbers) < 0:
                st.error("Values can't be negative.")
            else:
                db.add_food_entry(
                    user_id, date.today().isoformat(), slot, name.strip(),
                    calories, protein, carbs, fat,
                )
                st.session_state[f"{key_prefix}_saved"] = True
                st.rerun()


def _render_meal_request(request):
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
