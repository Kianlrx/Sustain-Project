# Find a Recipe page (SCRUM-77). Opened from the chef hat button above the meals
# and from "+ Add > Find a recipe" on a meal. The user describes what they feel
# like, picks a meal slot, and gets the recipes that best fit that slot's budget.
import os
from html import escape
from pathlib import Path

import streamlit as st

from services import db, preference_parser, recipe_finder

STATE_KEY = "recipe_finder"

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

    submission = _search_form(
        key="recipe_search_form",
        data={
            "craving": state.get("craving", ""),
            "slot": state["slot"],
            "split": state["split"],
            "calories": targets["calories"],
            "maxLength": preference_parser.MAX_PROMPT_LENGTH,
        },
        on_search_change=lambda: None,
    ).search
    if submission is not None:
        _submit_search(submission, state, targets, user)

    _render_results(state)

    st.divider()
    if st.button("Generate a recipe", key="finder_generate", icon=":material/auto_awesome:"):
        st.info("Recipe generation is coming soon. For now, pick one of the matches above.")



def _search_html():
    rows = "".join(
        f'<div class="slot" data-slot="{slot}">'
        f'<label><input type="radio" name="meal" value="{slot}" required> '
        f'{"Snacks" if slot == "Snack" else slot}</label>'
        f'<button type="button" data-change="-{recipe_finder.SPLIT_STEP}" aria-label="Less of the day for {slot.lower()}">&minus;</button>'
        '<output class="share"></output>'
        f'<button type="button" data-change="{recipe_finder.SPLIT_STEP}" aria-label="More of the day for {slot.lower()}">+</button>'
        '<output class="budget"></output></div>'
        for slot in recipe_finder.MEAL_SLOTS
    )
    return f"""
        <form>
            <div class="prompt">
                <label>What do you feel like?
                    <textarea name="craving" placeholder="Indian food but not too spicy, and make sure it&#39;s vegan"></textarea>
                </label>
                <button class="mic" type="button" aria-label="Speak your craving" title="Speak your craving">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
                        stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
                        <rect x="9" y="2" width="6" height="12" rx="3"/>
                        <path d="M19 10v1a7 7 0 0 1-14 0v-1 M12 18v4 M8 22h8"/>
                    </svg>
                </button>
            </div>
            <small class="voice-status" role="status"></small>
            <fieldset><legend>Which meal is it for?</legend>{rows}</fieldset>
            <small class="total" hidden></small>
            <button type="submit">Find recipes</button>
        </form>
    """


_PATH = Path(__file__).resolve().parents[1] / "components" / "recipe_finder"
_search_form = st.components.v2.component(
    "sustain_recipe_search",
    html=_search_html(),
    css=(_PATH / "search.css").read_text(encoding="utf-8"),
    js=(_PATH / "search.js").read_text(encoding="utf-8"),
)


def _submit_search(submission, state, targets, user):
    if not isinstance(submission, dict):
        return
    craving = submission.get("craving")
    slot = submission.get("slot")
    split = submission.get("split")
    if (
        not isinstance(craving, str)
        or len(craving) > preference_parser.MAX_PROMPT_LENGTH
        or slot not in recipe_finder.MEAL_SLOTS
        or not isinstance(split, dict)
        or set(split) != set(recipe_finder.MEAL_SLOTS)
        or any(
            type(share) is not int or not 0 <= share <= 100 or share % recipe_finder.SPLIT_STEP
            for share in split.values()
        )
    ):
        st.error("Check your meal shares and recipe preferences, then try again.")
        return
    state.update(slot=slot, split=split)
    _search(state, targets, user, craving.strip())


def _search(state, targets, user, craving):
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
