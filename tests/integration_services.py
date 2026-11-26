# Integration tests (black-box)
# A temporary SQLite database stands in for
# Supabase, and the USDA and Groq calls are faked, so no keys are needed.
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import pandas as pd

from services import db, preference_parser, recipe_search, targets, usda

DAY = "2026-11-20"
PROFILE = {
    "age": 25, "sex": "Male", "height_cm": 175, "weight_kg": 75, "body_fat_pct": None,
    "occupation_type": "Desk Job", "occupation_hours_per_workday": 8,
    "occupation_days_per_week": 5, "daily_steps": 5000,
    "exercise_sessions": [{
        "type": "Weight training (low intensity)", "met": 3.5,
        "duration_minutes": 45, "sessions_per_week": 3,
    }],
    "cooking_skill": "Beginner", "allergens": [], "diets": [],
    "fitness_goal": "Fat Loss", "measurement_units": "Metric",
}


class DatabaseTestCase(unittest.TestCase):
    """Gives each test its own empty database and a signed-up user."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        db_path = patch.object(db, "DB_PATH", Path(folder.name) / "integration.db")
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()
        db.create_user("joe", "secret1")
        self.user_id = db.check_login("joe", "secret1")["id"]


class AccountJourneyTests(DatabaseTestCase):
    def test_sign_up_onboarding_and_targets_work_together(self):
        self.assertFalse(db.create_user("joe", "another1"))  # username already taken
        self.assertIsNone(db.check_login("joe", "wrong-password"))
        self.assertFalse(db.check_login("joe", "secret1")["onboarding_complete"])

        db.save_profile(self.user_id, PROFILE)
        db.mark_onboarding_complete(self.user_id)
        saved = targets.recalibrate(self.user_id)

        self.assertTrue(db.check_login("joe", "secret1")["onboarding_complete"])
        self.assertEqual(saved, targets.calculate_targets(PROFILE))
        self.assertEqual(db.get_targets(self.user_id), (saved, False))

    def test_targets_set_by_hand_are_kept(self):
        db.save_profile(self.user_id, PROFILE)
        mine = {"calories": 2500, "protein_g": 150, "carbs_g": 280, "fat_g": 80}
        db.save_targets(self.user_id, mine, manual=True)
        self.assertEqual(targets.recalibrate(self.user_id), mine)

    def test_password_change_needs_the_current_password(self):
        self.assertFalse(db.change_password(self.user_id, "wrong-password", "newpass1"))
        self.assertTrue(db.change_password(self.user_id, "secret1", "newpass1"))
        self.assertIsNone(db.check_login("joe", "secret1"))
        self.assertIsNotNone(db.check_login("joe", "newpass1"))


class WeightJourneyTests(DatabaseTestCase):
    def test_latest_weigh_in_updates_profile_and_targets(self):
        db.save_profile(self.user_id, PROFILE)
        db.save_weight_entry(self.user_id, "2026-11-01", 80.0)
        db.save_weight_entry(self.user_id, "2026-11-20", 72.5)
        self.assertEqual(db.get_profile(self.user_id)["weight_kg"], 72.5)
        # protein target is 1.8 g per kg of body weight
        self.assertEqual(targets.recalibrate(self.user_id)["protein_g"], round(1.8 * 72.5))

        latest = db.get_weight_entries(self.user_id)[-1]
        db.delete_weight_entry(self.user_id, latest["id"])
        self.assertEqual(db.get_profile(self.user_id)["weight_kg"], 80.0)


class DiaryJourneyTests(DatabaseTestCase):
    def test_food_is_logged_edited_and_deleted(self):
        db.add_food_entry(self.user_id, DAY, "Breakfast", "Porridge", 350, 12, 55, 8)
        db.add_food_entry(self.user_id, DAY, "Lunch", "Chicken", 165, 31, 0, 4,
                          quantity=100, quantity_unit="g")
        entries = db.get_food_entries(self.user_id, DAY)
        self.assertEqual(sum(entry["calories"] for entry in entries), 515)

        chicken = entries[1]
        db.update_food_quantity(self.user_id, DAY, chicken["id"], 200, meal_slot="Dinner")
        db.delete_food_entry(self.user_id, DAY, entries[0]["id"])
        only, = db.get_food_entries(self.user_id, DAY)
        self.assertEqual((only["food_name"], only["calories"], only["meal_slot"]),
                         ("Chicken", 330, "Dinner"))

    def test_users_only_see_their_own_food(self):
        db.add_food_entry(self.user_id, DAY, "Lunch", "Soup", 200, 8, 20, 6)
        db.create_user("other", "secret1")
        other_id = db.check_login("other", "secret1")["id"]
        self.assertEqual(db.get_food_entries(other_id, DAY), [])

    def test_invalid_quantity_is_not_saved(self):
        with self.assertRaises(ValueError):
            db.add_food_entry(self.user_id, DAY, "Lunch", "Soup", 200, 8, 20, 6, quantity=0)
        self.assertEqual(db.get_food_entries(self.user_id, DAY), [])


class UsdaToDiaryTests(DatabaseTestCase):
    BANANA = {"foods": [{
        "fdcId": 173944, "description": "Banana, raw", "servingSize": 118, "servingSizeUnit": "g",
        "foodNutrients": [
            {"nutrientId": 1008, "value": 105}, {"nutrientId": 1003, "value": 1.3},
            {"nutrientId": 1005, "value": 27}, {"nutrientId": 1004, "value": 0.4},
        ],
    }]}

    @patch("services.usda.urlopen")
    def test_usda_result_can_be_logged_in_the_diary(self, urlopen):
        urlopen.return_value = io.BytesIO(json.dumps(self.BANANA).encode("utf-8"))
        food, = usda.search_foods("banana")
        nutrients = food["nutrients"]
        db.add_food_entry(
            self.user_id, DAY, "Snack", food["description"],
            round(nutrients["calories"]), round(nutrients["protein_g"]),
            round(nutrients["carbs_g"]), round(nutrients["fat_g"]),
            quantity=food["basis_grams"], quantity_unit="g",
        )
        entry, = db.get_food_entries(self.user_id, DAY)
        self.assertEqual((entry["food_name"], entry["calories"], entry["quantity"]),
                         ("Banana, raw", 105, 118))

    @patch("services.usda.urlopen", side_effect=URLError("offline"))
    def test_usda_outage_logs_nothing(self, urlopen):
        with self.assertRaises(usda.USDAError):
            usda.search_foods("banana")
        self.assertEqual(db.get_food_entries(self.user_id, DAY), [])


def recipe(recipe_id, name, parts, keywords):
    return {
        "RecipeId": recipe_id, "Name": name, "RecipeCategory": "Test",
        "Keywords": keywords, "Images": [], "RecipeIngredientParts": parts,
        "RecipeIngredientQuantities": ["1"] * len(parts), "RecipeInstructions": ["Mix it."],
        "DatePublished": pd.Timestamp("2020-01-01", tz="UTC"), "Calories": 400.0,
        "ProteinContent": 20.0, "CarbohydrateContent": 40.0, "FatContent": 10.0,
        "FiberContent": 5.0, "CholesterolContent": 0.0,
    }


RECIPES = pd.DataFrame([
    recipe(1, "Lentil Stew", ["lentils", "tomatoes"], ["Dinner", "< 30 Mins"]),
    recipe(2, "Peanut Rice", ["rice", "peanuts"], ["< 30 Mins"]),
    recipe(3, "Chicken Rice", ["chicken", "rice"], ["< 30 Mins"]),
    recipe(4, "Slow Bean Chili", ["beans", "tomatoes"], ["< 4 Hours"]),
])


def groq_answer(filters):
    # what Groq sends back: the model's JSON answer inside the first choice
    body = {"choices": [{"message": {"content": json.dumps(filters)}}]}
    return io.BytesIO(json.dumps(body).encode("utf-8"))


@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
@patch("services.preference_parser.time.sleep")  # don't really wait between calls
@patch("services.preference_parser.urlopen")
class CravingToRecipesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.recipes_db = Path(folder.name) / "recipes.db"
        recipe_search.save_database(recipe_search.add_tags(RECIPES), db_path=self.recipes_db)

    def search(self, craving):
        filters = preference_parser.parse_preferences(craving, "Dinner")
        args = preference_parser.to_search_args(filters)
        return list(recipe_search.find_recipes(**args, db_path=self.recipes_db)["Name"])

    def test_parsed_craving_finds_only_matching_recipes(self, urlopen, sleep):
        urlopen.return_value = groq_answer({
            "cuisines": [], "flavors": [], "preparation": [], "meal_category": "Any",
            "diets": ["Vegan"], "exclusions": ["peanut"], "max_cook_minutes": 30,
        })
        # vegan, no peanuts and under 30 minutes leaves only the lentil stew
        self.assertEqual(self.search("quick vegan dinner, no peanuts"), ["Lentil Stew"])

    def test_ai_outage_still_returns_recipes(self, urlopen, sleep):
        urlopen.side_effect = TimeoutError()
        with self.assertLogs("services.preference_parser", "WARNING"):
            names = self.search("quick vegan dinner, no peanuts")
        # the default filters are broad, so every recipe is still offered
        self.assertEqual(sorted(names), sorted(RECIPES["Name"]))


if __name__ == "__main__":
    unittest.main()