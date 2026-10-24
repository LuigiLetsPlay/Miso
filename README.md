<p align="center">
  <img src="assets/icon.png" width="128" alt="Miso">
</p>

<h1 align="center">Miso</h1>

<p align="center">
  GIFs, APNGs, WebPs und Bilder als Overlay auf deinen Desktop legen, mit eingebautem
  Steam Workshop für AnimaEngine.
</p>

<p align="center">
  <a href="https://github.com/LuigiLetsPlay/miso/releases/latest"><b>⬇ Download (Windows)</b></a>
</p>

---

## Installation

1. Lade **`Miso-Setup.exe`** aus dem [neuesten Release](https://github.com/LuigiLetsPlay/miso/releases/latest) herunter.
2. Ausführen. Admin-Rechte sind nicht nötig. Optional wird ein Desktop-Icon angelegt.
3. Fertig. Miso findest du im Startmenü.

Keine Lust auf Installation? Im Release gibt es auch **`Miso-portable.zip`**: entpacken und
`Miso.exe` starten.

> Windows SmartScreen kann beim ersten Start warnen, weil das Programm nicht signiert ist.
> „Weitere Informationen“ → „Trotzdem ausführen“.

## Features

- **Overlays**: Transparent, immer im Vordergrund, animiert. Ziehen, an den Ecken skalieren,
  Mausrad zum Zoomen, Rechtsklick für Deckkraft, Tempo und Spiegeln.
- **Fixieren**: Mit `Strg + Alt + E` werden Overlays durchklickbar und stören nicht mehr.
- **Steam Workshop**: AnimaEngine-Workshop durchsuchen und mit einem Klick herunterladen.
  Kein Steam und kein SteamCMD nötig.
- **Eigene Bilder**: Hochladen, Dateien reinziehen, Bilder direkt aus dem Browser ziehen oder
  `Strg + V`.
- **Bibliothek**: Favoriten, Suche, Filter und Sortierung nach zuletzt benutzt.
- **NSFW ausblenden**: Blendet Inhalte mit 18+, NSFW usw. im Titel überall aus, ohne etwas
  zu löschen.
- **Speicher**: Übersicht über den Platzverbrauch, Cache leeren und ungenutzte Elemente
  automatisch nach X Tagen löschen. Vor jedem Löschen wird nachgefragt.
- **Tray**: Miso läuft im Hintergrund weiter, solange Overlays auf dem Bildschirm sind.
  Das Verhalten ist einstellbar.
- Overlays bleiben nach einem Neustart erhalten, optional mit Windows-Autostart.

## Tastenkürzel

| Kürzel | Aktion |
| --- | --- |
| `Strg + Alt + E` | Bearbeiten-Modus an/aus (fixiert = durchklickbar) |
| `Strg + Alt + H` | Alle Overlays aus-/einblenden |
| `Strg + V` | Bild, GIF oder Bild-Link in die Bibliothek einfügen |

## Wie der Workshop-Download funktioniert

Miso macht dasselbe wie `steamcmd +login anonymous +workshop_download_item`, nur selbst
(`miso/steam/`):

1. Anonymer Login bei einem Steam-Server über WebSocket (Protobuf)
2. Depot-Schlüssel und Manifest-Code für das Item anfordern
3. Manifest und Datenblöcke vom Steam-CDN laden, mit AES entschlüsseln, mit LZMA/Zstd entpacken
   und zusammensetzen

## Daten

| Was | Wo |
| --- | --- |
| Einstellungen & Bibliothek | `%APPDATA%\Miso` |
| Workshop-Downloads | `%LOCALAPPDATA%\Miso\workshop` |
| Eigene Bilder | `%LOCALAPPDATA%\Miso\uploads` |

Beim Deinstallieren fragt Miso, ob diese Daten mitgelöscht werden sollen.

## Lizenz

Copyright © 2026 LuigiLetsPlay. Alle Rechte vorbehalten.
Miso darf aus den offiziellen Releases kostenlos privat genutzt werden. Kopieren, Verändern
oder Weitergeben des Programms oder des Quellcodes ist nicht erlaubt. Details in
[LICENSE](LICENSE). Mitgelieferte Bibliotheken: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Miso steht in keiner Verbindung zu Valve, Steam oder AnimaEngine. Workshop-Inhalte gehören
ihren jeweiligen Erstellern.
