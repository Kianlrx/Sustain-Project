import io
import json
import unittest
from unittest.mock import patch

from services.usda import USDAError, normalize_food_query, parse_food, search_foods


class USDAQueryTests(unittest.TestCase):
    def test_normalizes_whitespace_and_removes_control_characters(self):
        self.assertEqual(normalize_food_query("  apple\n\tpie  "), "apple pie")

    def test_rejects_empty_or_punctuation_only_queries(self):
        for query in ("", " \n ", "!?_*"):
            with self.subTest(query=query), self.assertRaises(ValueError):
                normalize_food_query(query)

    def test_rejects_queries_over_the_limit(self):
        with self.assertRaises(ValueError):
            normalize_food_query("a" * 101)


class USDAFoodParsingTests(unittest.TestCase):
    def test_parses_nutrients_and_uses_gram_serving_size(self):
        food = parse_food(
            {
                "fdcId": 123,
                "description": "Example food",
                "brandOwner": "Example brand",
                "servingSize": 50,
                "servingSizeUnit": "g",
                "foodNutrients": [
                    {"nutrientId": 1008, "value": 80},
                    {"nutrientId": 1003, "value": 2.5},
                    {"nutrientId": 1005, "value": 12},
                    {"nutrientId": 1004, "value": 1.5},
                ],
            }
        )
        self.assertEqual(food["fdc_id"], "123")
        self.assertEqual(food["basis_grams"], 50)
        self.assertEqual(food["nutrients"]["calories"], 80)
        self.assertEqual(food["nutrients"]["protein_g"], 2.5)

    def test_uses_name_matching_when_nutrient_ids_are_missing(self):
        food = parse_food(
            {
                "fdcId": 124,
                "description": "Name-matched food",
                "foodNutrients": [
                    {"nutrientName": "Energy", "unitName": "KCAL", "value": 90},
                    {"nutrientName": "Protein", "value": 3},
                    {"nutrientName": "Carbohydrate, by difference", "value": 11},
                    {"nutrientName": "Total lipid (fat)", "value": 2},
                ],
            }
        )
        self.assertEqual(
            food["nutrients"],
            {"calories": 90, "protein_g": 3, "carbs_g": 11, "fat_g": 2},
        )

    def test_search_encodes_query_and_parses_foods(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "foods": [
                        {
                            "fdcId": 125,
                            "description": "Apple, raw",
                            "foodNutrients": [],
                        }
                    ]
                }
            ).encode("utf-8")
        )
        with patch("services.usda.urlopen", return_value=response) as urlopen:
            results = search_foods("apple & pear")
        self.assertEqual(results[0]["description"], "Apple, raw")
        self.assertIn("query=apple+%26+pear", urlopen.call_args.args[0].full_url)

    def test_search_reports_unexpected_api_response(self):
        response = io.BytesIO(b'{"unexpected": []}')
        with patch("services.usda.urlopen", return_value=response):
            with self.assertRaises(USDAError):
                search_foods("apple")


if __name__ == "__main__":
    unittest.main()
