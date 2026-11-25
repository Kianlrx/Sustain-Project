export default function ({ parentElement, data, setTriggerValue }) {
    const form = parentElement.querySelector("form");
    const input = form.querySelector("input");
    const list = form.querySelector("ul");
    input.maxLength = data.maxLength;

    const words = (text) => text.toLowerCase().match(/[\p{L}\p{N}]+/gu) || [];
    const foods = data.foods.map((food) => ({ ...food, words: words(food.name) }));
    let active = -1;

    function highlight(index) {
        active = index;
        for (const [position, option] of Array.from(list.children).entries()) {
            option.setAttribute("aria-selected", String(position === active));
        }
        if (active < 0) input.removeAttribute("aria-activedescendant");
        else input.setAttribute("aria-activedescendant", list.children[active].id);
    }

    function close() {
        list.replaceChildren();
        list.hidden = true;
        input.setAttribute("aria-expanded", "false");
        highlight(-1);
    }

    function indicate(food) {
        close();
        input.value = food.name;
        setTriggerValue("select", food.id);
    }

    function suggest() {
        close();
        const terms = words(input.value);
        if (terms.join("").length < 2) return;

        const shown = new Set();
        for (const food of foods) {
            if (!terms.every((term) => food.words.some((word) => word.startsWith(term)))) continue;
            const name = food.words.join(" ");
            if (shown.has(name)) continue;
            shown.add(name);

            const option = document.createElement("li");
            option.id = `food-suggestion-${list.children.length}`;
            option.setAttribute("role", "option");
            option.setAttribute("aria-selected", "false");
            option.textContent = food.name;
            const source = document.createElement("small");
            source.textContent = food.source;
            option.append(source);
            option.onmousedown = (event) => event.preventDefault();
            option.onclick = () => indicate(food);
            list.append(option);
            if (list.children.length === 8) break;
        }
        list.hidden = list.children.length === 0;
        input.setAttribute("aria-expanded", String(!list.hidden));
    }

    input.oninput = suggest;
    input.onfocus = suggest;
    form.onfocusout = (event) => {
        if (!form.contains(event.relatedTarget)) close();
    };
    input.onkeydown = (event) => {
        if (event.isComposing) return;
        if (event.key === "Escape" && !list.hidden) {
            event.preventDefault();
            event.stopPropagation();
            close();
        }
        if (event.key === "Enter" && active >= 0) {
            event.preventDefault();
            list.children[active].click();
        }
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            if (list.hidden) suggest();
            const count = list.children.length;
            if (!count) return;
            event.preventDefault();
            const next = event.key === "ArrowDown" ? active + 1 : active < 0 ? count - 1 : active - 1;
            highlight((next + count) % count);
        }
    };
    form.onsubmit = (event) => {
        event.preventDefault();
        close();
        setTriggerValue("search", input.value);
    };
}
