from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services import db
from services.targets import CALORIE_FLOOR, calculate_targets, explain_targets
from services.tdee_engine import OCCUPATION_METS, WORK_STEPS_WARNING
from services.validation import (
    validate_food_entry,
    validate_manual_targets,
    validate_profile_settings,
)
from views.settings import FITNESS_GOALS

OCCUPATIONS = list(OCCUPATION_METS)

PROFILE = {
    "age": 30,
    "sex": "Male",
    "height_cm": 180,
    "weight_kg": 80.0,
    "body_fat_pct": None,
    "occupation_type": "Desk Job",
    "occupation_hours_per_workday": 8,
    "occupation_days_per_week": 5,
    "daily_steps": 7000,
    "exercise_sessions": [
        {
            "type": "Weight training (low intensity)",
            "met": 3.5,
            "duration_minutes": 60,
            "sessions_per_week": 3,
        }
    ],
    "cooking_skill": "Beginner",
    "allergens": [],
    "diets": [],
    "fitness_goal": "Fat Loss",
    "measurement_units": "Metric",
}


def settings_errors(**changes):
    values = dict(
        weight_kg=80.0,
        sessions_per_week=3,
        session_duration=60,
        occupation="Desk Job",
        goal="Fat Loss",
        measurement_units="Metric",
        other_exclusions="",
    )
    values.update(changes)
    return validate_profile_settings(**values, occupations=OCCUPATIONS, goals=FITNESS_GOALS)


class SettingsValidationTests(unittest.TestCase):
    def test_valid_settings_have_no_errors(self):
        self.assertEqual(settings_errors(), [])

    def test_zero_sessions_does_not_need_a_duration(self):
        self.assertEqual(settings_errors(sessions_per_week=0, session_duration=None), [])

    def test_negative_values_are_rejected(self):
        self.assertIn("Weight can't be negative.", settings_errors(weight_kg=-5))
        self.assertIn(
            "Training sessions per week can't be negative.",
            settings_errors(sessions_per_week=-1),
        )
        self.assertIn("Session duration can't be negative.", settings_errors(session_duration=-30))

    def test_out_of_range_values_are_rejected(self):
        self.assertTrue(settings_errors(weight_kg=19.5))
        self.assertTrue(settings_errors(weight_kg=500.5))
        self.assertTrue(settings_errors(sessions_per_week=15))
        self.assertTrue(settings_errors(session_duration=5))
        self.assertTrue(settings_errors(session_duration=241))

    def test_empty_values_are_rejected(self):
        self.assertIn("Weight is required.", settings_errors(weight_kg=None))
        self.assertIn("Weight is required.", settings_errors(weight_kg=""))
        self.assertIn("Session duration is required.", settings_errors(session_duration=None))

    def test_non_numbers_are_rejected(self):
        self.assertIn("Weight must be a number.", settings_errors(weight_kg="eighty"))
        self.assertIn("Weight must be a number.", settings_errors(weight_kg=float("nan")))
        self.assertIn("Weight must be a number.", settings_errors(weight_kg=True))
        self.assertTrue(settings_errors(sessions_per_week=2.5))

    def test_choices_must_come_from_the_lists(self):
        self.assertTrue(settings_errors(occupation="Astronaut"))
        self.assertTrue(settings_errors(goal="Bulk forever"))
        self.assertTrue(settings_errors(measurement_units="Stones"))

    def test_very_long_exclusion_is_rejected(self):
        self.assertTrue(settings_errors(other_exclusions="x" * 51))
        self.assertEqual(settings_errors(other_exclusions="kiwi, mango"), [])


class ManualTargetValidationTests(unittest.TestCase):
    def test_valid_targets_have_no_errors(self):
        self.assertEqual(
            validate_manual_targets(dict(calories=2000, protein_g=150, carbs_g=200, fat_g=60)),
            [],
        )

    def test_negative_out_of_range_and_empty_targets_are_rejected(self):
        errors = validate_manual_targets(dict(calories=1000, protein_g=-1, carbs_g=900, fat_g=None))
        self.assertIn("Calories must be between 1200 and 6000 kcal.", errors)
        self.assertIn("Protein can't be negative.", errors)
        self.assertIn("Carbs must be between 0 and 800 g.", errors)
        self.assertIn("Fat is required.", errors)


