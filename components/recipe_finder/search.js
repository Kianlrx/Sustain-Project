export default function ({ parentElement, data, setTriggerValue }) {
    const form = parentElement.querySelector("form");
    const prompt = form.elements.craving;
    const mic = form.querySelector(".mic");
    const status = form.querySelector(".voice-status");
    const rows = [...form.querySelectorAll(".slot")];
    prompt.maxLength = data.maxLength;
    let split = form.dataset.split ? JSON.parse(form.dataset.split) : { ...data.split };
    if (!form.dataset.split) {
        prompt.value = data.craving;
        form.elements.meal.value = data.slot;
    }

    function render() {
        form.dataset.split = JSON.stringify(split);
        for (const row of rows) {
            const share = split[row.dataset.slot];
            row.querySelector(".share").textContent = share + "%";
            row.querySelector(".budget").textContent =
                Math.round(data.calories * share / 100).toLocaleString("en-US") + " kcal";
        }
        const total = Object.values(split).reduce((sum, share) => sum + share, 0);
        const warning = form.querySelector(".total");
        warning.hidden = total === 100;
        warning.textContent = `Your meals add up to ${total}% of the day, not 100%.`;
    }
    render();
    for (const row of rows) {
        for (const button of row.querySelectorAll("button")) {
            button.onclick = () => {
                const slot = row.dataset.slot;
                split[slot] = Math.min(100, Math.max(0, split[slot] + Number(button.dataset.change)));
                render();
            };
        }
    }

    mic.onclick = () => {
        const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!Recognition) {
            status.textContent = "Speech recognition is not supported by this browser.";
            return;
        }
        const recognition = new Recognition();
        recognition.lang = navigator.language || "en-US";
        mic.disabled = true;
        status.textContent = "Listening\u2026";
        recognition.onresult = (event) => {
            prompt.value = event.results[0][0].transcript.trim().slice(0, data.maxLength);
        };
        recognition.onerror = (event) => {
            status.textContent = event.error === "not-allowed"
                ? "Allow microphone access to use voice input."
                : "Voice input could not be completed. Please try again.";
        };
        recognition.onend = () => {
            mic.disabled = false;
            if (status.textContent === "Listening\u2026") status.textContent = "";
        };
        try {
            recognition.start();
        } catch {
            mic.disabled = false;
            status.textContent = "Voice input could not be started. Please try again.";
        }
    };
    form.onsubmit = (event) => {
        event.preventDefault();
        setTriggerValue("search", { craving: prompt.value, slot: form.elements.meal.value, split });
    };
}
