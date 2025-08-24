# Implementation Plan

[Overview]
wbridge wird plattformübergreifend (Linux, macOS, Windows 11) mit einer klaren OS‑Adapter‑Architektur erweitert, behält die GTK4‑GUI bei und ergänzt monetarisierbare OS‑Module inklusive Store‑fähiger Distributionspfade.

Ziel ist: a) GUI: weiterhin ein gemeinsamer GTK4‑Codepfad, OS‑spezifische Integrationsschichten (Shortcuts, Autostart, Pfade) über Plugins, b) Selektion/Protokollierung: einheitliche History/Logging‑Schnittstellen mit OS‑spezifischen Selection‑Providern (Primary nur unter Linux), c) CLI/Shortcuts: die CLI bleibt, der Shortcut‑Empfang wird je OS systemkonform gelöst (GNOME Custom Shortcuts, macOS Shortcuts.app/Companion, Windows .lnk‑Hotkeys/Helper). Für macOS/Windows werden optionale, kostenpflichtige Module bereitgestellt, die Installation/Kauf so reibungslos wie möglich machen (Store‑Flows optimiert). Linux bleibt unverändert stabil.

[Types]  
Die Kern‑Typen werden um OS‑Adapter‑Protokolle erweitert; Primary Selection ist optional (nur Linux).

- OSName: Literal["linux","macos","windows"]  
  Validierung: zur Laufzeit aus Platform‑Detection gefüllt.

- SelectionKind: Literal["clipboard","primary"]  
  Validierung: primary wird auf macOS/Windows intern auf clipboard abgebildet (Capabilities prüfen).

- dataclass SelectionEvent:
  - ts: str (ISO‑Zeitstempel)
  - which: SelectionKind
  - text: str (Inhalt; Speicherung optional; für Privacy kann ein Hash gespeichert werden)
  - length: int
  - app: Optional[dict] = {"name": str, "title": str, "pid": int} (falls verfügbar)
  - platform: OSName

- dataclass TransportConfig:
  - mode: Literal["uds","pipe","tcp"]
  - uds_path: Optional[str]  (Linux/macOS)
  - pipe_name: Optional[str] (Windows, z. B. \\.\pipe\wbridge)
  - tcp_host: Optional[str]  (z. B. 127.0.0.1)
  - tcp_port: Optional[int]
  - token: Optional[str]     (Auth‑Token für TCP‑Fallback)
  Regeln:
  - Linux Default: uds @ $XDG_RUNTIME_DIR/wbridge.sock
  - macOS Default: uds; MAS‑Companion → tcp+token
  - Windows Default: pipe \\.\pipe\wbridge

- Protokolle (PEP 544 Protocols)
  - class IPCTransport(Protocol):
    - start() -> None
    - stop() -> None
    - request(obj: dict, timeout: float) -> tuple[bool, dict]
    - props: mode: str
  - class SelectionProvider(Protocol):
    - supports_primary: bool
    - get_text(which: SelectionKind) -> str
    - set_text(which: SelectionKind, text: str) -> None
    - watch(callback: Callable[[SelectionEvent], None]) -> Callable[[], None]  # unsub‑Fn
  - class ShortcutManager(Protocol):
    - install_binding(key: str, command: str, name: str) -> bool
    - remove_binding(key: str) -> bool
    - install_recommended(bindings: dict[str,str]) -> dict[str,int]
    - remove_recommended() -> dict[str,int]
  - class AutostartManager(Protocol):
    - enable() -> bool
    - disable() -> bool
    - is_enabled() -> bool
  - class AppInfoProvider(Protocol):
    - get_active_app() -> dict[str, str|int] | None  # name,title,pid

- dataclass PluginMeta:
  - name: str
  - version: str
  - os: OSName
  - capabilities: list[str]  # e.g. ["shortcuts","autostart","appinfo","native-clipboard","store-companion"]

[Files]
Neue OS‑Adapter und Transportschicht; bestehende Linux‑Implementierungen werden überführt, macOS/Windows über Plugins ergänzt. Zusätzlich: externe Store‑Projekte (Companion/Helper) für optimierte Kauf/Installations‑Flows.

