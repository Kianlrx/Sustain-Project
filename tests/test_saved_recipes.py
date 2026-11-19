import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import db


class SavedRecipeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db_path_patch = patch.object(db, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        db.init_db()
        db.create_user("first", "password")
        db.create_user("second", "password")
        self.first_user = db.check_login("first", "password")["id"]
        self.second_user = db.check_login("second", "password")["id"]

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_saved_recipes_are_user_scoped_and_can_be_removed(self):
        recipe = {"Name": "Bean bowl", "Calories": 350}
        db.save_recipe(self.first_user, 42, recipe)
        db.save_recipe(self.first_user, 42, {"Name": "Updated bowl"})
        db.save_recipe(self.second_user, 42, {"Name": "Other user's bowl"})

        self.assertEqual(
            db.get_saved_recipes(self.first_user),
            [{"Name": "Updated bowl", "recipe_id": "42"}],
        )
        db.remove_saved_recipe(self.first_user, 42)
        self.assertEqual(db.get_saved_recipes(self.first_user), [])
        self.assertEqual(
            db.get_saved_recipes(self.second_user)[0]["Name"],
            "Other user's bowl",
        )


if __name__ == "__main__":
    unittest.main()
