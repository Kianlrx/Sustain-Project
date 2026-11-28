# Find a Recipe (SCRUM-77): turns a craving and a meal slot into a recipe search
# on the food.com recipe database, then ranks the matches by how well they fit
# the slot's share of the day's calories.

from services import preference_parser, recipe_search

MEAL_SLOTS = ["Breakfast", "Lunch", "Dinner", "Snack"]
# share of the daily targets each meal gets, in percent (Kian's default split)
DEFAULT_SPLIT = {"Breakfast": 30, "Lunch": 30, "Dinner": 30, "Snack": 10}
SPLIT_STEP = 5

FALLBACK_CALORIE_RANGE = (0.6, 1.1)
POOL_SIZE = 60  # recipes fetched from the database before ranking
RESULTS_SHOWN = 5
MAX_RESULTS = 20

# columns searched for exclusion words (see recipe_search.find_recipes)
EXCLUSION_COLUMNS = ["Name", "RecipeIngredientParts", "RecipeInstructions"]


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
    """The calorie budget for the selected meal."""
    share = split[slot] / 100
    return {"calories": round(targets["calories"] * share)}


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
    skill = search_args.get("skill", profile.get("cooking_skill"))
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
    if "max_cook_minutes" in search_args:
        query["CookTime"] = {"max_minutes": search_args["max_cook_minutes"]}
    macro_preferences = {key: True for key in preference_parser.MACRO_PREFERENCES if key in search_args}
    if macro_preferences:
        query["macro_preferences"] = macro_preferences
    exclusions = list(dict.fromkeys(typed_words + search_args["allergens"]))
    if exclusions:
        query["exclude_words"] = {"columns": EXCLUSION_COLUMNS, "words": exclusions}
    query["SkillLevel"] = {"max": recipe_search.SKILL_LEVELS.index(skill) + 1}
    target = budget["calories"]
    margin = target * preference_parser.NUMERIC_TOLERANCE
    query["Calories"] = {"min": target - margin, "max": target + margin, "target": target}
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
        "cuisines": query.get("Keywords|RecipeCategory|Name", []),
        "skill": skill,
        "near_calories": query["Calories"]["target"],
        "max_cook_minutes": query.get("CookTime", {}).get("max_minutes"),
        **query.get("macro_preferences", {}),
    }


def fit_score(recipe, query):
    """Rank by calorie fit and requested flavour or preparation matches."""
    target = max(query["Calories"]["target"], 1)
    score = abs(recipe["Calories"] - target) / target
    name = str(recipe.get("Name", "")).lower()
    for word in query.get("rank_boost_words", []):
        if word in name:
            score -= 0.15
    return score


def run_query(query, db_path=None):
    """Search the database and return (recipes ranked best first, whether the calorie range was widened)."""
    db_path = db_path or recipe_search.DB_PATH
    args = _find_args(query)
    calorie_range = (query["Calories"]["min"], query["Calories"]["max"])
    strict = recipe_search.find_recipes(calories=calorie_range, limit=POOL_SIZE, db_path=db_path, **args)
    recipes = strict.to_dict("records")
    recipes.sort(key=lambda recipe: fit_score(recipe, query))
    if len(recipes) >= RESULTS_SHOWN:
        return recipes[:MAX_RESULTS], False

    target = query["Calories"]["target"]
    calories = tuple(round(target * share) for share in FALLBACK_CALORIE_RANGE)
    pool = recipe_search.find_recipes(calories=calories, limit=POOL_SIZE, db_path=db_path, **args)
    if len(pool) < RESULTS_SHOWN:
        pool = recipe_search.find_recipes(limit=POOL_SIZE, db_path=db_path, **args)
    strict_ids = set(strict["RecipeId"])
    fallback = [recipe for recipe in pool.to_dict("records") if recipe["RecipeId"] not in strict_ids]
    fallback.sort(key=lambda recipe: fit_score(recipe, query))
    return (recipes + fallback)[:MAX_RESULTS], bool(fallback)


def fit_label(recipe, query):
    """Short text for how a recipe's calories compare with the slot budget."""
    target = query["Calories"]["target"]
    difference = recipe["Calories"] - target
    if abs(difference) <= target * preference_parser.NUMERIC_TOLERANCE:
        return "On budget"
    gap = round(difference)
    return f"{abs(gap):,} kcal {'over' if gap > 0 else 'under'}"


def database_ready(db_path=None):
    return (db_path or recipe_search.DB_PATH).exists()
