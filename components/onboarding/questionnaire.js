const truncate = (number) => Math.trunc(number * 100 + Math.sign(number) * 1e-8) / 100;
export default function ({ parentElement, data, setTriggerValue }) {
    const form = parentElement.querySelector("form");
    if (!form || !data?.defaults) return;
    const fields = form.elements;
    const sections = [...form.querySelectorAll("section")];
    const tabs = [...form.querySelectorAll(".ob-tab")];
    const find = (selector) => form.querySelector(selector);
    const back = find("#back");
    const next = find("#next");
    const errors = find(".errors");
    let step = Number(form.dataset.step || 0);

    if (!form.dataset.ready) {
        for (const [key, value] of Object.entries(data.feedback?.answers || data.defaults)) {
            if (Array.isArray(value)) {
                for (const input of form.querySelectorAll(`[name="${key}"]`)) input.checked = value.includes(input.value);
            } else if (typeof value === "boolean") {
                fields[key].checked = value;
            } else {
                fields[key].value = value;
            }
        }
    }
    let units = fields.measurement_units.value || data.defaults.measurement_units;

    function readAnswers() {
        const answers = {};
        for (const [key, defaultValue] of Object.entries(data.defaults)) {
            if (Array.isArray(defaultValue)) {
                answers[key] = [...form.querySelectorAll(`[name="${key}"]:checked`)].map(input => input.value);
            } else if (typeof defaultValue === "boolean") {
                answers[key] = fields[key].checked;
            } else if (typeof defaultValue === "number") {
                answers[key] = fields[key].value === "" ? null : Number(fields[key].value);
            } else {
                answers[key] = fields[key].value;
            }
        }
        if (!answers.training_sessions_per_week) {
            answers.training_duration_minutes = data.defaults.training_duration_minutes;
        }
        return answers;
    }

    function showWarning(input, message) {
        let warning = input.nextElementSibling;
        if (!warning?.classList.contains("field-warning")) {
            warning = document.createElement("small");
            warning.className = "field-warning";
            input.after(warning);
        }
        warning.textContent = input.value.trim() ? message : "";
        warning.hidden = !warning.textContent;
    }

    function measurement(key, label, min, max) {
        const input = fields[key];
        const text = input.value.trim();
        const number = truncate(Number(text));
        const validNumber = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(text);
        const error = !validNumber ? `${label} must be a number.`
            : number < min || number > max ? `${label} must be between ${min} and ${max}.` : "";
        input.setCustomValidity(error);
        showWarning(input, error);
        return error ? null : number;
    }

    function renderBmi(height, weight, imperial) {
        const bmiBadge = find("#bmi");
        if (height !== null && weight !== null) {
            const bmi = (imperial ? weight / 2.2046226218 : weight) / ((imperial ? height * .0254 : height / 100) ** 2);
            const [category, color] = bmi < 18.5 ? ["Underweight", "blue"] : bmi < 25 ? ["Healthy Range", "green"]
                : bmi < 30 ? ["Overweight", "amber"] : ["Higher BMI", "amber"];
            bmiBadge.textContent = `BMI ${bmi.toFixed(1)} \u00b7 ${category}`;
            bmiBadge.className = `ob-pill ${color}`;
        } else {
            bmiBadge.textContent = "BMI \u2014";
            bmiBadge.className = "ob-pill grey";
        }
    }

    function update() {
        const selectedUnits = fields.measurement_units.value || units;
        const imperial = selectedUnits === "Imperial";
        const [heightLabel, minHeight, maxHeight, weightLabel, minWeight, maxWeight] = data.ranges[selectedUnits];
        if (selectedUnits !== units) {
            const factors = imperial ? [1 / 2.54, 2.2046226218] : [2.54, 1 / 2.2046226218];
            const oldRanges = data.ranges[units];
            [fields.height_cm, fields.weight_kg].forEach((input, index) => {
                const original = Number(input.value);
                if (!input.value.trim() || !Number.isFinite(original)) return;
                let converted = truncate(original * factors[index]);
                if (original >= oldRanges[index * 3 + 1] && original <= oldRanges[index * 3 + 2]) {
                    const min = index === 0 ? minHeight : minWeight;
                    const max = index === 0 ? maxHeight : maxWeight;
                    converted = Math.max(min, Math.min(max, converted));
                }
                input.value = converted;
            });
            units = selectedUnits;
        }

        const height = measurement("height_cm", heightLabel, minHeight, maxHeight);
        const weight = measurement("weight_kg", weightLabel, minWeight, maxWeight);
        renderBmi(height, weight, imperial);

        const answers = readAnswers();
        const hint = (key, value) => find(`label[for="${key}"] span`).textContent = value;
        for (const [key, label, min, max] of [
            ["height_cm", heightLabel, minHeight, maxHeight], ["weight_kg", weightLabel, minWeight, maxWeight],
        ]) {
            const fieldLabel = find(`label[for="${key}"]`);
            fieldLabel.firstChild.textContent = label;
            hint(key, `${min} \u2013 ${max}`);
        }

        find("#training-detail").hidden = !answers.training_sessions_per_week;
        const customSteps = answers.daily_steps_option === "Custom amount";
        find("#steps-detail").hidden = !customSteps;
        find("#formula").textContent = "Formula: " + (answers.ob_use_body_fat ? "Katch-McArdle" : "Mifflin-St Jeor");
        find("#formula").className = "ob-pill " + (answers.ob_use_body_fat ? "blue" : "grey");
        if (answers.ob_use_body_fat) measurement("body_fat_pct_input", "Body Fat %", 3, 80);

        const steps = answers.custom_daily_steps_input.trim();
        fields.custom_daily_steps_input.setCustomValidity(/^\d+$/.test(steps) && Number(steps) <= 50000
            ? "" : "Custom daily steps must be a whole number between 0 and 50000.");
        hint("training_sessions_per_week",
            `${answers.training_sessions_per_week} sessions \u00b7 ${answers.training_sessions_per_week * answers.training_duration_minutes} min/wk`);
        showWarning(fields.custom_daily_steps_input, fields.custom_daily_steps_input.validationMessage);
        find(".segments[aria-label='Measurement units']").previousElementSibling.querySelector("span")
            .textContent = `Using ${selectedUnits} System`;
        const customExclusions = answers.other_allergen.split(",").filter(value => value.trim()).length;
        find(".pills[aria-label='Allergens']").previousElementSibling.querySelector("span")
            .textContent = `${answers.allergens.length + customExclusions} excluded`;
        find(".pills[aria-label='Diet Types']").previousElementSibling.querySelector("span")
            .textContent = answers.dietary_preferences.join(", ") || "No restrictions";
        const goal = find(".cards[aria-label='Primary Fitness Goal']").previousElementSibling;
        goal.querySelector("span").textContent = data.goalHints[answers.fitness_goal];
    }

    function showStep(index, focus = false) {
        step = index;
        form.dataset.step = String(step);
        sections.forEach((section, i) => {
            section.hidden = i !== step;
            tabs[i].classList.toggle("active", i === step);
            tabs[i].classList.toggle("done", i < step);
            tabs[i].querySelector(".ob-num").textContent = i < step ? "\u2713" : i + 1;
            if (i === step) tabs[i].setAttribute("aria-current", "step");
            else tabs[i].removeAttribute("aria-current");
        });
        find(".ob-fill").style.width = `${(step + 1) / sections.length * 100}%`;
        const title = tabs[step].querySelector(".ob-tab-name").textContent;
        find("#ob-progress-label").textContent = `Step ${step + 1} of ${sections.length} \u2022 ${title}`;
        find("#ob-progress").value = step + 1;
        back.hidden = step === 0;
        next.textContent = step < sections.length - 1 ? "Next Step \u2192" : "Submit & View Plan \u2192";
        if (focus) {
            sections[step].querySelector("h2").focus();
            window.scrollTo(0, 0);
        }
    }

    function showErrors(messages) {
        errors.replaceChildren(...messages.map(message => {
            const paragraph = document.createElement("p");
            paragraph.textContent = message;
            return paragraph;
        }));
        errors.hidden = messages.length === 0;
    }

    showStep(step);
    update();
    form.dataset.ready = "true";
    if (data.feedback && form.dataset.attempt !== String(data.feedback.attempt)) {
        form.dataset.attempt = String(data.feedback.attempt);
        showStep(data.feedback.step, true);
        showErrors(data.feedback.errors);
    }

    next.disabled = false;
    back.disabled = false;
    form.oninput = update;
    // Some browser controls commit changes without dispatching an input event.
    form.onchange = update;
    form.onfocusout = (event) => {
        const input = event.target;
        if (["height_cm", "weight_kg", "body_fat_pct_input"].includes(input.name)
            && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(input.value.trim())
            && Number.isFinite(Number(input.value))) {
            input.value = truncate(Number(input.value));
            update();
        }
    };
    back.onclick = () => {
        showErrors([]);
        showStep(step - 1, true);
    };
    form.onsubmit = (event) => {
        event.preventDefault();
        update();
        const invalid = [...sections[step].querySelectorAll("input, select")]
            .filter(input => input.getClientRects().length > 0 && !input.validity.valid);
        showErrors(invalid.map(input => input.validationMessage));
        if (invalid.length) {
            invalid[0].focus();
        } else if (step < sections.length - 1) {
            showStep(step + 1, true);
        } else {
            next.disabled = true;
            back.disabled = true;
            setTriggerValue("submit", readAnswers());
        }
    };
}
