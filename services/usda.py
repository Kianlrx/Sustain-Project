"""FoodData Central search and nutrient parsing helpers."""

import json
import math
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
MAX_QUERY_LENGTH = 100
NUTRIENT_IDS = {
    "calories": (1008, 2047, 2048),
    "protein_g": (1003,),
    "carbs_g": (1005,),
    "fat_g": (1004,),
}
NUTRIENT_NAME_PATTERNS = {
    "calories": re.compile(r"\b(?:energy|calories?)\b", re.IGNORECASE),
    "protein_g": re.compile(r"\bprotein\b", re.IGNORECASE),
    "carbs_g": re.compile(r"\bcarbohydrate\b", re.IGNORECASE),
    "fat_g": re.compile(r"\b(?:total lipid|total fat)\b", re.IGNORECASE),
}


class USDAError(Exception):
    """Raised when FoodData Central cannot return a usable search response."""


def normalize_food_query(query):
    """Normalize user input and reject empty, control-only, or excessive queries."""
    if not isinstance(query, str):
        raise ValueError("Enter a food to search for.")
    normalized = re.sub(r"[\x00-\x1f\x7f]", " ", query)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized or not re.search(r"[^\W_]", normalized, re.UNICODE):
        raise ValueError("Enter a food name containing letters or numbers.")
    if len(normalized) > MAX_QUERY_LENGTH:
        raise ValueError(f"Searches must be {MAX_QUERY_LENGTH} characters or fewer.")
    return normalized


def _food_nutrients(food):
    nutrients = food.get("foodNutrients") or []
    if not isinstance(nutrients, list):
        nutrients = []
    nutrients = [
        nutrient for nutrient in nutrients
        if isinstance(nutrient, dict)
        and isinstance(nutrient.get("value"), (int, float))
        and math.isfinite(nutrient["value"])
    ]
    result = {}
    for nutrient_key, ids in NUTRIENT_IDS.items():
        match = next(
            (
                nutrient for nutrient in nutrients
                if nutrient.get("nutrientId") in ids
            ),
            None,
        )
        if match is None:
            match = next(
                (
                    nutrient for nutrient in nutrients
                    if NUTRIENT_NAME_PATTERNS[nutrient_key].search(
                        str(nutrient.get("nutrientName", ""))
                    )
                    and (
                        nutrient_key != "calories"
                        or str(nutrient.get("unitName", "")).upper() == "KCAL"
                    )
                ),
                None,
            )
        result[nutrient_key] = float(match["value"]) if match else 0.0
    return result


def parse_food(food):
    """Convert one FoodData Central search result to a stable UI-friendly shape."""
    serving_size = food.get("servingSize")
    serving_unit = str(food.get("servingSizeUnit") or "").lower()
    if (
        isinstance(serving_size, (int, float))
        and math.isfinite(serving_size)
        and serving_size > 0
        and serving_unit in ("g", "ml")
    ):
        basis_grams = float(serving_size)
    else:
        basis_grams = 100.0
    return {
        "fdc_id": str(food["fdcId"]),
        "description": str(food.get("description") or "Unnamed food"),
        "brand": str(food.get("brandOwner") or ""),
        "basis_grams": basis_grams,
        "nutrients": _food_nutrients(food),
    }


def search_foods(query, page_size=25, timeout=10):
    """Search USDA FoodData Central for foods matching a validated query."""
    query = normalize_food_query(query)
    api_key = os.environ.get("USDA_API_KEY", "DEMO_KEY").strip() or "DEMO_KEY"
    parameters = urlencode(
        {
            "api_key": api_key,
            "query": query,
            "pageSize": max(1, min(int(page_size), 50)),
        }
    )
    request = Request(
        f"{API_URL}?{parameters}",
        headers={"User-Agent": "Sustain/1.0"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise USDAError(f"USDA FoodData Central returned HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise USDAError("Could not connect to USDA FoodData Central.") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise USDAError("USDA FoodData Central returned an invalid response.") from error

    foods = payload.get("foods") if isinstance(payload, dict) else None
    if not isinstance(foods, list):
        raise USDAError("USDA FoodData Central returned an unexpected response.")
    return [parse_food(food) for food in foods if isinstance(food, dict) and food.get("fdcId")]
