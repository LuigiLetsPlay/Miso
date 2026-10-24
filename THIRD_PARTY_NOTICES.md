# Third-party notices

Miso's release builds bundle the following libraries. Each is used under its own
license, which is unaffected by Miso's proprietary license.

| Component | License | Source |
| --- | --- | --- |
| Qt for Python (PySide6) and Qt 6 | LGPL-3.0 | https://www.qt.io/qt-for-python |
| Python runtime | PSF License | https://www.python.org |
| Pillow | MIT-CMU (HPND) | https://python-pillow.org |
| cryptography | Apache-2.0 or BSD-3-Clause | https://github.com/pyca/cryptography |
| websockets | BSD-3-Clause | https://github.com/python-websockets/websockets |
| PyInstaller bootloader | GPL-2.0 with bootloader exception | https://pyinstaller.org |

## LGPL (Qt / PySide6)

The Qt and PySide6 libraries are shipped as separate, unmodified DLL/PYD files in
the `_internal` folder of the installation. You may replace them with your own
compatible builds. The full license text is available at
https://www.gnu.org/licenses/lgpl-3.0.html and the corresponding source code at
https://code.qt.io.
