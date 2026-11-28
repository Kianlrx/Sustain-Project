# Dashboard that shows:
# Macro progress bar
# Meal slots (Breakfast, Lunch, Dinner, Snacks)
# Logged items.
from datetime import date, datetime
from html import escape

import streamlit as st

from services import db, recipe_finder, targets as targets_service
from services.validation import validate_food_entry
from views.find_recipe import render_find_recipe_page
from views.food_search import (
    render_food_search_dialog,
    render_saved_recipes_dialog,
)
from views.dashboard import COLORS

MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]
ADD_COLUMN_WIDTH = 76
ICON_BUTTON_WIDTH = 40

DIARY_CARD_SHADOWS = """
<style>
    .block-container {
        max-width: 1440px;
        padding: 2rem clamp(1rem, 3vw, 2rem) 3rem;
    }
    .st-key-diary_date h1 {
        padding: 0;
    }
    .st-key-diary_summary_card {
        padding: 20px 24px;
        border: 1px solid var(--sustain-border);
        border-radius: 16px;
        background: var(--sustain-surface);
    }
    .st-key-diary_summary_card strong {
        font-weight: 500;
    }
    .diary-over-target {
        color: var(--sustain-negative);
    }
    [class*="st-key-diary_meal_card_"] {
        border: 1px solid var(--sustain-border);
        border-radius: 12px;
        background: var(--sustain-surface);
    }
    .st-key-diary_meal_breakfast,
    .st-key-diary_meal_lunch,
    .st-key-diary_meal_dinner,
    .st-key-diary_meal_snack {
        padding: 4px 12px;
    }
    .st-key-diary_meal_breakfast button,
    .st-key-diary_meal_lunch button,
    .st-key-diary_meal_dinner button,
    .st-key-diary_meal_snack button {
        min-height: 2.6rem;
        justify-content: flex-start;
        border: 0;
        background: transparent;
        color: var(--sustain-text);
        text-align: left;
    }
    .st-key-diary_meal_breakfast button:hover,
    .st-key-diary_meal_lunch button:hover,
    .st-key-diary_meal_dinner button:hover,
    .st-key-diary_meal_snack button:hover {
        border: 0;
        background: var(--sustain-hover);
        color: var(--sustain-text);
    }
    [class*="st-key-diary_foods_"] {
        padding: 4px 12px;
        border-top: 1px solid var(--sustain-border);
    }
    .diary-food-divider {
        border-top: 1px solid var(--sustain-border);
    }
    .diary-food-name {
        line-height: 1.2;
        overflow-wrap: anywhere;
    }
    .diary-food-quantity {
        margin-top: 4px;
        color: var(--sustain-muted);
        font-size: .8125rem;
        font-variant-numeric: tabular-nums;
        line-height: 1.2;
    }
    [class*="st-key-diary_addwrap_"] [data-testid="stPopoverButton"] {
        min-height: 32px;
        padding: 4px 12px;
        white-space: nowrap;
        justify-content: center;
        border: 0;
        border-radius: 8px;
        background: var(--sustain-accent);
        color: #fff;
        font-size: .8125rem;
        font-weight: 500;
        box-shadow: none;
        transition: background-color .15s cubic-bezier(.22, 1, .36, 1);
    }
    [class*="st-key-diary_toggle_"] button:hover,
    [class*="st-key-diary_toggle_"] button:focus,
    [class*="st-key-diary_toggle_"] button:active {
        background: transparent;
        box-shadow: none;
        color: var(--sustain-text);
    }
    [class*="st-key-diary_chevron_"] button {
        min-height: 40px;
        justify-content: center;
        padding: 0;
    }
    [class*="st-key-diary_chevron_"] [data-testid="stIconMaterial"] {
        -webkit-text-stroke: .45px currentColor;
    }
    [class*="st-key-diary_addwrap_"] [data-testid="stPopoverButton"] > div > [aria-hidden="true"] {
        display: none;
    }
    [class*="st-key-diary_toggle_"] button {
        min-height: 0;
        padding: 0;
    }
    [class*="st-key-diary_toggle_"] button p {
        font-size: 1.0625rem;
        font-weight: 500;
    }
    [class*="st-key-diary_edit_"] button,
    [class*="st-key-diary_delete_"] button {
        border: 0;
        background: transparent;
    }
    [class*="st-key-diary_edit_"] button:hover {
        background: var(--sustain-hover);
    }
    [class*="st-key-diary_delete_"] button:hover {
        background: var(--sustain-negative-soft);
        color: var(--sustain-negative);
    }
    [class*="st-key-diary_edit_"] [data-testid="stPopoverButton"] {
        height: 40px;
        justify-content: center;
        padding: 0;
    }
    [class*="st-key-diary_edit_"] [data-testid="stPopoverButton"] > div > [aria-hidden="true"] {
        display: none;
    }
    [data-testid="stPopoverBody"]:has([class*="st-key-diary_food_editor_"]) {
        width: 310px;
        min-width: 0 !important;
        padding: .65rem;
    }
    @media (max-width: 480px) {
        [data-testid="stPopoverBody"]:has([class*="st-key-diary_food_editor_"]) {
            width: min(310px, calc(100vw - 4rem));
        }
    }
    .block-container h1 {
        padding-top: 0;
    }
    [class*="st-key-diary_addwrap_"] [data-testid="stPopoverButton"]:hover {
        border: 0;
        background: var(--sustain-accent-hover);
        color: #fff;
    }
    [data-testid="stPopoverBody"]:has([class*="st-key-diary_menu_"]) {
        min-width: 0 !important;
        width: max-content;
        /* Streamlit aligns the left edges. Offset by half the 76px trigger width. */
        translate: calc(38px - 50%) 5px;
        padding: 0 5px !important;
        border: 1px solid var(--sustain-border);
        border-radius: 12px;
        box-shadow: var(--sustain-popover-shadow);
    }
    [data-testid="stPopoverBody"] [class*="st-key-diary_menu_"] [data-testid="stButton"] button {
        min-height: 2rem;
        justify-content: flex-start;
        gap: .45rem;
        padding: 0 !important;
        border: 0;
        border-radius: 8px;
        background: transparent;
        font-size: .92rem;
    }
    [data-testid="stPopoverBody"] [class*="st-key-diary_menu_"] [data-testid="stButton"] button:hover {
        background: color-mix(in srgb, currentColor 8%, transparent);
    }
    [class*="st-key-diary_menu_"] button span[data-testid="stIconMaterial"] {
        font-size: 1.125rem;
        color: inherit;
        opacity: .8;
    }
    .st-key-diary_request_meal button {
        min-height: 38px;
        padding: 4px 10px;
        gap: 6px;
        border: 1px solid var(--sustain-border-strong);
        border-radius: 8px;
        background: var(--sustain-raised);
        color: var(--sustain-text);
        white-space: nowrap;
    }
    .st-key-diary_request_meal button p {
        font-size: .875rem;
        font-weight: 600;
    }
    .st-key-diary_request_meal button:hover {
        border-color: var(--sustain-border);
        background: var(--sustain-hover-strong);
        color: var(--sustain-text);
    }
    .st-key-diary_request_meal [data-testid="stIconMaterial"] {
        flex-shrink: 0;
        color: var(--sustain-text);
        font-size: 1.5rem;
        line-height: 1;
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
        render_find_recipe_page(st.session_state.meal_request)
        return

    st.html(DIARY_CARD_SHADOWS)
    today = date.today()
    saved_date = f"diary_selected_date_{user['id']}"
    picker_key = f"diary_date_picker_{user['id']}"
    st.session_state.setdefault(picker_key, st.session_state.get(saved_date, today))
    with st.container(
        key="diary_date", horizontal=True, horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        title = st.empty()
        selected = st.date_input(
            "Diary date", min_value=date(1900, 1, 1), max_value=today,
            key=picker_key, format="DD/MM/YYYY", label_visibility="collapsed",
            width=155,
        )
    if selected is None:
        selected = st.session_state.get(saved_date, today)
    else:
        st.session_state[saved_date] = selected
    title.title(
        "Today's Diary" if selected == today else selected.strftime("%A, %d %B"),
        anchor=False,
        width="content",
    )
    log_date = selected.isoformat()

    targets = targets_service.recalibrate(user["id"])
    if targets is None:
        st.info("No targets yet. Complete the onboarding questionnaire first.")
        return

    entries = db.get_food_entries(user["id"], log_date)
    totals = {key: sum(entry[key] for entry in entries) for _, key, _ in NUTRIENTS}
    _render_progress(targets, totals)

    remaining = {
        key: max(targets[key] - totals[key], 0) for _, key, _ in NUTRIENTS
    }

    active_dialog = st.session_state.pop("next_diary_dialog", None)
    if active_dialog == "food":
        render_food_search_dialog(user["id"], log_date)
    elif active_dialog == "recipe":
        # "+ Add > Find a recipe" opens the Find a Recipe page for that meal
        _open_find_recipe(
            st.session_state.get("diary_dialog_meal_slot", "Snack"), targets, remaining, log_date,
        )
    elif active_dialog == "saved":
        render_saved_recipes_dialog(user["id"])
    elif active_dialog == "saved_foods":
        _render_saved_foods_dialog(user["id"], log_date)
    elif active_dialog == "custom":
        _render_custom_food_dialog(user["id"], log_date)

    with st.container(
        key="diary_meals_toolbar", horizontal=True,
        vertical_alignment="center", gap="small",
    ):
        st.html(
            '<h2 style="margin:0;padding:0;color:var(--sustain-text);font-size:1.375rem;'
            'font-weight:500;">Meals</h2>',
            width="content",
        )
        if st.button(
            "Find a recipe", key="diary_request_meal", icon=":material/chef_hat:",
            width="content",
        ):
            _open_find_recipe(
                recipe_finder.default_slot(datetime.now().hour), targets, remaining, log_date,
            )

    for slot in MEAL_SLOTS:
        slot_entries = [entry for entry in entries if entry["meal_slot"] == slot]
        _render_meal_slot(user["id"], log_date, slot, slot_entries)


def _render_progress(targets, totals):
    with st.container(border=True, key="diary_summary_card"):
        calories, calorie_target = totals["calories"], targets["calories"]
        title, remaining = st.columns([3, 1], vertical_alignment="center")
        title.subheader("Daily summary", anchor=False)
        calorie_remaining = calorie_target - calories
        remaining_text = (
            f"{calorie_remaining:,} kcal"
            if calorie_remaining >= 0
            else f"{abs(calorie_remaining):,} kcal over"
        )
        remaining.markdown(
            f'<p style="margin:0;text-align:right;color:var(--sustain-muted);font-size:.8rem;">'
            f'Remaining: <strong style="color:var(--sustain-text)">{remaining_text}</strong></p>',
            unsafe_allow_html=True,
        )
        st.markdown(
            _progress_label_markup(
                "Calories", f"{_progress_percentage(calories, calorie_target)}%",
                over_target=calories > calorie_target,
            )
            + _progress_markup(calories, calorie_target, COLORS["calories"], "Calories"),
            unsafe_allow_html=True,
        )
        st.caption(
            f"{_progress_value_markup(f'{calories:,}', calories > calorie_target)} / {calorie_target:,} kcal",
            unsafe_allow_html=True,
        )
        macros = st.columns(3)
        for col, (label, key, unit) in zip(macros, NUTRIENTS[1:]):
            with col:
                color_key = {
                    "protein_g": "protein",
                    "carbs_g": "carbs",
                    "fat_g": "fat",
                }[key]
                percentage = _progress_percentage(totals[key], targets[key])
                over_target = totals[key] > targets[key]
                col.markdown(
                    _progress_label_markup(label, f"{percentage}%", over_target=over_target)
                    + _progress_markup(
                        totals[key],
                        targets[key],
                        COLORS[color_key],
                        label,
                    ),
                    unsafe_allow_html=True,
                )
                col.caption(
                    f"{_progress_value_markup(_format_nutrient(totals[key]), over_target)} / "
                    f"{_format_nutrient(targets[key])}{unit}",
                    unsafe_allow_html=True,
                )


def _format_nutrient(value):
    rounded = round(float(value), 1)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.1f}"


def _progress_percentage(value, target):
    return round(value / target * 100) if target else 0


def _progress_value_markup(text, over_target):
    css_class = ' class="diary-over-target"' if over_target else ""
    return f"<span{css_class}>{text}</span>"


def _progress_label_markup(label, percentage=None, *, over_target=False):
    percentage_markup = _progress_value_markup(percentage, over_target) if percentage is not None else ""
    return (
        '<div style="display:flex; align-items:baseline; justify-content:'
        'space-between; gap:8px; margin-bottom:8px; color:var(--sustain-text); '
        'font-size:.9375rem; font-variant-numeric:tabular-nums;">'
        f"<strong>{label}</strong>{percentage_markup}</div>"
    )


def _progress_markup(value, target, color, label):
    progress = min(max(value / target, 0.0), 1.0) if target else 0.0
    percent = progress * 100
    return (
        f'<div role="progressbar" aria-label="{label}" '
        f'aria-valuenow="{percent:.0f}" aria-valuemin="0" aria-valuemax="100" '
        'style="height:8px; overflow:hidden; border-radius:4px; '
        'background:var(--sustain-raised);">'
        f'<div style="width:{percent:.2f}%; height:100%; min-width:'
        f'{"2px" if progress else "0"}; border-radius:4px; background:{color};">'
        "</div></div>"
    )


def _meal_expanded_key(slot):
    return f"diary_meal_expanded_{slot.lower()}"


def _display_meal_slot(slot):
    return "Snacks" if slot == "Snack" else slot


ADD_MENU_OPTIONS = (
    ("Search food", "food", ":material/search:", "blue"),
    ("Find a recipe", "recipe", ":material/menu_book:", "purple"),
    ("Saved recipes", "saved", ":material/bookmark:", "yellow"),
    ("Saved foods", "saved_foods", ":material/favorite:", "red"),
    ("Custom food", "custom", ":material/edit_note:", "green"),
)


def _render_add_menu(slot):
    slot_key = slot.lower()
    with st.container(
        key=f"diary_addwrap_{slot_key}", width=ADD_COLUMN_WIDTH,
        horizontal=True, horizontal_alignment="center",
    ):
        with st.popover("+ Add", width=ADD_COLUMN_WIDTH):
            with st.container(key=f"diary_menu_{slot_key}", gap=None):
                for label, dialog, icon, color in ADD_MENU_OPTIONS:
                    if st.button(
                        label,
                        key=f"diary_add_{slot_key}_{dialog}_c-{color}",
                        icon=icon,
                        type="tertiary",
                        use_container_width=True,
                    ):
                        st.session_state.next_diary_dialog = dialog
                        st.session_state.diary_dialog_meal_slot = slot
                        st.rerun()


@st.dialog("Saved foods", width="medium")
def _render_saved_foods_dialog(user_id, log_date):
    slot = st.session_state.get("diary_dialog_meal_slot", "Snack")
    st.caption(f"Foods you've logged before. Adding to {_display_meal_slot(slot)}.")
    foods = db.get_logged_foods(user_id)
    if not foods:
        st.info("No saved foods yet. Foods you log will show up here.")
    for index, food in enumerate(foods):
        with st.container(border=True, key=f"bordered_card_saved_food_{index}"):
            info, action = st.columns([5, 1.4], vertical_alignment="center")
            info.markdown(f"**{escape(food['food_name'])}**")
            info.caption(
                f"{food['calories']:,} kcal · P {food['protein_g']}g · "
                f"C {food['carbs_g']}g · F {food['fat_g']}g"
            )
            if action.button("Add", key=f"saved_food_add_{index}", icon=":material/add:"):
                db.add_food_entry(
                    user_id, log_date, slot, food["food_name"],
                    food["calories"], food["protein_g"], food["carbs_g"], food["fat_g"],
                    quantity=food["quantity"], quantity_unit=food["quantity_unit"],
                )
                st.rerun()


@st.dialog("Custom food", width="medium")
def _render_custom_food_dialog(user_id, log_date):
    slot = st.session_state.get("diary_dialog_meal_slot", "Snack")
    _render_quick_log(user_id, slot, log_date)


def _render_meal_slot(user_id, log_date, slot, entries):
    totals = {
        key: sum(entry[key] for entry in entries)
        for key in ("calories", "protein_g", "carbs_g", "fat_g")
    }
    slot_key = slot.lower()
    expanded_key = _meal_expanded_key(slot)
    expanded = st.session_state.get(expanded_key, False)
    meal_label = _display_meal_slot(slot)
    with st.container(key=f"diary_meal_card_{slot_key}", gap=None):
        with st.container(
            key=f"diary_meal_{slot_key}", horizontal=True, horizontal_alignment="distribute",
            vertical_alignment="center", gap="small",
        ):
            with st.container(width="content", gap=None):
                toggle_clicked = st.button(
                    meal_label,
                    key=f"diary_toggle_{slot_key}",
                )
                st.html(_meal_summary_markup(totals, bool(entries)), width="content")
            with st.container(horizontal=True, vertical_alignment="center", width="content", gap="small"):
                _render_add_menu(slot)
                if st.button(
                    "",
                    icon=(
                        ":material/keyboard_arrow_up:"
                        if expanded
                        else ":material/keyboard_arrow_down:"
                    ),
                    key=f"diary_chevron_{slot_key}",
                    width=ICON_BUTTON_WIDTH,
                ):
                    toggle_clicked = True
            if toggle_clicked:
                st.session_state[expanded_key] = not expanded
                st.rerun()

        if expanded:
            with st.container(key=f"diary_foods_{slot_key}", gap="xxsmall"):
                if not entries:
                    st.caption("No foods logged yet.")
                    return
                for index, entry in enumerate(entries):
                    if index:
                        st.html('<div class="diary-food-divider" aria-hidden="true"></div>')
                    _render_food_entry(user_id, log_date, entry)


def _render_food_entry(user_id, log_date, entry):
    entry_id = entry["id"]
    name, nutrition, actions_col = st.columns([3, 5, 2], vertical_alignment="center")
    amount = f"{entry['quantity']:,.2f}".rstrip("0").rstrip(".")
    unit = escape(entry["quantity_unit"])
    name.html(
        f'<div class="diary-food-name"><strong>{escape(entry["food_name"])}</strong>'
        f'<div class="diary-food-quantity">{amount}&nbsp;{unit}</div></div>'
    )
    nutrition.caption(
        f"{entry['calories']:,} kcal  ·  {entry['protein_g']}g protein  ·  "
        f"{entry['carbs_g']}g carbs  ·  {entry['fat_g']}g fat"
    )
    actions = actions_col.container(horizontal=True, horizontal_alignment="right", gap="xxsmall")
    editor = actions.popover(
        "", icon=":material/edit:", width=ICON_BUTTON_WIDTH,
        key=f"diary_edit_{entry_id}", on_change="rerun",
    )
    if editor.open:
        with editor:
            _render_food_editor(user_id, log_date, entry)
    if actions.button(
        "", icon=":material/close:", key=f"diary_delete_{entry_id}",
    ):
        db.delete_food_entry(user_id, log_date, entry_id)
        st.rerun()


def _render_food_editor(user_id, log_date, entry):
    entry_id = entry["id"]
    editor_key = f"diary_edit_{entry_id}"
    quantity_key = f"diary_food_quantity_{entry_id}"
    meal_key = f"diary_food_meal_{entry_id}"

    def close():
        st.session_state[editor_key] = False

    def save():
        meal_slot = st.session_state[meal_key]
        db.update_food_quantity(
            user_id, log_date, entry_id, st.session_state[quantity_key], meal_slot=meal_slot,
        )
        st.session_state[_meal_expanded_key(meal_slot)] = True
        close()

    with st.container(key=f"diary_food_editor_{entry_id}"):
        with st.form(f"diary_quantity_form_{entry_id}", border=False, enter_to_submit=False):
            with st.container(horizontal=True, vertical_alignment="bottom", gap="xsmall"):
                st.number_input(
                    f"Quantity ({entry['quantity_unit']})", min_value=0.01,
                    value=float(entry["quantity"]), step=1.0 if entry["quantity_unit"] == "g" else 0.25,
                    format="%.2f", width=120, key=quantity_key,
                )
                st.selectbox(
                    "Meal", MEAL_SLOTS, index=MEAL_SLOTS.index(entry["meal_slot"]),
                    format_func=_display_meal_slot, width=145, key=meal_key,
                )
            with st.container(horizontal=True, horizontal_alignment="distribute"):
                st.form_submit_button("Cancel", on_click=close)
                st.form_submit_button("Save", type="primary", on_click=save)


def _meal_summary_markup(totals, has_entries):
    color = "var(--sustain-text)" if has_entries else "var(--sustain-muted)"
    values = (
        f"{totals['calories']:,} kcal",
        f"{_format_nutrient(totals['protein_g'])}p",
        f"{_format_nutrient(totals['carbs_g'])}c",
        f"{_format_nutrient(totals['fat_g'])}f",
    )
    stats = " <span style='color:var(--sustain-muted)'>·</span> ".join(values)
    return (
        f"<div style='text-align:left;color:{color};font-size:.8125rem;"
        f"font-variant-numeric:tabular-nums;line-height:1.4'>{stats}</div>"
    )

def _render_quick_log(user_id, meal_slot, log_date):
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
            errors = validate_food_entry(name, calories, protein, carbs, fat)
            for error in errors:
                st.error(error)
            if not errors:
                db.add_food_entry(
                    user_id, log_date, slot, name.strip(),
                    calories, protein, carbs, fat,
                )
                st.session_state[f"{key_prefix}_saved"] = True
                st.rerun()


def _open_find_recipe(slot, targets, remaining, log_date):
    st.session_state.meal_request = {
        "slot": slot,
        "targets": targets,
        "remaining": remaining,
        "log_date": log_date,
    }
    st.rerun()
