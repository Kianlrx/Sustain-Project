import math
import unittest

from views.dashboard import (
    _nutrition_section,
    _profile_summary,
    _projected_weight,
    _projection_markup,
    _trajectory_chart,
)


class WeightTrajectoryTests(unittest.TestCase):
    def test_dynamic_projection_matches_reference_at_start(self):
        self.assertEqual(_projected_weight(80, 500, 0), 80)

    def test_dynamic_projection_matches_reference_equation_at_24_weeks(self):
        expected = (
            80
            - 2.54 * (1 - math.exp(-0.35 * 24))
            - 9.79 * (1 - math.exp(-0.0415 * 24))
        )
        self.assertAlmostEqual(_projected_weight(80, 500, 24), expected)

    def test_dynamic_curve_is_nonlinear_and_slows_over_time(self):
        start = _projected_weight(80, 500, 0)
        first_week = _projected_weight(80, 500, 1)
        second_week = _projected_weight(80, 500, 2)
        third_week = _projected_weight(80, 500, 3)
        self.assertGreater(start - first_week, second_week - third_week)

    def test_projection_scales_with_daily_deficit(self):
        self.assertAlmostEqual(
            80 - _projected_weight(80, 250, 24),
            (80 - _projected_weight(80, 500, 24)) / 2,
        )

    def test_non_deficit_has_no_weight_loss_projection(self):
        self.assertEqual(_projected_weight(80, 0, 24), 80)

    def test_chart_shows_weight_axis_and_only_dynamic_curve(self):
        chart = _trajectory_chart(80, 500)
        self.assertIn("Weight (kg)", chart)
        self.assertIn("Week 24:", chart)
        self.assertEqual(chart.count('class="sd-chart-point"'), 25)
        self.assertNotIn("Linear comparison", chart)
        self.assertNotIn("sd-chart-linear-segment", chart)

    def test_chart_uses_imperial_units_for_all_weekly_hover_values(self):
        chart = _trajectory_chart(75, 500, measurement_units="Imperial")
        self.assertIn("Weight (lb)", chart)
        self.assertIn("Week 0: 165.3 lb estimated weight", chart)
        self.assertIn("Week 24:", chart)

    def test_chart_can_show_a_constant_calorie_target(self):
        chart = _trajectory_chart(80, 500, metric="Calories", calorie_target=1800)
        self.assertIn("Calories (kcal/day)", chart)
        self.assertEqual(chart.count('class="sd-chart-point"'), 25)
        self.assertIn("Week 24: 1800.0 kcal/day calorie target", chart)

    def test_projection_reports_expected_next_week_change_in_selected_units(self):
        markup = _projection_markup(
            {"weight_kg": 75, "measurement_units": "Imperial"}, -500
        )
        self.assertIn("Expected change next week:", markup)
        self.assertIn("lb", markup)

    def test_profile_summary_is_a_card_and_formats_imperial_measurements(self):
        markup = _profile_summary(
            {
                "age": 25,
                "sex": "Female",
                "height_cm": 175,
                "weight_kg": 75,
                "measurement_units": "Imperial",
                "fitness_goal": "Fat Loss",
                "exercise_sessions": [],
                "diets": [],
                "allergens": [],
            },
            {"bmr_method": "Mifflin-St Jeor"},
        )
        self.assertIn("Your nutrition profile", markup)
        self.assertIn("68.9 in", markup)
        self.assertIn("165.3 lb", markup)
        self.assertNotIn("sd-pills", markup)

    def test_nutrition_section_uses_separate_macro_cards_with_percentages(self):
        markup = _nutrition_section(
            {"calories": 1800, "protein_g": 135, "carbs_g": 180, "fat_g": 60},
            {"tdee_kcal": 2000},
            -200,
        )
        self.assertIn("sd-calorie-card", markup)
        self.assertEqual(markup.count('class="sd-macro-card"'), 3)
        self.assertIn("135 g", markup)
        self.assertIn("30%", markup)
        self.assertEqual(markup.count('class="sd-budget"'), 4)

    def test_projection_explains_early_water_shift_and_slowing(self):
        markup = _projection_markup({"weight_kg": 80}, -500)
        self.assertIn("glycogen and its associated water", markup)
        self.assertIn("gradually slows", markup)
        self.assertIn("real results vary", markup)


if __name__ == "__main__":
    unittest.main()
