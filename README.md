<p align="center">
  <img src="assets/icon.png" width="128" alt="Miso">
</p>

<h1 align="center">Miso</h1>

<p align="center">
  Put animated GIFs, APNGs, WebPs and images on your Windows desktop as overlays,
  with a built-in Steam Workshop browser.
</p>

<p align="center">
  <a href="https://github.com/LuigiLetsPlay/Miso/releases/latest"><b>⬇ Download for Windows</b></a>
</p>

---

## Installation

1. Download **`Miso-Setup.exe`** from the [latest release](https://github.com/LuigiLetsPlay/Miso/releases/latest).
2. Run it. No admin rights needed. A desktop shortcut is optional.
3. Done. Miso is in your Start menu.

Prefer no installer? Every release also has **`Miso-portable.zip`**: unzip it and run `Miso.exe`.

> Windows SmartScreen may warn you because Miso isn't code-signed.
> Click "More info" → "Run anyway".

The app itself is currently in German.

## Features

- **Overlays**: transparent, always on top, animated. Drag them, resize from the corners, zoom
  with the mouse wheel, right-click for opacity, speed and mirroring.
- **Lock mode**: `Ctrl + Alt + E` makes overlays click-through so they never get in your way.
- **Profiles**: different overlay layouts (e.g. Gaming, Work, Stream). Switch with
  `Ctrl + Alt + ← / →` from anywhere.
- **Steam Workshop**: browse the AnimaEngine workshop and download with one click. No Steam
  client or SteamCMD required.
- **Your own images**: upload files, drag images straight from your browser, or paste with
  `Ctrl + V`.
- **Library**: favourites, search, filters, sorting by last used.
- **Hide NSFW** (on by default): hides anything with 18+, NSFW etc. in the title everywhere,
  without deleting it.
- **Storage**: see what uses space, clear the cache, and auto-delete items you haven't used for
  X days. Miso always asks before deleting anything.
- **Tray**: Miso keeps running in the tray while overlays are on screen (configurable).
- **Auto-update**: Miso checks GitHub for new releases, verifies the download and updates itself
  (asks first, or fully automatic if you like).
- **Custom shortcuts**: change every global hotkey in the settings.
- Smooth animations throughout (can be turned off; respects Windows' animation setting).
- Overlays survive restarts, with optional autostart.

## Shortcuts

Defaults; all global shortcuts can be changed in the settings.

| Shortcut | Action |
| --- | --- |
| `Ctrl + Alt + E` | Toggle edit mode (locked = click-through) |
| `Ctrl + Alt + H` | Hide / show all overlays |
| `Ctrl + Alt + ← / →` | Previous / next profile |
| `Ctrl + V` | Paste an image, GIF or image link into the library |

## How the Workshop download works

Miso does what `steamcmd +login anonymous +workshop_download_item` does, natively
(`miso/steam/`):

1. Anonymous login to a Steam connection manager over WebSocket (protobuf)
2. Request the depot key and manifest request code for the item
3. Fetch the manifest and chunks from the Steam CDN, AES-decrypt, LZMA/Zstd-decompress and
   reassemble the files

## Data

| What | Where |
| --- | --- |
| Settings, library, profiles | `%APPDATA%\Miso` |
| Workshop downloads | `%LOCALAPPDATA%\Miso\workshop` |
| Your uploads | `%LOCALAPPDATA%\Miso\uploads` |

The uninstaller asks whether this data should be removed as well.

## License

Copyright © 2026 LuigiLetsPlay. All rights reserved.
You may use the official releases free of charge for personal use. Copying, modifying or
redistributing the program or its source code is not permitted. See [LICENSE](LICENSE).
Bundled libraries: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Miso is not affiliated with or endorsed by Valve, Steam or AnimaEngine. Workshop content
belongs to its respective creators.
