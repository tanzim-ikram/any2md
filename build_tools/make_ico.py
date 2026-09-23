"""Generate multi-resolution Any2MD Logo.ico from Any2MD Logo.png."""

from pathlib import Path
from PIL import Image

ROOT_DIR = Path(__file__).resolve().parent.parent
PNG_PATH = ROOT_DIR / "Any2MD Logo.png"
ICO_PATH = ROOT_DIR / "Any2MD Logo.ico"


def generate_ico() -> Path:
    if not PNG_PATH.exists():
        raise FileNotFoundError(f"Source logo not found at {PNG_PATH}")

    img = Image.open(PNG_PATH)
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Standard Windows icon sizes (16 to 256 px)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICO_PATH, format="ICO", sizes=sizes)
    print(f"Generated multi-resolution ICO at: {ICO_PATH} ({ICO_PATH.stat().st_size} bytes)")
    return ICO_PATH


if __name__ == "__main__":
    generate_ico()