class FoodEntryValidationTests(unittest.TestCase):
    def test_valid_food_has_no_errors(self):
        self.assertEqual(validate_food_entry("Toast", 120, 4, 20, 2), [])

    def test_zero_is_allowed(self):
        self.assertEqual(validate_food_entry("Water", 0, 0, 0, 0), [])

    def test_empty_name_and_numbers_are_rejected(self):
        errors = validate_food_entry("   ", None, None, None, None)
        self.assertIn("Food name is required.", errors)
        self.assertIn("Calories is required.", errors)
        self.assertEqual(len(errors), 5)

    def test_negative_values_are_rejected(self):
        errors = validate_food_entry("Toast", -120, -1, -1, -1)
        self.assertIn("Calories can't be negative.", errors)
        self.assertIn("Fat can't be negative.", errors)

    def test_out_of_range_values_are_rejected(self):
        self.assertIn(
            "Calories must be between 0 and 5000 kcal.",
            validate_food_entry("Cake", 50000, 4, 20, 2),
        )
        self.assertTrue(validate_food_entry("Cake", 500, 501, 20, 2))
        self.assertTrue(validate_food_entry("x" * 101, 100, 1, 1, 1))


class TargetExplanationTests(unittest.TestCase):
    def test_explanation_matches_the_real_targets(self):
        steps = explain_targets(PROFILE)
        self.assertEqual(steps["targets"], calculate_targets(PROFILE))
        self.assertEqual(steps["goal_modifier"], 0.80)
        self.assertEqual(steps["goal_adjusted_kcal"], round(steps["tdee_kcal"] * 0.80))
        self.assertEqual(steps["targets"]["calories"], steps["goal_adjusted_kcal"])
        self.assertAlmostEqual(  # parts are rounded one by one, so allow 2 kcal
            steps["tdee_kcal"],
            steps["bmr_kcal"] + steps["neat_kcal"] + steps["eat_kcal"] + steps["tef_kcal"],
            delta=2,
        )
        self.assertAlmostEqual(
            steps["activity_multiplier"], steps["tdee_kcal"] / steps["bmr_kcal"], places=2
        )
        self.assertEqual(steps["bmr_method"], "Mifflin-St Jeor")

    def test_explanation_flags_the_calorie_floor(self):
        small = dict(PROFILE, age=80, sex="Female", height_cm=150, weight_kg=40.0,
                     exercise_sessions=[], daily_steps=0, fitness_goal="Fat Loss")
        steps = explain_targets(small)
        self.assertTrue(steps["calorie_floor_applied"])
        self.assertEqual(steps["targets"]["calories"], CALORIE_FLOOR)


class FormsInAppTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_path = patch.object(db, "DB_PATH", Path(directory.name) / "forms.db")
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()
        db.create_user("forms-test", "password")
        self.user = db.check_login("forms-test", "password")
        db.save_profile(self.user["id"], dict(PROFILE))

    def settings_app(self):
        app = AppTest.from_string(
            "from views.settings import render_settings_page\nrender_settings_page()",
            default_timeout=15,
        )
        app.session_state.user = self.user
        app.run()
        self.assertFalse(app.exception)
        return app

    def test_settings_shows_how_targets_are_calculated(self):
        app = self.settings_app()
        expanders = [e.label for e in app.expander]
        self.assertIn("How your targets are calculated", expanders)
        text = " ".join(m.value for m in app.markdown)
        self.assertIn("Resting burn (BMR)", text)
        self.assertIn("activity multiplier", text)
        self.assertIn("Goal adjustment (Fat Loss)", text)

    def test_settings_has_no_work_steps_input_or_warning(self):
        app = self.settings_app()
        labels = [n.label.lower() for n in app.number_input] + [
            t.label.lower() for t in app.text_input
        ]
        self.assertFalse([label for label in labels if "step" in label])
        self.assertNotIn(WORK_STEPS_WARNING, [w.value for w in app.warning])

    def test_quick_log_shows_errors_for_empty_and_negative_values(self):
        def quick_log():
            from views.diary import _render_quick_log
            _render_quick_log(1, "Lunch", "2026-01-01")

        app = AppTest.from_function(quick_log, default_timeout=15)
        app.run()
        app.button[0].click().run()
        errors = [e.value for e in app.error]
        self.assertIn("Food name is required.", errors)
        self.assertIn("Calories is required.", errors)

        app.text_input[0].set_value("Toast")
        for box in app.number_input:
            box.set_value(-5)
        app.button[0].click().run()
        errors = [e.value for e in app.error]
        self.assertIn("Calories can't be negative.", errors)
        self.assertEqual(db.get_food_entries(1, "2026-01-01"), [])

        for box in app.number_input:
            box.set_value(10)
        app.button[0].click().run()
        self.assertFalse(app.error)
        self.assertEqual(len(db.get_food_entries(1, "2026-01-01")), 1)


if __name__ == "__main__":
    unittest.main()
