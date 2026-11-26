# Checks that no kind of user gets locked out: every value the forms accept
# must give targets, and every page must open, without an error.
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services import db
from services.targets import CALORIE_FLOOR, GOAL_MODIFIERS, calculate_targets
from services.tdee_engine import (
    OCCUPATION_METS,
    SEX_NOT_SPECIFIED_WARNING,
    STEP_COUNT_ESTIMATES,
    TRAINING_TYPE_METS,
    calculate_bmr,
    calculate_tdee,
)
from services.validation import WEIGHT_MAX_KG, WEIGHT_MIN_KG, validate_profile_settings
from views.onboarding import DEFAULTS, _collect_profile
from views.settings import FITNESS_GOALS

# The smallest and largest values each form allows.
AGES = (15, 16, 100, 120)
HEIGHTS_CM = (100, 120, 250)
WEIGHTS_KG = (WEIGHT_MIN_KG, 30, 300, WEIGHT_MAX_KG)
BODY_FATS = (None, 3, 80)
SEXES = ("Male", "Female", "Other", None)


def make_profile(age, height, weight, body_fat, sex, index=0):
    """A profile with these body values; the other answers rotate with index."""
    goals = list(GOAL_MODIFIERS)
    occupations = list(OCCUPATION_METS)
    training = list(TRAINING_TYPE_METS)
    steps = [0, 50_000, None, *STEP_COUNT_ESTIMATES]
    sessions = (0, 1, 14)[index % 3]
    return {
        "age": age,
        "sex": sex,
        "height_cm": height,
        "weight_kg": weight,
        "body_fat_pct": body_fat,
        "occupation_type": occupations[index % len(occupations)],
        "occupation_hours_per_workday": 8,
        "occupation_days_per_week": 5,
        "daily_steps": steps[index % len(steps)],
        "exercise_sessions": [
            {
                "type": training[index % len(training)],
                "met": TRAINING_TYPE_METS[training[index % len(training)]],
                "duration_minutes": (10, 240)[index % 2],
                "sessions_per_week": sessions,
            }
        ]
        if sessions
        else [],
        "cooking_skill": "Beginner",
        "allergens": [],
        "diets": [],
        "fitness_goal": goals[index % len(goals)],
        "measurement_units": "Metric",
    }


class EveryUserGetsTargetsTests(unittest.TestCase):
    def test_all_edge_combinations_give_targets(self):
        combos = itertools.product(AGES, HEIGHTS_CM, WEIGHTS_KG, BODY_FATS, SEXES)
        for index, values in enumerate(combos):
            profile = make_profile(*values, index=index)
            with self.subTest(profile=values, goal=profile["fitness_goal"]):
                targets = calculate_targets(profile)
                self.assertGreaterEqual(targets["calories"], CALORIE_FLOOR)
                for key in ("protein_g", "carbs_g", "fat_g"):
                    self.assertGreaterEqual(targets[key], 0)
                # Dashboard and weight pages use the saved targets as intake.
                calculate_tdee(profile, macros=targets)

    def test_every_goal_occupation_and_workout_gives_targets(self):
        for goal, occupation, workout in itertools.product(
            GOAL_MODIFIERS, OCCUPATION_METS, TRAINING_TYPE_METS
        ):
            profile = make_profile(30, 175, 75, None, "Female")
            profile.update(fitness_goal=goal, occupation_type=occupation)
            profile["exercise_sessions"] = [
                {"type": workout, "met": TRAINING_TYPE_METS[workout],
                 "duration_minutes": 60, "sessions_per_week": 3}
            ]
            with self.subTest(goal=goal, occupation=occupation, workout=workout):
                self.assertGreaterEqual(calculate_targets(profile)["calories"], CALORIE_FLOOR)

    def test_boundary_values_are_accepted_by_the_engine(self):
        # These used to raise: the forms allowed them but the engine did not.
        for changes in (
            {"weight_kg": 30}, {"weight_kg": 20}, {"weight_kg": 500},
            {"height_cm": 100}, {"height_cm": 250}, {"age": 15},
        ):
            profile = make_profile(30, 175, 75, None, "Male")
            profile.update(changes)
            with self.subTest(changes=changes):
                self.assertGreater(calculate_bmr(profile), 0)
        self.assertGreater(calculate_bmr(make_profile(30, 175, 75, 80, "Male")), 0)

    def test_sex_other_than_male_or_female_uses_the_midpoint(self):
        male = calculate_bmr(make_profile(30, 175, 75, None, "Male"))
        female = calculate_bmr(make_profile(30, 175, 75, None, "Female"))
        for sex in ("Other", "Prefer not to say", None):
            with self.subTest(sex=sex):
                profile = make_profile(30, 175, 75, None, sex)
                self.assertEqual(calculate_bmr(profile), (male + female) / 2)
                self.assertIn(SEX_NOT_SPECIFIED_WARNING, calculate_tdee(profile)["warnings"])
        self.assertNotIn(
            SEX_NOT_SPECIFIED_WARNING,
            calculate_tdee(make_profile(30, 175, 75, None, "Male"))["warnings"],
        )

    def test_values_outside_the_ranges_are_still_rejected(self):
        for changes in (
            {"weight_kg": 19.9}, {"weight_kg": 500.1}, {"height_cm": 99},
            {"height_cm": 251}, {"age": 14}, {"age": 121}, {"age": 30.5},
        ):
            profile = make_profile(30, 175, 75, None, "Male")
            profile.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                calculate_bmr(profile)


