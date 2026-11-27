import unittest

from views.onboarding import (
    DEFAULTS,
    _collect_profile,
    _convert_measurement_value,
    _integer_input_warning,
    _measurement_warning,
    _normalize_allergens,
    _onboarding_html,
    _parse_measurement,
    _truncate_input_value,
)


class OnboardingInputTests(unittest.TestCase):
    def test_initial_markup_shows_default_bmi_and_includes_body_fat_control(self):
        html = _onboarding_html()
        self.assertIn("BMI 24.5", html)
        self.assertIn('aria-controls="body-fat-detail"', html)
        self.assertIn('<div id="body-fat-detail">', html)

    def test_footer_contains_navigation_and_step_progress(self):
        footer = _onboarding_html().split("<footer", 1)[1].split("</footer>", 1)[0]
        self.assertIn('id="back"', footer)
        self.assertIn('id="next"', footer)
        self.assertIn("Step 1 of 3 &bull; Body Metrics", footer)
        self.assertIn('<progress id="ob-progress" value="1" max="3"', footer)
        self.assertNotIn("Maintenance TDEE", footer)
        self.assertNotIn('id="target-label"', footer)
        self.assertNotIn("ob-macro", footer)

    def test_height_truncates_more_than_two_decimal_places(self):
        self.assertEqual(_parse_measurement("175.239", "Height (cm)", 100, 250), 175.23)

    def test_measurement_truncates_more_than_two_decimal_places(self):
        self.assertEqual(_parse_measurement("72.389", "Weight (kg)", 30, 300), 72.38)

    def test_height_and_weight_input_values_are_truncated(self):
        self.assertEqual(_truncate_input_value("175.239"), "175.23")
        self.assertEqual(_truncate_input_value("72.389"), "72.38")

    def test_input_values_with_trailing_zero_decimals_are_normalized(self):
        self.assertEqual(_truncate_input_value("-173.00"), "-173")

    def test_measurement_warnings_report_out_of_range_values_immediately(self):
        self.assertEqual(
            _measurement_warning("99", "Height (cm)", 100, 250),
            "Height (cm) must be between 100 and 250.",
        )
        self.assertEqual(
            _measurement_warning("301", "Weight (kg)", 30, 300),
            "Weight (kg) must be between 30 and 300.",
        )
        self.assertEqual(
            _measurement_warning("-1", "Body Fat %", 3, 80),
            "Body Fat % must be between 3 and 80.",
        )
        self.assertIsNone(_measurement_warning("175", "Height (cm)", 100, 250))
        self.assertIsNone(_measurement_warning("", "Height (cm)", 100, 250))

    def test_large_values_report_range_warning(self):
        for label, minimum, maximum in (
            ("Height (cm)", 100, 250),
            ("Weight (kg)", 30, 300),
            ("Body Fat %", 3, 80),
        ):
            with self.subTest(label=label):
                self.assertEqual(
                    _measurement_warning("89234849", label, minimum, maximum),
                    f"{label} must be between {minimum} and {maximum}.",
                )

    def test_measurement_warning_reports_non_numeric_values(self):
        self.assertEqual(
            _measurement_warning("five", "Height (cm)", 100, 250),
            "Height (cm) must be a number.",
        )

    def test_integer_input_warnings_report_invalid_custom_steps_and_duration(self):
        self.assertEqual(
            _integer_input_warning("89234849", "Custom daily steps", 0, 50000),
            "Custom daily steps must be between 0 and 50000.",
        )
        self.assertEqual(
            _integer_input_warning("-1", "Average time per workout", 10, 240),
            "Average time per workout must be between 10 and 240.",
        )
        self.assertEqual(
            _integer_input_warning("10.5", "Average time per workout", 10, 240),
            "Average time per workout must be a whole number.",
        )
        self.assertIsNone(
            _integer_input_warning("50000", "Custom daily steps", 0, 50000)
        )
        self.assertIsNone(
            _integer_input_warning("60", "Average time per workout", 10, 240)
        )
        self.assertIsNone(
            _integer_input_warning("", "Custom daily steps", 0, 50000)
        )

    def test_body_fat_percentage_truncates_more_than_two_decimal_places(self):
        self.assertEqual(_parse_measurement("18.239", "Body Fat %", 3, 80), 18.23)

    def test_body_fat_percentage_accepts_requested_range_boundaries(self):
        self.assertEqual(_parse_measurement("3", "Body Fat %", 3, 80), 3)
        self.assertEqual(_parse_measurement("80", "Body Fat %", 3, 80), 80)

    def test_body_fat_percentage_rejects_negative_and_out_of_range_values(self):
        for value in ("-1", "2.99", "80.01"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    ValueError, "Body Fat % must be between 3 and 80"
                ):
                    _parse_measurement(value, "Body Fat %", 3, 80)

    def test_negative_weight_reports_weight_range(self):
        with self.assertRaisesRegex(ValueError, "Weight \\(kg\\).*between 30 and 300"):
            _parse_measurement(_truncate_input_value("-173.00"), "Weight (kg)", 30, 300)

    def test_negative_height_reports_height_range(self):
        with self.assertRaisesRegex(ValueError, "Height \\(cm\\).*between 100 and 250"):
            _parse_measurement(_truncate_input_value("-173.00"), "Height (cm)", 100, 250)

    def test_non_numeric_measurement_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Height \\(cm\\) must be a number"):
            _parse_measurement("five", "Height (cm)", 100, 250)

    def test_metric_inputs_convert_to_truncated_imperial_values(self):
        self.assertEqual(
            _convert_measurement_value("175", "height", "Metric", "Imperial"),
            "68.89",
        )
        self.assertEqual(
            _convert_measurement_value("75", "weight", "Metric", "Imperial"),
            "165.34",
        )

    def test_imperial_inputs_convert_to_metric_values(self):
        self.assertEqual(
            _convert_measurement_value("68.90", "height", "Imperial", "Metric"),
            "175.00",
        )
        self.assertEqual(
            _convert_measurement_value("165.35", "weight", "Imperial", "Metric"),
            "75.00",
        )

    def test_minimum_imperial_values_convert_within_metric_ranges(self):
        self.assertGreaterEqual(
            float(_convert_measurement_value("39.38", "height", "Imperial", "Metric")),
            100,
        )
        self.assertGreaterEqual(
            float(_convert_measurement_value("66.15", "weight", "Imperial", "Metric")),
            30,
        )

    def test_custom_restrictions_are_optional_and_comma_separated(self):
        self.assertEqual(_normalize_allergens(["Dairy", "Other"], ""), ["Dairy"])
        self.assertEqual(
            _normalize_allergens(["Other"], "sesame, mushrooms"),
            ["sesame", "mushrooms"],
        )


