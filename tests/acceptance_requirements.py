# Acceptance tests (white-box): check Sustain meets its non-functional requirements
# for speed, page loading time, accuracy and memory use. They rely on knowing how the
# code works inside (formulas, constants, database indexes), unlike the black-box tests.
# Each test prints what it measured, so the pipeline log shows the margin to each limit.
import gc
import io
import json
import os
import random
import sqlite3
import tempfile
import time
import tracemalloc
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from services import db, preference_parser, recipe_search, targets
from services.tdee_engine import calculate_bmr
from integration_services import PROFILE, recipe

APP = str(Path(__file__).resolve().parents[1] / "app.py")

# The requirements. Limits follow the usual response-time guide: under 0.1 s feels
# instant, and a page should be ready within about 3 s.
INSTANT_S = 0.1          # NFR-1 to 4: calculations and database reads feel instant
AI_MAX_WAIT_S = 60       # NFR-5: the app never waits more than a minute for the AI
PAGE_LOAD_S = 3          # NFR-6 and 7: every page loads within 3 seconds
CALORIE_TOLERANCE = 1    # NFR-8 and 10: within 1 kcal of the exact value
MACRO_TOLERANCE = 0.01   # NFR-9: macros add up to within 1% of the calorie target
MEMORY_GROWTH_KB = 100   # NFR-12 to 14: repeating an action doesn't keep using memory


def average_seconds(action, repeats):
    action()  # warm-up run, so first-time imports and caches aren't counted
    start = time.perf_counter()
    for _ in range(repeats):
        action()
    return (time.perf_counter() - start) / repeats


def memory_growth_kb(action, repeats):
    action()  # warm-up run, as above
    gc.collect()
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    for _ in range(repeats):
        action()
    gc.collect()
    after = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    return (after - before) / 1024


def report(name, measured, limit, unit):
    print(f"\n  {name}: {measured:.3f} {unit} (limit {limit} {unit})")


