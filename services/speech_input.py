from pathlib import Path

import streamlit.components.v1 as components


_component = components.declare_component(
    "sustain_browser_speech_input",
    path=str(Path(__file__).resolve().parents[1] / "components" / "speech_input"),
)


def speech_input(key):
    return _component(key=key, default=None)
