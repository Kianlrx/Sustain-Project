import gzip
import json
import os
import re
import shutil
import sqlite3
from contextlib import closing, nullcontext
from http.client import HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from urllib.parse import urlsplit
from urllib.request import urlopen
from zlib import error as CompressionError

import pandas as pd
from streamlit import secrets
from streamlit.errors import StreamlitSecretNotFoundError

from services.food_data import NUTRITION_COLUMNS, OUTPUT_FOLDER

DB_PATH = OUTPUT_FOLDER / "recipes.db"
_download_lock = Lock()


class RecipeDatabaseUnavailable(RuntimeError):
    pass


def ensure_database(db_path=None):
    """Cache the published recipe index on first use when no local copy exists."""
    path = Path(db_path or DB_PATH)
    if path.is_file():
        return path

    with _download_lock:
        if path.is_file():
            return path
        url = os.environ.get("RECIPE_DATABASE_URL")
        if not url:
            try:
                url = secrets.get("RECIPE_DATABASE_URL")
            except StreamlitSecretNotFoundError:
                pass
        if not url:
            raise RecipeDatabaseUnavailable(
                "The recipe catalog is unavailable. Set RECIPE_DATABASE_URL to the "
                "Supabase Storage download URL or build the local recipe index."
            )

        temporary = None
        try:
            if urlsplit(url).scheme != "https":
                raise ValueError("The catalog URL must use HTTPS.")
            path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                with urlopen(url, timeout=30) as response:
                    compressed = urlsplit(url).path.endswith(".gz")
                    with (gzip.GzipFile(fileobj=response) if compressed else nullcontext(response)) as source:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
            with closing(sqlite3.connect(temporary.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
                if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                    raise sqlite3.DatabaseError("Recipe index failed its integrity check.")
                conn.execute("SELECT RecipeId, Name, Calories, SkillLevel FROM recipes LIMIT 1")
            if not path.is_file():
                temporary.replace(path)
        except (OSError, ValueError, EOFError, HTTPException, CompressionError, sqlite3.Error) as exc:
            if not path.is_file():
                raise RecipeDatabaseUnavailable(
                    "The recipe catalog could not be downloaded. Check the Storage URL and try again."
                ) from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return path

SKILL_LEVELS = ["Beginner", "Intermediate", "Advanced"]

LIST_COLUMNS = ["Images", "Keywords", "RecipeIngredientQuantities", "RecipeIngredientParts", "RecipeInstructions"]

# words that mean a recipe contains each allergen from the onboarding form
ALLERGEN_WORDS = {
    "Peanuts": ["peanut"],
    "Tree Nuts": ["nut", "almond", "walnut", "pecan", "cashew", "pistachio", "hazelnut", "macadamia", "chestnut", "praline", "marzipan", "nutella"],
    "Dairy": ["milk", "buttermilk", "butter", "cheese", "cream", "yogurt", "yoghurt", "whey", "ghee", "parmesan", "mozzarella", "cheddar", "ricotta", "feta", "mascarpone", "custard", "creme fraiche", "fraiche", "kefir", "paneer", "brie", "gouda", "gruyere", "provolone", "queso"],
    "Eggs": ["egg", "eggnog", "mayonnaise", "mayo", "meringue", "custard", "frittata", "quiche", "omelet", "omelette", "aioli", "hollandaise"],
    "Gluten": ["wheat", "flour", "bread", "breadcrumb", "pasta", "spaghetti", "macaroni", "noodle", "couscous", "barley", "rye", "semolina", "cracker", "biscuit", "tortilla", "pita", "bagel", "croissant", "dough", "pastry", "crust", "bun", "beer", "soy sauce"],
    "Shellfish": ["shellfish", "shrimp", "prawn", "crab", "lobster", "clam", "mussel", "oyster", "scallop", "crawfish", "crayfish"],
    "Soy": ["soy", "soya", "soybean", "tofu", "edamame", "miso", "tempeh", "tamari"],
    "Pork": ["pork", "bacon", "ham", "prosciutto", "pancetta", "chorizo", "salami", "pepperoni", "lard", "sausage", "gammon", "bratwurst", "knackwurst", "kielbasa", "frankfurter", "wiener", "hot dog"],
}

# words that mean a recipe is not vegetarian
MEAT_WORDS = ALLERGEN_WORDS["Shellfish"] + ALLERGEN_WORDS["Pork"] + [
    "meat", "beef", "steak", "veal", "lamb", "mutton", "chicken", "turkey", "duck", "goose", "venison", "bison", "rabbit",
    "fish", "catfish", "salmon", "tuna", "cod", "halibut", "tilapia", "trout", "anchovy", "anchovies", "sardine", "mackerel",
    "worcestershire", "gelatin", "poultry", "roast", "sirloin", "tenderloin", "chuck", "brisket", "rib", "pastrami", "bologna",
    "jerky", "meatball", "meatloaf", "burger", "hamburger", "liver", "giblet", "oxtail", "goat", "quail", "pheasant", "broth", "stock",
    "walleye", "perch", "bass", "pike", "haddock", "snapper", "mahi", "swordfish", "whitefish", "flounder", "herring", "carp",
    "lox", "caviar", "roe", "squid", "calamari", "octopus", "eel",
]

# plant foods whose names contain animal words, swapped before checking
PLANT_SWAPS = {
    "peanut butter": "peanut",
    "almond butter": "almond",
    "cashew butter": "cashew",
    "nut butter": "nut",
    "apple butter": "apple",
    "cocoa butter": "cocoa",
    "butter beans": "beans",
    "butter lettuce": "lettuce",
    "coconut milk": "coconut",
    "coconut cream": "coconut",
    "almond milk": "almond",
    "soy milk": "soy",
    "rice milk": "rice",
    "oat milk": "oat",
    "cream of tartar": "tartar",
    "bean curd": "tofu",
    "vegetable broth": "vegetable",
    "vegetable stock": "vegetable",
    "egg free": "",
    "dairy free": "",
    "lactose free": "",
}

# words that mean a recipe is not vegan
ANIMAL_WORDS = MEAT_WORDS + ALLERGEN_WORDS["Dairy"] + ALLERGEN_WORDS["Eggs"] + ["honey"]


def free_column(allergen):
    # turns "Tree Nuts" into "TreeNutsFree"
    return allergen.replace(" ", "") + "Free"


def contains_any(text, words):
    # match whole words only so "nut" does not match "nutmeg"
    pattern = r"\b(?:" + "|".join(words) + r")s?\b"
    return text.str.contains(pattern, regex=True)


def add_tags(df):
    df = df.copy()
    # search the name, category, keywords, ingredients and instructions because ingredient lists are often incomplete
    text = (
        df["Name"] + " "
        + df["RecipeCategory"] + " "
        + df["Keywords"].map(lambda words: " ".join(w for w in words if w))
        + " " + df["RecipeIngredientParts"].map(" ".join)
        + " " + df["RecipeInstructions"].map(" ".join)
    ).str.lower()
    for phrase, swap in PLANT_SWAPS.items():
        # so "almond milk" counts as a nut but not as dairy
        text = text.str.replace(phrase, swap, regex=False)

    for allergen, words in ALLERGEN_WORDS.items():
        # 1 means the recipe is free of this allergen
        df[free_column(allergen)] = (~contains_any(text, words)).astype(int)

    # vegetarian means no meat or fish words
    df["Vegetarian"] = (~contains_any(text, MEAT_WORDS)).astype(int)
    # vegan also means no dairy, eggs or honey, and no cholesterol because only animal foods have it
    df["Vegan"] = (~contains_any(text, ANIMAL_WORDS) & (df["CholesterolContent"] == 0)).astype(int)
    # keto means 10g or less of net carbs per serving
    df["Keto"] = (df["CarbohydrateContent"] - df["FiberContent"] <= 10).astype(int)

    steps = df["RecipeInstructions"].map(len)
    ingredients = df["RecipeIngredientQuantities"].map(len)
    # every recipe starts as intermediate
    df["SkillLevel"] = 2
    # few steps and few ingredients is beginner
    df.loc[(steps <= 5) & (ingredients <= 8), "SkillLevel"] = 1
    # many steps or many ingredients is advanced
    df.loc[(steps >= 10) | (ingredients >= 14), "SkillLevel"] = 3
    return df


def save_database(df, db_path=DB_PATH):
    df = df.copy()
    for column in LIST_COLUMNS:
        # sqlite cannot store lists so we save them as json text
        df[column] = df[column].map(lambda items: json.dumps(list(items)))
    # sqlite cannot store dates with time zones so we save them as text
    df["DatePublished"] = df["DatePublished"].astype(str)
    # ids are whole numbers
    df["RecipeId"] = df["RecipeId"].astype(int)

    conn = sqlite3.connect(db_path)
    df.to_sql("recipes", conn, if_exists="replace", index=False)
    # compound index so macro filters and sorting by calories are fast
    conn.execute("CREATE INDEX idx_recipes_macros ON recipes (Calories, ProteinContent, CarbohydrateContent, FatContent)")
    # index so one recipe can be found quickly by its id
    conn.execute("CREATE UNIQUE INDEX idx_recipes_id ON recipes (RecipeId)")
    conn.commit()
    conn.close()


def build_database():
    recipes = pd.read_parquet(OUTPUT_FOLDER / "recipes_clean.parquet")
    scaled = pd.read_parquet(OUTPUT_FOLDER / "recipes_scaled.parquet")
    for column in NUTRITION_COLUMNS:
        # keep the 0 to 1 values next to the real ones
        recipes["Scaled" + column] = scaled[column].values
    recipes = add_tags(recipes)
    save_database(recipes)
    return recipes


_COOK_TIME = re.compile(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?")


def _cook_minutes(value):
    match = _COOK_TIME.fullmatch(value) if isinstance(value, str) else None
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = (float(part or 0) for part in match.groups())
    return days * 1440 + hours * 60 + minutes + seconds / 60


def find_recipes(calories=None, protein=None, carbs=None, fat=None, diets=(), allergens=(),
                 keywords=(), skill="Advanced", limit=20, db_path=DB_PATH, cuisines=(), near_calories=None,
                 max_cook_minutes=None, high_protein=False, low_carb=False, low_fat=False):
    conditions = []
    values = []

    macro_ranges = {
        "Calories": calories,
        "ProteinContent": protein,
        "CarbohydrateContent": carbs,
        "FatContent": fat,
    }
    for column, macro_range in macro_ranges.items():
        if macro_range is None:
            continue
        low, high = macro_range
        if low is not None:
            # recipe must have at least this much
            conditions.append(f"{column} >= ?")
            values.append(low)
        if high is not None:
            # recipe must not have more than this
            conditions.append(f"{column} <= ?")
            values.append(high)

    # Protein and carbohydrates provide 4 kcal/g and fat provides 9 kcal/g.
    if high_protein or low_carb or low_fat:
        conditions.append("Calories > 0")
    if high_protein:
        conditions.append("ProteinContent * 400 >= Calories * 30")
    if low_carb:
        conditions.append("CarbohydrateContent * 400 < Calories * 26")
    if low_fat:
        conditions.append("FatContent * 900 <= Calories * 30")

    for diet in diets:
        if diet not in ["Vegetarian", "Vegan", "Keto"]:
            raise ValueError(f"Unknown diet: {diet}")
        # recipe must have this diet tag
        conditions.append(f"{diet} = 1")

    for allergen in allergens:
        if allergen in ALLERGEN_WORDS:
            # recipe must be free of this allergen
            conditions.append(f"{free_column(allergen)} = 1")
        else:
            # for allergens typed in by the user, the text must not appear anywhere
            conditions.append("Name NOT LIKE ? AND RecipeIngredientParts NOT LIKE ? AND RecipeInstructions NOT LIKE ?")
            values.extend([f"%{allergen}%"] * 3)

    for keyword in keywords:
        # recipe must have this food.com keyword, for example "Breakfast" or "< 30 Mins"
        conditions.append("Keywords LIKE ?")
        values.append(f'%"{keyword}"%')

    if max_cook_minutes is not None:
        conditions.append("cook_minutes(CookTime) <= ?")
        values.append(max_cook_minutes)

    if cuisines:
        # recipe must match at least one cuisine, as a food.com keyword (e.g. "Indian"),
        # its category, or a word in its name
        matches = []
        for cuisine in cuisines:
            matches.append("Keywords LIKE ? OR RecipeCategory LIKE ? OR Name LIKE ?")
            values.extend([f'%"{cuisine}"%', cuisine, f"%{cuisine}%"])
        conditions.append("(" + " OR ".join(f"({match})" for match in matches) + ")")

    # recipe must not be harder than the user's skill level
    conditions.append("SkillLevel <= ?")
    values.append(SKILL_LEVELS.index(skill) + 1)

    if near_calories is None:
        # biggest meals that still fit the budget come first
        order = "Calories DESC"
    else:
        # meals closest to the calorie budget come first
        order = "ABS(Calories - ?)"
        values.append(near_calories)
    sql = "SELECT * FROM recipes WHERE " + " AND ".join(conditions) + f" ORDER BY {order} LIMIT ?"
    values.append(limit)

    with closing(sqlite3.connect(db_path)) as conn:
        if max_cook_minutes is not None:
            conn.create_function("cook_minutes", 1, _cook_minutes, deterministic=True)
        return pd.read_sql_query(sql, conn, params=values)


def get_recipe(recipe_id, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    # uses the id index so this is instant
    results = pd.read_sql_query("SELECT * FROM recipes WHERE RecipeId = ?", conn, params=[recipe_id])
    conn.close()
    if results.empty:
        return None
    recipe = results.iloc[0].to_dict()
    for column in LIST_COLUMNS:
        # turn the json text back into lists
        recipe[column] = json.loads(recipe[column])
    return recipe


if __name__ == "__main__":
    recipes = build_database()
    print("Saved", len(recipes), "recipes to", DB_PATH)
