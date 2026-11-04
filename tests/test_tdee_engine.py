import unittest

from services.tdee_engine import (
    OCCUPATION_METS,
    TRAINING_TYPE_METS,
    calculate_bmr,
    calculate_eat,
    calculate_neat,
    calculate_occupational_neat,
    calculate_tdee,
)
from services.targets import calculate_targets


TEST_PROFILES = [
    {
        "age": 25, "sex": "Male", "height_cm": 175, "weight_kg": 75,
        "body_fat_pct": None,
        "occupation_type": "Desk Job", "daily_steps": "2,500-5,000",
    },
    {
        "age": 35, "sex": "Female", "height_cm": 165, "weight_kg": 65,
        "body_fat_pct": None,
        "occupation_type": "Standing", "daily_steps": "5,000-7,500",
    },
    {
        "age": 40, "sex": "Male", "height_cm": 180, "weight_kg": 90,
        "body_fat_pct": 25,
        "occupation_type": "Active Work", "daily_steps": "7,500-10,000",
    },
    {
        "age": 28, "sex": "Female", "height_cm": 160, "weight_kg": 55,
        "body_fat_pct": 22,
        "occupation_type": "Desk Job", "daily_steps": "More than 10,000",
    },
    {
        "age": 20, "sex": "Male", "height_cm": 184, "weight_kg": 93,
        "body_fat_pct": 20,
        "occupation_type": "Desk Job", "daily_steps": 8_800, # Zach
    },
    {
        "age": 52, "sex": "Female", "height_cm": 168, "weight_kg": 78,
        "body_fat_pct": 35,
        "occupation_type": "Heavy Labor", "daily_steps": "Less than 2,500",
    },
    {
        "age": 67, "sex": "Male", "height_cm": 172, "weight_kg": 70,
        "body_fat_pct": None,
        "occupation_type": "Standing", "daily_steps": 0,
    },
    {
        "age": 19, "sex": "Female", "height_cm": 170, "weight_kg": 60,
        "body_fat_pct": 18,
        "occupation_type": "Desk Job", "daily_steps": "2,500-5,000",
    },
    {
        "age": 45, "sex": "Male", "height_cm": 178, "weight_kg": 105,
        "body_fat_pct": 32,
        "occupation_type": "Active Work", "daily_steps": "More than 10,000",
    },
    {
        "age": 39, "sex": "Female", "height_cm": 155, "weight_kg": 92,
        "body_fat_pct": None,
        "occupation_type": "Standing", "daily_steps": "5,000-7,500",
    },
]

TEST_EXERCISE_SESSIONS = [
    [{
        "type": "Weight training (low intensity)", "met": 3.5,
        "duration_minutes": 45, "sessions_per_week": 1, "steps_per_session": 0,
    }],
    [{
        "type": "Weight training (low intensity)", "met": 3.5,
        "duration_minutes": 60, "sessions_per_week": 3, "steps_per_session": 0,
    }],
    [{
        "type": "Endurance training (medium intensity)", "met": 6.8,
        "duration_minutes": 45, "sessions_per_week": 2, "steps_per_session": 0,
    }],
    [{
        "type": "Interval training (high intensity)", "met": 8.0,
        "duration_minutes": 30, "sessions_per_week": 3, "steps_per_session": 0,
    }],
    [{
        "type": "Weight training (low intensity)", "met": 3.5,
        "duration_minutes": 75, "sessions_per_week": 4, "steps_per_session": 0,
    }],
    [{
        "type": "Endurance training (medium intensity)", "met": 6.8,
        "duration_minutes": 50, "sessions_per_week": 2, "steps_per_session": 0,
    }],
    [{
        "type": "Endurance training (medium intensity)", "met": 6.8,
        "duration_minutes": 40, "sessions_per_week": 2, "steps_per_session": 0,
    }],
    [{
        "type": "Weight training (low intensity)", "met": 3.5,
        "duration_minutes": 55, "sessions_per_week": 3, "steps_per_session": 0,
    }],
    [{
        "type": "Interval training (high intensity)", "met": 8.0,
        "duration_minutes": 35, "sessions_per_week": 4, "steps_per_session": 0,
    }],
    [{
        "type": "Interval training (high intensity)", "met": 8.0,
        "duration_minutes": 30, "sessions_per_week": 14, "steps_per_session": 0,
    }],
]

for test_profile, sessions in zip(TEST_PROFILES, TEST_EXERCISE_SESSIONS):
    test_profile["exercise_sessions"] = sessions

OCCUPATION_SCHEDULES = [
    (8, 5, 500),
    (8, 5, 2500),
    (4, 5, 4000),
    (8, 5, 1000),
    (4, 5, 6000),
    (2, 5, 500),
    (8, 5, 0),
    (8, 5, 500),
    (4, 5, 5000),
    (8, 5, 2500),
]
for test_profile, (hours, days, work_steps) in zip(
    TEST_PROFILES, OCCUPATION_SCHEDULES
):
    test_profile["occupation_hours_per_workday"] = hours
    test_profile["occupation_days_per_week"] = days
    test_profile["occupational_steps_per_workday"] = work_steps


