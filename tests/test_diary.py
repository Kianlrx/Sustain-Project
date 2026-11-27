from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from services import db

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


class DiaryQuantityTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        db_path = patch.object(db, "DB_PATH", Path(directory.name) / "diary.db")
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()
        db.create_user("diary-test", "password")
        self.user = db.check_login("diary-test", "password")

    def test_legacy_entry_keeps_original_nutrition_and_editing_does_not_drift(self):
        day = "2026-01-01"
        with db.get_connection() as connection:
            connection.execute(
                "INSERT INTO food_log "
                "(user_id, log_date, meal_slot, food_name, calories, protein_g, carbs_g, fat_g) "
                "VALUES (?, ?, 'Lunch', 'Legacy meal', 101, 7, 9, 13)",
                (self.user["id"], day),
            )
        entry, = db.get_food_entries(self.user["id"], day)
        self.assertEqual((entry["quantity"], entry["calories"]), (1, 101))
        db.update_food_quantity(self.user["id"], day, entry["id"], 0.5)
        db.update_food_quantity(self.user["id"], day, entry["id"], 1)
        self.assertEqual(db.get_food_entries(self.user["id"], day), [entry])
        db.delete_food_entry(self.user["id"] + 1, day, entry["id"])
        self.assertEqual(db.get_food_entries(self.user["id"], day), [entry])

    def test_diary_can_select_and_edit_a_past_day(self):
        user_id = self.user["id"]
        historical = date.today() - timedelta(days=3)
        db.save_targets(user_id, dict(calories=2000, protein_g=130, carbs_g=220, fat_g=65), manual=True)
        db.add_food_entry(user_id, date.today().isoformat(), "Lunch", "Today's food", 100, 5, 10, 4)
        db.add_food_entry(
            user_id, historical.isoformat(), "Lunch", "Past food", 200, 10, 20, 8,
            quantity=100, quantity_unit="g",
        )
        app = AppTest.from_string(
            "from views.diary import render_diary_page\nrender_diary_page()",
            default_timeout=15,
        )
        app.session_state.user = self.user
        app.run()
        self.assertFalse(app.exception)
        app.date_input(key=f"diary_date_picker_{user_id}").set_value(historical)
        next(button for button in app.button if button.label == "Go").click().run()
        self.assertFalse(app.exception)
        app.button(key="diary_toggle_lunch").click().run()
        self.assertFalse(app.exception)
        entry, = db.get_food_entries(user_id, historical.isoformat())
        app.session_state[f"diary_edit_{entry['id']}"] = True
        app.run()
        self.assertFalse(app.exception)
        app.number_input[0].set_value(150)
        app.selectbox[0].select("Dinner")
        next(button for button in app.button if button.label == "Save").click().run()
        self.assertFalse(app.exception)
        updated, = db.get_food_entries(user_id, historical.isoformat())
        self.assertEqual((updated["quantity"], updated["calories"], updated["meal_slot"]), (150, 300, "Dinner"))
        app.button(key=f"diary_delete_{entry['id']}").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(db.get_food_entries(user_id, historical.isoformat()), [])
        self.assertEqual(len(db.get_food_entries(user_id, date.today().isoformat())), 1)


if __name__ == "__main__":
    unittest.main()
