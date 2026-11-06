from dataclasses import dataclass, field


DIETARY_PREFERENCES = ("Vegetarian", "Vegan", "Keto")


@dataclass
class UserProfile:
    age: int
    sex: str
    height_cm: float
    weight_kg: float
    body_fat_pct: float | None
    occupation_type: str
    daily_steps: int | str
    exercise_sessions: list[dict[str, float | int | str]]
    cooking_skill: str
    allergens: list[str]
    fitness_goal: str
    occupation_hours_per_workday: float | None = None
    occupation_days_per_week: float | None = None
    occupational_steps_per_workday: int | None = None
    diets: list[str] = field(default_factory=list)