class OnboardingEdgeTests(unittest.TestCase):
    def answers(self, **overrides):
        state = dict(DEFAULTS)
        state.update(overrides)
        return state

    def test_smallest_and_largest_metric_answers_are_accepted(self):
        for overrides in (
            {"ob_age": 15, "height_cm": "100", "weight_kg": "30"},
            {"ob_age": 100, "height_cm": "250", "weight_kg": "300"},
            {"ob_use_body_fat": True, "body_fat_pct_input": "80"},
            {"ob_use_body_fat": True, "body_fat_pct_input": "3"},
            {"ob_sex": "Female", "ob_age": 15, "height_cm": "100", "weight_kg": "30"},
        ):
            with self.subTest(overrides=overrides):
                profile, errors = _collect_profile(self.answers(**overrides))
                self.assertFalse(any(errors.values()), errors)
                self.assertIsNotNone(profile)

    def test_smallest_and_largest_imperial_answers_are_accepted(self):
        for height, weight in (("39.38", "66.15"), ("98.42", "661.38")):
            with self.subTest(height=height, weight=weight):
                profile, errors = _collect_profile(
                    self.answers(measurement_units="Imperial", height_cm=height, weight_kg=weight)
                )
                self.assertFalse(any(errors.values()), errors)
                calculate_targets(profile)

    def test_every_goal_occupation_and_skill_is_accepted(self):
        for goal, occupation, skill in itertools.product(
            ("Fat Loss", "Muscle Gain", "Recomposition", "GLP-1 Support"),
            ("Desk Job", "Standing", "Active Work", "Heavy Labor"),
            ("Beginner", "Intermediate", "Advanced"),
        ):
            with self.subTest(goal=goal, occupation=occupation, skill=skill):
                profile, errors = _collect_profile(
                    self.answers(
                        fitness_goal=goal, occupation_movement=occupation, cooking_skill=skill
                    )
                )
                self.assertFalse(any(errors.values()), errors)

    def test_profile_the_engine_cannot_use_is_not_saved(self):
        with patch(
            "views.onboarding.targets_service.calculate_targets",
            side_effect=ValueError("boom"),
        ):
            profile, errors = _collect_profile(self.answers())
        self.assertIsNone(profile)
        self.assertTrue(any("boom" in message for message in errors[1]))


class SettingsEdgeTests(unittest.TestCase):
    def test_weight_log_range_is_accepted_in_settings(self):
        for weight in (WEIGHT_MIN_KG, 30, WEIGHT_MAX_KG):
            with self.subTest(weight=weight):
                self.assertEqual(
                    validate_profile_settings(
                        weight, 0, None, "Desk Job", "Fat Loss", "Metric", "",
                        occupations=list(OCCUPATION_METS), goals=FITNESS_GOALS,
                    ),
                    [],
                )


class PagesOpenForEdgeUsersTests(unittest.TestCase):
    """Open the real pages for unusual saved profiles and check none crash."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_path = patch.object(db, "DB_PATH", Path(directory.name) / "edge.db")
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()

    def open_pages(self, name, profile):
        db.create_user(name, "password")
        user = db.check_login(name, "password")
        db.save_profile(user["id"], profile)
        for module, function in (
            ("views.settings", "render_settings_page"),
            ("views.dashboard", "render_dashboard_page"),
            ("views.diary", "render_diary_page"),
            ("views.weight", "render_weight_page"),
        ):
            with self.subTest(user=name, page=module):
                app = AppTest.from_string(
                    f"from {module} import {function}\n{function}()", default_timeout=30
                )
                app.session_state.user = user
                app.run()
                self.assertFalse(app.exception, [e.message for e in app.exception])

    def test_pages_open_for_edge_profiles(self):
        cases = {
            "small": make_profile(15, 100, 30, None, "Female"),
            "large": make_profile(120, 250, 500, None, "Male"),
            "light-logged": make_profile(40, 150, 20, None, "Female"),
            "body-fat-80": make_profile(40, 170, 120, 80, "Male"),
            "other-sex": make_profile(30, 170, 70, None, "Other"),
        }
        odd = make_profile(30, 170, 70, None, "Male")
        odd.update(fitness_goal="Maintain", allergens=None, diets=["Paleo"])
        cases["unknown-goal"] = odd
        for name, profile in cases.items():
            self.open_pages(name, profile)


if __name__ == "__main__":
    unittest.main()