- Neue Dateien (Core, im bestehenden Repo)
  - src/wbridge/os/__init__.py
  - src/wbridge/os/base.py
    - Enthält o. g. Protocols, PluginMeta, Factory‑Helpers.
  - src/wbridge/os/linux.py
    - Adapter nutzt bestehende Module: selection (GDK), Shortcuts (gnome_shortcuts), Autostart (~/.config/autostart), UDS‑Pfade, AppInfo optional (später).
  - src/wbridge/os/macos_stub.py
    - Stub‑Adapter: Selection via GDK Clipboard (kein Primary), UDS‑Transport; markiert fehlende Capabilities (Shortcuts/Autostart delegieren an Plugin).
  - src/wbridge/os/windows_stub.py
    - Stub‑Adapter: Selection via GDK Clipboard, Named Pipe Transport; Shortcuts/Autostart als No‑Op oder Delegation an Plugin.
  - src/wbridge/ipc/transport.py
    - Klassen: UnixSocketServer/Client, NamedPipeServer/Client, TcpServer/Client (localhost + Token)
    - Factory: create_server(cfg: TransportConfig), create_client(cfg: TransportConfig)
  - src/wbridge/os/plugin_loader.py
    - Laden von entry_points "wbridge.plugins" und Auswahl eines OS‑Plugins (wenn vorhanden), Fallback auf Stub.
  - src/wbridge/app_integration.py
    - Thin‑layer, der in app.py/cli.py die OS‑Adapter initialisiert (SelectionProvider, ShortcutManager, AutostartManager, AppInfoProvider, IPCTransport).
  - docs/ARCHITECTURE-OS-ADAPTERS.md (Entwicklerdoku)

- Modifizierte Dateien (Core)
  - src/wbridge/app.py
    - Nutzung von app_integration.OSAdapter (anstatt fest Linux); SelectionProvider statt SelectionMonitor; Transport via TransportFactory.
    - Primary: nur nutzen, wenn supports_primary True.
  - src/wbridge/server_ipc.py
    - Delegiert an transport.create_server(); keine feste UDS‑Annahme mehr.
  - src/wbridge/client_ipc.py
    - Delegiert an transport.create_client(); Pipe/TCP/UDS je OS.
  - src/wbridge/platform.py
    - OS‑Detection (linux/macos/windows), Pfade (XDG‑ähnlich per OS), Named‑Pipe Name für Windows.
  - src/wbridge/gnome_shortcuts.py, src/wbridge/autostart.py
    - Nach src/wbridge/os/linux.py integriert oder von dort aufgerufen.
  - README.md, DESIGN.md
    - Cross‑Platform, Plugins, Store‑Flows, Lizenzabschnitt aktualisieren.

