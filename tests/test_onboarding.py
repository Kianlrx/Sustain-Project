import unittest

from views.onboarding import (
    _convert_measurement_value,
    _normalize_allergens,
    _parse_measurement,
    _truncate_input_value,
)


class OnboardingInputTests(unittest.TestCase):
    def test_height_truncates_more_than_two_decimal_places(self):
        self.assertEqual(_parse_measurement("175.239", "Height (cm)", 100, 250), 175.23)

    def test_measurement_truncates_more_than_two_decimal_places(self):
        self.assertEqual(_parse_measurement("72.389", "Weight (kg)", 30, 300), 72.38)

    def test_height_and_weight_input_values_are_truncated(self):
        self.assertEqual(_truncate_input_value("175.239"), "175.23")
        self.assertEqual(_truncate_input_value("72.389"), "72.38")

    def test_body_fat_percentage_truncates_more_than_two_decimal_places(self):
        self.assertEqual(_parse_measurement("18.239", "Body Fat %", 3, 60), 18.23)

    def test_negative_weight_reports_weight_range(self):
        with self.assertRaisesRegex(ValueError, "Weight \\(kg\\).*between 30 and 300"):
            _parse_measurement("-5", "Weight (kg)", 30, 300)

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


if __name__ == "__main__":
    unittest.main()
