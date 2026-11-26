# Dashboard that shows:
# Macro progress bar
# Meal slots (Breakfast, Lunch, Dinner, Snacks)
# Logged items.
from datetime import date
from html import escape

import streamlit as st

from services import db, targets as targets_service
from services.validation import validate_food_entry
from views.food_search import (
    render_find_recipe_dialog,
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
        max-width: none;
        padding: 3.75rem clamp(1rem, 3vw, 2.5rem) 3rem;
    }
    .st-key-diary_summary_card {
        padding: 1rem 1.25rem;
        border: 1px solid var(--sustain-border);
        border-radius: 10px;
        background: var(--sustain-surface);
    }
    .diary-over-target {
        color: #ff4b4b;
    }
    [class*="st-key-diary_meal_card_"] {
        border: 1px solid var(--sustain-border);
        border-radius: 6px;
        background: var(--sustain-surface);
    }
    .st-key-diary_meal_breakfast,
    .st-key-diary_meal_lunch,
    .st-key-diary_meal_dinner,
    .st-key-diary_meal_snack {
        padding: .3rem .75rem;
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
        padding: .35rem .75rem;
        border-top: 1px solid var(--sustain-border);
    }
    .diary-food-divider {
        border-top: 1px solid var(--sustain-border);
        opacity: .4;
    }
    .diary-food-name {
        line-height: 1.2;
        overflow-wrap: anywhere;
    }
    .diary-food-quantity {
        margin-top: .15rem;
        color: var(--sustain-muted);
        font-size: .8rem;
        line-height: 1.2;
    }
    [class*="st-key-diary_addwrap_"] button {
        min-height: 1.9rem;
        padding: .18rem .87rem .18rem .72rem;
        white-space: nowrap;
        justify-content: center;
        border: 0;
        border-radius: 999px;
        background: #d92d38;
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
        font-size: 1.1rem;
        font-weight: 700;
    }
    [class*="st-key-diary_edit_"] button,
    [class*="st-key-diary_delete_"] button {
        border: 0;
        background: transparent;
    }
    [class*="st-key-diary_edit_"] button:hover {
        background: rgba(52, 211, 153, .14);
    }
    [class*="st-key-diary_delete_"] button:hover {
        background: rgba(255, 75, 75, .14);
        color: #ff4b4b;
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
    [class*="st-key-diary_addwrap_"] button:hover {
        border: 0;
        background: #c81e2a;
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
        box-shadow: 0 12px 32px rgba(0, 0, 0, .25);
    }
    [data-testid="stPopoverBody"] [class*="st-key-diary_menu_"] [data-testid="stButton"] button {
        min-height: 2rem;
        justify-content: flex-start;
        gap: .45rem;
        padding: 0 !important;
        border: 0;
        border-radius: 8px;
        background: transparent;
        color: var(--sustain-text);
        font-size: .92rem;
    }
    [data-testid="stPopoverBody"] [class*="st-key-diary_menu_"] [data-testid="stButton"] button:hover {
        background: var(--sustain-hover);
        color: var(--sustain-text);
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
    .st-key-diary_meals_toolbar {
        padding-right: .75rem;
    }
    .st-key-diary_request_meal button,
    .st-key-diary_expand_all button {
        height: 40px;
        min-height: 40px;
        padding: 0;
        border: 1px solid transparent;
        border-radius: 10px;
    }
    .st-key-diary_request_meal button {
        background: #c4510b;
        color: white;
    }
    .st-key-diary_request_meal button:hover {
        background: #a9420a;
        color: white;
    }
    .st-key-diary_request_meal [data-testid="stIconMaterial"] {
        color: white;
        font-size: 1.45rem;
        transform: scale(.9);
    }
    .st-key-diary_expand_all button {
        border-color: var(--sustain-border);
        background: var(--sustain-hover);
        color: var(--sustain-text);
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

    st.html(DIARY_CARD_SHADOWS)
    title_col, date_col = st.columns([3, 2], vertical_alignment="center")
    today = date.today()
    saved_date = f"diary_selected_date_{user['id']}"
    picker_key = f"diary_date_picker_{user['id']}"
    st.session_state.setdefault(picker_key, st.session_state.get(saved_date, today))
    with date_col, st.container(
        key="diary_date", horizontal=True, horizontal_alignment="right",
        vertical_alignment="center",
    ):
        selected = st.date_input(
            "Diary date", min_value=date(1900, 1, 1), max_value=today,
            key=picker_key, format="DD/MM/YYYY", label_visibility="collapsed",
            width=155,
        )
    st.session_state[saved_date] = selected
    title_col.title("Today's Diary" if selected == today else "Diary", anchor=False)
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
        render_find_recipe_dialog()
    elif active_dialog == "saved":
        render_saved_recipes_dialog(user["id"])
    elif active_dialog == "saved_foods":
        _render_saved_foods_dialog(user["id"], log_date)
    elif active_dialog == "custom":
        _render_custom_food_dialog(user["id"], log_date)

    expanded_keys = [_meal_expanded_key(slot) for slot in MEAL_SLOTS]
    for key in expanded_keys:
        st.session_state.setdefault(key, False)
    all_expanded = all(st.session_state[key] for key in expanded_keys)

    with st.container(
        key="diary_meals_toolbar", horizontal=True, horizontal_alignment="distribute",
        vertical_alignment="center", gap="small",
    ):
        st.html(
            f'<div style="display:flex;align-items:center;gap:.35rem;">'
            f'<h2 style="margin:0;padding:0;color:var(--sustain-text);font-size:1.25rem;'
            f'font-weight:700;">Meals</h2>'
            f'<span style="padding:.12rem .42rem;border:1px solid var(--sustain-border);'
            f'border-radius:999px;background:var(--sustain-surface);color:var(--sustain-muted);'
            f'font-size:.78rem;">{len(entries)} '
            f'{"item" if len(entries) == 1 else "items"}</span></div>',
            width="content",
        )
        with st.container(horizontal=True, vertical_alignment="center", width="content", gap="small"):
            with st.container(
                horizontal=True, horizontal_alignment="center", width=ADD_COLUMN_WIDTH,
            ):
                if st.button(
                    "", key="diary_request_meal", icon=":material/chef_hat:",
                    width=72, type="primary", help="Request a meal",
                ):
                    st.session_state.meal_request = {
                        "slot": "Snack",
                        "remaining": remaining,
                        "log_date": log_date,
                    }
                    st.rerun()
            if st.button(
                "", key="diary_expand_all",
                icon=":material/arrow_upward:" if all_expanded else ":material/arrow_downward:",
                width=ICON_BUTTON_WIDTH,
            ):
                for key in expanded_keys:
                    st.session_state[key] = not all_expanded
                st.rerun()

    for slot in MEAL_SLOTS:
        slot_entries = [entry for entry in entries if entry["meal_slot"] == slot]
        _render_meal_slot(user["id"], log_date, slot, slot_entries)


def _render_progress(targets, totals):
    with st.container(border=True, key="diary_summary_card"):
        calories, calorie_target = totals["calories"], targets["calories"]
        title, remaining = st.columns([3, 1], vertical_alignment="center")
        title.subheader("Daily Summary", anchor=False)
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
        'space-between; gap:.5rem; margin-bottom:.35rem; color:var(--sustain-text); '
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
        'background:var(--sustain-border);">'
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
                        use_container_width=True,
                    ):
                        st.session_state.next_diary_dialog = dialog
                        st.session_state.diary_dialog_meal_slot = slot
                        st.rerun()


@st.dialog("Saved Foods", width="medium")
def _render_saved_foods_dialog(user_id, log_date):
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
                    user_id, log_date, slot, food["food_name"],
                    food["calories"], food["protein_g"], food["carbs_g"], food["fat_g"],
                    quantity=food["quantity"], quantity_unit=food["quantity_unit"],
                )
                st.rerun()


@st.dialog("Custom Food", width="medium")
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
    expanded = st.session_state[expanded_key]
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
        f"<div style='text-align:left;color:{color};font-size:.8rem;"
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


def _render_meal_request(request):
    slot = request["slot"]
    st.title(f"{slot} request", anchor=False)
    st.subheader(f"Remaining budget for {request.get('log_date', date.today().isoformat())}", anchor=False)
    cols = st.columns(4)
    for col, (label, key, unit) in zip(cols, NUTRIENTS):
        col.metric(label, f"{request['remaining'][key]} {unit}")
    st.info("Meal suggestions will appear here once the meal prompt is built.")
    if st.button("Back to diary"):
        del st.session_state.meal_request
        st.rerun()
