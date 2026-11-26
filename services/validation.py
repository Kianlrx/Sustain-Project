# Input checks for the settings form and the food logging form.
# Each function returns a list of error messages. An empty list means the input is fine.
# The checks live here (not in the views) so they can be unit tested without Streamlit.

import math

from services.tdee_engine import MAX_WEIGHT_KG, MIN_WEIGHT_KG

# Settings: personal details. Same range as the weight log, so any weight a
# user has logged can be shown and saved here without being changed.
WEIGHT_MIN_KG = float(MIN_WEIGHT_KG)
WEIGHT_MAX_KG = float(MAX_WEIGHT_KG)
SESSIONS_MIN = 0
SESSIONS_MAX = 14
DURATION_MIN = 10
DURATION_MAX = 240
MAX_EXCLUSION_LENGTH = 50

# Settings: hand-set targets (same limits as the number boxes)
TARGET_LIMITS = {
    "calories": ("Calories", 1200, 6000),
    "protein_g": ("Protein", 0, 400),
    "carbs_g": ("Carbs", 0, 800),
    "fat_g": ("Fat", 0, 300),
}

# Food logging: one item
FOOD_NAME_MAX_LENGTH = 100
FOOD_LIMITS = {
    "calories": ("Calories", 0, 5000),
    "protein_g": ("Protein", 0, 500),
    "carbs_g": ("Carbs", 0, 1000),
    "fat_g": ("Fat", 0, 500),
}


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _check_range(value, label, minimum, maximum, unit=""):
    if value is None or (isinstance(value, str) and not value.strip()):
        return [f"{label} is required."]
    if not _is_number(value):
        return [f"{label} must be a number."]
    if value < 0:
        return [f"{label} can't be negative."]
    if not minimum <= value <= maximum:
        return [f"{label} must be between {minimum:g} and {maximum:g}{unit}."]
    return []


def validate_profile_settings(
    weight_kg,
    sessions_per_week,
    session_duration,
    occupation,
    goal,
    measurement_units,
    other_exclusions,
    *,
    occupations,
    goals,
):
    errors = _check_range(weight_kg, "Weight", WEIGHT_MIN_KG, WEIGHT_MAX_KG, " kg")
    errors += _check_range(sessions_per_week, "Training sessions per week", SESSIONS_MIN, SESSIONS_MAX)
    if _is_number(sessions_per_week) and sessions_per_week != int(sessions_per_week):
        errors.append("Training sessions per week must be a whole number.")
    if _is_number(sessions_per_week) and sessions_per_week > 0:
        errors += _check_range(
            session_duration, "Session duration", DURATION_MIN, DURATION_MAX, " minutes"
        )
    if occupation not in occupations:
        errors.append("Choose a daily occupation movement from the list.")
    if goal not in goals:
        errors.append("Choose a fitness goal from the list.")
    if measurement_units not in ("Metric", "Imperial"):
        errors.append("Choose Metric or Imperial units.")
    for item in (other_exclusions or "").split(","):
        if len(item.strip()) > MAX_EXCLUSION_LENGTH:
            errors.append(
                f"Each other exclusion must be {MAX_EXCLUSION_LENGTH} characters or fewer."
            )
            break
    return errors


def validate_manual_targets(targets):
    errors = []
    for key, (label, minimum, maximum) in TARGET_LIMITS.items():
        unit = " kcal" if key == "calories" else " g"
        errors += _check_range(targets.get(key), label, minimum, maximum, unit)
    return errors


def validate_food_entry(name, calories, protein_g, carbs_g, fat_g):
    errors = []
    if name is None or not str(name).strip():
        errors.append("Food name is required.")
    elif len(str(name).strip()) > FOOD_NAME_MAX_LENGTH:
        errors.append(f"Food name must be {FOOD_NAME_MAX_LENGTH} characters or fewer.")
    values = {"calories": calories, "protein_g": protein_g, "carbs_g": carbs_g, "fat_g": fat_g}
    for key, (label, minimum, maximum) in FOOD_LIMITS.items():
        unit = " kcal" if key == "calories" else " g"
        errors += _check_range(values[key], label, minimum, maximum, unit)
    return errors
