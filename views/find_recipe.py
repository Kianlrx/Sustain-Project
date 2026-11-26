# Find a Recipe page (SCRUM-77). Opened from the chef hat button above the meals
# and from "+ Add > Find a recipe" on a meal. The user describes what they feel
# like, picks a meal slot, and gets the recipes that best fit that slot's budget.
import os
from html import escape

import streamlit as st

from services import db, preference_parser, recipe_finder
from services.speech_input import speech_input

STATE_KEY = "recipe_finder"
PROMPT_KEY = "recipe_craving_input"

PAGE_STYLES = """
<style>
    .st-key-finder_budget {
        padding: 8px 14px;
        border: 1px solid var(--sustain-border);
        border-radius: 10px;
        background: var(--sustain-surface);
        color: var(--sustain-secondary);
        font-size: .8125rem;
        font-variant-numeric: tabular-nums;
    }
    .finder-budget strong { color: var(--sustain-text); font-weight: 500; }
    .st-key-finder_prompt textarea { font-size: 1.0625rem; }
    [class*="st-key-finder_slot_row_"] {
        padding: 4px 8px 4px 4px;
        border: 1px solid var(--sustain-border);
        border-radius: 10px;
        background: var(--sustain-surface);
    }
    [class*="st-key-finder_slot_row_"]:has([class*="st-key-finder_pick_"] button[kind="primary"]) {
        border-color: var(--sustain-accent);
    }
    [class*="st-key-finder_pick_"] button {
        justify-content: flex-start;
        border: 0;
        background: transparent;
        color: var(--sustain-text);
        box-shadow: none;
    }
    [class*="st-key-finder_pick_"] button > div { justify-content: flex-start; }
    [class*="st-key-finder_pick_"] button[kind="primary"],
    [class*="st-key-finder_pick_"] button[kind="primary"]:hover {
        background: transparent;
        color: var(--sustain-text);
        font-weight: 500;
    }
    [class*="st-key-finder_pick_"] [data-testid="stIconMaterial"],
    .st-key-finder_generate [data-testid="stIconMaterial"],
    .st-key-finder_back [data-testid="stIconMaterial"] {
        color: var(--sustain-accent);
    }
    [class*="st-key-finder_minus_"] button,
    [class*="st-key-finder_plus_"] button {
        min-height: 30px;
        height: 30px;
        padding: 0;
        border-radius: 8px;
    }
    .finder-slot-share {
        min-width: 3.2rem;
        color: var(--sustain-text);
        text-align: center;
        font-variant-numeric: tabular-nums;
    }
    .finder-slot-kcal {
        min-width: 5.5rem;
        color: var(--sustain-muted);
        font-size: .8125rem;
        text-align: right;
        font-variant-numeric: tabular-nums;
    }
    [class*="st-key-finder_result_"] {
        padding: 12px 16px;
        border: 1px solid var(--sustain-border);
        border-radius: 12px;
        background: var(--sustain-surface);
    }
    .finder-result-name { color: var(--sustain-text); font-weight: 500; line-height: 1.3; }
    .finder-result-meta {
        margin-top: 4px;
        color: var(--sustain-muted);
        font-size: .8125rem;
        font-variant-numeric: tabular-nums;
    }
    .finder-fit {
        color: var(--sustain-accent);
        font-size: .8125rem;
        font-weight: 500;
        white-space: nowrap;
    }
</style>
"""


def _state():
    state = st.session_state.get(STATE_KEY)
    if state is None:
        state = {"split": dict(recipe_finder.DEFAULT_SPLIT)}
        st.session_state[STATE_KEY] = state
    return state


def render_find_recipe_page(request):
    state = _state()
    state.setdefault("slot", request["slot"])
    targets = request["targets"]
    user = st.session_state.user

    st.html(PAGE_STYLES)
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        if st.button("Back to diary", key="finder_back", icon=":material/arrow_back:"):
            st.session_state.pop("meal_request", None)
            st.session_state.pop(STATE_KEY, None)
            st.rerun()
    st.title("Find a recipe", anchor=False)

    remaining = request["remaining"]
    with st.container(key="finder_budget"):
        st.html(
            '<div class="finder-budget">Left today: '
            f'<strong>{remaining["calories"]:,} kcal</strong> · '
            f'P {remaining["protein_g"]}g · C {remaining["carbs_g"]}g · F {remaining["fat_g"]}g</div>'
        )

    _render_prompt()
    _render_slots(state, targets)

    if st.button("Find recipes", key="finder_submit", type="primary", icon=":material/search:"):
        _search(state, targets, user)

    _render_results(state)

    st.divider()
    if st.button("Generate a recipe", key="finder_generate", icon=":material/auto_awesome:"):
        st.info("Recipe generation is coming soon. For now, pick one of the matches above.")


