import base64
from functools import lru_cache
from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "sustain_logo_svg.svg"


@lru_cache(maxsize=1)
def logo_data_uri():
    svg = LOGO_PATH.read_bytes()
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode()
