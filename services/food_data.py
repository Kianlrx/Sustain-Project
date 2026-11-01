from pathlib import Path

import kagglehub
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

DATASET = "irkaal/foodcom-recipes-and-reviews"
OUTPUT_FOLDER = Path("data")

NUTRITION_COLUMNS = [
    "Calories",
    "FatContent",
    "SaturatedFatContent",
    "CholesterolContent",
    "SodiumContent",
    "CarbohydrateContent",
    "FiberContent",
    "SugarContent",
    "ProteinContent",
]


def load_recipes():
    # download the dataset from kaggle, or reuse the saved copy
    folder = kagglehub.dataset_download(DATASET)
    # read the recipes file into a dataframe
    return pd.read_parquet(Path(folder) / "recipes.parquet")


def remove_nulls(df):
    # these columns have too many empty values to keep
    df = df.drop(columns=["RecipeYield", "AggregatedRating", "ReviewCount"])
    # remove any recipe with a null value
    return df.dropna()


def remove_incorrect(df):
    # a recipe needs ingredients
    has_ingredients = df["RecipeIngredientParts"].map(len) > 0
    # a recipe needs quantities
    has_quantities = df["RecipeIngredientQuantities"].map(len) > 0
    # a recipe needs instructions
    has_instructions = df["RecipeInstructions"].map(len) > 0
    # a recipe with 0 calories is a data error
    has_calories = df["Calories"] > 0
    # sugar is part of carbs so it cannot be higher
    valid_sugar = df["SugarContent"] <= df["CarbohydrateContent"]
    return df[has_ingredients & has_quantities & has_instructions & has_calories & valid_sugar]


def remove_outliers(df):
    columns = NUTRITION_COLUMNS + ["RecipeServings"]
    # find the lowest 1% and highest 1% cut off for each column
    low = df[columns].quantile(0.01)
    high = df[columns].quantile(0.99)
    # keep recipes where every column is inside its cut offs
    keep = ((df[columns] >= low) & (df[columns] <= high)).all(axis=1)
    return df[keep]


def scale_nutrition(df):
    # copy so the real nutrition values stay unchanged
    scaled = df.copy()
    # put each nutrition column on a scale from 0 to 1
    scaled[NUTRITION_COLUMNS] = MinMaxScaler().fit_transform(df[NUTRITION_COLUMNS])
    return scaled


def main():
    recipes = load_recipes()
    print("Loaded:", len(recipes))

    recipes = remove_nulls(recipes)
    print("After removing nulls:", len(recipes))

    recipes = remove_incorrect(recipes)
    print("After removing incorrect values:", len(recipes))

    recipes = remove_outliers(recipes)
    print("After removing outliers:", len(recipes))

    scaled = scale_nutrition(recipes)

    # create the output folder if it is missing
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    # save the real values for showing to users
    recipes.to_parquet(OUTPUT_FOLDER / "recipes_clean.parquet", index=False)
    # save the scaled values for analysis and models
    scaled.to_parquet(OUTPUT_FOLDER / "recipes_scaled.parquet", index=False)
    print("Saved files to", OUTPUT_FOLDER)


if __name__ == "__main__":
    main()
