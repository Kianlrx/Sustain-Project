import json
import os
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from services import preference_parser as parser

SAMPLE = {
    "cuisines": ["thai"], "flavors": ["spicy"], "preparation": [],
    "meal_category": "Dinner", "diets": ["Vegan"], "exclusions": ["peanut"],
    "max_cook_minutes": 20,
}


def fake_response(content):
    # what Groq sends back: the model's answer as a string inside the first choice
    body = {"choices": [{"message": {"content": content}}]}
    return BytesIO(json.dumps(body).encode("utf-8"))


def rate_limited():
    return HTTPError(parser.API_URL, 429, "Too Many Requests", {}, None)


class TestPromptTemplate(unittest.TestCase):
    def test_schema_is_strict(self):
        # Groq's strict mode rejects schemas with optional or extra fields
        schema = parser.FILTER_SCHEMA
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertFalse(schema["additionalProperties"])

    def test_prompt_explains_every_field(self):
        for field in parser.FILTER_SCHEMA["properties"]:
            self.assertIn(field, parser.SYSTEM_PROMPT)

    def test_diets_match_recipe_search(self):
        # find_recipes raises an error for any diet it doesn't know
        for diet in parser.DIETS:
            self.assertIn(diet, ["Vegetarian", "Vegan", "Keto"])



@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
@patch("services.preference_parser.time.sleep")  # don't really wait in tests
@patch("services.preference_parser.urlopen")
class TestServiceClient(unittest.TestCase):
    def test_returns_filters_from_model(self, urlopen, sleep):
        urlopen.return_value = fake_response(json.dumps(SAMPLE))
        self.assertEqual(parser.request_filters("vegan thai, spicy, no peanuts"), SAMPLE)
        sent = json.loads(urlopen.call_args[0][0].data)
        self.assertEqual(sent["model"], parser.MODEL)
        self.assertTrue(sent["response_format"]["json_schema"]["strict"])
        self.assertEqual(urlopen.call_args.kwargs["timeout"], parser.TIMEOUT_SECONDS)

    def test_retries_after_rate_limit(self, urlopen, sleep):
        urlopen.side_effect = [rate_limited(), fake_response(json.dumps(SAMPLE))]
        self.assertEqual(parser.request_filters("thai"), SAMPLE)
        self.assertEqual(urlopen.call_count, 2)

    def test_gives_up_after_repeated_timeouts(self, urlopen, sleep):
        urlopen.side_effect = TimeoutError()
        with self.assertRaises(parser.AIServiceError):
            parser.request_filters("thai")
        self.assertEqual(urlopen.call_count, parser.MAX_ATTEMPTS)

    def test_spaces_out_calls(self, urlopen, sleep):
        urlopen.side_effect = [fake_response(json.dumps(SAMPLE)) for _ in range(2)]
        parser.request_filters("thai")
        parser.request_filters("curry")
        # the second call waits so calls stay SECONDS_BETWEEN_CALLS apart
        self.assertGreater(sleep.call_args[0][0], 0)

    def test_does_not_retry_bad_key(self, urlopen, sleep):
        urlopen.side_effect = HTTPError(parser.API_URL, 401, "Unauthorized", {}, None)
        with self.assertRaises(parser.AIServiceError):
            parser.request_filters("thai")
        self.assertEqual(urlopen.call_count, 1)

    def test_rejects_answer_that_is_not_json(self, urlopen, sleep):
        urlopen.return_value = fake_response("Sure! Here are your filters")
        with self.assertRaises(parser.AIServiceError):
            parser.request_filters("thai")

    def test_needs_api_key(self, urlopen, sleep):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaises(parser.AIServiceError):
                parser.request_filters("thai")
        urlopen.assert_not_called()


class TestSearchArgs(unittest.TestCase):
    def test_filters_become_find_recipes_arguments(self):
        self.assertEqual(
            parser.to_search_args(SAMPLE),
            {"diets": ["Vegan"], "allergens": ["peanut"], "keywords": ["< 30 Mins"]},
        )



@patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
@patch("services.preference_parser.time.sleep")
@patch("services.preference_parser.urlopen")
class TestFallbacks(unittest.TestCase):
    def test_empty_or_symbol_only_prompts_skip_the_model(self, urlopen, sleep):
        for prompt in ["", "   ", "???", None]:
            self.assertEqual(parser.parse_preferences(prompt, "Lunch"), parser.default_filters("Lunch"))
        urlopen.assert_not_called()

    def test_api_failure_returns_defaults(self, urlopen, sleep):
        urlopen.side_effect = TimeoutError()
        with self.assertLogs("services.preference_parser", "WARNING"):
            filters = parser.parse_preferences("pasta please", "Dinner")
        self.assertEqual(filters, parser.default_filters("Dinner"))

    def test_invalid_json_returns_defaults(self, urlopen, sleep):
        urlopen.return_value = fake_response("{not json")
        with self.assertLogs("services.preference_parser", "WARNING"):
            self.assertEqual(parser.parse_preferences("pasta"), parser.default_filters())

    def test_gibberish_gives_broad_filters(self, urlopen, sleep):
        # the model is told to return nothing when the text is not about food
        urlopen.return_value = fake_response(json.dumps(parser.default_filters()))
        self.assertEqual(parser.parse_preferences("asdkjh qwe", "Snack"), parser.default_filters("Snack"))

    def test_valid_answer_is_kept(self, urlopen, sleep):
        urlopen.return_value = fake_response(json.dumps(SAMPLE))
        self.assertEqual(parser.parse_preferences("spicy vegan thai dinner, no peanuts"), SAMPLE)


class TestCleanFilters(unittest.TestCase):
    def test_wrong_values_are_replaced(self):
        raw = {
            "cuisines": "italian", "flavors": ["Sweet", "sweet", 3],
            "meal_category": "Brunch", "diets": ["Vegan", "Paleo"],
            "max_cook_minutes": -5,
        }
        filters = parser.clean_filters(raw)
        self.assertEqual(filters["cuisines"], [])
        self.assertEqual(filters["flavors"], ["sweet"])
        self.assertEqual(filters["meal_category"], "Any")
        self.assertEqual(filters["diets"], ["Vegan"])
        self.assertIsNone(filters["max_cook_minutes"])

    def test_spicy_but_no_spice(self):
        raw = dict(SAMPLE, flavors=["spicy", "sour"], exclusions=["spice", "chili"])
        self.assertEqual(parser.clean_filters(raw)["flavors"], ["sour"])

    def test_meal_slot_is_used_when_no_meal_is_named(self):
        self.assertEqual(parser.clean_filters(dict(SAMPLE, meal_category="Any"), "Lunch")["meal_category"], "Lunch")
        self.assertEqual(parser.clean_filters(dict(SAMPLE, meal_category="Dessert"), "Lunch")["meal_category"], "Dessert")

    def test_not_a_dict_gives_defaults(self):
        self.assertEqual(parser.clean_filters(["thai"]), parser.default_filters())