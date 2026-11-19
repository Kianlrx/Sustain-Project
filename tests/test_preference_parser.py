import unittest

from services import preference_parser as parser


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