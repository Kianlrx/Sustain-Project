import os
import tempfile
import unittest
from datetime import date, timedelta

from services import db
from views.weight import (
    _preset_window,
    _weight_chart,
    clamp_window,
    expected_weights,
    trend_line,
)


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

    def test_smoothing_reduces_day_to_day_swings(self):
        entries = [
            {"log_date": date(2026, 1, day).isoformat(), "weight_kg": 80 + (-1) ** day}
            for day in range(1, 25)
        ]
        actual = [entry['weight_kg'] for entry in entries]
        smoother = trend_line(entries)
        actual_swings = sum(abs(right - left) for left, right in zip(actual, actual[1:]))
        smoother_swings = sum(abs(right - left) for left, right in zip(smoother, smoother[1:]))
        self.assertLess(smoother_swings, actual_swings)

    def test_trend_with_few_logs_passes_through_them(self):
        entries = [
            {"log_date": "2026-01-01", "weight_kg": 80.0, "note": ""},
            {"log_date": "2026-01-09", "weight_kg": 78.0, "note": ""},
        ]
        self.assertEqual(trend_line(entries), [80.0, 78.0])

    def test_year_preset_extends_before_first_log_and_ends_at_latest(self):
        first, latest, today = date(2026, 11, 1), date(2026, 11, 9), date(2026, 11, 27)
        self.assertEqual(_preset_window("1Y", first, today, latest), (date(2025, 11, 9), latest))

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
        tooltip_layer = spec["layer"][3]
        tooltip = tooltip_layer["encoding"]["tooltip"]
        self.assertEqual(tooltip[1]["title"], "Weight")
        self.assertEqual(tooltip[1]["field"], "weight_label")
        tooltip_rows = spec["datasets"][tooltip_layer["data"]["name"]]
        self.assertEqual([row["weight_label"] for row in tooltip_rows], ["80kg", "79.5kg"])
        marks = [layer["mark"] for layer in spec["layer"]]
        self.assertEqual(marks[0]["strokeDash"], [1, 7])
        self.assertTrue(marks[0]["clip"])
        self.assertTrue(marks[1]["clip"])
        self.assertEqual(marks[1]["interpolate"], "monotone")
        self.assertEqual(marks[2]["color"], "#34d399")
        self.assertEqual(
            spec["layer"][0]["encoding"]["x"]["scale"]["domain"],
            ["2025-12-31T00:00:00", "2026-01-03T00:00:00"],
        )
        line_data = spec["datasets"][spec["layer"][0]["data"]["name"]]
        self.assertEqual(
            [line_data[0]["date"], line_data[-1]["date"]],
            ["2025-12-31T00:43:12", "2026-01-02T23:16:48"],
        )
        self.assertEqual(
            spec["layer"][0]["encoding"]["x"]["axis"]["tickCount"],
            {"interval": "day", "step": 1},
        )
        self.assertEqual(marks[3]["size"], 300)
        hover = spec["params"][0]["select"]
        self.assertEqual(hover["on"], "pointerover")
        self.assertNotIn("nearest", hover)
        self.assertFalse(any("bind" in p for p in spec.get("params", [])))  # no free zoom

    def test_chart_renders_expected_curve_without_weigh_ins(self):
        today = date.today()
        expected = expected_weights(today, 75.0, today + timedelta(days=7), -500)
        spec = _weight_chart([], expected, "kg", 1.0, today, today + timedelta(days=7)).to_dict()
        self.assertEqual(len(spec["layer"]), 4)

    def test_chart_trend_includes_only_nearest_preceding_log(self):
        entries = [
            {"log_date": f"2026-01-{day:02}", "weight_kg": weight, "note": ""}
            for day, weight in enumerate((97, 95, 80, 79, 81, 78, 90, 92), 1)
        ]
        expected = expected_weights(date(2026, 1, 1), 80.0, date(2026, 1, 8), -500)
        spec = _weight_chart(
            entries, expected, "kg", 1.0, date(2026, 1, 3), date(2026, 1, 6)
        ).to_dict()
        datasets = spec["datasets"]
        trend_data = datasets[spec["layer"][1]["data"]["name"]]
        expected_data = datasets[spec["layer"][0]["data"]["name"]]
        dot_data = datasets[spec["layer"][2]["data"]["name"]]

        self.assertEqual(
            [row["date"] for row in trend_data],
            [
                "2026-01-02T01:12:00",
                "2026-01-03T00:00:00",
                "2026-01-04T00:00:00",
                "2026-01-05T00:00:00",
                "2026-01-06T00:00:00",
            ],
        )
        fitted = trend_line(entries[1:6])[1:]
        for row, baseline, entry in zip(trend_data[1:], fitted, entries[2:6]):
            actual = entry["weight_kg"]
            self.assertLessEqual(abs(row["average"] - actual), abs(baseline - actual))
            self.assertAlmostEqual(row["average"], baseline + 0.4 * (actual - baseline))
        self.assertEqual(
            [
                expected_data[0]["date"],
                expected_data[-1]["date"],
            ],
            ["2026-01-02T01:12:00", "2026-01-06T22:48:00"],
        )
        self.assertEqual(
            [row["date"][:10] for row in dot_data],
            ["2026-01-03", "2026-01-04", "2026-01-05", "2026-01-06"],
        )

    def test_preceding_log_affects_fit_with_two_visible_logs(self):
        entries = [
            {"log_date": f"2026-01-{day:02}", "weight_kg": weight, "note": ""}
            for day, weight in enumerate((83, 80, 80), 1)
        ]
        expected = expected_weights(date(2026, 1, 1), 83, date(2026, 1, 3), -500)
        spec = _weight_chart(
            entries, expected, "kg", 1.0, date(2026, 1, 2), date(2026, 1, 3)
        ).to_dict()
        trend = spec["datasets"][spec["layer"][1]["data"]["name"]]
        self.assertEqual([row["average"] for row in trend[1:]], [80.6, 79.7])
        self.assertAlmostEqual(trend[0]["average"], 82.637)
        self.assertEqual([row["date"][:10] for row in trend], ["2026-01-01", "2026-01-02", "2026-01-03"])

    def test_seven_day_line_connects_actual_weights_from_preceding_log(self):
        entries = [
            {"log_date": f"2026-01-{day:02}", "weight_kg": weight, "note": ""}
            for day, weight in ((1, 86), (2, 83), (5, 80), (9, 81))
        ]
        expected = expected_weights(date(2026, 1, 1), 86, date(2026, 1, 9), -500)
        spec = _weight_chart(
            entries, expected, "kg", 1.0, date(2026, 1, 3), date(2026, 1, 9),
            connect_weigh_ins=True,
        ).to_dict()
        self.assertEqual(spec["layer"][1]["mark"]["interpolate"], "linear")
        trend = spec["datasets"][spec["layer"][1]["data"]["name"]]
        self.assertEqual([row["average"] for row in trend[1:]], [80, 81])
        self.assertAlmostEqual(trend[0]["average"], 82.92)
        self.assertEqual(trend[0]["date"], "2026-01-02T01:55:12")

    def test_chart_trend_stops_at_latest_log(self):
        entries = [
            {"log_date": f"2026-01-{day:02}", "weight_kg": 80.0 - day / 10, "note": ""}
            for day in range(1, 7)
        ]
        expected = expected_weights(date(2026, 1, 1), 80.0, date(2026, 1, 6), -500)
        spec = _weight_chart(
            entries, expected, "kg", 1.0, date(2026, 1, 3), date(2026, 1, 6)
        ).to_dict()
        datasets = spec["datasets"]
        trend_data = datasets[spec["layer"][1]["data"]["name"]]

        self.assertEqual(trend_data[-1]["date"], "2026-01-06T00:00:00")


