from dataclasses import dataclass


@dataclass
class UserProfile:
    age: int
    sex: str
    height_cm: float
    weight_kg: float
    body_fat_pct: float | None
    activity_level: str
    occupation_type: str
    daily_steps: int | str
    cooking_skill: str
    allergens: list[str]
    fitness_goal: str