"""Live nutrition preview for a food search result."""

import streamlit as st


food_amount = st.components.v2.component(
    "sustain_food_amount",
    html="""
        <form>
            <div class="details">
                <strong></strong>
                <small class="brand" hidden></small>
                <small class="nutrition"></small>
            </div>
            <label><input type="number" required><span></span></label>
            <button type="submit">+ Add</button>
        </form>
    """,
    css="""
        form { display: flex; flex-wrap: wrap; align-items: center; gap: .6rem; }
        .details { flex: 1 1 12rem; min-width: 0; overflow-wrap: anywhere; }
        small { display: block; color: var(--st-text-color); opacity: .7; margin-top: .2rem; }
        [hidden] { display: none; }
        label, button {
            display: inline-flex; align-items: center; min-height: 2.5rem;
            padding: .4rem .65rem; border: 1px solid var(--st-border-color, #808080);
            border-radius: .5rem; background: var(--st-secondary-background-color);
            color: inherit; font: inherit;
        }
        label { gap: .2rem; }
        label:focus-within { outline: 1px solid var(--st-primary-color); }
        label span { opacity: .7; }
        input {
            width: 4ch; min-width: 0; color: inherit; font: inherit;
            background: transparent; outline: 0; border: 0; appearance: textfield;
        }
        input::-webkit-inner-spin-button, input::-webkit-outer-spin-button {
            appearance: none; margin: 0;
        }
        button { cursor: pointer; }
        button:disabled { cursor: default; opacity: .5; }
    """,
    js="""
        export default function ({ parentElement, data, setTriggerValue }) {
            const form = parentElement.querySelector("form");
            const input = form.querySelector("input");
            const button = form.querySelector("button");
            const nutrition = form.querySelector(".nutrition");
            const brand = form.querySelector(".brand");
            form.querySelector("strong").textContent = data.description;
            brand.textContent = data.brand;
            brand.hidden = !data.brand;
            form.querySelector("label span").textContent = data.unit;
            input.setAttribute("aria-label", `Amount (${data.unit}) for ${data.description}`);
            input.min = data.minimum;
            input.max = data.maximum;
            input.step = data.wholeGrams ? "1" : "any";
            if (!input.dataset.initialized) {
                input.value = data.defaultAmount;
                input.dataset.initialized = "true";
            }

            // Match Python's round-to-even rule for values exactly halfway.
            function rounded(value) {
                const lower = Math.floor(value);
                return Math.max(0, value - lower === 0.5 ? lower + lower % 2 : Math.round(value));
            }

            function preview() {
                button.disabled = !input.validity.valid;
                if (button.disabled) {
                    nutrition.textContent = "Enter a valid amount to see nutrition.";
                    return;
                }
                const scale = input.valueAsNumber / data.basis;
                const total = (key) => rounded(data.nutrients[key] * scale);
                nutrition.textContent = `${total("calories")} kcal · P ${total("protein_g")} g · C ${total("carbs_g")} g · F ${total("fat_g")} g`;
            }
            input.oninput = preview;
            form.onsubmit = (event) => {
                event.preventDefault();
                if (input.validity.valid) setTriggerValue("add", input.valueAsNumber);
            };
            preview();
        }
    """,
)
