"""Estimate daily energy expenditure from an onboarding profile.

Profile fields
--------------
Required:
    weight_kg: float
    occupation_type: one of OCCUPATION_METS or a legacy occupation label
    daily_steps: integer, a supported range label, or None/"Unknown"
    occupation_hours_per_workday: hours spent in the selected work activity
    occupation_days_per_week: number of workdays
    occupational_steps_per_workday: optional work steps included in daily_steps

Also required when body_fat_pct is absent:
    age: int
    height_cm: float
    sex: "Male" or "Female"

Optional:
    body_fat_pct: float
    exercise_sessions: list[dict], each containing:
        met: activity MET value (e.g. 3.5 for brisk walking, 6.8 for
             moderate cycling, 5.0 for general resistance training)
        duration_minutes: duration of one session
        sessions_per_week: average weekly frequency
        steps_per_session: optional average steps counted by the wearable
                           during one session. Supply this for walking/running
                           sessions if daily_steps includes workout steps, so
                           those steps are not counted in both NEAT and EAT.

The model is an estimate, not a substitute for measured energy expenditure.
Work activity is estimated from its MET value and time spent doing it, with
steps removed from the occupational estimate when work steps are supplied.
Onboarding assumes 8 hours/day for desk or standing work, 4 hours for active
work, or 2 hours for heavy labor, with a five-day workweek.
Exercise calories use net METs (MET - 1) to avoid adding resting energy a
second time. If no exercise_sessions are supplied,
EAT is zero; the old activity_level label is deliberately not converted into
exercise calories because it does not contain enough information.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


# Compendium-style reference MET estimates for the existing broad work choices.
# Work duration is required because a job title does not describe the whole shift.
OCCUPATION_METS = {
    "Desk Job": 1.3,
    "Standing": 1.8,
    "Active Work": 3.8,
    "Heavy Labor": 6.5,
}

# Representative time spent in the selected activity on a typical workday.
DEFAULT_OCCUPATION_HOURS_PER_WORKDAY = {
    "Desk Job": 8,
    "Standing": 8,
    "Active Work": 4,
    "Heavy Labor": 2,
}

# Used only for older saved profiles that do not contain work-duration inputs.
OCCUPATION_NON_STEP_MULTIPLIERS = {
    "Desk Job": 0.05,
    "Standing": 0.10,
    "Active Work": 0.20,
    "Heavy Labor": 0.30,
}

# Representative MET values for the broad workout categories in onboarding.
# General resistance training is used for the low-intensity weight-training
# choice; actual cost varies with exercise selection, rest periods, and effort.
TRAINING_TYPE_METS = {
    "Weight training (low intensity)": 3.5,
    "Endurance training (medium intensity)": 6.8,
    "Interval training (high intensity)": 8.0,
}

# Backwards-compatible constant name. Values now represent non-step activity.
NEAT_MULTIPLIERS = OCCUPATION_NON_STEP_MULTIPLIERS

STEP_COUNT_ESTIMATES = {
    "Less than 2,500": 1_250,
    "2,500-5,000": 3_750,
    "5,000-7,500": 6_250,
    "7,500-10,000": 8_750,
    # This is only a rough midpoint; an exact average is strongly preferred.
    "More than 10,000": 12_500,
}

UNKNOWN_STEP_VALUES = {"unknown", "not sure", "prefer not to say", ""}
DEFAULT_UNKNOWN_STEPS = 5_000
STEP_KCAL_PER_KG_PER_STEP = 0.00035
DEFAULT_OCCUPATION_DAYS_PER_WEEK = 5
MAX_OCCUPATION_HOURS_PER_DAY = 16
MAX_OCCUPATION_DAYS_PER_WEEK = 7

# TEF coefficients are approximate fractions of macronutrient energy:
# protein 25%, carbohydrate 7.5%, fat 1.5%.
PROTEIN_TEF_KCAL_PER_G = 1.0
CARB_TEF_KCAL_PER_G = 0.30
FAT_TEF_KCAL_PER_G = 0.135

PROTEIN_G_PER_KG_BODY_WEIGHT = 1.8
PROTEIN_G_PER_KG_LEAN_MASS = 2.0
FAT_KCAL_FRACTION = 0.25
MIN_FAT_G_PER_KG_REFERENCE_WEIGHT = 0.6


def _finite_float(value: Any, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be finite")
    return result


def calculate_bmr(profile: Mapping[str, Any]) -> float:
    """Return estimated resting energy expenditure in kcal/day.

    Katch-McArdle is used when body-fat percentage is supplied; otherwise
    Mifflin-St Jeor is used. These are prediction equations, not measurements.
    """
    weight = _finite_float(profile["weight_kg"], "weight_kg")
    if not 30 < weight < 500:
        raise ValueError("weight_kg must be greater than 30kg and less than 500kg")

    body_fat_pct = profile.get("body_fat_pct")
    if body_fat_pct is not None:
        body_fat_pct = _finite_float(body_fat_pct, "body_fat_pct")
        if not 3 <= body_fat_pct < 80:
            raise ValueError("body_fat_pct must be between 3% and 80%")
        lean_mass = weight * (1 - body_fat_pct / 100)
        return 370 + 21.6 * lean_mass

    age_value = _finite_float(profile["age"], "age")
    if not age_value.is_integer() or not 15 < age_value <= 120:
        raise ValueError("age must be a whole number between 16 and 120")
    age = int(age_value)
    height = _finite_float(profile["height_cm"], "height_cm")
    if not 120 < height < 250:
        raise ValueError("height_cm must be between 120cm and 250cm")

    sex_adjustment = {"Male": 5, "Female": -161}.get(profile.get("sex"))
    if sex_adjustment is None:
        raise ValueError("sex must be 'Male' or 'Female'")
    return 10 * weight + 6.25 * height - 5 * age + sex_adjustment


def normalize_step_count(daily_steps: int | str | None) -> int:
    """Normalize exact counts/range labels; unknown values use a neutral 5k.

    A true zero remains zero. Use None or "Unknown" when the user does not
    know their step count; do not use zero as a proxy for missing data.
    """
    if daily_steps is None:
        return DEFAULT_UNKNOWN_STEPS

    if isinstance(daily_steps, str):
        stripped = daily_steps.strip()
        if stripped.lower() in UNKNOWN_STEP_VALUES:
            return DEFAULT_UNKNOWN_STEPS
        if stripped in STEP_COUNT_ESTIMATES:
            return STEP_COUNT_ESTIMATES[stripped]
        normalized_range = stripped.replace(" ", "")
        if normalized_range in STEP_COUNT_ESTIMATES:
            return STEP_COUNT_ESTIMATES[normalized_range]
        try:
            daily_steps = int(stripped.replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"Unrecognized daily_steps value: {daily_steps!r}") from exc

    if isinstance(daily_steps, bool):
        raise ValueError("daily_steps must be a non-negative integer")
    try:
        steps = int(daily_steps)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("daily_steps must be a non-negative integer") from exc
    if steps < 0 or steps != daily_steps:
        raise ValueError("daily_steps must be a non-negative integer")
    return steps


def _exercise_session_values(
    exercise_sessions: Sequence[Mapping[str, Any]] | None,
) -> tuple[float, list[dict[str, float | bool]]]:
    """Return average daily exercise steps and validated session details."""
    if exercise_sessions is None:
        return 0.0, []
    if isinstance(exercise_sessions, (str, bytes)) or not isinstance(
        exercise_sessions, Sequence
    ):
        raise ValueError("exercise_sessions must be a list of session mappings")

    total_weekly_steps = 0.0
    details: list[dict[str, float | bool]] = []

    for index, session in enumerate(exercise_sessions):
        if not isinstance(session, Mapping):
            raise ValueError(f"exercise_sessions[{index}] must be a mapping")
        try:
            met = _finite_float(session["met"], f"exercise_sessions[{index}].met")
            duration = _finite_float(
                session["duration_minutes"],
                f"exercise_sessions[{index}].duration_minutes",
            )
            frequency = _finite_float(
                session["sessions_per_week"],
                f"exercise_sessions[{index}].sessions_per_week",
            )
        except KeyError as exc:
            raise ValueError(
                f"exercise_sessions[{index}] is missing required field {exc.args[0]!r}"
            ) from exc

        raw_steps_per_session = session.get("steps_per_session")
        steps_per_session = (
            0.0
            if raw_steps_per_session is None
            else _finite_float(
                raw_steps_per_session,
                f"exercise_sessions[{index}].steps_per_session",
            )
        )
        if not 1 <= met <= 20:
            raise ValueError(f"exercise_sessions[{index}].met must be between 1 and 20")
        if not 0 < duration <= 1_440:
            raise ValueError(
                f"exercise_sessions[{index}].duration_minutes must be between 0 and 1440"
            )
        if not 0 <= frequency <= 21:
            raise ValueError(
                f"exercise_sessions[{index}].sessions_per_week must be between 0 and 21"
            )
        if steps_per_session < 0:
            raise ValueError(
                f"exercise_sessions[{index}].steps_per_session cannot be negative"
            )

        # Store intensity/time/frequency; calculate_eat applies body weight.
        total_weekly_steps += steps_per_session * frequency
        details.append(
            {
                "met": met,
                "duration_minutes": duration,
                "sessions_per_week": frequency,
                "steps_per_session": steps_per_session,
                "step_count_provided": raw_steps_per_session is not None,
            }
        )

    # Exercise steps are averaged over seven days for subtraction from NEAT.
    return total_weekly_steps / 7, details


def calculate_eat(
    weight_kg: float,
    exercise_sessions: Sequence[Mapping[str, Any]] | None,
) -> float:
    """Estimate average daily net exercise expenditure from session METs.

    Each session uses net METs (MET - 1), duration and weekly frequency:
    kcal = (MET - 1) * 3.5 * weight_kg / 200 * minutes.
    """
    weight = _finite_float(weight_kg, "weight_kg")
    if weight <= 0:
        raise ValueError("weight_kg must be greater than zero")
    _, sessions = _exercise_session_values(exercise_sessions)
    weekly_kcal = sum(
        (s["met"] - 1)
        * 3.5
        * weight
        / 200
        * s["duration_minutes"]
        * s["sessions_per_week"]
        for s in sessions
    )
    return weekly_kcal / 7


def calculate_occupational_neat(
    weight_kg: float,
    occupation_type: str,
    hours_per_workday: float,
    workdays_per_week: float,
    work_steps_per_workday: float | None = None,
) -> tuple[float, float, float]:
    """Return non-step work NEAT, total net work energy, and counted work-step energy."""
    try:
        met = OCCUPATION_METS[occupation_type]
    except KeyError as exc:
        raise ValueError(f"Unrecognized occupation_type: {occupation_type!r}") from exc

    weight = _finite_float(weight_kg, "weight_kg")
    hours = _finite_float(hours_per_workday, "occupation_hours_per_workday")
    days = _finite_float(workdays_per_week, "occupation_days_per_week")
    if weight <= 0:
        raise ValueError("weight_kg must be greater than zero")
    if not 0 <= hours <= MAX_OCCUPATION_HOURS_PER_DAY:
        raise ValueError("occupation_hours_per_workday must be between 0 and 16")
    if not 0 <= days <= MAX_OCCUPATION_DAYS_PER_WEEK:
        raise ValueError("occupation_days_per_week must be between 0 and 7")

    total_work_kcal = (
        (met - 1)
        * 3.5
        * weight
        / 200
        * hours
        * 60
        * days
        / 7
    )
    if work_steps_per_workday is None:
        return total_work_kcal, total_work_kcal, 0.0

    work_steps = _finite_float(
        work_steps_per_workday, "occupational_steps_per_workday"
    )
    if work_steps < 0:
        raise ValueError("occupational_steps_per_workday cannot be negative")
    average_work_steps = work_steps * days / 7
    estimated_step_energy = average_work_steps * weight * STEP_KCAL_PER_KG_PER_STEP
    counted_step_energy = min(total_work_kcal, estimated_step_energy)
    return (
        total_work_kcal - counted_step_energy,
        total_work_kcal,
        counted_step_energy,
    )


def calculate_neat(
    bmr: float,
    weight_kg: float,
    daily_steps: int | str | None,
    occupation_type: str,
    exercise_steps_per_day: float = 0.0,
    occupation_hours_per_workday: float | None = None,
    occupation_days_per_week: float = DEFAULT_OCCUPATION_DAYS_PER_WEEK,
    occupational_steps_per_workday: float | None = None,
) -> float:
    """Estimate non-exercise activity, supporting legacy and time-based work inputs."""
    steps = normalize_step_count(daily_steps)
    exercise_steps = _finite_float(exercise_steps_per_day, "exercise_steps_per_day")
    if exercise_steps < 0:
        raise ValueError("exercise_steps_per_day cannot be negative")
    weight = _finite_float(weight_kg, "weight_kg")
    if occupation_hours_per_workday is None:
        try:
            multiplier = OCCUPATION_NON_STEP_MULTIPLIERS[occupation_type]
        except KeyError as exc:
            raise ValueError(
                f"Unrecognized occupation_type: {occupation_type!r}"
            ) from exc
        occupation_neat = _finite_float(bmr, "bmr") * multiplier
        work_steps_per_day = 0.0
    else:
        occupation_neat, _, counted_work_step_energy = calculate_occupational_neat(
            weight,
            occupation_type,
            occupation_hours_per_workday,
            occupation_days_per_week,
            occupational_steps_per_workday,
        )
        work_steps_per_day = (
            counted_work_step_energy
            / (weight * STEP_KCAL_PER_KG_PER_STEP)
        )
    non_exercise_steps = max(0.0, steps - exercise_steps - work_steps_per_day)
    step_neat = non_exercise_steps * weight * STEP_KCAL_PER_KG_PER_STEP
    return occupation_neat + step_neat


def calculate_tef(protein_g: float, carbs_g: float, fat_g: float) -> float:
    """Estimate TEF from macronutrients using approximate average coefficients."""
    protein = _finite_float(protein_g, "protein_g")
    carbs = _finite_float(carbs_g, "carbs_g")
    fat = _finite_float(fat_g, "fat_g")
    if min(protein, carbs, fat) < 0:
        raise ValueError("macronutrient grams must be zero or greater")
    return (
        protein * PROTEIN_TEF_KCAL_PER_G
        + carbs * CARB_TEF_KCAL_PER_G
        + fat * FAT_TEF_KCAL_PER_G
    )


def _protein_reference_weight(profile: Mapping[str, Any]) -> tuple[float, str]:
    """Choose actual, lean or adjusted weight for a practical protein target."""
    weight = _finite_float(profile["weight_kg"], "weight_kg")
    body_fat_pct = profile.get("body_fat_pct")

    if body_fat_pct is not None:
        body_fat = _finite_float(body_fat_pct, "body_fat_pct")
        if not 3 <= body_fat < 80:
            raise ValueError("body_fat_pct must be between 3% and 80%")
        sex = profile.get("sex")
        high_body_fat_threshold = {"Male": 25.0, "Female": 35.0}.get(sex)
        if high_body_fat_threshold is not None and body_fat >= high_body_fat_threshold:
            return weight * (1 - body_fat / 100), "lean_body_mass"
        return weight, "body_weight"

    height_cm = profile.get("height_cm")
    if height_cm is not None:
        height_m = _finite_float(height_cm, "height_cm") / 100
        if height_m > 0:
            bmi = weight / (height_m * height_m)
            if bmi >= 30:
                # Adjusted weight avoids scaling protein directly to excess
                # adipose mass. BMI 25 is used as the reference-weight anchor.
                ideal_weight = 25 * height_m * height_m
                adjusted_weight = ideal_weight + 0.4 * (weight - ideal_weight)
                return adjusted_weight, "adjusted_body_weight"
    return weight, "body_weight"


def _estimate_macros(
    profile: Mapping[str, Any], calories: float
) -> dict[str, int | float | str]:
    """Create maintenance macros using a body-composition-aware protein target."""
    calorie_target = _finite_float(calories, "calories")
    if calorie_target <= 0:
        raise ValueError("calories must be greater than zero")

    reference_weight, protein_basis = _protein_reference_weight(profile)
    if protein_basis == "lean_body_mass":
        protein_g = round(PROTEIN_G_PER_KG_LEAN_MASS * reference_weight)
    else:
        protein_g = round(PROTEIN_G_PER_KG_BODY_WEIGHT * reference_weight)

    fat_g = max(
        round(calorie_target * FAT_KCAL_FRACTION / 9),
        math.ceil(MIN_FAT_G_PER_KG_REFERENCE_WEIGHT * reference_weight),
    )
    remaining_for_carbs = calorie_target - protein_g * 4 - fat_g * 9
    if remaining_for_carbs < 0:
        raise ValueError(
            "Calorie target is too low to accommodate the protein and minimum fat targets"
        )
    carbs_g = round(remaining_for_carbs / 4)
    return {
        "protein_g": protein_g,
        "carbs_g": carbs_g,
        "fat_g": fat_g,
        "protein_reference_weight_kg": round(reference_weight, 1),
        "protein_basis": protein_basis,
    }


def calculate_tdee(
    profile: Mapping[str, Any],
    macros: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Return estimated BMR, NEAT, EAT, TEF and TDEE in kcal/day.

    When macros are omitted, maintenance macros and TEF are solved together
    iteratively, so macro calories converge on the returned TDEE. When macros
    are supplied, they are treated as the user's intake; the TDEE estimate then
    uses their corresponding TEF and reports the resulting energy balance.

    `exercise_sessions` is a list of MET-based sessions. The former
    `activity_level` input is not used to invent EAT calories; if it is present
    without sessions, a warning is returned and EAT is zero.
    """
    bmr = calculate_bmr(profile)
    weight = _finite_float(profile["weight_kg"], "weight_kg")
    daily_steps = profile.get("daily_steps")
    exercise_sessions = profile.get("exercise_sessions", [])

    eat = calculate_eat(weight, exercise_sessions)
    exercise_steps_per_day, session_details = _exercise_session_values(
        exercise_sessions
    )
    steps_used = normalize_step_count(daily_steps)
    occupation_type = profile["occupation_type"]
    occupation_hours = profile.get("occupation_hours_per_workday")
    occupation_days = profile.get("occupation_days_per_week")
    if occupation_hours is not None and occupation_days is None:
        occupation_days = DEFAULT_OCCUPATION_DAYS_PER_WEEK
    occupational_steps = profile.get("occupational_steps_per_workday")
    if occupation_hours is None:
        try:
            occupation_multiplier = OCCUPATION_NON_STEP_MULTIPLIERS[occupation_type]
        except KeyError as exc:
            raise ValueError(
                f"Unrecognized occupation_type: {occupation_type!r}"
            ) from exc
        occupation_neat = bmr * occupation_multiplier
        occupation_total_kcal = occupation_neat
        work_step_kcal = 0.0
        work_steps_per_day = 0.0
    else:
        occupation_neat, occupation_total_kcal, work_step_kcal = (
            calculate_occupational_neat(
                weight,
                occupation_type,
                occupation_hours,
                occupation_days,
                occupational_steps,
            )
        )
        work_steps_per_day = (
            work_step_kcal / (weight * STEP_KCAL_PER_KG_PER_STEP)
        )
        occupation_multiplier = None
    non_exercise_steps = max(
        0.0, steps_used - exercise_steps_per_day - work_steps_per_day
    )
    step_neat = non_exercise_steps * weight * STEP_KCAL_PER_KG_PER_STEP
    neat = occupation_neat + step_neat
    base_expenditure = bmr + neat + eat

    warnings: list[str] = []
    if occupation_hours is None:
        warnings.append(
            "Work hours were not provided; the legacy occupation multiplier "
            "was used. Add work hours in Settings for a time-based estimate."
        )
    elif (
        "occupation_days_per_week" not in profile
        or profile.get("occupation_days_per_week") is None
    ):
        warnings.append("Workdays per week were not provided; the estimate assumes 5.")
    if (
        occupation_hours is not None
        and occupation_hours == 0
        and occupation_type in {"Active Work", "Heavy Labor"}
    ):
        warnings.append(
            "No active work hours were entered for this physical occupation; "
            "occupational activity beyond reported steps is estimated as zero."
        )
    if (
        occupation_hours is not None
        and occupation_hours > 0
        and occupational_steps is None
    ):
        warnings.append(
            "Work steps were not supplied. If daily steps include steps taken "
            "at work, work activity and step NEAT may overlap."
        )
    if (
        occupation_hours is not None
        and occupation_hours > 0
        and occupation_type in {"Active Work", "Heavy Labor"}
        and steps_used < 2_500
    ):
        warnings.append(
            "The combination of physical work and fewer than 2,500 daily steps "
            "is unusual but possible. Confirm that work hours and step counts "
            "are typical."
        )
    if not exercise_sessions:
        if profile.get("activity_level") is not None:
            warnings.append(
                "activity_level is retained for UI compatibility but is not used "
                "to estimate EAT; provide exercise_sessions with MET, "
                "duration_minutes and sessions_per_week. EAT was set to 0."
            )
        else:
            warnings.append(
                "No exercise_sessions supplied; EAT was set to 0. Add MET-based "
                "sessions to include structured exercise."
            )
    if any(
        not session["step_count_provided"]
        and session.get("type")
        in {
            "Endurance training (medium intensity)",
            "Interval training (high intensity)",
        }
        for session in session_details
    ):
        warnings.append(
            "Workout step counts were not provided for cardio-style sessions. "
            "If those steps are included in total daily steps, NEAT may overlap "
            "with EAT."
        )
    if isinstance(daily_steps, str) and (
        daily_steps.strip() in STEP_COUNT_ESTIMATES
        or daily_steps.strip().replace(" ", "") in STEP_COUNT_ESTIMATES
    ):
        warnings.append(
            "The selected step range was converted to an approximate step count; "
            "an exact 7-day average is more reliable. The 'More than 10,000' "
            "option currently uses 12,500 steps/day."
        )
    if daily_steps is None or (
        isinstance(daily_steps, str)
        and daily_steps.strip().lower() in UNKNOWN_STEP_VALUES
    ):
        warnings.append(
            f"Daily steps were unknown; a neutral default of {DEFAULT_UNKNOWN_STEPS:,} "
            "steps/day was used."
        )
    reported_work_steps_per_day = (
        _finite_float(occupational_steps, "occupational_steps_per_workday")
        * float(occupation_days)
        / 7
        if occupational_steps is not None and occupation_hours is not None
        else work_steps_per_day
    )
    if exercise_steps_per_day + reported_work_steps_per_day > steps_used:
        warnings.append(
            "Estimated work and exercise steps exceed total daily steps; "
            "remaining step-based NEAT was clamped to zero. Check that all "
            "step inputs use the same daily average."
        )

    if macros is None:
        # Fixed-point iteration: intake = BMR + NEAT + EAT + TEF(intake).
        # Macro grams are recalculated at each candidate intake until stable.
        candidate_calories = base_expenditure / 0.90
        macro_values: dict[str, Any] = {}
        tef = 0.0
        for _ in range(100):
            macro_values = _estimate_macros(profile, candidate_calories)
            tef = calculate_tef(
                macro_values["protein_g"],
                macro_values["carbs_g"],
                macro_values["fat_g"],
            )
            updated_calories = base_expenditure + tef
            if abs(updated_calories - candidate_calories) < 0.1:
                candidate_calories = updated_calories
                break
            candidate_calories = updated_calories
        # Recalculate at the converged intake to keep macros and TEF aligned.
        macro_values = _estimate_macros(profile, candidate_calories)
        tef = calculate_tef(
            macro_values["protein_g"],
            macro_values["carbs_g"],
            macro_values["fat_g"],
        )
        macro_calories = (
            macro_values["protein_g"] * 4
            + macro_values["carbs_g"] * 4
            + macro_values["fat_g"] * 9
        )
        tdee = base_expenditure + tef
        # Integer macro rounding can leave a small residual; report the actual
        # macro calorie total and the independently calculated TDEE.
        energy_balance = macro_calories - tdee
    else:
        try:
            protein_g = _finite_float(macros["protein_g"], "protein_g")
            carbs_g = _finite_float(macros["carbs_g"], "carbs_g")
            fat_g = _finite_float(macros["fat_g"], "fat_g")
        except KeyError as exc:
            raise ValueError(f"Missing macro value: {exc.args[0]}") from exc
        if min(protein_g, carbs_g, fat_g) < 0:
            raise ValueError("macronutrient grams must be zero or greater")
        macro_values = {
            "protein_g": round(protein_g),
            "carbs_g": round(carbs_g),
            "fat_g": round(fat_g),
        }
        # Use the same rounded gram values for the displayed macros, TEF and
        # calorie total so the returned figures are internally consistent.
        protein_g = float(macro_values["protein_g"])
        carbs_g = float(macro_values["carbs_g"])
        fat_g = float(macro_values["fat_g"])
        tef = calculate_tef(protein_g, carbs_g, fat_g)
        macro_calories = protein_g * 4 + carbs_g * 4 + fat_g * 9
        tdee = base_expenditure + tef
        energy_balance = macro_calories - tdee

    tdee_rounded = round(tdee)
    components = {
        "bmr_kcal": round(bmr),
        "neat_kcal": round(neat),
        "eat_kcal": round(eat),
        "tef_kcal": round(tef),
    }
    return {
        **components,
        "tdee_kcal": tdee_rounded,
        "base_expenditure_before_tef_kcal": round(base_expenditure),
        "macro_calories_kcal": round(macro_calories),
        "energy_balance_kcal": round(energy_balance),
        "step_count_used": steps_used,
        "non_exercise_steps_used": round(non_exercise_steps),
        "exercise_steps_per_day": round(exercise_steps_per_day),
        "occupational_steps_per_day": round(work_steps_per_day),
        "occupation_non_step_neat_kcal": round(occupation_neat),
        "occupation_total_neat_kcal": round(occupation_total_kcal),
        "work_step_energy_in_occupation_kcal": round(work_step_kcal),
        "step_neat_kcal": round(step_neat),
        "bmr_method": "Katch-McArdle" if profile.get("body_fat_pct") is not None else "Mifflin-St Jeor",
        "occupation_met": OCCUPATION_METS.get(occupation_type),
        "occupation_hours_per_workday": occupation_hours,
        "occupation_days_per_week": occupation_days,
        "occupation_non_step_multiplier": occupation_multiplier,
        # Retained as an alias for callers displaying the old field name.
        "neat_multiplier": occupation_multiplier,
        "eat_method": "net_met_sessions",
        "exercise_sessions_used": session_details,
        "macros": {
            "protein_g": round(float(macro_values["protein_g"])),
            "carbs_g": round(float(macro_values["carbs_g"])),
            "fat_g": round(float(macro_values["fat_g"])),
            **(
                {
                    "protein_reference_weight_kg": macro_values[
                        "protein_reference_weight_kg"
                    ],
                    "protein_basis": macro_values["protein_basis"],
                }
                if "protein_basis" in macro_values
                else {}
            ),
        },
        "warnings": warnings,
    }