def _render_prompt():
    st.session_state.setdefault(PROMPT_KEY, "")
    text_col, mic_col = st.columns([12, 1], vertical_alignment="bottom")
    with mic_col:
        spoken = speech_input(key="recipe_craving_microphone")
    if isinstance(spoken, dict) and spoken.get("error"):
        st.warning(spoken["error"])
    elif isinstance(spoken, str) and spoken.strip():
        st.session_state[PROMPT_KEY] = spoken.strip()
    with text_col, st.container(key="finder_prompt"):
        st.text_area(
            "What do you feel like?",
            placeholder="Indian food but not too spicy, and make sure it's vegan",
            key=PROMPT_KEY,
            height=96,
            max_chars=preference_parser.MAX_PROMPT_LENGTH,
        )


def _render_slots(state, targets):
    st.markdown("**Which meal is it for?**")
    split = state["split"]
    for slot in recipe_finder.MEAL_SLOTS:
        key = slot.lower()
        selected = state["slot"] == slot
        budget = recipe_finder.slot_budget(targets, split, slot)
        with st.container(
            key=f"finder_slot_row_{key}", horizontal=True, vertical_alignment="center", gap="small",
        ):
            if st.button(
                "Snacks" if slot == "Snack" else slot,
                key=f"finder_pick_{key}",
                icon=":material/radio_button_checked:" if selected else ":material/radio_button_unchecked:",
                type="primary" if selected else "secondary",
                width="stretch",
            ):
                state["slot"] = slot
                st.rerun()
            if st.button("", key=f"finder_minus_{key}", icon=":material/remove:", width=34,
                         help=f"Less of the day for {slot.lower()}"):
                state["split"] = recipe_finder.adjust_split(split, slot, -recipe_finder.SPLIT_STEP)
                st.rerun()
            st.html(f'<span class="finder-slot-share">{split[slot]}%</span>', width="content")
            if st.button("", key=f"finder_plus_{key}", icon=":material/add:", width=34,
                         help=f"More of the day for {slot.lower()}"):
                state["split"] = recipe_finder.adjust_split(split, slot, recipe_finder.SPLIT_STEP)
                st.rerun()
            st.html(f'<span class="finder-slot-kcal">{budget["calories"]:,} kcal</span>', width="content")
    total = sum(split.values())
    if total != 100:
        st.caption(f"Your meals add up to {total}% of the day, not 100%.")


def _search(state, targets, user):
    craving = st.session_state.get(PROMPT_KEY, "").strip()
    slot = state["slot"]
    budget = recipe_finder.slot_budget(targets, state["split"], slot)
    if budget["calories"] <= 0:
        st.error("This meal has 0% of the day. Raise it with + first.")
        return
    if not recipe_finder.database_ready():
        st.error(
            "The recipe database is not built yet. In a terminal, run "
            "`python -m services.food_data` and then `python -m services.recipe_search`."
        )
        return
    with st.spinner("Finding recipes..."):
        filters = preference_parser.parse_preferences(craving, slot)
        query = recipe_finder.build_query(filters, budget, db.get_profile(user["id"]))
        results, widened = recipe_finder.run_query(query)
    state.update(
        query=query, results=results, widened=widened, visible=recipe_finder.RESULTS_SHOWN,
        ai_used=bool(craving) and bool(os.environ.get("GROQ_API_KEY", "").strip()),
        craving=craving,
    )


def _render_results(state):
    if "results" not in state:
        return
    query, results = state["query"], state["results"]
    with st.expander("Search filters (from your text)", icon=":material/data_object:"):
        if state["craving"] and not state["ai_used"]:
            st.caption("AI reading is off (no GROQ_API_KEY), so only your profile and the calorie budget are used.")
        st.json(query)

    st.subheader("Best matches", anchor=False)
    if not results:
        st.info("No recipes match all of that. Try fewer conditions or another meal size.")
        return
    if state["widened"]:
        st.caption("Few recipes fit this meal's calories, so the closest ones are shown.")
    for recipe in results[: state["visible"]]:
        _render_recipe(recipe, query)
    if len(results) > state["visible"] and st.button("Show more", key="finder_show_more"):
        state["visible"] = min(state["visible"] + recipe_finder.RESULTS_SHOWN, len(results))
        st.rerun()


def _render_recipe(recipe, query):
    with st.container(key=f"finder_result_{int(recipe['RecipeId'])}"):
        st.html(
            '<div style="display:flex;justify-content:space-between;gap:12px;align-items:baseline;">'
            f'<div class="finder-result-name">{escape(str(recipe["Name"]))}</div>'
            f'<span class="finder-fit">{escape(recipe_finder.fit_label(recipe, query))}</span></div>'
            f'<div class="finder-result-meta">{round(recipe["Calories"]):,} kcal · '
            f'P {round(recipe["ProteinContent"])}g · C {round(recipe["CarbohydrateContent"])}g · '
            f'F {round(recipe["FatContent"])}g · {escape(str(recipe.get("RecipeCategory", "")))}</div>'
        )
