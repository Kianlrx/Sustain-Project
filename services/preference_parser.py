# Turns a user's free-text meal craving into search filters for the recipe database,
# using an AI model on Groq's free plan.

# Values the recipe search understands (see services/recipe_search.py)
DIETS = ["Vegetarian", "Vegan", "Keto"]
MEAL_CATEGORIES = ["Breakfast", "Lunch", "Dinner", "Snack", "Dessert", "Any"]

# Instructions sent to the model along with every craving.
SYSTEM_PROMPT = """You turn a person's description of what they feel like eating into search filters for a recipe database.
Only use what the person says. Never add preferences they did not mention.

- cuisines: cuisines they ask for, as lowercase words, e.g. "italian", "mexican", "thai".
- flavors: flavours they want, as short lowercase words, e.g. "spicy", "sweet", "savory", "creamy".
- preparation: cooking styles they want, as short lowercase words, e.g. "baked", "grilled", "one-pot", "no-cook".
- meal_category: Breakfast, Lunch, Dinner, Snack or Dessert if they name a meal, otherwise Any.
- diets: Vegetarian, Vegan or Keto, only if they ask for one.
- exclusions: ingredients to avoid, as short lowercase ingredient names. When they want to avoid a flavour,
  list what causes it, e.g. "not too spicy" gives ["chili", "jalapeno", "cayenne", "hot sauce"].
- max_cook_minutes: the most minutes they want to spend cooking, e.g. "quick" is 30. null if not mentioned.

If they both want and avoid something, e.g. "spicy but no spice", leave it out of flavors and keep the exclusions.
If the text is not about food, return empty lists, Any and null."""

# Shape of the JSON the model must return. Groq's strict mode needs every field
# listed in "required" and "additionalProperties" set to False.
WORD_LIST = {"type": "array", "items": {"type": "string"}}
FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "cuisines": WORD_LIST,
        "flavors": WORD_LIST,
        "preparation": WORD_LIST,
        "meal_category": {"type": "string", "enum": MEAL_CATEGORIES},
        "diets": {"type": "array", "items": {"type": "string", "enum": DIETS}},
        "exclusions": WORD_LIST,
        "max_cook_minutes": {"type": ["integer", "null"]},
    },
    "required": [
        "cuisines", "flavors", "preparation", "meal_category",
        "diets", "exclusions", "max_cook_minutes",
    ],
    "additionalProperties": False,
}