- Neue externe (separate Repos/Produkte)
  - macOS (kostenpflichtiges Plugin + Store‑Companion)
    - Py‑Plugin: "wbridge-macos" (PyPI, kommerzielle Lizenz)
      - Paketname/Namespace: wbridge_macos
      - entry_points: {"wbridge.plugins": ["macos = wbridge_macos.adapter:MacOSAdapter"]}
      - Features: Shortcut‑Installer (Shortcuts CLI/Import), Autostart (SMLoginItem/Anleitung), AppInfo (NSWorkspace), ggf. native NSPasteboard‑Watcher (PyObjC)
    - App Store Companion (Swift/SwiftUI):
      - Bundle: "wbridge Companion"
      - App Intents/Shortcuts Extension → triggert lokale Requests (localhost TCP + Token) an Core
      - Onboarding: "Core installieren" (Link auf notarisiertes DMG bzw. Homebrew Cask), Health‑Check, Shortcuts installieren
  - Windows (kostenpflichtiges Plugin + Store‑App)
    - Py‑Plugin: "wbridge-win" (PyPI, kommerzielle Lizenz)
      - Namespace: wbridge_win
      - entry_points: {"wbridge.plugins": ["windows = wbridge_win.adapter:WindowsAdapter"]}
      - Features: RegisterHotKey‑Helper‑Steuerung, .lnk‑Hotkeys/Installer, Autostart (Startup‑Folder/RegRun), AppInfo (Win32 API)
    - Microsoft Store App (MSIX):
      - "wbridge for Windows" (bezahltes Paket) bündelt: Core (gepackagtes Python/GTK), Plugin, Hotkey‑Helper (C#/C++)
      - 1‑Klick‑Installation aus dem Store, kein separater Python/GTK‑Setup für Endnutzer nötig

- Konfiguration (Core)
  - ~/.config/wbridge/settings.ini → neue Sektion [ipc]
    - transport = "uds" | "pipe" | "tcp"
    - tcp_port = 18082 (Beispiel)
    - token = (zufällig; wird einmalig generiert)
  - Für macOS‑MAS‑Companion: transport=tcp; token‑Pfad in state‑Dir

[Functions]
Die Hauptfunktionen werden um Adapter‑Fabriken ergänzt; vorhandene Logik wird entkoppelt.

- Neu (Core)
  - app_integration.get_os_adapter() -> tuple[SelectionProvider, ShortcutManager, AutostartManager, AppInfoProvider, IPCTransport]
  - transport.create_server(cfg: TransportConfig) -> IPCServerLike
  - transport.create_client(cfg: TransportConfig) -> IPCClientLike
  - platform.current_os() -> OSName
  - platform.transport_defaults(os: OSName) -> TransportConfig

- Modifiziert (Core – Signaturen bleiben kompatibel, Implementierung ruft Adapter)
  - BridgeApplication.__init__/do_startup (src/wbridge/app.py)
    - Initialisiert Adapter; startet Transport gemäß Config/OS; ersetzt SelectionMonitor durch SelectionProvider.watch
  - _get_selection_blocking/_set_selection_mainthread
    - Nutzen SelectionProvider
  - server_ipc.IPCServer
    - Kapselt nur noch Routing/Framing; Transport‑Bindung in transport.py
  - client_ipc.send_request
    - Nutzt create_client(cfg) und unterstützt Pipe/TCP/UDS
  - gnome_shortcuts / autostart
    - über os/linux Adapter aufgerufen

- Entfernt/verschoben
  - selection_monitor.py (funktional ersetzt durch SelectionProvider; Linux‑Implementierung geht in os/linux.py über)

[Classes]
Neue Transports und Adapter‑Implementierungen; GUI‑Klassen bleiben unverändert.

- Neue Klassen (Core)
  - UnixSocketServer/Client, NamedPipeServer/Client, TcpServer/Client (src/wbridge/ipc/transport.py)
- Neue Klassen (Plugins)
  - MacOSAdapter (wbridge_macos.adapter) implementiert SelectionProvider/ShortcutManager/AutostartManager/AppInfoProvider soweit sinnvoll
  - WindowsAdapter (wbridge_win.adapter) analog
- Modifizierte Klassen
  - BridgeApplication (nutzt Adapter), IPCServer (nutzt Transport)
- Entfernte Klassen
  - keine (nur Umzug/Neuorganisation der Selektion)

[Dependencies]
Gezielte optionale Abhängigkeiten; Core bleibt leicht.

- Core (weiterhin):
  - PyGObject/GTK4 (Systempakete unter Linux; gebündelt in Windows‑MSIX; notarisiertes Bundle im macOS‑DMG)
  - Optional: requests (für HTTP‑Actions)
- Extras/Plugins:
  - macOS‑Plugin: pyobjc (für NSPasteboard/NSWorkspace), evtl. rumps/Swift‑Bridge (optional)
  - Windows‑Plugin: pywin32, keyboard‑Hook/Hotkey‑Helper (C#/C++ – als separater Binärteil in Store‑App)
- Packaging/Build:
  - Windows: PyInstaller/Nuitka für Core‑Binaries; MSIX Packaging Tool; Code‑Signing (EV empfohlen)
  - macOS: Notarisierung (codesign + notarytool), DMG; Companion in Xcode (App Sandbox, Hardened Runtime, App Intents)
- Store‑Spezifika:
  - macOS App Store: Companion App mit Shortcuts‑Extension, Netzwerk‑Client‑Entitlement (localhost), keine CLI‑Pfadabhängigkeit
  - Microsoft Store: Win32 MSIX erlaubt; Hintergrund‑Hotkeys via Helper (im Paket)

[Testing]
Kombination aus Unit‑, Integrations‑ und End‑to‑End‑Tests pro OS.

- Core
  - Transport‑Matrix: uds (Linux/macOS), pipe (Windows), tcp (Fallback) – Roundtrip‑Tests
  - SelectionProvider Stub: Verhalten ohne primary testen (macOS/Windows)
  - CLI/IPC Kommandos: ui.show, selection get/set, history list/apply/swap, action.run, trigger
- Linux (Regression)
  - GNOME Shortcuts, Autostart, Primary‑Semantik
- macOS
  - Clipboard (NSPasteboard oder GDK), kein Primary; Companion ↔ Core über TCP+Token
  - Shortcuts.app: Shortcut → Companion → Core → Action.run
  - Notarisierte DMG‑Installation, Gatekeeper‑Flow, Health‑Check in Companion
- Windows
  - Named Pipe Stabilität; .lnk‑Hotkeys (Basis), RegisterHotKey‑Helper (Plugin)
  - MSIX Install/Update, Autostart (Startup/RegRun), Core‑Binaries Start
- Privacy/Security
  - Token‑Pflege für TCP; Socket/Pipe Zugriffsrechte
  - Logging: Option, Selektion als Hash statt Klartext zu persistieren

[Implementation Order]
Schrittfolge minimiert Risiko und hält Linux stabil; Store‑Flows werden optimiert.

1) Core‑Vorbereitung
   - os/base.py, ipc/transport.py, plugin_loader, app_integration
   - platform.current_os(), transport_defaults()
   - server_ipc/client_ipc auf Transport‑Fabrik umstellen
2) Linux Adapter
   - os/linux.py: Portierung vorhandener Selektion/Shortcuts/Autostart
   - App weiter funktionsgleich (Regressionstests)
