from datetime import date

import streamlit as st

from services import db
from services.food_amount import food_amount
from services.food_autocomplete import food_autocomplete
from services.usda import USDAError, normalize_food_query, search_foods
from services.speech_input import speech_input


def _close_dialog():
    st.rerun()


@st.dialog("Search Food", width="medium")
def render_food_search_dialog(user_id, log_date=None):
    query, selected = food_autocomplete(user_id)
    meal_slot = st.session_state.get("diary_dialog_meal_slot", "Snack")
    scope = (user_id, log_date, meal_slot)
    state = st.session_state.get("food_search_state")
    if state is None or state["scope"] != scope:
        state = {"scope": scope}
        st.session_state.food_search_state = state

    if selected is not None:
        state.clear()
        state.update(scope=scope, selected=selected)
    elif query is not None:
        state.clear()
        state.update(scope=scope, visible_count=5)
        try:
            normalized_query = normalize_food_query(query)
            state["results"] = search_foods(normalized_query)
            state["query"] = normalized_query
        except (ValueError, USDAError) as error:
            state["error"] = str(error)

    if "error" in state:
        st.error(state["error"])
    if "selected" in state:
        _render_food_result(user_id, state["selected"], meal_slot, log_date)

    results = state.get("results")
    if results is not None:
        st.markdown("#### USDA Database Matches")
        st.caption(f'Results for "{state["query"]}"')
        if not results:
            st.info("No matching foods were found. Try a broader search.")
        visible_count = state["visible_count"]
        for food in results[:visible_count]:
            _render_food_result(user_id, food, meal_slot, log_date)
        if len(results) > visible_count and st.button("Show more", key="show_more_food_results"):
            state["visible_count"] = min(visible_count + 5, len(results))
            st.rerun(scope="fragment")

    if st.button("Close", key="close_food_search_dialog"):
        st.session_state.pop("food_search_state", None)
        _close_dialog()


def _render_food_result(user_id, food, meal_slot, log_date=None):
    food_id = food.get("id") or food["fdc_id"]
    unit = food.get("quantity_unit", "g")
    default_amount = food.get("default_amount", 100)
    basis = food.get("basis_quantity", food.get("basis_grams"))
    whole_grams = "default_amount" not in food
    minimum = 1 if whole_grams else min(default_amount, 0.01)
    maximum = max(default_amount, 2000)
    nutrients = food["nutrients"]

    with st.container(border=True):
        result = food_amount(
            key=f"food_amount_preview_{food_id}",
            data={
                "description": food["description"],
                "brand": food["brand"],
                "nutrients": nutrients,
                "basis": basis,
                "unit": unit,
                "defaultAmount": default_amount,
                "minimum": minimum,
                "maximum": maximum,
                "wholeGrams": whole_grams,
            },
            on_add_change=lambda: None,
        )
        amount = result.add
        if amount is None:
            return
        if (
            type(amount) not in (int, float)
            or not minimum <= amount <= maximum
            or (whole_grams and amount % 1)
        ):
            st.error("Enter a valid amount before adding this food.")
            return

        scale = amount / basis
        scaled = {key: max(round(value * scale), 0) for key, value in nutrients.items()}
        db.add_food_entry(
            user_id,
            log_date or date.today().isoformat(),
            meal_slot,
            food["description"],
            scaled["calories"],
            scaled["protein_g"],
            scaled["carbs_g"],
            scaled["fat_g"],
            quantity=amount,
            quantity_unit=unit,
        )
        st.session_state.pop("food_search_state", None)
        st.rerun()


@st.dialog("Tell us what you feel like", width="large")
def render_find_recipe_dialog():
    st.write("Describe what sounds good. Recipe matching will be connected later.")
    st.caption("Voice input uses your browser's speech recognition; availability and privacy depend on your browser.")
    st.session_state.setdefault("recipe_craving_input", "")
    text_col, mic_col = st.columns([8, 1])

    with mic_col:
        spoken = speech_input(key="recipe_craving_microphone")
    if isinstance(spoken, dict) and spoken.get("error"):
        st.warning(spoken["error"])
    elif isinstance(spoken, str) and spoken.strip():
        st.session_state.recipe_craving_input = spoken.strip()

    with text_col:
        st.text_input(
            "Tell us what you feel like",
            placeholder="Something warm, quick, and comforting...",
            key="recipe_craving_input",
            label_visibility="collapsed",
        )

    if st.button("Find recipes", key="submit_recipe_craving"):
        craving = st.session_state.recipe_craving_input.strip()
        if not craving:
            st.error("Tell us what you feel like first.")
        else:
            st.session_state.recipe_search_prompt = craving
            st.info("Recipe matching will be available when the recipe database is connected.")

    if st.button("Close", key="close_recipe_dialog"):
        _close_dialog()


@st.dialog("Saved Recipes", width="large")
def render_saved_recipes_dialog(user_id):
    recipes = db.get_saved_recipes(user_id)
    if not recipes:
        st.info("You haven't saved any recipes yet.")
    for recipe in recipes:
        recipe_id = recipe["recipe_id"]
        with st.container(border=True):
            title, action = st.columns([5, 1])
            title.markdown(f"**{recipe.get('Name', recipe.get('name', 'Saved recipe'))}**")
            calories = recipe.get("Calories", recipe.get("calories"))
            if calories is not None:
                title.caption(f"{calories} kcal")
            if action.button("Remove", key=f"remove_saved_recipe_{recipe_id}"):
                db.remove_saved_recipe(user_id, recipe_id)
                st.session_state.next_diary_dialog = "saved"
                st.rerun()
    if st.button("Close", key="close_saved_recipes_dialog"):
        _close_dialog()
