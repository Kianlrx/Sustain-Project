import json
import sqlite3

import pandas as pd

from services.food_data import NUTRITION_COLUMNS, OUTPUT_FOLDER

DB_PATH = OUTPUT_FOLDER / "recipes.db"

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


def column_name(allergen):
    # turns "Tree Nuts" into "ContainsTreeNuts"
    return "Contains" + allergen.replace(" ", "")


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
        # 1 means the recipe contains this allergen
        df[column_name(allergen)] = contains_any(text, words).astype(int)

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

    with sqlite3.connect(db_path) as conn:
        df.to_sql("recipes", conn, if_exists="replace", index=False)
        # compound index so macro filters and sorting by calories are fast
        conn.execute("CREATE INDEX idx_recipes_macros ON recipes (Calories, ProteinContent, CarbohydrateContent, FatContent)")
        # index so one recipe can be found quickly by its id
        conn.execute("CREATE UNIQUE INDEX idx_recipes_id ON recipes (RecipeId)")


def build_database():
    recipes = pd.read_parquet(OUTPUT_FOLDER / "recipes_clean.parquet")
    scaled = pd.read_parquet(OUTPUT_FOLDER / "recipes_scaled.parquet")
    for column in NUTRITION_COLUMNS:
        # keep the 0 to 1 values next to the real ones
        recipes["Scaled" + column] = scaled[column].values
    recipes = add_tags(recipes)
    save_database(recipes)
    return recipes


def find_recipes(max_calories=None, max_protein=None, max_carbs=None, max_fat=None,
                 diets=(), allergens=(), skill="Advanced", limit=20, db_path=DB_PATH):
    conditions = []
    values = []

    macro_limits = {
        "Calories": max_calories,
        "ProteinContent": max_protein,
        "CarbohydrateContent": max_carbs,
        "FatContent": max_fat,
    }
    for column, limit_value in macro_limits.items():
        if limit_value is not None:
            # recipe must fit inside the macro budget
            conditions.append(f"{column} <= ?")
            values.append(limit_value)

    for diet in diets:
        if diet not in ["Vegetarian", "Vegan", "Keto"]:
            raise ValueError(f"Unknown diet: {diet}")
        # recipe must have this diet tag
        conditions.append(f"{diet} = 1")

    for allergen in allergens:
        if allergen in ALLERGEN_WORDS:
            # recipe must not contain this allergen
            conditions.append(f"{column_name(allergen)} = 0")
        else:
            # for allergens typed in by the user, the text must not appear anywhere
            conditions.append("Name NOT LIKE ? AND RecipeIngredientParts NOT LIKE ? AND RecipeInstructions NOT LIKE ?")
            values.extend([f"%{allergen}%"] * 3)

    # recipe must not be harder than the user's skill level
    conditions.append("SkillLevel <= ?")
    values.append(SKILL_LEVELS.index(skill) + 1)

    # biggest meals that still fit the budget come first
    sql = "SELECT * FROM recipes WHERE " + " AND ".join(conditions) + " ORDER BY Calories DESC LIMIT ?"
    values.append(limit)

    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(sql, conn, params=values)


if __name__ == "__main__":
    recipes = build_database()
    print("Saved", len(recipes), "recipes to", DB_PATH)
