"""English translations, keyed by the German source text.

Placeholders are named {a0}, {a1}, … in the order they appear in the German text. A
translation may leave some out: German plural endings ("Bild{a1}" -> "Bilder") are passed
as separate values and English simply phrases those sentences without them.
"""
EN: dict[str, str] = {
    # --- navigation / pages ----------------------------------------------------------
    "Entdecken": "Discover",
    "Bibliothek": "Library",
    "Overlays": "Overlays",
    "Einstellungen": "Settings",
    "Auf dem Bildschirm": "On screen",
    "Miso so, wie du es willst": "Make Miso yours",

    # --- workshop ----------------------------------------------------------------------
    "Workshop durchsuchen …": "Search the workshop …",
    "Im Trend": "Trending",
    "Beliebt": "Popular",
    "Neu": "New",
    "Top bewertet": "Top rated",
    "Neu laden": "Reload",
    "Erneut versuchen": "Try again",
    "Lädt mehr …": "Loading more …",
    "Keine Treffer.": "No results.",
    "Das war alles": "That's everything",
    "Workshop konnte nicht geladen werden.\n{a0}": "Couldn't load the workshop.\n{a0}",
    "{a0} Abos  ·  {a1}": "{a0} subscribers  ·  {a1}",
    "Herunterladen": "Download",
    "Platzieren": "Place",
    "In Bibliothek": "In library",
    "Download abbrechen": "Cancel download",
    "Aus Bibliothek löschen": "Delete from library",
    "Auf dem Bildschirm platzieren": "Place on screen",
    "Wird heruntergeladen": "Downloading",
    "„{a0}“ heruntergeladen. Klick drauf zum Platzieren": "“{a0}” downloaded. Click it to place it",
    "Keine Workshop-Daten gefunden": "No workshop data found",
    "Item enthält kein Bild/GIF": "This item contains no image or GIF",
    "Item enthält keine Bilder": "This item contains no images",
    "Abgebrochen": "Cancelled",

    # --- steam download ----------------------------------------------------------------
    "Verbinde mit Steam ({a0}) …": "Connecting to Steam ({a0}) …",
    "Anonym bei Steam angemeldet": "Signed in to Steam anonymously",
    "Keine Steam-Server gefunden": "No Steam servers found",
    "Von Steam abgemeldet (EResult {a0})": "Logged off by Steam (EResult {a0})",
    "Steam antwortet nicht (Timeout)": "Steam isn't responding (timeout)",
    "Kein Zugriff auf Depot {a0} (EResult {a1})": "No access to depot {a0} (EResult {a1})",
    "Lade Manifest …": "Loading manifest …",
    "Manifest ist beschädigt": "The manifest is damaged",
    "Manifest konnte nicht geladen werden": "Couldn't load the manifest",
    "{a0} Datei(en), {a1:.1f} MB": "{a0} file(s), {a1:.1f} MB",
    "{a0} Datei(en) übersprungen (kein Bild)": "Skipped {a0} file(s) (not an image)",
    "Unbekanntes Chunk-Format": "Unknown chunk format",
    "Zstd-Chunk benötigt Python 3.14+": "Zstd chunks need Python 3.14+",
    "Chunk hat falsche Größe": "Chunk has the wrong size",
    "Chunk-Prüfsumme stimmt nicht": "Chunk checksum mismatch",
    "Chunk-Download fehlgeschlagen: {a0}": "Chunk download failed: {a0}",

    # --- library -----------------------------------------------------------------------
    "  Hochladen": "  Upload",
    "Eigene Bilder hochladen": "Upload your own images",
    "Klicken, Dateien reinziehen, Bilder direkt aus dem Browser ziehen oder Strg + V  ·  GIF, PNG, APNG, WebP, JPG":
        "Click, drop files, drag images straight from your browser or press Ctrl + V  ·  GIF, PNG, APNG, WebP, JPG",
    "Bibliothek durchsuchen …": "Search the library …",
    "Alle": "All",
    "Favoriten": "Favourites",
    "Eigene": "Own",
    "Zuletzt benutzt": "Last used",
    "Neu hinzugefügt": "Recently added",
    "Größe": "Size",
    "Sortieren: {a0}  ▾": "Sort: {a0}  ▾",
    "Noch leer hier": "Nothing here yet",
    "Lade etwas im Workshop herunter oder lade eigene Bilder hoch.":
        "Download something from the workshop or upload your own images.",
    "Keine Treffer für diesen Filter.": "Nothing matches this filter.",
    "Element": "item",
    "Elemente": "items",
    "Eigenes": "Own",
    "Verknüpft": "Linked",
    "Pack · {a0} Bilder": "Pack · {a0} images",
    "Pack öffnen …": "Open pack …",
    "Im Pack suchen …": "Search this pack …",
    "{a0} Bilder  ·  Klicken zum Platzieren, mehrere nacheinander möglich":
        "{a0} images  ·  click to place, as many as you like",
    "Fertig": "Done",
    "Favorisieren": "Add to favourites",
    "Aus Favoriten entfernen": "Remove from favourites",
    "Umbenennen …": "Rename …",
    "Bild umbenennen": "Rename image",
    "Löschen …": "Delete …",
    "Bilder oder GIFs hochladen": "Upload images or GIFs",
    "Bilder (*.gif *.png *.apng *.webp *.jpg *.jpeg *.bmp)": "Images (*.gif *.png *.apng *.webp *.jpg *.jpeg *.bmp)",
    "gerade eben": "just now",
    "vor {a0} Min.": "{a0} min ago",
    "vor {a0} Std.": "{a0} h ago",
    "vor {a0} Tagen": "{a0} days ago",

    # --- uploads / import --------------------------------------------------------------
    "Loslassen zum Hinzufügen": "Drop to add",
    "Dateien, oder Bilder und GIFs direkt aus dem Browser": "Files, or images and GIFs straight from your browser",
    "Da war kein Bild dabei": "There was no image in there",
    "{a0} Bild{a1} wird hinzugefügt …": "Adding {a0} image(s) …",
    "{a0} Bild{a1} wird hochgeladen …": "Uploading {a0} image(s) …",
    "{a0} Bild{a1} in der Bibliothek": "{a0} image(s) added to the library",
    "Hinzufügen fehlgeschlagen: {a0}": "Couldn't add: {a0}",
    "Eingefügtes Bild": "Pasted image",
    "Bild aus dem Web": "Image from the web",
    "Das ist kein unterstütztes Bild": "That's not a supported image",
    "Format {a0} wird nicht unterstützt": "Format {a0} isn't supported",
    "„{a0}“ wird nicht unterstützt": "“{a0}” isn't supported",
    "Bild aus der Zwischenablage konnte nicht gespeichert werden": "Couldn't save the image from the clipboard",
    "Datei ist größer als 200 MB": "File is larger than 200 MB",

    # --- deleting ----------------------------------------------------------------------
    "Löschen": "Delete",
    "Abbrechen": "Cancel",
    "Diesmal nicht": "Not this time",
    "„{a0}“ löschen?": "Delete “{a0}”?",
    "„{a0}“ gelöscht": "“{a0}” deleted",
    " · {a0} frei": " · {a0} freed",
    "Die Datei wird von deinem PC gelöscht.": "The file will be deleted from your PC.",
    "Der Eintrag verschwindet aus der Bibliothek, die Originaldatei bleibt.":
        "The entry is removed from the library; the original file stays.",
    " Es wird auch vom Bildschirm entfernt.": " It will also be removed from the screen.",
    "Nichts zu löschen. Alles wird gerade benutzt oder ist favorisiert.":
        "Nothing to delete. Everything is in use or a favourite.",
    "{a0} ungenutzte{a1} Element{a2} löschen?": "Delete {a0} unused item(s)?",
    "{a0}.\n\nDiese Elemente sind {a1} und nicht favorisiert. Das gibt {a2} frei. Favoriten werden nie gelöscht.":
        "{a0}.\n\nThese items are {a1} and not favourites. This frees {a2}. Favourites are never deleted.",
    " und {a0} weitere": " and {a0} more",
    "seit {a0} Tagen nicht benutzt": "unused for {a0} days",
    "gerade nicht auf dem Bildschirm": "not on screen right now",
    "{a0} gelöscht · {a1} frei": "{a0} deleted · {a1} freed",

    # --- overlays page / overlay windows -----------------------------------------------
    "Alle ausblenden": "Hide all",
    "Alle einblenden": "Show all",
    "Alle entfernen": "Remove all",
    "Alle {a0} Overlays entfernen?": "Remove all {a0} overlays?",
    "Sie verschwinden vom Bildschirm. Die Bilder bleiben in deiner Bibliothek.":
        "They disappear from the screen. The images stay in your library.",
    "Wähle etwas aus deiner Bibliothek oder dem Workshop, um es auf den Bildschirm zu legen.":
        "Pick something from your library or the workshop to put it on screen.",
    "{a0} aktive{a1} Overlay{a2}  ·  Profil „{a3}“": "{a0} active overlay{a2}  ·  profile “{a3}”",
    '<span style="color:{a0}">Im {a1}Bearbeiten-Modus</b> kannst du Overlays ziehen, an den Ecken skalieren oder '
    'mit dem {a2}Mausrad</b> zoomen. Rechtsklick öffnet mehr Optionen. Danach mit {a3}{a4}</b> fixieren: Dann '
    'lassen sich die Overlays durchklicken.</span>':
        '<span style="color:{a0}">In {a1}edit mode</b> you can drag overlays, resize them from the corners or zoom '
        'with the {a2}mouse wheel</b>. Right-click for more options. Then press {a3}{a4}</b> to lock them: locked '
        'overlays are click-through.</span>',
    "Deckkraft": "Opacity",
    "Geschwindigkeit": "Speed",
    "Horizontal spiegeln": "Mirror horizontally",
    "Originalgröße": "Original size",
    "Bildschirm-Mitte": "Centre of screen",
    "In die Bildschirmmitte": "Move to the centre of the screen",
    "Fertig (Overlay fixieren)": "Done (lock overlays)",
    "Entfernen": "Remove",
    "Ein-/Ausblenden": "Show / hide",
    "Kann nicht geladen werden\n{a0}": "Can't be loaded\n{a0}",
    "Lädt …": "Loading …",
    "Ziehen zum Verschieben, Mausrad zum Skalieren. {a0} fixiert die Overlays.":
        "Drag to move, mouse wheel to resize. {a0} locks the overlays.",

    # --- profiles ----------------------------------------------------------------------
    "Profil": "Profile",
    "Neues Profil": "New profile",
    "Anlegen": "Create",
    "Ein neues, leeres Profil. Die Bibliothek teilen sich alle Profile.":
        "A new, empty profile. All profiles share the same library.",
    "Profil verwalten": "Manage profile",
    "Profile verwalten": "Manage profiles",
    "Aktivieren": "Activate",
    "Duplizieren": "Duplicate",
    "Profil umbenennen": "Rename profile",
    "Profil löschen": "Delete profile",
    "Profil „{a0}“ löschen?": "Delete profile “{a0}”?",
    "Die Anordnung mit {a0} Overlay{a1} geht verloren. Die Bilder selbst bleiben in deiner Bibliothek.":
        "Its layout with {a0} overlay{a1} will be lost. The images stay in your library.",
    "{a0} Kopie": "{a0} copy",
    "{a0} Overlay{a1}  ·  Rechtsklick für Optionen": "{a0} overlay{a1}  ·  right-click for options",
    "{a0}  /  {a1} zum Wechseln": "{a0}  /  {a1} to switch",
    "Vorheriges Profil": "Previous profile",
    "Nächstes Profil": "Next profile",
    "Vorheriges Profil ({a0})": "Previous profile ({a0})",
    "Nächstes Profil ({a0})": "Next profile ({a0})",
    "Profil {a0} von {a1}": "Profile {a0} of {a1}",
    "Profil {a0} von {a1}  ·  {a2} Overlay{a3}": "Profile {a0} of {a1}  ·  {a2} overlay{a3}",

    # --- sidebar / tray / main window --------------------------------------------------
    "Bearbeiten": "Editing",
    "Fixiert": "Locked",
    "Overlays ziehen & skalieren\n{a0} zum Fixieren": "Drag & resize overlays\n{a0} to lock",
    "Overlays sind durchklickbar\n{a0} zum Bearbeiten": "Overlays are click-through\n{a0} to edit",
    "Miso öffnen": "Open Miso",
    "Bearbeiten-Modus": "Edit mode",
    "Overlays ausblenden": "Hide overlays",
    "Beenden": "Quit",
    "Deine Overlays bleiben auf dem Bildschirm.": "Your overlays stay on screen.",
    "Miso läuft im Hintergrund weiter.": "Miso keeps running in the background.",
    "{a0} Rechtsklick aufs Tray-Icon für Optionen.": "{a0} Right-click the tray icon for options.",

    # --- dialogs -----------------------------------------------------------------------
    "Speichern": "Save",
    "Wird vorbereitet …": "Preparing …",
    "{a0} von {a1}": "{a0} of {a1}",

    # --- settings ----------------------------------------------------------------------
    "Inhalt": "Content",
    "NSFW ausblenden": "Hide NSFW",
    "Blendet alles mit 18+, NSFW, hentai usw. im Titel aus: im Workshop, in der Bibliothek und auf dem Bildschirm. "
    "Gelöscht wird dabei nichts.":
        "Hides everything with 18+, NSFW, hentai etc. in the title: in the workshop, the library and on screen. "
        "Nothing gets deleted.",
    "Speicher": "Storage",
    "{a0} belegt": "{a0} used",
    "Cache leeren": "Clear cache",
    "Ordner öffnen": "Open folder",
    "Eigene Bilder": "Your images",
    "Cache": "Cache",
    "Cache leeren?": "Clear the cache?",
    "Löscht zwischengespeicherte Vorschaubilder ({a0}). Deine Bibliothek bleibt unberührt, Vorschauen werden bei "
    "Bedarf neu geladen.":
        "Deletes cached thumbnails ({a0}). Your library isn't touched; thumbnails are reloaded when needed.",
    "Cache geleert · {a0} frei": "Cache cleared · {a0} freed",
    "Ungenutztes automatisch löschen": "Delete unused items automatically",
    "Elemente, die so lange nicht auf dem Bildschirm waren, werden gelöscht. Favoriten und Overlays, die gerade "
    "laufen, bleiben immer. Du wirst vorher gefragt.":
        "Items that haven't been on screen for this long are deleted. Favourites and overlays that are showing "
        "always stay. Miso asks you first.",
    "Nie": "Never",
    "Nach 7 Tagen": "After 7 days",
    "Nach 14 Tagen": "After 14 days",
    "Nach 30 Tagen": "After 30 days",
    "Nach 60 Tagen": "After 60 days",
    "Nach 90 Tagen": "After 90 days",
    "Automatisch löschen nach {a0} Tagen?": "Delete automatically after {a0} days?",
    "Elemente, die {a0} Tage nicht auf dem Bildschirm waren, werden gelöscht. Favoriten und aktive Overlays "
    "bleiben immer. Vor jedem Löschen fragt Miso dich noch einmal.":
        "Items that haven't been on screen for {a0} days get deleted. Favourites and active overlays always stay. "
        "Miso asks you again before every deletion.",
    "Alle ungenutzten löschen": "Delete all unused",
    "Löscht alles aus der Bibliothek, was gerade nicht auf dem Bildschirm ist und kein Favorit ist.":
        "Deletes everything from the library that isn't on screen and isn't a favourite.",
    "Jetzt aufräumen …": "Clean up now …",
    "Allgemein": "General",
    "Beim Schließen des Fensters": "When closing the window",
    "Automatisch: Solange Overlays auf dem Bildschirm sind, läuft Miso im Infobereich (Tray) weiter. Ohne "
    "Overlays wird Miso einfach beendet.":
        "Automatic: while overlays are on screen, Miso keeps running in the system tray. Without overlays it "
        "simply quits.",
    "Automatisch": "Automatic",
    "Immer in den Tray": "Always to tray",
    "Immer beenden": "Always quit",
    "Animationen": "Animations",
    "Weiche Übergänge, Einblendungen und Bewegungen. Sind Animationen in Windows ausgeschaltet, bleibt Miso "
    "ebenfalls ruhig.":
        "Smooth transitions, fades and motion. If animations are turned off in Windows, Miso stays still too.",
    "Mit Windows starten": "Start with Windows",
    "Overlays sind direkt nach dem Hochfahren wieder da.": "Your overlays are back right after booting.",
    "Unsichtbar starten": "Start hidden",
    "Beim Start nur die Overlays zeigen, nicht dieses Fenster.": "Only show the overlays on start, not this window.",
    "Updates": "Updates",
    "Nach Updates suchen": "Check for updates",
    "Neue Versionen kommen direkt von GitHub. Das Setup wird vor der Installation auf Vollständigkeit und "
    "Prüfsumme kontrolliert.":
        "New versions come straight from GitHub. The setup is checked for completeness and its checksum before "
        "it's installed.",
    "Automatisch nach Updates suchen": "Check for updates automatically",
    "Beim Start und alle 12 Stunden. Du wirst gefragt, bevor etwas installiert wird.":
        "On start and every 12 hours. You're asked before anything is installed.",
    "Updates ohne Nachfrage installieren": "Install updates without asking",
    "Lädt neue Versionen automatisch und startet Miso danach neu (nur bei installiertem Miso, nicht bei der "
    "portablen Version).":
        "Downloads new versions automatically and restarts Miso afterwards (installed Miso only, not the "
        "portable version).",
    "Tastenkürzel": "Shortcuts",
    "Klick auf ein Kürzel und drück die neue Tastenkombination (mit Strg, Alt, Umschalt oder Win). Esc bricht ab. "
    "Die Kürzel funktionieren überall, auch wenn Miso im Tray ist.":
        "Click a shortcut and press the new key combination (with Ctrl, Alt, Shift or Win). Esc cancels. "
        "Shortcuts work everywhere, even while Miso is in the tray.",
    "Klicken und neue Tastenkombination drücken": "Click and press a new key combination",
    "Auf Standard zurücksetzen": "Reset to default",
    "Tasten drücken …": "Press keys …",
    "Alle aus-/einblenden": "Hide / show all",
    "Overlays verschieben oder fixieren (durchklickbar).": "Move overlays or lock them (click-through).",
    "Blendet alle Overlays schnell aus und wieder ein.": "Quickly hides all overlays and shows them again.",
    "Zum vorherigen Profil springen.": "Jump to the previous profile.",
    "Zum nächsten Profil springen.": "Jump to the next profile.",
    "Bild einfügen": "Paste image",
    "Kopiertes Bild, GIF oder Bild-Link direkt in die Bibliothek (im Miso-Fenster).":
        "Puts a copied image, GIF or image link straight into the library (in the Miso window).",
    "Strg + V": "Ctrl + V",
    "Steam-Verbindung": "Steam connection",
    "Direkt": "Direct",
    "Miso lädt Workshop-Items selbst über das Steam-Netzwerk (anonymer Login, Steam CDN). Kein Steam, kein "
    "SteamCMD nötig.":
        "Miso downloads workshop items itself over the Steam network (anonymous login, Steam CDN). No Steam, "
        "no SteamCMD needed.",

    # --- updates -----------------------------------------------------------------------
    "Suche nach Updates …": "Checking for updates …",
    "Miso ist aktuell (Version {a0})": "Miso is up to date (version {a0})",
    "Update-Suche fehlgeschlagen: {a0}": "Update check failed: {a0}",
    "  Update auf {a0}": "  Update to {a0}",
    "Miso {a0} ist da": "Miso {a0} is here",
    "Du hast Version {a0}.": "You have version {a0}.",
    "Du hast Version {a0}.\n\n{a1}": "You have version {a0}.\n\n{a1}",
    "\n\nDiese Kopie ist nicht installiert (portabel). Die Release-Seite wird im Browser geöffnet.":
        "\n\nThis copy isn't installed (portable). The release page opens in your browser.",
    "Jetzt aktualisieren": "Update now",
    "Später": "Later",
    "Miso {a0} wird heruntergeladen": "Downloading Miso {a0}",
    "Wird installiert, Miso startet gleich neu …": "Installing, Miso restarts in a moment …",
    "Update fehlgeschlagen: {a0}": "Update failed: {a0}",
    "Download unvollständig": "Download incomplete",
    "Prüfsumme stimmt nicht, Update wurde verworfen": "Checksum mismatch, update discarded",
    "Download ist keine Windows-Datei": "The download isn't a Windows program",

    # --- hotkeys -----------------------------------------------------------------------
    "{a0} ist schon für „{a1}“ vergeben": "{a0} is already used for “{a1}”",
    "{a0} wird schon von einem anderen Programm benutzt": "{a0} is already used by another program",
    "Strg": "Ctrl",
    "Umschalt": "Shift",
    "Leertaste": "Space",
    "Pos1": "Home",
    "Ende": "End",
    "Bild ↑": "Page Up",
    "Bild ↓": "Page Down",
    "Einfg": "Insert",
    "Entf": "Delete",

    # --- added in 1.1.2: language, games, packs, sorting --------------------------------
    "Sprache": "Language",
    "Sprache der Oberfläche. Wird nach einem Neustart von Miso übernommen.":
        "Language of the interface. Takes effect after Miso restarts.",
    "Sprache ändern?": "Change language?",
    "Miso startet dafür kurz neu. Deine Overlays bleiben, wo sie sind.":
        "Miso restarts briefly for this. Your overlays stay where they are.",
    "Neu starten": "Restart",
    "Spiele": "Games",
    "Vollbild-Spiele": "Fullscreen games",
    "Overlays bleiben über Spielen im Modus „Vollbild (Fenster)“ bzw. „Rahmenlos“. Wechselt ein Spiel die "
    "Auflösung, bleiben sie an derselben Stelle. Bei exklusivem Vollbild kann Windows keine fremden Fenster "
    "darüber zeigen; Miso greift absichtlich nicht ins Spiel ein (kein Anti-Cheat-Risiko).":
        "Overlays stay on top of games in “fullscreen windowed” / “borderless” mode. If a game changes the "
        "resolution, they keep their spot. In exclusive fullscreen Windows can't show other windows on top; "
        "Miso deliberately never hooks into games (no anti-cheat risk).",
    "Gut": "Good",
    "Ziehen zum Sortieren": "Drag to reorder",
    "{a0} NSFW ausgeblendet": "{a0} NSFW hidden",
    "ausgeblendet": "hidden",
    "Im Steam Workshop ansehen": "View in the Steam Workshop",
    "Im Explorer zeigen": "Show in Explorer",
    "Download fehlgeschlagen: {a0}": "Download failed: {a0}",
    "Nichts platziert": "Nothing placed",
    "Standard": "Default",
    "Workshop-Seite hat ein unbekanntes Format": "The workshop page has an unknown format",
    "Verbindung zu Steam fehlgeschlagen: {a0}": "Couldn't connect to Steam: {a0}",
    "Anonymer Login fehlgeschlagen (EResult {a0})": "Anonymous login failed (EResult {a0})",
    "Aktiv": "Active",
    "„{a0}“ platziert": "“{a0}” placed",
    "{a0} fehlgeschlagen (EResult {a1})": "{a0} failed (EResult {a1})",
}
