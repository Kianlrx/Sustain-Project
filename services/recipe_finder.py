# Find a Recipe (SCRUM-77): turns a craving and a meal slot into a recipe search
# on the food.com recipe database, then ranks the matches by how well they fit
# the slot's share of the day's calories and macros.

from services import preference_parser, recipe_search

MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]
# share of the daily targets each meal gets, in percent (Kian's default split)
DEFAULT_SPLIT = {"Breakfast": 30, "Lunch": 30, "Dinner": 30, "Snack": 10}
SPLIT_STEP = 5

# a recipe counts as a fit when its calories are between these shares of the budget
CALORIE_RANGE = (0.6, 1.1)
POOL_SIZE = 60  # recipes fetched from the database before ranking
RESULTS_SHOWN = 5
MAX_RESULTS = 20

# columns searched for exclusion words (see recipe_search.find_recipes)
EXCLUSION_COLUMNS = ["Name", "RecipeIngredientParts", "RecipeInstructions"]
MACRO_COLUMNS = {
    "protein_g": "ProteinContent",
    "carbs_g": "CarbohydrateContent",
    "fat_g": "FatContent",
}


def default_slot(hour):
    """The meal slot that fits the time of day, used when the user has not picked one."""
    if hour < 11:
        return "Breakfast"
    if hour < 16:
        return "Lunch"
    if hour < 21:
        return "Dinner"
    return "Snack"


def adjust_split(split, slot, change):
    """Return a copy of the split with one slot's percentage moved up or down, kept between 0 and 100."""
    split = dict(split)
    split[slot] = min(100, max(0, split[slot] + change))
    return split


def slot_budget(targets, split, slot):
    """The calories and macros a slot gets from the daily targets."""
    share = split[slot] / 100
    return {key: round(targets[key] * share) for key in ["calories", "protein_g", "carbs_g", "fat_g"]}


def build_query(filters, budget, profile=None):
    """The search as JSON, keyed by the recipe database's own column names.

    `filters` comes from preference_parser.parse_preferences. This is what the
    page shows, and run_query reads only this, so the two cannot drift apart.
    """
    profile = profile or {}
    search_args = preference_parser.to_search_args(filters)

    # the user's saved allergens and diets always apply, plus what they typed
    allergens = [a for a in profile.get("allergens", []) if isinstance(a, str) and a.strip()]
    known = [a for a in allergens if a in recipe_search.ALLERGEN_WORDS]
    typed_words = [a.strip().lower() for a in allergens if a not in recipe_search.ALLERGEN_WORDS]
    diets = list(dict.fromkeys(list(profile.get("diets", [])) + search_args["diets"]))
    diets = [diet for diet in diets if diet in preference_parser.DIETS]
    skill = profile.get("cooking_skill")
    if skill not in recipe_search.SKILL_LEVELS:
        skill = "Advanced"

    query = {}
    for diet in diets:
        query[diet] = 1
    for allergen in known:
        query[recipe_search.free_column(allergen)] = 1
    if filters["cuisines"]:
        # any one of these, found in Keywords, RecipeCategory or Name
        query["Keywords|RecipeCategory|Name"] = [c.title() for c in filters["cuisines"]]
    if search_args["keywords"]:
        query["Keywords"] = search_args["keywords"]
    exclusions = list(dict.fromkeys(typed_words + search_args["allergens"]))
    if exclusions:
        query["exclude_words"] = {"columns": EXCLUSION_COLUMNS, "words": exclusions}
    query["SkillLevel"] = {"max": recipe_search.SKILL_LEVELS.index(skill) + 1}
    low, high = CALORIE_RANGE
    query["Calories"] = {
        "min": round(budget["calories"] * low),
        "max": round(budget["calories"] * high),
        "target": budget["calories"],
    }
    for key, column in MACRO_COLUMNS.items():
        query[column] = {"target": budget[key]}
    # flavours and cooking styles have no column, so they only push matching names up the list
    boost = filters["flavors"] + filters["preparation"]
    if boost:
        query["rank_boost_words"] = boost
    return query


def _find_args(query):
    diets = [diet for diet in preference_parser.DIETS if query.get(diet) == 1]
    allergens = [
        allergen for allergen in recipe_search.ALLERGEN_WORDS
        if query.get(recipe_search.free_column(allergen)) == 1
    ]
    allergens += query.get("exclude_words", {}).get("words", [])
    skill = recipe_search.SKILL_LEVELS[query["SkillLevel"]["max"] - 1]
    return {
        "diets": diets,
        "allergens": allergens,
        "keywords": query.get("Keywords", []),
        "cuisines": query.get("Keywords|RecipeCategory|Name", []),
        "skill": skill,
        "near_calories": query["Calories"]["target"],
    }


def fit_score(recipe, query):
    """Lower is better: how far the recipe is from the slot's calories, then its macros."""
    target = max(query["Calories"]["target"], 1)
    score = abs(recipe["Calories"] - target) / target
    macro_gaps = [
        abs(recipe[column] - query[column]["target"]) / max(query[column]["target"], 1)
        for column in MACRO_COLUMNS.values()
    ]
    score += 0.5 * sum(macro_gaps) / len(macro_gaps)
    name = str(recipe.get("Name", "")).lower()
    for word in query.get("rank_boost_words", []):
        if word in name:
            score -= 0.15
    return score


def run_query(query, db_path=None):
    """Search the database and return (recipes ranked best first, whether the calorie range was widened)."""
    db_path = db_path or recipe_search.DB_PATH
    args = _find_args(query)
    calories = (query["Calories"]["min"], query["Calories"]["max"])
    pool = recipe_search.find_recipes(calories=calories, limit=POOL_SIZE, db_path=db_path, **args)
    widened = False
    if len(pool) < RESULTS_SHOWN:
        # too few in range, so take the closest recipes whatever their size
        pool = recipe_search.find_recipes(limit=POOL_SIZE, db_path=db_path, **args)
        widened = True
    recipes = pool.to_dict("records")
    recipes.sort(key=lambda recipe: fit_score(recipe, query))
    return recipes[:MAX_RESULTS], widened


def fit_label(recipe, query):
    """Short text for how a recipe's calories compare with the slot budget."""
    target = query["Calories"]["target"]
    gap = round(recipe["Calories"] - target)
    if abs(gap) <= target * 0.05:
        return "On budget"
    return f"{abs(gap):,} kcal {'over' if gap > 0 else 'under'}"


def database_ready(db_path=None):
    return (db_path or recipe_search.DB_PATH).exists()
