from pathlib import Path

import streamlit.components.v1 as components


_activity_selector = components.declare_component(
    "activity_selector",
    path=str(Path(__file__).parent / "activity_selector"),
)


def hint_selectbox(
    label: str,
    options: list[str],
    descriptions: dict[str, str],
    value: str,
    key: str,
) -> str:
    return _activity_selector(
        label=label,
        options=options,
        descriptions=descriptions,
        value=value,
        default=value,
        key=key,
        default_value=value,
        height=70,
    )
