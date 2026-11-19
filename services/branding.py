import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image

LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "sustain_logo.png"


@lru_cache(maxsize=1)
def logo_data_uri():
    # The source PNG is ~650KB; embed a 64px copy (2x for a sharp 32px logo).
    with Image.open(LOGO_PATH) as image:
        image = image.convert("RGBA")
        image.thumbnail((64, 64), Image.LANCZOS)
        buffer = BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
