import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from services import db, recipe_finder, recipe_search
from services.preference_parser import default_filters

APP = str(Path(__file__).resolve().parents[1] / "app.py")

TARGETS = {"calories": 2000, "protein_g": 150, "carbs_g": 200, "fat_g": 60}

# every column the recipe database has after recipe_search.add_tags
DATABASE_COLUMNS = {
    "Vegetarian", "Vegan", "Keto", "SkillLevel", "Calories", "Keywords", "RecipeCategory", "Name",
    "ProteinContent", "CarbohydrateContent", "FatContent",
} | {recipe_search.free_column(allergen) for allergen in recipe_search.ALLERGEN_WORDS}
# keys in the query that are not one column, and what they search
EXTRA_KEYS = {"Keywords|RecipeCategory|Name", "exclude_words", "rank_boost_words"}


def recipe(recipe_id, name, parts, calories, protein=30.0, carbs=60.0, fat=15.0,
           category="One Dish Meal", keywords=(), cholesterol=0.0):
    return {
        "RecipeId": recipe_id, "Name": name, "RecipeCategory": category, "Keywords": list(keywords),
        "Images": [], "RecipeIngredientParts": parts, "RecipeIngredientQuantities": ["1"] * len(parts),
        "RecipeInstructions": ["Cook it."] * 3, "DatePublished": pd.Timestamp("2020-01-01", tz="UTC"),
        "Calories": calories, "ProteinContent": protein, "CarbohydrateContent": carbs, "FatContent": fat,
        "FiberContent": 5.0, "CholesterolContent": cholesterol,
    }


RECIPES = pd.DataFrame([
    recipe(1, "Chana Masala", ["chickpeas", "tomatoes", "garam masala"], 590, keywords=["Indian", "< 60 Mins"]),
    recipe(2, "Vindaloo Potatoes", ["potatoes", "cayenne", "chili"], 610, keywords=["Indian"]),
    recipe(3, "Paneer Tikka", ["paneer", "yogurt"], 600, keywords=["Indian"], cholesterol=60.0),
    recipe(4, "Dal Tadka", ["lentils", "cumin"], 400, category="Indian"),
    recipe(5, "Tofu Stir Fry", ["tofu", "broccoli"], 600, keywords=["Asian"]),
    recipe(6, "Big Lentil Curry", ["lentils", "coconut milk"], 1400, keywords=["Indian"]),
    recipe(7, "Creamy Vegetable Korma", ["cashews", "cauliflower"], 650, keywords=["Indian"]),
])


PROFILE = {
    "age": 25, "sex": "Male", "height_cm": 175, "weight_kg": 75, "body_fat_pct": None,
    "occupation_type": "Desk Job", "occupation_hours_per_workday": 8,
    "occupation_days_per_week": 5, "daily_steps": 5000, "exercise_sessions": [],
    "cooking_skill": "Advanced", "allergens": [], "diets": [],
    "fitness_goal": "Recomposition", "measurement_units": "Metric",
}


def make_database(folder):
    path = Path(folder) / "recipes.db"
    recipe_search.save_database(recipe_search.add_tags(RECIPES), db_path=path)
    return path


class SlotTests(unittest.TestCase):
    def test_default_split_is_30_30_30_10(self):
        self.assertEqual(recipe_finder.DEFAULT_SPLIT, {"Breakfast": 30, "Lunch": 30, "Dinner": 30, "Snack": 10})

    def test_default_slot_follows_time_of_day(self):
        self.assertEqual(recipe_finder.default_slot(8), "Breakfast")
        self.assertEqual(recipe_finder.default_slot(13), "Lunch")
        self.assertEqual(recipe_finder.default_slot(19), "Dinner")
        self.assertEqual(recipe_finder.default_slot(23), "Snack")

    def test_adjust_split_changes_one_slot_and_stays_in_range(self):
        split = recipe_finder.adjust_split(recipe_finder.DEFAULT_SPLIT, "Lunch", 5)
        self.assertEqual(split["Lunch"], 35)
        self.assertEqual(split["Dinner"], 30)
        self.assertEqual(recipe_finder.DEFAULT_SPLIT["Lunch"], 30)  # the default is not changed
        self.assertEqual(recipe_finder.adjust_split({"Snack": 0}, "Snack", -5)["Snack"], 0)
        self.assertEqual(recipe_finder.adjust_split({"Snack": 100}, "Snack", 5)["Snack"], 100)

    def test_slot_budget_is_share_of_daily_targets(self):
        budget = recipe_finder.slot_budget(TARGETS, recipe_finder.DEFAULT_SPLIT, "Dinner")
        self.assertEqual(budget, {"calories": 600, "protein_g": 45, "carbs_g": 60, "fat_g": 18})


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.budget = recipe_finder.slot_budget(TARGETS, recipe_finder.DEFAULT_SPLIT, "Dinner")
        self.filters = default_filters("Dinner")
        self.filters.update(
            cuisines=["indian"], diets=["Vegan"], flavors=["creamy"],
            exclusions=["chili", "cayenne"], max_cook_minutes=60,
        )

    def test_query_only_uses_database_columns(self):
        query = recipe_finder.build_query(self.filters, self.budget, {"allergens": ["Peanuts"]})
        self.assertLessEqual(set(query) - EXTRA_KEYS, DATABASE_COLUMNS)
        self.assertEqual(set(query["exclude_words"]["columns"]) - DATABASE_COLUMNS,
                         {"RecipeIngredientParts", "RecipeInstructions"})

    def test_query_combines_craving_and_profile(self):
        profile = {"allergens": ["Peanuts", "mushroom"], "diets": ["Vegetarian"], "cooking_skill": "Beginner"}
        query = recipe_finder.build_query(self.filters, self.budget, profile)
        self.assertEqual(query["Vegan"], 1)
        self.assertEqual(query["Vegetarian"], 1)
        self.assertEqual(query["PeanutsFree"], 1)
        self.assertEqual(query["Keywords|RecipeCategory|Name"], ["Indian"])
        self.assertEqual(query["Keywords"], ["< 60 Mins"])
        self.assertEqual(query["exclude_words"]["words"], ["mushroom", "chili", "cayenne"])
        self.assertEqual(query["SkillLevel"], {"max": 1})
        self.assertEqual(query["Calories"], {"min": 360, "max": 660, "target": 600})
        self.assertEqual(query["rank_boost_words"], ["creamy"])

    def test_unknown_skill_and_missing_profile_are_safe(self):
        query = recipe_finder.build_query(default_filters(), self.budget, {"cooking_skill": "Chef"})
        self.assertEqual(query["SkillLevel"], {"max": 3})
        self.assertNotIn("Vegan", recipe_finder.build_query(default_filters(), self.budget, None))


class SearchTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.db_path = make_database(folder.name)
        self.budget = recipe_finder.slot_budget(TARGETS, recipe_finder.DEFAULT_SPLIT, "Dinner")

    def names(self, filters, profile=None):
        query = recipe_finder.build_query(filters, self.budget, profile)
        results, _ = recipe_finder.run_query(query, db_path=self.db_path)
        return [r["Name"] for r in results]

    def test_indian_vegan_not_spicy(self):
        filters = default_filters()
        filters.update(cuisines=["indian"], diets=["Vegan"], exclusions=["chili", "cayenne"])
        names = self.names(filters)
        # no paneer (not vegan), no vindaloo (spicy), no tofu stir fry (not Indian)
        self.assertNotIn("Paneer Tikka", names)
        self.assertNotIn("Vindaloo Potatoes", names)
        self.assertNotIn("Tofu Stir Fry", names)
        self.assertIn("Chana Masala", names)
        self.assertIn("Dal Tadka", names)  # Indian by its category

    def test_closest_to_budget_comes_first(self):
        filters = default_filters()
        filters["cuisines"] = ["indian"]
        names = self.names(filters)
        self.assertIn(names[0], ["Chana Masala", "Paneer Tikka", "Vindaloo Potatoes"])
        self.assertNotIn("Big Lentil Curry", names)  # far too big for one dinner

    def test_flavour_word_pushes_recipe_up(self):
        filters = default_filters()
        filters.update(cuisines=["indian"], flavors=["creamy"])
        self.assertEqual(self.names(filters)[0], "Creamy Vegetable Korma")

    def test_fit_label(self):
        query = recipe_finder.build_query(default_filters(), self.budget)
        self.assertEqual(recipe_finder.fit_label({"Calories": 610}, query), "On budget")
        self.assertEqual(recipe_finder.fit_label({"Calories": 400}, query), "200 kcal under")
        self.assertEqual(recipe_finder.fit_label({"Calories": 900}, query), "300 kcal over")

    def test_database_ready(self):
        self.assertTrue(recipe_finder.database_ready(self.db_path))
        self.assertFalse(recipe_finder.database_ready(self.db_path.with_name("missing.db")))


class FindRecipePageTests(unittest.TestCase):
    """The page itself, clicked through like a user would."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for target, path in [(db, Path(folder.name) / "app.db"), (recipe_search, make_database(folder.name))]:
            patcher = patch.object(target, "DB_PATH", path)
            patcher.start()
            self.addCleanup(patcher.stop)
        no_ai = patch.dict("os.environ", {"GROQ_API_KEY": ""})
        no_ai.start()
        self.addCleanup(no_ai.stop)
        db.init_db()
        db.create_user("joe", "secret1")
        user_id = db.check_login("joe", "secret1")["id"]
        db.save_profile(user_id, PROFILE)
        db.mark_onboarding_complete(user_id)

        self.app = AppTest.from_file(APP, default_timeout=30)
        self.app.run()
        self.app.text_input(key="login_username").set_value("joe")
        self.app.text_input(key="login_password").set_value("secret1")
        self.click(next(b for b in self.app.button if b.label == "Log in"))

    def click(self, button):
        button.click().run()
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])

    def test_header_button_opens_page_and_finds_recipes(self):
        self.click(self.app.button(key="diary_request_meal"))
        self.assertEqual(self.app.title[0].value, "Find a recipe")

        self.click(self.app.button(key="finder_pick_dinner"))
        self.click(self.app.button(key="finder_plus_dinner"))
        self.assertEqual(self.app.session_state["recipe_finder"]["split"]["Dinner"], 35)

        self.app.text_area(key="recipe_craving_input").set_value("Indian food")
        self.click(self.app.button(key="finder_submit"))
        state = self.app.session_state["recipe_finder"]
        self.assertEqual(state["slot"], "Dinner")
        self.assertTrue(state["results"])
        cards = lambda: [c for c in self.app.get("html") if 'class="finder-result-name"' in c.proto.body]
        self.assertEqual(len(cards()), min(5, len(state["results"])))
        if len(state["results"]) > 5:
            self.click(self.app.button(key="finder_show_more"))
            self.assertEqual(len(cards()), min(10, len(state["results"])))

        self.click(self.app.button(key="finder_generate"))
        self.assertTrue(self.app.info)

        self.click(self.app.button(key="finder_back"))
        self.assertNotIn("meal_request", self.app.session_state)

    def test_add_menu_opens_page_for_that_meal(self):
        self.click(self.app.button(key="diary_add_lunch_recipe_c-purple"))
        self.assertEqual(self.app.title[0].value, "Find a recipe")
        self.assertEqual(self.app.session_state["meal_request"]["slot"], "Lunch")


if __name__ == "__main__":
    unittest.main()
