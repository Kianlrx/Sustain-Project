import unittest

from views.dashboard import COLORS
from views.diary import (
    _display_meal_slot,
    _format_nutrient,
    _meal_summary_markup,
    _progress_label_markup,
    _progress_markup,
    _progress_percentage,
)


class DiaryProgressTests(unittest.TestCase):
    def test_formats_nutrients_without_unnecessary_decimal_zeros(self):
        self.assertEqual(_format_nutrient(22), "22")
        self.assertEqual(_format_nutrient(22.5), "22.5")

    def test_displays_snack_meal_as_plural(self):
        self.assertEqual(_display_meal_slot("Snack"), "Snacks")

    def test_meal_summary_contains_calories_and_all_macros(self):
        markup = _meal_summary_markup(
            {
                "calories": 825,
                "protein_g": 22,
                "carbs_g": 108,
                "fat_g": 34,
            },
            has_entries=True,
        )

        self.assertIn("825 kcal", markup)
        self.assertIn("22p", markup)
        self.assertIn("108c", markup)
        self.assertIn("34f", markup)

    def test_progress_label_is_bold(self):
        markup = _progress_label_markup("Calories")

        self.assertIn("<strong>Calories</strong>", markup)

    def test_macro_progress_label_shows_percentage(self):
        markup = _progress_label_markup("Protein", "16%")

        self.assertIn("<strong>Protein</strong>", markup)
        self.assertIn("<span>16%</span>", markup)

    def test_progress_percentage_matches_consumed_share_of_target(self):
        self.assertEqual(_progress_percentage(22, 135), 16)
        self.assertEqual(_progress_percentage(108, 195), 55)
        self.assertEqual(_progress_percentage(34, 49), 69)
        self.assertEqual(_progress_percentage(825, 1762), 47)

    def test_progress_percentage_handles_zero_target(self):
        self.assertEqual(_progress_percentage(10, 0), 0)

    def test_progress_markup_uses_dashboard_color_and_target_ratio(self):
        markup = _progress_markup(50, 100, COLORS["protein"], "Protein")

        self.assertIn('aria-label="Protein"', markup)
        self.assertIn('aria-valuenow="50"', markup)
        self.assertIn("width:50.00%", markup)
        self.assertIn(f"background:{COLORS['protein']}", markup)

    def test_progress_markup_caps_progress_at_target(self):
        markup = _progress_markup(150, 100, COLORS["calories"], "Calories")

        self.assertIn('aria-valuenow="100"', markup)
        self.assertIn("width:100.00%", markup)

    def test_progress_markup_handles_zero_target(self):
        markup = _progress_markup(10, 0, COLORS["fat"], "Fat")

        self.assertIn('aria-valuenow="0"', markup)
        self.assertIn("width:0.00%", markup)


if __name__ == "__main__":
    unittest.main()
