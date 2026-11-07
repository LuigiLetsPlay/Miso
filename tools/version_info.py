"""Write build/version_info.txt (Windows version resource for Miso.exe) from miso.__version__."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from miso import __version__  # noqa: E402

nums = [int(n) for n in __version__.split(".")[:4]]
nums += [0] * (4 - len(nums))
ver = tuple(nums)

TEMPLATE = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={ver}, prodvers={ver}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', 'LuigiLetsPlay'),
      StringStruct('FileDescription', 'Miso - GIF and image overlays for the desktop'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'Miso'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 LuigiLetsPlay. All rights reserved.'),
      StringStruct('OriginalFilename', 'Miso.exe'),
      StringStruct('ProductName', 'Miso'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('Comments', 'https://github.com/LuigiLetsPlay/Miso')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""

out = ROOT / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(TEMPLATE, "utf-8")
print(out)