3) Windows Minimal
   - os/windows_stub.py (Selection via GDK), Transport=Named Pipe
   - CLI/GUI Roundtrip auf Windows (ohne Hotkey‑Helper)
4) macOS Minimal
   - os/macos_stub.py (Selection via GDK), Transport=UDS
   - CLI/GUI Roundtrip auf macOS (ohne Companion)
5) Plugin‑Schnittstellen und Laden
   - entry_points "wbridge.plugins"; Fallback auf Stub
6) Windows Plugin + Store‑App
   - wbridge-win (PyPlugin) + "wbridge for Windows" (MSIX) mit gebündeltem Core
   - Hotkey‑Helper integrieren; Onboarding “fertig nach Installation”
7) macOS Plugin + Companion
   - wbridge-macos (PyPlugin) + "wbridge Companion" (MAS) mit Shortcuts‑Extension
   - Onboarding: "Core installieren" (DMG/Brew), Health‑Check, 1‑Klick Shortcuts‑Import
   - TCP+Token zwischen Companion ↔ Core
8) Docs & Lizenz
   - README/DESIGN aktualisieren (OS‑Adapter, Plugins, Store‑Flows, Privacy)
   - Lizenztexte: Core MIT (oder Apache‑2.0), Plugins kommerzielle EULA/BSL
9) Tests/QA
   - Matrix‑Tests je OS, Installationspfade (pipx, DMG, MSIX, Store)
   - Store‑Compliance (Sandbox/Entitlements/Hardened Runtime, Windows Store‑Policies)
10) Optional Phase 2 (Frictionless++ macOS)
   - Untersuchung native SwiftUI‑App (vollständig ohne GTK) als “wbridge Pro” für 100% MAS‑Konformität (später, kein Blocker)
