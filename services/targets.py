# Daily calorie and macro targets from a saved profile, and the recalibration trigger.
#
# TEMPORARY: the real engine is SCRUM-24 (services/tdee_engine.py, BMR + NEAT + EAT + TEF).
# This uses Mifflin-St Jeor x an activity multiplier so the settings page works today.
# When tdee_engine.py is ready, replace calculate_targets() with a call to it.

from services import db

ACTIVITY_MULTIPLIERS = {
    "Sedentary": 1.2,
    "Lightly Active": 1.375,
    "Moderately Active": 1.55,
    "Very Active": 1.725,
    "Athlete": 1.9,
}

GOAL_MODIFIERS = {
    "Fat Loss": 0.80,
    "Muscle Gain": 1.10,
    "Recomposition": 1.00,
    "GLP-1 Support": 0.85,  # open question on SCRUM-24; confirm with the team
}

CALORIE_FLOOR = 1200  # proposed default on SCRUM-115, to be confirmed


def calculate_targets(profile):
    weight = profile["weight_kg"]
    bmr = 10 * weight + 6.25 * profile["height_cm"] - 5 * profile["age"]
    bmr += 5 if profile["sex"] == "Male" else -161
    tdee = bmr * ACTIVITY_MULTIPLIERS.get(profile["activity_level"], 1.2)
    calories = max(CALORIE_FLOOR, round(tdee * GOAL_MODIFIERS.get(profile["fitness_goal"], 1.0)))

    protein_g = round(1.8 * weight)
    fat_g = round(calories * 0.25 / 9)
    carbs_g = max(0, round((calories - protein_g * 4 - fat_g * 9) / 4))
    return {"calories": calories, "protein_g": protein_g, "carbs_g": carbs_g, "fat_g": fat_g}


def recalibrate(user_id):
    """SCRUM-95 trigger: call after any profile change. Recalculates and saves the
    targets unless the user has set them by hand. Returns the targets now in force."""
    targets, manual = db.get_targets(user_id)
    if manual and targets:
        return targets
    profile = db.get_profile(user_id)
    if profile is None:
        return None
    targets = calculate_targets(profile)
    db.save_targets(user_id, targets, manual=False)
    return targets
