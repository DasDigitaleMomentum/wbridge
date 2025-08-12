# Implementation Log – wbridge

Purpose
- Track significant implementation steps, decisions, merges, and next actions.
- Keep entries concise and actionable. One log per change-set, newest first.

Conventions
- Timestamp: local time of the developer system
- Scope: brief summary of touched areas
- Commits: local and/or remote SHAs if relevant
- Links: issue/PR if available (future)

---

## 2025-08-12 – History/GUI/IPC enhancements

- Timestamp: 2025-08-12
- Scope:
  - IPC: implementiert `history.list/apply/swap`; `action.run` + `trigger`; Settings/Actions werden beim Start geladen.
  - GUI/History: zweizeilige Einträge mit Apply-Buttons, „Aktuell: …“-Label je Bereich, manueller Refresh + Zähler; Swap‑Button; stabile Refresh‑Mechanik (Dirty‑Flag), keine UI‑Blockierung.
  - GUI/Actions: Liste aus actions.json; Quellwahl (Clipboard/Primary/Text); Run‑Button mit Ergebnisanzeige; Reload actions.
  - GUI/Settings: Basisinfos (GDK‑Backend, Socket, Log) + Platzhalter‑Buttons (Shortcuts/Autostart).
  - Stabilität: zentrale Apply‑Logik, asynchrone Lese‑Guards (`_reading_cb`, `_reading_pr`), kein reentrantes Listen‑Refresh, Shutdown‑Fix (`Gtk.Application.do_shutdown(self)`).
  - CLI: History‑Subcommands arbeiten gegen neue IPC‑Handler; manuelle Tests durchgeführt.
  - DESIGN.md: Checkliste angepasst (umgesetzte Punkte abgehakt).
- Local commit:
  - tbd (nach Push): feat(gui,ipc): History‑IPC, History‑UI mit „Aktuell“, Actions‑Tab, Settings‑Basis; Async‑Guards/Dirty‑Refresh; CLI‑Integration
- Notes:
  - Bugfixes: „Doppel‑Klick nötig“ und „Hängen nach erster Selektion“ behoben durch sofortige History‑Aktualisierung, asynchrones Label‑Update, Dirty‑Flag‑Refresh und In‑Flight‑Guards.

## 2025-08-12 – Initial scaffold, push to org

- Timestamp: 2025-08-12
- Scope:
  - Repo scaffolded locally (single package with CLI+GUI).
  - Created: pyproject.toml, README.md, DESIGN.md, LICENSE (MIT), .gitignore.
  - Source modules added under src/wbridge/: app.py, cli.py, server_ipc.py, client_ipc.py, history.py, config.py, actions.py, gnome_shortcuts.py, platform.py, logging_setup.py, __init__.py.
  - IPC server started from GUI; ui.show handler implemented; CLI wired to IPC.
- Local commit:
  - d694c5f chore: scaffold wbridge (CLI+GUI, IPC server/client, docs, config)
- Remote integration:
  - Remote default branch contained initial skeleton (e.g., LICENSE). Performed merge favoring local scaffold for conflicts.
  - Merge and push completed.
  - Remote tip: bbd642f main
- Notes:
  - SSH key added and authorized for org; push now functional.
  - LICENSE conflict auto-merged using recursive strategy (ours preference). Final license retained as MIT from local scaffold.

Next Steps (per DESIGN.md Checklist)
- Extend IPC handler to support: selection.get/set, history.list/apply/swap, action.run/trigger.
- Add GUI tabs (History/Actions/Settings/Status) and wire to services.
- Implement actions management UI and settings loading.
- Provide GNOME shortcuts install/remove UI and Autostart toggle.
