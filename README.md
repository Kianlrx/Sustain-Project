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

Install the project dependencies:

```powershell
python -m pip install -r requirements.txt
```

Create a Supabase project or use an existing development project. In its dashboard, open **Connect**, choose **Session pooler** on port `5432`, and copy the PostgreSQL URI. Replace the entire password placeholder, including its brackets, and URL-encode any reserved characters in the password.

Create `.streamlit/secrets.toml` in the project folder:

```toml
DATABASE_URL = "postgresql://postgres.PROJECT_REF:ENCODED_PASSWORD@POOLER_HOST:5432/postgres"
```

Keep the credentials private. Git ignores this file. You can also set `DATABASE_URL` as an environment variable, which takes precedence.

Start Streamlit:

```powershell
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

- The app creates its tables in the `sustain` schema on Supabase when it starts.
- Accounts, profiles, nutrition targets, food logs, weight logs, and saved recipes are stored in Supabase. The recipe search index is a separate local SQLite database.
- `.gitignore` excludes the local database, Python cache files, virtual environment, and downloaded data.
- The Diary supports manual food entry and USDA food lookup. Barcode scanning is not currently available.
- Recipe craving input and saved-recipe storage are present, but recipe matching is not yet connected.
- Voice input uses browser speech recognition. It requires a supported browser and microphone permission.

## Run tests

With the virtual environment activated, run:

```powershell
python -m unittest discover -s tests -v
```