class DatabaseTestCase(unittest.TestCase):
    """A temporary database with one signed-up user; add_a_month_of_data fills it in."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        db_path = patch.object(db, "DB_PATH", Path(folder.name) / "acceptance.db")
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()
        db.create_user("joe", "secret1")
        self.user = db.check_login("joe", "secret1")
        self.user_id = self.user["id"]

    def add_a_month_of_data(self):
        db.save_profile(self.user_id, PROFILE)
        db.mark_onboarding_complete(self.user_id)
        self.user = db.check_login("joe", "secret1")
        for days_ago in range(30):
            day = (date.today() - timedelta(days=days_ago)).isoformat()
            for slot in ("Breakfast", "Lunch", "Dinner"):
                db.add_food_entry(self.user_id, day, slot, f"{slot} food", 500, 30, 60, 15)
            db.save_weight_entry(self.user_id, day, 75 + days_ago / 10)


class SpeedTests(DatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        # 20,000 made-up recipes, built the same way as the real recipe database
        rng = random.Random(1)
        foods = ["rice", "beans", "tomatoes", "chicken", "tofu", "peanuts", "lentils",
                 "onion", "garlic", "cheese", "eggs", "spinach"]
        rows = [recipe(i, f"Recipe {i}", rng.sample(foods, 4),
                       rng.sample(["Dinner", "Lunch", "< 30 Mins", "< 60 Mins", "Easy"], 2))
                for i in range(1, 20_001)]
        recipes = pd.DataFrame(rows)
        recipes["Calories"] = [rng.uniform(100, 1200) for _ in rows]
        cls.folder = tempfile.TemporaryDirectory()
        cls.recipes_db = Path(cls.folder.name) / "recipes.db"
        recipe_search.save_database(recipe_search.add_tags(recipes), db_path=cls.recipes_db)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_nfr1_daily_targets_are_instant(self):
        seconds = average_seconds(lambda: targets.calculate_targets(PROFILE), 1000)
        report("NFR-1 daily targets", seconds * 1000, INSTANT_S * 1000, "ms")
        self.assertLess(seconds, INSTANT_S)

    def test_nfr2_recipe_search_is_instant_on_20000_recipes(self):
        def search():
            return recipe_search.find_recipes(
                calories=(300, 700), protein=(10, None), diets=["Vegetarian"],
                allergens=["Peanuts"], limit=20, db_path=self.recipes_db,
            )
        seconds = average_seconds(search, 20)
        report("NFR-2 recipe search", seconds * 1000, INSTANT_S * 1000, "ms")
        self.assertLess(seconds, INSTANT_S)
        self.assertEqual(len(search()), 20)

        # white-box: the search relies on these indexes to stay fast as the data grows
        conn = sqlite3.connect(self.recipes_db)
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        conn.close()  # Windows can't delete the temporary folder while the file is open
        self.assertTrue({"idx_recipes_macros", "idx_recipes_id"} <= indexes)

    def test_nfr3_opening_a_recipe_is_instant(self):
        seconds = average_seconds(lambda: recipe_search.get_recipe(12_345, db_path=self.recipes_db), 100)
        report("NFR-3 open a recipe", seconds * 1000, INSTANT_S * 1000, "ms")
        self.assertLess(seconds, INSTANT_S)

    def test_nfr4_reading_a_busy_diary_day_is_instant(self):
        day = date.today().isoformat()
        for number in range(50):
            db.add_food_entry(self.user_id, day, "Lunch", f"Food {number}", 200, 10, 20, 5)
        seconds = average_seconds(lambda: db.get_food_entries(self.user_id, day), 50)
        report("NFR-4 diary day with 50 foods", seconds * 1000, INSTANT_S * 1000, "ms")
        self.assertLess(seconds, INSTANT_S)

    def test_nfr5_ai_wait_is_limited(self):
        parser = preference_parser
        # white-box: worst case when Groq never answers = every attempt timing out,
        # plus the waits between attempts and between calls
        worst = (parser.MAX_ATTEMPTS * (parser.TIMEOUT_SECONDS + parser.SECONDS_BETWEEN_CALLS)
                 + sum(2 ** attempt for attempt in range(1, parser.MAX_ATTEMPTS)))
        report("NFR-5 longest possible AI wait", worst, AI_MAX_WAIT_S, "s")
        self.assertLessEqual(worst, AI_MAX_WAIT_S)

        # an unclear craving is answered straight away without calling the AI
        with patch("services.preference_parser.urlopen") as urlopen:
            seconds = average_seconds(lambda: parser.parse_preferences("???"), 1000)
        urlopen.assert_not_called()
        self.assertLess(seconds, INSTANT_S)


class LoadingTimeTests(DatabaseTestCase):
    def page_load_seconds(self, make_app):
        make_app().run()  # warm-up run: the first run also imports the page's code
        app = make_app()
        start = time.perf_counter()
        app.run()
        seconds = time.perf_counter() - start
        self.assertFalse(app.exception, [e.message for e in app.exception])
        return seconds

    def test_nfr6_login_page_loads_quickly(self):
        seconds = self.page_load_seconds(lambda: AppTest.from_file(APP, default_timeout=30))
        report("NFR-6 login page", seconds, PAGE_LOAD_S, "s")
        self.assertLess(seconds, PAGE_LOAD_S)

    def page(self, module, function):
        # one page on its own, opened by the logged-in user
        app = AppTest.from_string(f"from {module} import {function}\n{function}()", default_timeout=30)
        app.session_state.user = self.user
        return app

    def test_nfr7_every_page_loads_quickly_with_a_month_of_data(self):
        self.add_a_month_of_data()
        for module, function in [("views.diary", "render_diary_page"),
                                 ("views.dashboard", "render_dashboard_page"),
                                 ("views.weight", "render_weight_page"),
                                 ("views.settings", "render_settings_page")]:
            with self.subTest(page=module):
                seconds = self.page_load_seconds(lambda: self.page(module, function))
                report(f"NFR-7 {module} page", seconds, PAGE_LOAD_S, "s")
                self.assertLess(seconds, PAGE_LOAD_S)


class AccuracyTests(DatabaseTestCase):
    def test_nfr8_bmr_matches_the_published_equations(self):
        # expected values worked out by hand from each equation
        people = [
            # Mifflin-St Jeor, men: 10 x kg + 6.25 x cm - 5 x age + 5
            (dict(weight_kg=75, height_cm=175, age=25, sex="Male", body_fat_pct=None), 1723.75),
            # Mifflin-St Jeor, women: 10 x kg + 6.25 x cm - 5 x age - 161
            (dict(weight_kg=65, height_cm=165, age=35, sex="Female", body_fat_pct=None), 1345.25),
            # Katch-McArdle: 370 + 21.6 x lean mass (90 kg at 25% body fat = 67.5 kg lean)
            (dict(weight_kg=90, height_cm=180, age=40, sex="Male", body_fat_pct=25), 1828.0),
        ]
        for person, expected in people:
            with self.subTest(person=person):
                self.assertAlmostEqual(calculate_bmr(person), expected, delta=CALORIE_TOLERANCE)

    def test_nfr9_macros_add_up_to_the_calorie_target(self):
        for goal in targets.GOAL_MODIFIERS:
            with self.subTest(goal=goal):
                daily = targets.calculate_targets(dict(PROFILE, fitness_goal=goal))
                # protein and carbs have 4 kcal per gram, fat has 9
                macro_kcal = daily["protein_g"] * 4 + daily["carbs_g"] * 4 + daily["fat_g"] * 9
                self.assertLessEqual(abs(macro_kcal - daily["calories"]),
                                     daily["calories"] * MACRO_TOLERANCE)

    def test_nfr10_changing_a_food_amount_scales_calories_exactly(self):
        # chicken: 165 kcal per 100 g
        db.add_food_entry(self.user_id, "2026-11-20", "Lunch", "Chicken", 165, 31, 0, 4,
                          quantity=100, quantity_unit="g")
        entry_id = db.get_food_entries(self.user_id, "2026-11-20")[0]["id"]
        for grams in (1, 33, 99, 150, 250, 333, 1000):
            with self.subTest(grams=grams):
                db.update_food_quantity(self.user_id, "2026-11-20", entry_id, grams)
                entry, = db.get_food_entries(self.user_id, "2026-11-20")
                self.assertAlmostEqual(entry["calories"], 165 * grams / 100, delta=CALORIE_TOLERANCE)

    def test_nfr11_ai_filters_always_match_the_schema(self):
        # 300 random, badly formed AI answers must still give valid filters
        rng = random.Random(42)
        junk = [None, True, 3, -5, 2.5, "", "Vegan", "x" * 100, [], {"a": 1},
                ["Vegan", 7, None], ["thai", " THAI ", "thai"], 90, 5000]
        answers = []
        for _ in range(300):
            filters = {key: rng.choice(junk) for key in preference_parser.FILTER_SCHEMA["properties"]}
            answers.append(json.dumps(filters))
        answers += ["[1, 2]", '"text"', "not json"]

        def fake_urlopen(request, timeout=None):
            body = {"choices": [{"message": {"content": answers.pop()}}]}
            return io.BytesIO(json.dumps(body).encode("utf-8"))

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
                patch("services.preference_parser.urlopen", fake_urlopen), \
                patch("services.preference_parser.time.sleep"), \
                self.assertLogs("services.preference_parser", "WARNING"):
            while answers:
                slot = rng.choice(preference_parser.MEAL_CATEGORIES + [None, "Brunch"])
                self.assert_valid_filters(preference_parser.parse_preferences("something tasty", slot))

    def assert_valid_filters(self, filters):
        self.assertEqual(set(filters), set(preference_parser.FILTER_SCHEMA["properties"]))
        for key in ("cuisines", "flavors", "preparation", "exclusions"):
            for word in filters[key]:
                self.assertEqual(word, word.strip().lower())
                self.assertTrue(word)
        self.assertLessEqual(set(filters["diets"]), set(preference_parser.DIETS))
        self.assertIn(filters["meal_category"], preference_parser.MEAL_CATEGORIES)
        minutes = filters["max_cook_minutes"]
        self.assertTrue(minutes is None or (type(minutes) is int and 0 < minutes <= 24 * 60))


class MemoryTests(DatabaseTestCase):
    def test_nfr12_calculating_targets_does_not_leak_memory(self):
        growth = memory_growth_kb(lambda: targets.calculate_targets(PROFILE), 2000)
        report("NFR-12 memory growth, 2,000 target calculations", growth, MEMORY_GROWTH_KB, "KB")
        self.assertLess(growth, MEMORY_GROWTH_KB)

    def test_nfr13_diary_database_calls_do_not_leak_memory(self):
        def log_and_delete():
            db.add_food_entry(self.user_id, "2026-11-20", "Lunch", "Soup", 200, 8, 20, 6)
            entry = db.get_food_entries(self.user_id, "2026-11-20")[-1]
            db.delete_food_entry(self.user_id, "2026-11-20", entry["id"])
        growth = memory_growth_kb(log_and_delete, 200)
        report("NFR-13 memory growth, 200 log-and-delete cycles", growth, MEMORY_GROWTH_KB, "KB")
        self.assertLess(growth, MEMORY_GROWTH_KB)

    def test_nfr14_ai_parser_does_not_leak_memory(self):
        answer = json.dumps({"choices": [{"message": {"content": json.dumps({
            "cuisines": ["thai"], "flavors": ["spicy"], "preparation": [],
            "meal_category": "Dinner", "diets": ["Vegan"], "exclusions": ["peanut"],
            "max_cook_minutes": 20,
        })}}]}).encode("utf-8")

        # plain functions, not mocks: a mock remembers every call and would itself use memory
        def fake_urlopen(request, timeout=None):
            return io.BytesIO(answer)

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), \
                patch("services.preference_parser.urlopen", fake_urlopen), \
                patch("services.preference_parser.time.sleep", lambda seconds: None):
            growth = memory_growth_kb(lambda: preference_parser.parse_preferences("spicy thai"), 500)
        report("NFR-14 memory growth, 500 AI parses", growth, MEMORY_GROWTH_KB, "KB")
        self.assertLess(growth, MEMORY_GROWTH_KB)


if __name__ == "__main__":
    unittest.main()