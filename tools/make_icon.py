"""Convert assets/icon.png into assets/icon.ico (used for the .exe)."""
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "assets"

im = Image.open(ASSETS / "icon.png").convert("RGBA")
side = max(im.size)
square = Image.new("RGBA", (side, side))
square.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
square.save(ASSETS / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])

# small images for the installer wizard (100 % and 200 % DPI), icon on white
for name, size in (("setup-small.bmp", 55), ("setup-small-200.bmp", 110)):
    bg = Image.new("RGB", (size, size), "white")
    icon = square.resize((size, size), Image.Resampling.LANCZOS)
    bg.paste(icon, (0, 0), icon)
    bg.save(ASSETS / name)
print("ok")