class WeightLogTests(unittest.TestCase):
    def setUp(self):
        self.original = db.DB_PATH
        handle, db.DB_PATH = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db.init_db()
        db.create_user("weigher", "password123")
        self.user_id = db.check_login("weigher", "password123")["id"]
        db.save_profile(
            self.user_id,
            {
                "weight_kg": 80.0,
                "height_cm": 175.0,
                "age": 30,
                "sex": "Male",
                "measurement_units": "Metric",
            },
        )

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
        self.assertEqual(db.get_profile(self.user_id)["weight_kg"], 79.0)

    def test_edit_updates_entry_and_latest_profile_weight(self):
        db.save_weight_entry(self.user_id, "2026-01-01", 80.0, "old")
        entry_id = db.get_weight_entries(self.user_id)[0]["id"]
        db.update_weight_entry(self.user_id, entry_id, "2026-01-02", 78.5, "updated")

        entry = db.get_weight_entries(self.user_id)[0]
        self.assertEqual(
            (entry["log_date"], entry["weight_kg"], entry["note"]),
            ("2026-01-02", 78.5, "updated"),
        )
        self.assertEqual(db.get_profile(self.user_id)["weight_kg"], 78.5)

    def test_delete_only_removes_own_entry(self):
        db.save_weight_entry(self.user_id, "2026-01-01", 80.0)
        entry_id = db.get_weight_entries(self.user_id)[0]["id"]
        db.delete_weight_entry(self.user_id + 1, entry_id)
        self.assertEqual(len(db.get_weight_entries(self.user_id)), 1)
        db.delete_weight_entry(self.user_id, entry_id)
        self.assertEqual(db.get_weight_entries(self.user_id), [])


if __name__ == "__main__":
    unittest.main()
