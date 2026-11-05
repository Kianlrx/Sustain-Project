# Daily calorie and macro targets from a saved profile, and the recalibration trigger.

from services import db
from services.tdee_engine import calculate_tdee

GOAL_MODIFIERS = {
    "Fat Loss": 0.80,
    "Muscle Gain": 1.10,
    "Recomposition": 1.00,
    "GLP-1 Support": 0.85,  # open question on SCRUM-24; confirm with the team
}

CALORIE_FLOOR = 1200  # proposed default on SCRUM-115, to be confirmed


def calculate_targets(profile):
    weight = profile["weight_kg"]
    tdee = calculate_tdee(profile)["tdee_kcal"]
    calories = max(
        CALORIE_FLOOR,
        round(tdee * GOAL_MODIFIERS.get(profile["fitness_goal"], 1.0)),
    )

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
