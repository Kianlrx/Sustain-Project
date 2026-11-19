# Dashboard that shows:
# Macro progress bar
# Meal slots (Breakfast, Lunch, Dinner, Snacks)
# Logged items.
from datetime import date
from html import escape

import streamlit as st

from services import db, targets as targets_service
from views.food_search import (
    render_find_recipe_dialog,
    render_food_search_dialog,
    render_saved_recipes_dialog,
)
from views.dashboard import COLORS

MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]

DIARY_CARD_SHADOWS = """
<style>
    [data-testid="stAppViewContainer"] {
        background: #0e1117;
        color: #f8fafc;
    }
    .block-container {
        max-width: none;
        padding: 2rem clamp(1rem, 3vw, 2.5rem) 3rem;
    }
    .st-key-diary_summary_card {
        padding: 1rem 1.25rem;
        border: 1px solid #262d3d;
        border-radius: 10px;
        background: #161b24;
    }
    .st-key-diary_meal_breakfast,
    .st-key-diary_meal_lunch,
    .st-key-diary_meal_dinner,
    .st-key-diary_meal_snack {
        padding: .3rem .75rem;
        border: 1px solid #262d3d;
        border-radius: 6px;
        background: #161b24;
    }
    .st-key-diary_meal_breakfast button,
    .st-key-diary_meal_lunch button,
    .st-key-diary_meal_dinner button,
    .st-key-diary_meal_snack button {
        min-height: 2.6rem;
        justify-content: flex-start;
        border: 0;
        background: transparent;
        color: #f8fafc;
        text-align: left;
    }
    .st-key-diary_meal_breakfast button:hover,
    .st-key-diary_meal_lunch button:hover,
    .st-key-diary_meal_dinner button:hover,
    .st-key-diary_meal_snack button:hover {
        border: 0;
        background: #1d2432;
        color: #fff;
    }
    [class*="st-key-diary_foods_"] {
        margin: 0 .1rem .25rem;
        padding: .35rem .75rem;
        border: 1px solid #262d3d;
        border-top: 0;
        border-radius: 0 0 6px 6px;
        background: #11151d;
    }
    [class*="st-key-diary_addwrap_"] {
        align-items: flex-end;
        width: 100%;
    }
    [class*="st-key-diary_addwrap_"] [data-testid="stPopover"] {
        display: flex;
        justify-content: flex-end;
        width: 100%;
        padding-right: 0;
    }
    [class*="st-key-diary_addwrap_"] button {
        min-height: 1.9rem;
        padding: .1rem 1.1rem;
        justify-content: center;
        border: 0;
        border-radius: 999px;
        background: #ef4444;
        color: #fff;
        font-size: .82rem;
        font-weight: 600;
        box-shadow: 0 2px 8px rgba(239, 68, 68, .3);
    }
    [class*="st-key-diary_toggle_"] button:hover,
    [class*="st-key-diary_toggle_"] button:focus,
    [class*="st-key-diary_toggle_"] button:active {
        background: transparent;
        box-shadow: none;
        color: #f8fafc;
    }
    [class*="st-key-diary_chevron_"] button {
        justify-content: center;
        padding: 0;
    }
    [class*="st-key-diary_addwrap_"] button > div:has(> svg) {
        display: none;
    }
    [class*="st-key-diary_addwrap_"] button:hover {
        border: 0;
        background: #f25c5c;
        color: #fff;
    }
    [data-testid="stPopoverBody"] {
        min-width: 15rem;
        padding: .4rem;
        border: 1px solid #2b3347;
        border-radius: 12px;
        background: #1a2030;
        box-shadow: 0 12px 32px rgba(0, 0, 0, .45);
    }
    [class*="st-key-diary_menu_"] {
        gap: .1rem;
    }
    [class*="st-key-diary_menu_"] button {
        min-height: 2.4rem;
        justify-content: flex-start;
        gap: .6rem;
        padding: 0 .7rem;
        border: 0;
        border-radius: 8px;
        background: transparent;
        color: #e2e8f0;
        font-size: .92rem;
    }
    [class*="st-key-diary_menu_"] button:hover {
        background: #262e42;
        color: #fff;
    }
    [class*="st-key-diary_menu_"] button span[data-testid="stIconMaterial"] {
        font-size: 1.3rem;
    }
    [class*="st-key-diary_add_"][class*="_c-blue"] span[data-testid="stIconMaterial"] {
        color: #38bdf8;
    }
    [class*="st-key-diary_add_"][class*="_c-purple"] span[data-testid="stIconMaterial"] {
        color: #a78bfa;
    }
    [class*="st-key-diary_add_"][class*="_c-yellow"] span[data-testid="stIconMaterial"] {
        color: #fbbf24;
    }
    [class*="st-key-diary_add_"][class*="_c-red"] span[data-testid="stIconMaterial"] {
        color: #ff4b4b;
    }
    [class*="st-key-diary_add_"][class*="_c-green"] span[data-testid="stIconMaterial"] {
        color: #34d399;
    }
    .st-key-diary_meals_toolbar button {
        min-height: 2.25rem;
        border: 1px solid #343e54;
        background: #1d2432;
        color: #f8fafc;
    }
    .st-key-diary_meals_toolbar button:hover {
        border-color: #4b5876;
        background: #252e40;
        color: #fff;
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

    st.markdown(DIARY_CARD_SHADOWS, unsafe_allow_html=True)
    title_col, date_col = st.columns([3, 2], vertical_alignment="center")
    title_col.title("Today's Diary")
    date_col.markdown(
        f'<p style="margin:0;text-align:right;color:#94a3b8;">'
        f'{date.today().strftime("%A, %d %B %Y")}</p>',
        unsafe_allow_html=True,
    )
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
    elif active_dialog == "saved_foods":
        _render_saved_foods_dialog(user["id"])
    elif active_dialog == "custom":
        _render_custom_food_dialog(user["id"])

    expanded_keys = [_meal_expanded_key(slot) for slot in MEAL_SLOTS]
    for key in expanded_keys:
        st.session_state.setdefault(key, False)
    all_expanded = all(st.session_state[key] for key in expanded_keys)

    with st.container(key="diary_meals_toolbar"):
        heading, request_meal, expand_all = st.columns(
            [6, 1.8, 1.5], vertical_alignment="center"
        )
        heading.markdown(
            f'<div style="display:flex;align-items:center;gap:.75rem;">'
            f'<h2 style="margin:0;color:#f8fafc;font-size:1.25rem;'
            f'font-weight:700;">Meals</h2>'
            f'<span style="padding:.18rem .65rem;border:1px solid #262d3d;'
            f'border-radius:999px;background:#161b24;color:#8b95a5;'
            f'font-size:.78rem;">{len(entries)} '
            f'{"item" if len(entries) == 1 else "items"}</span></div>',
            unsafe_allow_html=True,
        )
        if request_meal.button(
            "Request a meal", key="diary_request_meal", use_container_width=True
        ):
            st.session_state.meal_request = {
                "slot": "Snack",
                "remaining": remaining,
            }
            st.rerun()
        with expand_all:
            if st.button(
                "Collapse All" if all_expanded else "Expand All",
                key="diary_expand_all",
                use_container_width=True,
            ):
                for key in expanded_keys:
                    st.session_state[key] = not all_expanded
                st.rerun()

    for slot in MEAL_SLOTS:
        slot_entries = [entry for entry in entries if entry["meal_slot"] == slot]
        _render_meal_slot(slot, slot_entries)


def _render_progress(targets, totals):
    with st.container(border=True, key="diary_summary_card"):
        calories, calorie_target = totals["calories"], targets["calories"]
        title, remaining = st.columns([3, 1], vertical_alignment="center")
        title.subheader("Daily Summary")
        calorie_remaining = calorie_target - calories
        remaining_text = (
            f"{calorie_remaining:,} kcal"
            if calorie_remaining >= 0
            else f"{abs(calorie_remaining):,} kcal over"
        )
        remaining.markdown(
            f'<p style="margin:0;text-align:right;color:#8b95a5;font-size:.8rem;">'
            f'Remaining: <strong style="color:#cbd5e1">{remaining_text}</strong></p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            _progress_label_markup(
                "Calories", f"{_progress_percentage(calories, calorie_target)}%"
            )
            + _progress_markup(calories, calorie_target, COLORS["calories"], "Calories"),
            unsafe_allow_html=True,
        )
        st.caption(f"{calories:,} / {calorie_target:,} kcal")
        macros = st.columns(3)
        for col, (label, key, unit) in zip(macros, NUTRIENTS[1:]):
            with col:
                color_key = {
                    "protein_g": "protein",
                    "carbs_g": "carbs",
                    "fat_g": "fat",
                }[key]
                percentage = _progress_percentage(totals[key], targets[key])
                col.markdown(
                    _progress_label_markup(label, f"{percentage}%")
                    + _progress_markup(
                        totals[key],
                        targets[key],
                        COLORS[color_key],
                        label,
                    ),
                    unsafe_allow_html=True,
                )
                col.caption(
                    f"{_format_nutrient(totals[key])} / "
                    f"{_format_nutrient(targets[key])}{unit}"
                )


def _format_nutrient(value):
    rounded = round(float(value), 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def _progress_percentage(value, target):
    return round(value / target * 100) if target else 0


def _progress_label_markup(label, percentage=None):
    percentage_markup = f"<span>{percentage}</span>" if percentage is not None else ""
    return (
        '<div style="display:flex; align-items:baseline; justify-content:'
        'space-between; gap:.5rem; margin-bottom:.35rem; color:#f8fafc; '
        'font-size:.95rem;">'
        f"<strong>{label}</strong>{percentage_markup}</div>"
    )


def _progress_markup(value, target, color, label):
    progress = min(max(value / target, 0.0), 1.0) if target else 0.0
    percent = progress * 100
    return (
        f'<div role="progressbar" aria-label="{label}" '
        f'aria-valuenow="{percent:.0f}" aria-valuemin="0" aria-valuemax="100" '
        'style="height:10px; overflow:hidden; border-radius:999px; '
        'background:#262d3d;">'
        f'<div style="width:{percent:.2f}%; height:100%; min-width:'
        f'{"2px" if progress else "0"}; border-radius:999px; background:{color};">'
        "</div></div>"
    )


def _meal_expanded_key(slot):
    return f"diary_meal_expanded_{slot.lower()}"


def _display_meal_slot(slot):
    return "Snacks" if slot == "Snack" else slot


ADD_MENU_OPTIONS = (
    ("Search Food", "food", ":material/search:", "blue"),
    ("Find a Recipe", "recipe", ":material/menu_book:", "purple"),
    ("Saved Recipes", "saved", ":material/bookmark:", "yellow"),
    ("Saved Foods", "saved_foods", ":material/favorite:", "red"),
    ("Custom Food", "custom", ":material/edit_note:", "green"),
)


def _render_add_menu(slot):
    slot_key = slot.lower()
    with st.container(key=f"diary_addwrap_{slot_key}"):
        with st.popover("Add", icon=":material/add:"):
            with st.container(key=f"diary_menu_{slot_key}"):
                for label, dialog, icon, color in ADD_MENU_OPTIONS:
                    if st.button(
                        label,
                        key=f"diary_add_{slot_key}_{dialog}_c-{color}",
                        icon=icon,
                        use_container_width=True,
                    ):
                        st.session_state.next_diary_dialog = dialog
                        st.session_state.diary_dialog_meal_slot = slot
                        st.rerun()


@st.dialog("Saved Foods", width="medium")
def _render_saved_foods_dialog(user_id):
    slot = st.session_state.get("diary_dialog_meal_slot", "Snack")
    st.caption(f"Foods you've logged before. Adding to {_display_meal_slot(slot)}.")
    foods = db.get_logged_foods(user_id)
    if not foods:
        st.info("No saved foods yet. Foods you log will show up here.")
    for index, food in enumerate(foods):
        with st.container(border=True):
            info, action = st.columns([5, 1.4], vertical_alignment="center")
            info.markdown(f"**{escape(food['food_name'])}**")
            info.caption(
                f"{food['calories']:,} kcal · P {food['protein_g']}g · "
                f"C {food['carbs_g']}g · F {food['fat_g']}g"
            )
            if action.button("Add", key=f"saved_food_add_{index}", icon=":material/add:"):
                db.add_food_entry(
                    user_id, date.today().isoformat(), slot, food["food_name"],
                    food["calories"], food["protein_g"], food["carbs_g"], food["fat_g"],
                )
                st.session_state.food_logged_message = (
                    f"Added {food['food_name']} to {_display_meal_slot(slot)}."
                )
                st.rerun()


@st.dialog("Custom Food", width="medium")
def _render_custom_food_dialog(user_id):
    slot = st.session_state.get("diary_dialog_meal_slot", "Snack")
    _render_quick_log(user_id, slot)


def _render_meal_slot(slot, entries):
    totals = {
        key: sum(entry[key] for entry in entries)
        for key in ("calories", "protein_g", "carbs_g", "fat_g")
    }
    slot_key = slot.lower()
    expanded_key = _meal_expanded_key(slot)
    expanded = st.session_state[expanded_key]
    meal_label = _display_meal_slot(slot)
    with st.container(key=f"diary_meal_{slot_key}"):
        name, add, summary, toggle = st.columns(
            [9.35, 0.75, 1.0, 0.3], vertical_alignment="center"
        )
        toggle_clicked = name.button(
            meal_label,
            key=f"diary_toggle_{slot_key}",
            use_container_width=True,
        )
        with add:
            _render_add_menu(slot)
        summary.markdown(
            _meal_summary_markup(totals, bool(entries)),
            unsafe_allow_html=True,
        )
        if toggle.button(
            "",
            icon=(
                ":material/keyboard_arrow_up:"
                if expanded
                else ":material/keyboard_arrow_down:"
            ),
            key=f"diary_chevron_{slot_key}",
            use_container_width=True,
        ):
            toggle_clicked = True
        if toggle_clicked:
            st.session_state[expanded_key] = not expanded
            st.rerun()

    if expanded:
        with st.container(key=f"diary_foods_{slot_key}"):
            if not entries:
                st.caption("No foods logged yet.")
                return
            for entry in entries:
                name, nutrition = st.columns([1.2, 3], vertical_alignment="center")
                name.markdown(f"**{escape(entry['food_name'])}**")
                nutrition.caption(
                    f"{entry['calories']:,} kcal  ·  "
                    f"{entry['protein_g']}g protein  ·  "
                    f"{entry['carbs_g']}g carbs  ·  {entry['fat_g']}g fat"
                )


def _meal_summary_markup(totals, has_entries):
    color = "#cbd5e1" if has_entries else "#8b95a5"
    values = (
        f"{totals['calories']:,} kcal",
        f"{_format_nutrient(totals['protein_g'])}p",
        f"{_format_nutrient(totals['carbs_g'])}c",
        f"{_format_nutrient(totals['fat_g'])}f",
    )
    stats = " <span style='color:#525d73'>·</span> ".join(values)
    return (
        f"<div style='text-align:right;color:{color};font-size:.8rem;"
        f"font-variant-numeric:tabular-nums;white-space:nowrap;transform:translateY(-8px)'>{stats}</div>"
    )

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
