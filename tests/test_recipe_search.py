import os
import tempfile
import unittest

import pandas as pd

from services.recipe_search import add_tags, find_recipes, save_database


def make_recipe(recipe_id, name, parts, calories, carbs, steps=3, keywords=(), cholesterol=0.0):
    return {
        "RecipeId": recipe_id,
        "Name": name,
        "RecipeCategory": "Test",
        "Keywords": list(keywords),
        "Images": [],
        "RecipeIngredientParts": parts,
        "RecipeIngredientQuantities": ["1"] * len(parts),
        "RecipeInstructions": ["Mix it."] * steps,
        "DatePublished": pd.Timestamp("2020-01-01", tz="UTC"),
        "Calories": calories,
        "ProteinContent": 20.0,
        "CarbohydrateContent": carbs,
        "FatContent": 10.0,
        "FiberContent": 0.0,
        "CholesterolContent": cholesterol,
    }


RECIPES = pd.DataFrame([
    make_recipe(1, "Pork Sate", ["soy sauce", "lime"], 500, 20),
    make_recipe(2, "Tofu Salad", ["tofu", "lettuce"], 300, 8),
    make_recipe(3, "Cheese Omelette", ["eggs", "cheese"], 400, 2, cholesterol=300.0),
    make_recipe(4, "Nutmeg Rice", ["rice", "nutmeg"], 350, 60, steps=12),
])

EXTRA_RECIPES = pd.DataFrame([
    make_recipe(5, "Almond Milk Smoothie", ["almond milk", "banana"], 200, 30),
    make_recipe(6, "Pot Roast", ["sirloin tip roast"], 600, 5, cholesterol=150.0),
    make_recipe(7, "Easy Crock Pot Dinner", ["oregano", "diced tomatoes"], 450, 10, cholesterol=90.0),
])


class TestTags(unittest.TestCase):
    def setUp(self):
        self.tagged = add_tags(RECIPES).set_index("RecipeId")

    def test_pork_found_in_name_when_missing_from_ingredients(self):
        self.assertEqual(self.tagged.loc[1, "ContainsPork"], 1)

    def test_soy_sauce_counts_as_soy_and_gluten(self):
        self.assertEqual(self.tagged.loc[1, "ContainsSoy"], 1)
        self.assertEqual(self.tagged.loc[1, "ContainsGluten"], 1)

    def test_nutmeg_is_not_a_tree_nut(self):
        self.assertEqual(self.tagged.loc[4, "ContainsTreeNuts"], 0)

    def test_diet_tags(self):
        self.assertEqual(self.tagged.loc[2, "Vegan"], 1)
        self.assertEqual(self.tagged.loc[3, "Vegetarian"], 1)
        self.assertEqual(self.tagged.loc[3, "Vegan"], 0)
        self.assertEqual(self.tagged.loc[1, "Vegetarian"], 0)

    def test_plant_milk_is_a_nut_not_dairy(self):
        tagged = add_tags(EXTRA_RECIPES).set_index("RecipeId")
        self.assertEqual(tagged.loc[5, "ContainsDairy"], 0)
        self.assertEqual(tagged.loc[5, "ContainsTreeNuts"], 1)
        self.assertEqual(tagged.loc[5, "Vegan"], 1)

    def test_meat_cuts_are_not_vegetarian(self):
        tagged = add_tags(EXTRA_RECIPES).set_index("RecipeId")
        self.assertEqual(tagged.loc[6, "Vegetarian"], 0)

    def test_cholesterol_means_not_vegan(self):
        tagged = add_tags(EXTRA_RECIPES).set_index("RecipeId")
        self.assertEqual(tagged.loc[7, "Vegan"], 0)

    def test_keto_uses_net_carbs(self):
        self.assertEqual(self.tagged.loc[3, "Keto"], 1)
        self.assertEqual(self.tagged.loc[4, "Keto"], 0)

    def test_skill_level(self):
        self.assertEqual(self.tagged.loc[2, "SkillLevel"], 1)
        self.assertEqual(self.tagged.loc[4, "SkillLevel"], 3)


class TestFindRecipes(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.db_path = os.path.join(folder, "test.db")
        save_database(add_tags(RECIPES), self.db_path)

    def find_ids(self, **filters):
        return list(find_recipes(db_path=self.db_path, **filters)["RecipeId"])

    def test_calorie_budget_and_order(self):
        self.assertEqual(self.find_ids(max_calories=400), [3, 4, 2])

    def test_diet_filter(self):
        self.assertEqual(self.find_ids(diets=["Vegan"]), [4, 2])

    def test_allergen_filter(self):
        self.assertEqual(self.find_ids(allergens=["Eggs", "Soy"]), [4])

    def test_typed_in_allergen(self):
        self.assertEqual(self.find_ids(allergens=["lettuce"]), [1, 3, 4])

    def test_skill_filter(self):
        self.assertEqual(self.find_ids(skill="Beginner"), [1, 3, 2])

    def test_unknown_diet(self):
        with self.assertRaises(ValueError):
            self.find_ids(diets=["Paleo"])


if __name__ == "__main__":
    unittest.main()
