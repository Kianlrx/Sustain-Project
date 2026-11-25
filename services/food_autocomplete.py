"""Browser-side food suggestions with server-owned nutrition values."""

import csv
from functools import lru_cache
from pathlib import Path

import streamlit as st

from services import db
from services.usda import MAX_QUERY_LENGTH


ROOT = Path(__file__).resolve().parents[1]
_component = st.components.v2.component(
    "sustain_food_autocomplete",
    html="""
        <form>
            <label for="food-query">Food name</label>
            <div class="search">
                <input id="food-query" placeholder="e.g. chicken breast"
                       required autocomplete="off" role="combobox" aria-autocomplete="list"
                       aria-controls="food-suggestions" aria-expanded="false">
                <button type="submit">Search</button>
            </div>
            <ul id="food-suggestions" role="listbox" aria-label="Food suggestions" hidden></ul>
        </form>
    """,
    js=(ROOT / "components" / "food_autocomplete" / "search.js").read_text(encoding="utf-8"),
    css="""
        label { display: block; margin-bottom: .35rem; }
        .search { display: flex; gap: .5rem; }
        input, button, ul {
            font: inherit; color: inherit; border: 1px solid var(--st-border-color, #808080);
            border-radius: .5rem; background: var(--st-secondary-background-color);
        }
        input { min-width: 0; flex: 1; padding: .5rem .65rem; }
        button { padding: .5rem .75rem; cursor: pointer; }
        ul { list-style: none; margin: .25rem 0 0; padding: .25rem; }
        li { padding: .4rem .55rem; border-radius: .3rem; cursor: pointer; }
        li:hover, li[aria-selected="true"] { background: var(--st-background-color); }
        small { display: block; opacity: .75; }
    """,
)


@lru_cache(maxsize=1)
def _common_foods():
    with (ROOT / "assets" / "common_usda_foods.csv").open(encoding="utf-8", newline="") as file:
        return tuple({
            "id": f"common-{row['fdc_id']}",
            "description": row["name"],
            "source": "Common USDA food",
            "brand": "",
            "basis_quantity": 100,
            "nutrients": {key: float(row[key]) for key in db.FOOD_NUTRIENTS},
        } for row in csv.DictReader(file))


def food_autocomplete(user_id):
    recent = [
        {
            "id": f"recent-{entry['food_name']}",
            "description": entry["food_name"],
            "source": "Recently logged",
            "brand": "",
            "basis_quantity": entry["base_quantity"],
            "quantity_unit": entry["quantity_unit"],
            "default_amount": entry["quantity"],
            "nutrients": {key: entry[key] for key in db.FOOD_NUTRIENTS},
        }
        for entry in db.get_logged_foods(user_id, at_base_quantity=True)
    ]
    foods = {food["id"]: food for food in (*recent, *_common_foods())}
    result = _component(
        key=f"food_autocomplete_{user_id}",
        data={
            "foods": [
                {"id": food["id"], "name": food["description"], "source": food["source"]}
                for food in foods.values()
            ],
            "maxLength": MAX_QUERY_LENGTH,
        },
        on_search_change=lambda: None,
        on_select_change=lambda: None,
    )
    selected_id = result.select
    return result.search, foods.get(selected_id) if isinstance(selected_id, str) else None
