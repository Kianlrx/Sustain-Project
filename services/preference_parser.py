# Turns a user's free-text meal craving into search filters for the recipe database,
# using an AI model on Groq's free plan.

import json
import logging
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
# The free plan allows 30 requests a minute, so leave at least 2 seconds between calls.
SECONDS_BETWEEN_CALLS = 2
MAX_PROMPT_LENGTH = 500

# food.com keywords for cooking time, quickest first
TIME_KEYWORDS = [(15, "< 15 Mins"), (30, "< 30 Mins"), (60, "< 60 Mins"), (240, "< 4 Hours")]

_last_call = 0.0

logger = logging.getLogger(__name__)

class AIServiceError(Exception):
    """Raised when the AI model cannot give back usable filters."""


def request_filters(prompt):
    """Send the craving to the model and return its filters as a dict."""
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise AIServiceError("GROQ_API_KEY is not set.")

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        # strict mode makes the model's answer always match FILTER_SCHEMA
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "recipe_filters", "strict": True, "schema": FILTER_SCHEMA},
        },
        "reasoning_effort": "low",  # a simple task, so answer quickly
        "include_reasoning": False,  # only the JSON is needed
    }
    request = Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Sustain/1.0",
        },
    )

    for attempt in range(1, MAX_ATTEMPTS + 1):
        _wait_for_rate_limit()
        try:
            with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return _read_filters(payload)
        except HTTPError as error:
            # 429 is too many requests and 5xx is a server problem; both are worth retrying
            if error.code != 429 and error.code < 500:
                raise AIServiceError(f"AI service returned HTTP {error.code}.") from error
            last_error = error
        except (URLError, TimeoutError, OSError) as error:
            last_error = error  # no connection, or the request timed out
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AIServiceError("AI service returned an invalid response.") from error
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)  # wait 2 seconds, then 4, before trying again
    raise AIServiceError("Could not get an answer from the AI service.") from last_error


def _wait_for_rate_limit():
    # Space calls out so the app stays under the free plan's limit.
    global _last_call
    wait = SECONDS_BETWEEN_CALLS - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _read_filters(payload):
    # The model's JSON answer is a string inside the first choice.
    try:
        filters = json.loads(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise AIServiceError("AI service returned an unexpected response.") from error
    if not isinstance(filters, dict):
        raise AIServiceError("AI service did not return a JSON object.")
    return filters


def to_search_args(filters):
    """Turn filters into arguments for recipe_search.find_recipes."""
    keywords = []
    if filters["max_cook_minutes"]:
        # the quickest time keyword that still allows the time asked for
        for minutes, keyword in TIME_KEYWORDS:
            if filters["max_cook_minutes"] <= minutes:
                keywords.append(keyword)
                break
    # cuisines, flavors and preparation have no database column yet,
    # so they stay in the filters for ranking results later
    return {"diets": filters["diets"], "allergens": filters["exclusions"], "keywords": keywords}

def default_filters(meal_category="Any"):
    """Broad filters used when the craving is unclear or the AI service fails."""
    return {
        "cuisines": [], "flavors": [], "preparation": [],
        "meal_category": meal_category,
        "diets": [], "exclusions": [],
        "max_cook_minutes": None,
    }


def clean_filters(raw, meal_category="Any"):
    """Keep only valid values from the model; anything missing or wrong uses the default."""
    filters = default_filters(meal_category)
    if not isinstance(raw, dict):
        return filters

    for key in ["cuisines", "flavors", "preparation", "exclusions"]:
        filters[key] = _clean_words(raw.get(key))
    if isinstance(raw.get("diets"), list):
        filters["diets"] = [diet for diet in DIETS if diet in raw["diets"]]
    if raw.get("meal_category") in MEAL_CATEGORIES and raw["meal_category"] != "Any":
        filters["meal_category"] = raw["meal_category"]
    minutes = raw.get("max_cook_minutes")
    # True and False count as numbers in Python, so rule them out
    if isinstance(minutes, int) and not isinstance(minutes, bool) and 0 < minutes <= 24 * 60:
        filters["max_cook_minutes"] = minutes

    # Something can't be wanted and avoided at once ("spicy but no spice"), so avoiding wins.
    # Words are compared by their first 4 letters so "spicy" matches "spice".
    avoided = [word[:4] for word in filters["exclusions"]]
    filters["flavors"] = [flavor for flavor in filters["flavors"] if flavor[:4] not in avoided]
    return filters


def _clean_words(value):
    # A list of short, lowercase words without repeats; anything else becomes an empty list.
    if not isinstance(value, list):
        return []
    words = []
    for item in value:
        if isinstance(item, str):
            word = item.strip().lower()
            if word and len(word) <= 40 and word not in words:
                words.append(word)
    return words[:10]


def parse_preferences(prompt, meal_slot=None):
    """Turn a craving into filters. Always returns usable filters, even if the AI fails."""
    meal_category = meal_slot if meal_slot in MEAL_CATEGORIES else "Any"
    # Empty text, or text with no letters such as "???", has nothing to extract.
    if not isinstance(prompt, str) or not re.search(r"[^\W\d_]", prompt):
        return default_filters(meal_category)
    try:
        raw = request_filters(prompt.strip()[:MAX_PROMPT_LENGTH])
    except AIServiceError as error:
        logger.warning("Using default filters: %s", error)
        return default_filters(meal_category)
    return clean_filters(raw, meal_category)

if __name__ == "__main__":
    # Try it from the project folder: python -m services.preference_parser "something quick and spicy"
    import sys

    result = parse_preferences(" ".join(sys.argv[1:]))
    print(result)
    print(to_search_args(result))