class TdeeEngineTests(unittest.TestCase):
    def test_ten_onboarding_scenarios_return_complete_breakdowns(self):
        self.assertEqual(len(TEST_PROFILES), 10)
        print("\nTDEE calculation scenarios (all kcal values are per day)")
        for index, profile in enumerate(TEST_PROFILES, start=1):
            with self.subTest(case=index):
                result = calculate_tdee(profile)
                session = profile["exercise_sessions"][0]
                expected_eat = (
                    (session["met"] - 1)
                    * 3.5
                    * profile["weight_kg"]
                    / 200
                    * session["duration_minutes"]
                    * session["sessions_per_week"]
                    / 7
                )
                macro_kcals = {
                    "protein": result["macros"]["protein_g"] * 4,
                    "carbs": result["macros"]["carbs_g"] * 4,
                    "fat": result["macros"]["fat_g"] * 9,
                }
                bmr_formula = (
                    "Katch-McArdle"
                    if profile["body_fat_pct"] is not None
                    else "Mifflin-St Jeor"
                )
                session_summary = ", ".join(
                    f"{session['type']} (MET {session['met']}, "
                    f"{session['duration_minutes']} min x "
                    f"{session['sessions_per_week']}/week)"
                    for session in profile["exercise_sessions"]
                ) or "No planned training"
                print(
                    f"\nCase {index}\n"
                    f"  Inputs: age={profile['age']}, sex={profile['sex']}, "
                    f"height_cm={profile['height_cm']}, weight_kg={profile['weight_kg']}, "
                    f"body_fat_pct={profile['body_fat_pct']}, "
                    f"occupation_type={profile['occupation_type']}, "
                    f"daily_steps={profile['daily_steps']}, "
                    f"exercise_sessions={session_summary}\n"
                    f"  Formula/factors: BMR={bmr_formula}, "
                    f"occupation_MET={result['occupation_met']}, "
                    f"work_time={profile['occupation_hours_per_workday']} h/day x "
                    f"{profile['occupation_days_per_week']} days/week, "
                    f"work_steps={profile['occupational_steps_per_workday']}/workday, "
                    f"EAT_method={result['eat_method']}, "
                    f"step_count_used={result['step_count_used']}\n"
                    f"  Components: BMR={result['bmr_kcal']} kcal, "
                    f"NEAT={result['neat_kcal']} kcal, EAT={result['eat_kcal']} kcal, "
                    f"TEF={result['tef_kcal']} kcal\n"
                    f"  Macros: protein={result['macros']['protein_g']} g "
                    f"({macro_kcals['protein']} kcal), "
                    f"carbs={result['macros']['carbs_g']} g "
                    f"({macro_kcals['carbs']} kcal), "
                    f"fat={result['macros']['fat_g']} g "
                    f"({macro_kcals['fat']} kcal); "
                    f"macro calorie total={sum(macro_kcals.values())} kcal\n"
                    f"  TDEE={result['tdee_kcal']} kcal/day"
                )
                self.assertAlmostEqual(result["eat_kcal"], round(expected_eat), delta=1)
                self.assertGreater(result["bmr_kcal"], 0)
                self.assertGreaterEqual(result["neat_kcal"], 0)
                self.assertGreaterEqual(result["eat_kcal"], 0)
                self.assertGreaterEqual(result["tef_kcal"], 0)
                self.assertAlmostEqual(
                    result["tdee_kcal"],
                    sum(
                        result[key]
                        for key in ("bmr_kcal", "neat_kcal", "eat_kcal", "tef_kcal")
                    ),
                    delta=1,
                )

    def test_body_fat_selects_katch_mcardle(self):
        profile = TEST_PROFILES[2]
        expected = 370 + 21.6 * (90 * 0.75)
        self.assertEqual(calculate_bmr(profile), expected)

    def test_missing_body_fat_selects_mifflin_st_jeor(self):
        profile = TEST_PROFILES[0]
        expected = 10 * 75 + 6.25 * 175 - 5 * 25 + 5
        self.assertEqual(calculate_bmr(profile), expected)

    def test_custom_macros_are_used_for_tef(self):
        result = calculate_tdee(
            TEST_PROFILES[0],
            macros={"protein_g": 100, "carbs_g": 200, "fat_g": 50},
        )
        self.assertEqual(result["tef_kcal"], round(100 + 200 * 0.3 + 50 * 0.135))

    def test_net_met_exercise_is_averaged_over_the_week(self):
        sessions = [{
            "met": 6.8,
            "duration_minutes": 60,
            "sessions_per_week": 3,
        }]
        expected = (6.8 - 1) * 3.5 * 80 / 200 * 60 * 3 / 7
        self.assertAlmostEqual(calculate_eat(80, sessions), expected)

    def test_training_type_met_estimates_increase_with_intensity(self):
        self.assertLess(
            TRAINING_TYPE_METS["Weight training (low intensity)"],
            TRAINING_TYPE_METS["Endurance training (medium intensity)"],
        )
        self.assertLess(
            TRAINING_TYPE_METS["Endurance training (medium intensity)"],
            TRAINING_TYPE_METS["Interval training (high intensity)"],
        )
        self.assertEqual(TRAINING_TYPE_METS["Weight training (low intensity)"], 3.5)

    def test_hourly_calorie_estimate_matches_net_met_engine(self):
        weight_kg = 75
        for exercise_type, met in TRAINING_TYPE_METS.items():
            with self.subTest(exercise_type=exercise_type):
                hourly_estimate = (met - 1) * 3.5 * weight_kg / 200 * 60
                engine_estimate = calculate_eat(
                    weight_kg,
                    [{
                        "type": exercise_type,
                        "met": met,
                        "duration_minutes": 60,
                        "sessions_per_week": 7,
                    }],
                )
                self.assertAlmostEqual(engine_estimate, hourly_estimate)

    def test_onboarding_training_inputs_cover_one_to_fourteen_sessions(self):
        sessions = [
            profile["exercise_sessions"][0]
            for profile in TEST_PROFILES
        ]
        weekly_frequencies = [session["sessions_per_week"] for session in sessions]
        self.assertEqual(min(weekly_frequencies), 1)
        self.assertEqual(max(weekly_frequencies), 14)
        self.assertEqual(len(TEST_PROFILES), 10)
        self.assertTrue(
            all(10 <= session["duration_minutes"] <= 240 for session in sessions)
        )
        self.assertTrue(
            all(session["type"] in TRAINING_TYPE_METS for session in sessions)
        )

    def test_workout_steps_are_removed_from_step_based_neat(self):
        neat_without_workout_steps = calculate_neat(
            1500, 80, 10_000, "Desk Job", exercise_steps_per_day=0
        )
        neat_with_workout_steps = calculate_neat(
            1500, 80, 10_000, "Desk Job", exercise_steps_per_day=2_000
        )
        self.assertAlmostEqual(
            neat_without_workout_steps - neat_with_workout_steps,
            2_000 * 80 * 0.00035,
        )

    def test_occupational_neat_scales_with_met_hours_and_workdays(self):
        weight = 80
        met = OCCUPATION_METS["Active Work"]
        expected = (met - 1) * 3.5 * weight / 200 * 4 * 60 * 5 / 7
        occupational_neat, total_work_kcal, counted_work_steps = (
            calculate_occupational_neat(weight, "Active Work", 4, 5, 0)
        )
        self.assertAlmostEqual(occupational_neat, expected)
        self.assertAlmostEqual(total_work_kcal, expected)
        self.assertEqual(counted_work_steps, 0)

    def test_occupational_steps_are_not_counted_twice(self):
        weight = 80
        work_steps = 3_000
        workdays = 5
        result = calculate_occupational_neat(
            weight, "Active Work", 4, workdays, work_steps
        )
        estimated_weekly_average_steps = work_steps * workdays / 7
        expected_step_energy = (
            estimated_weekly_average_steps * weight * 0.00035
        )
        self.assertAlmostEqual(result[2], expected_step_energy)
        self.assertAlmostEqual(
            result[0] + result[2],
            result[1],
        )
        neat = calculate_neat(
            1_800,
            weight,
            8_000,
            "Active Work",
            occupation_hours_per_workday=4,
            occupation_days_per_week=workdays,
            occupational_steps_per_workday=work_steps,
        )
        expected_neat = result[0] + (
            8_000 - estimated_weekly_average_steps
        ) * weight * 0.00035
        self.assertAlmostEqual(neat, expected_neat)

    def test_legacy_profiles_keep_old_occupation_multiplier_with_warning(self):
        profile = {
            "age": 25, "sex": "Male", "height_cm": 175, "weight_kg": 75,
            "body_fat_pct": None, "occupation_type": "Desk Job",
            "daily_steps": 0, "exercise_sessions": [],
        }
        result = calculate_tdee(profile)
        self.assertEqual(result["neat_multiplier"], 0.05)
        self.assertEqual(result["occupation_non_step_neat_kcal"], round(result["bmr_kcal"] * 0.05))
        self.assertTrue(any("legacy occupation multiplier" in warning for warning in result["warnings"]))

    def test_no_training_sessions_means_zero_eat(self):
        profile = {**TEST_PROFILES[0], "exercise_sessions": []}
        self.assertEqual(calculate_tdee(profile)["eat_kcal"], 0)

    def test_onboarding_profile_drives_daily_targets(self):
        profile = {**TEST_PROFILES[0], "fitness_goal": "Recomposition"}
        tdee = calculate_tdee(profile)["tdee_kcal"]
        targets = calculate_targets(profile)
        self.assertEqual(targets["calories"], tdee)
        self.assertEqual(targets["protein_g"], round(1.8 * profile["weight_kg"]))


if __name__ == "__main__":
    unittest.main()