class CollectProfileTests(unittest.TestCase):
    def answers(self, **overrides):
        state = dict(DEFAULTS)
        state.update(overrides)
        return state

    def test_default_answers_build_a_complete_profile(self):
        profile, errors = _collect_profile(self.answers())
        self.assertFalse(any(errors.values()))
        self.assertEqual(profile["height_cm"], 175)
        self.assertEqual(profile["weight_kg"], 75)
        self.assertIsNone(profile["body_fat_pct"])
        self.assertEqual(profile["measurement_units"], "Metric")

    def test_up_to_fourteen_training_sessions_are_accepted(self):
        profile, errors = _collect_profile(self.answers(training_sessions_per_week=14))
        self.assertFalse(errors[2])
        self.assertEqual(profile["exercise_sessions"][0]["sessions_per_week"], 14)
        _, errors = _collect_profile(self.answers(training_sessions_per_week=15))
        self.assertTrue(errors[2])

    def test_no_sessions_means_no_exercise(self):
        profile, _ = _collect_profile(self.answers(training_sessions_per_week=0))
        self.assertEqual(profile["exercise_sessions"], [])

    def test_errors_are_reported_on_the_step_they_belong_to(self):
        profile, errors = _collect_profile(
            self.answers(
                height_cm="five",
                daily_steps_option="Custom amount",
                custom_daily_steps_input="",
            )
        )
        self.assertIsNone(profile)
        self.assertEqual(errors[1], ["Height (cm) must be a number."])
        self.assertEqual(errors[2], ["Custom daily steps must be a whole number."])

    def test_body_fat_is_only_used_when_switched_on(self):
        profile, _ = _collect_profile(self.answers(body_fat_pct_input="18"))
        self.assertIsNone(profile["body_fat_pct"])
        profile, _ = _collect_profile(
            self.answers(ob_use_body_fat=True, body_fat_pct_input="18")
        )
        self.assertEqual(profile["body_fat_pct"], 18)

    def test_imperial_answers_are_saved_in_metric(self):
        profile, _ = _collect_profile(
            self.answers(measurement_units="Imperial", height_cm="68.9", weight_kg="165.35")
        )
        self.assertAlmostEqual(profile["height_cm"], 175.0, places=1)
        self.assertAlmostEqual(profile["weight_kg"], 75.0, places=1)
        self.assertEqual(profile["measurement_units"], "Imperial")

    def test_allergen_pills_and_custom_exclusions_are_combined(self):
        profile, _ = _collect_profile(
            self.answers(allergens=["Dairy"], other_allergen="cilantro, mushrooms")
        )
        self.assertEqual(profile["allergens"], ["Dairy", "cilantro", "mushrooms"])


if __name__ == "__main__":
    unittest.main()
