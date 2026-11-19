import os
import tempfile
import unittest
from datetime import date

from services import db
from views.weight import _weight_chart, clamp_window, expected_weights, trend_line


class ExpectedWeightTests(unittest.TestCase):
    def test_deficit_lowers_expected_weight(self):
        series = expected_weights(date(2026, 1, 1), 80.0, date(2026, 1, 29), -500)
        self.assertEqual(len(series), 29)
        self.assertEqual(series[0]["kg"], 80.0)
        self.assertLess(series[-1]["kg"], series[0]["kg"])

    def test_surplus_raises_expected_weight(self):
        series = expected_weights(date(2026, 1, 1), 70.0, date(2026, 1, 29), 400)
        self.assertGreater(series[-1]["kg"], 70.0)

    def test_maintenance_is_flat(self):
        series = expected_weights(date(2026, 1, 1), 70.0, date(2026, 1, 15), 10)
        self.assertTrue(all(point["kg"] == 70.0 for point in series))

    def test_trend_follows_a_straight_line_exactly(self):
        entries = [
            {"log_date": date(2026, 1, 1 + i).isoformat(), "weight_kg": 80.0 - i * 0.5, "note": ""}
            for i in range(10)
        ]
        fitted = trend_line(entries)
        for entry, value in zip(entries, fitted):
            self.assertAlmostEqual(value, entry["weight_kg"], places=6)

    def test_trend_stays_close_to_noisy_logs(self):
        weights = [80.0, 80.4, 79.6, 80.3, 79.5, 80.2, 79.4, 80.1, 79.3, 79.9, 79.2, 79.8]
        entries = [
            {"log_date": date(2026, 1, 1 + i).isoformat(), "weight_kg": w, "note": ""}
            for i, w in enumerate(weights)
        ]
        for entry, value in zip(entries, trend_line(entries)):
            self.assertLess(abs(value - entry["weight_kg"]), 0.6)

    def test_trend_with_few_logs_passes_through_them(self):
        entries = [
            {"log_date": "2026-01-01", "weight_kg": 80.0, "note": ""},
            {"log_date": "2026-01-09", "weight_kg": 78.0, "note": ""},
        ]
        self.assertEqual(trend_line(entries), [80.0, 78.0])

    def test_window_is_clamped_to_logged_dates(self):
        first, last = date(2026, 1, 1), date(2026, 3, 1)
        self.assertEqual(
            clamp_window(date(2025, 6, 1), date(2027, 1, 1), first, last), (first, last)
        )

    def test_window_cannot_zoom_in_past_a_week(self):
        first, last = date(2026, 1, 1), date(2026, 3, 1)
        start, end = clamp_window(date(2026, 2, 1), date(2026, 2, 2), first, last)
        self.assertEqual((end - start).days, 6)
        start, end = clamp_window(date(2026, 3, 1), date(2026, 3, 1), first, last)
        self.assertEqual(end, last)
        self.assertEqual((end - start).days, 6)

    def test_chart_has_expected_trend_and_dot_layers(self):
        entries = [
            {"log_date": "2026-01-01", "weight_kg": 80.0, "note": ""},
            {"log_date": "2026-01-02", "weight_kg": 79.5, "note": "ok"},
        ]
        expected = expected_weights(date(2026, 1, 1), 80.0, date(2026, 1, 2), -500)
        spec = _weight_chart(
            entries, expected, "kg", 1.0, date(2026, 1, 1), date(2026, 1, 2)
        ).to_dict()
        marks = [layer["mark"] for layer in spec["layer"]]
        self.assertEqual(marks[0]["strokeDash"], [1, 7])
        self.assertEqual(marks[2]["color"], "#34d399")
        self.assertFalse(any("bind" in p for p in spec.get("params", [])))  # no free zoom


class WeightLogTests(unittest.TestCase):
    def setUp(self):
        self.original = db.DB_PATH
        handle, db.DB_PATH = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db.init_db()
        db.create_user("weigher", "password123")
        self.user_id = db.check_login("weigher", "password123")["id"]

    def tearDown(self):
        os.remove(db.DB_PATH)
        db.DB_PATH = self.original

    def test_same_day_replaces_entry(self):
        db.save_weight_entry(self.user_id, "2026-01-01", 80.0, "first")
        db.save_weight_entry(self.user_id, "2026-01-01", 79.5, "second")
        db.save_weight_entry(self.user_id, "2026-01-02", 79.0)
        entries = db.get_weight_entries(self.user_id)
        self.assertEqual([e["weight_kg"] for e in entries], [79.5, 79.0])
        self.assertEqual(entries[0]["note"], "second")

    def test_delete_only_removes_own_entry(self):
        db.save_weight_entry(self.user_id, "2026-01-01", 80.0)
        entry_id = db.get_weight_entries(self.user_id)[0]["id"]
        db.delete_weight_entry(self.user_id + 1, entry_id)
        self.assertEqual(len(db.get_weight_entries(self.user_id)), 1)
        db.delete_weight_entry(self.user_id, entry_id)
        self.assertEqual(db.get_weight_entries(self.user_id), [])


if __name__ == "__main__":
    unittest.main()
