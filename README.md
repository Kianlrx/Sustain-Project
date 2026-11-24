# Sustain

Sustain is a Streamlit-based nutrition and food diary application that helps users manage their dietary goals through personalized nutrition tracking and intelligent meal recommendations. Users can create an account, complete onboarding, review personalized nutrition targets, log foods, and manage their profile. The platform also retrieves recipes from a curated recipe dataset and filters them based on each user's nutritional requirements, including calorie and macronutrient targets (protein, carbohydrates, and fats) as well as dietary constraints such as vegetarian, vegan, gluten-free, or other preferences. When no suitable recipe is available in the dataset, an AI-powered agent automatically generates a custom recipe tailored to the user's specific nutritional goals and dietary needs.

# Streamlit Website

You can access the latest version of the Sustain App at ``https://sustain-app.streamlit.app/``

## Requirements

- Python 3.10 or newer
- `pip`
- Internet access for USDA FoodData Central food searches

## Set up and run

Open a terminal in the project folder and create a virtual environment:

```powershell
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use Command Prompt instead:

```bat
.venv\Scripts\activate.bat
```

Install the project dependencies and start Streamlit:

```powershell
python -m pip install -r requirements.txt
$env:USDA_API_KEY = "PDC6KmT8nFtzmp8HjqTmRp8tJkJMGt9qdKfkC7HP"
python -m streamlit run app.py
```

Streamlit prints a local URL (usually `http://localhost:8501`) in the terminal. Open that URL in your browser. Use **Sign up** to create an account, then complete onboarding to access the Dashboard, Diary, and Settings.

To stop the app, press `Ctrl+C` in the terminal running Streamlit.

## USDA food search

The Diary's **Search Food** action searches USDA FoodData Central. The app uses the USDA `DEMO_KEY` if no API key is configured; USDA may apply stricter rate limits to that key.

For regular use, set your own key as the `USDA_API_KEY` environment variable before launching the app:

```powershell
$env:USDA_API_KEY = "your-usda-api-key"
python -m streamlit run app.py
```

Get an API key from the [USDA FoodData Central API](https://fdc.nal.usda.gov/api-key-signup.html). Do not commit API keys to the repository.

## Data and features

- The SQLite database (`sustain.db`) is created automatically in the current working directory when the app starts.
- Keep using the project folder as the working directory so the database stays in a predictable location.
- `.gitignore` excludes the local database, Python cache files, virtual environment, and downloaded data.
- The Diary supports manual food entry and USDA food lookup. Barcode scanning is not currently available.
- Recipe craving input and saved-recipe storage are present, but recipe matching is not yet connected.
- Voice input uses browser speech recognition. It requires a supported browser and microphone permission.

## Run tests

With the virtual environment activated, run:

```powershell
python -m unittest discover -s tests -v
```
