from datetime import date

import streamlit as st

from services import db
from services.usda import USDAError, normalize_food_query, search_foods
from services.speech_input import speech_input


def _close_dialog():
    st.rerun()


@st.dialog("Search Food", width="medium")
def render_food_search_dialog(user_id):
    st.write("Search foods from USDA FoodData Central.")
    with st.form("usda_food_search_form"):
        query = st.text_input(
            "Food name",
            placeholder="e.g. apple, chicken breast, Greek yogurt",
            key="usda_food_query_input",
        )
        submitted = st.form_submit_button("Search")

    if submitted:
        st.session_state.usda_food_results = None
        st.session_state.usda_food_search_error = None
        st.session_state.food_search_visible_count = 5
        try:
            normalized_query = normalize_food_query(query)
            st.session_state.usda_food_results = search_foods(normalized_query)
            st.session_state.usda_food_last_query = normalized_query
            st.session_state.usda_food_search_error = None
        except ValueError as error:
            st.session_state.usda_food_search_error = str(error)
        except USDAError as error:
            st.session_state.usda_food_search_error = str(error)

    if st.session_state.get("usda_food_search_error"):
        st.error(st.session_state.usda_food_search_error)

    results = st.session_state.get("usda_food_results")
    if results is not None:
        st.markdown("#### USDA Database Matches")
        st.caption(f'Results for "{st.session_state.get("usda_food_last_query", "")}"')
        if not results:
            st.info("No matching foods were found. Try a broader search.")
        visible_count = st.session_state.get("food_search_visible_count", 5)
        meal_slot = st.session_state.get("diary_dialog_meal_slot", "Snack")
        for food in results[:visible_count]:
            _render_food_result(user_id, food, meal_slot)
        if len(results) > visible_count and st.button("Show more", key="show_more_food_results"):
            st.session_state.food_search_visible_count = min(
                visible_count + 5, len(results)
            )
            st.rerun()

    if st.button("Close", key="close_food_search_dialog"):
        _close_dialog()


def _render_food_result(user_id, food, meal_slot):
    with st.container(border=True):
        title, amount_col, action = st.columns([6, 1.2, 1.3])
        title.markdown(f"**{food['description']}**")
        if food["brand"]:
            title.caption(food["brand"])
        nutrients = food["nutrients"]
        title.caption(
            f"{nutrients['calories']:.0f} kcal · "
            f"P {nutrients['protein_g']:.1f}g · "
            f"C {nutrients['carbs_g']:.1f}g · "
            f"F {nutrients['fat_g']:.1f}g "
            f"per {food['basis_grams']:g}g"
        )
        amount = amount_col.number_input(
            "Amount (g)",
            min_value=1,
            max_value=2000,
            value=100,
            key=f"food_amount_{food['fdc_id']}",
            label_visibility="collapsed",
        )
        if action.button("＋ Add", key=f"add_food_{food['fdc_id']}"):
            scale = amount / food["basis_grams"]
            scaled = {
                key: max(round(value * scale), 0)
                for key, value in nutrients.items()
            }
            db.add_food_entry(
                user_id,
                date.today().isoformat(),
                meal_slot,
                food["description"],
                scaled["calories"],
                scaled["protein_g"],
                scaled["carbs_g"],
                scaled["fat_g"],
            )
            st.session_state.food_logged_message = (
                f"Added {food['description']} ({amount} g) to {meal_slot}."
            )
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
