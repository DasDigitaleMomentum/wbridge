# Status

Problem & Goal
You want to quickly understand your runtime environment and diagnose issues (HTTP integration, shortcuts, clipboard behavior). 
The Status page summarizes environment details and shows a live log tail for fast troubleshooting.

What’s on this page
- Environment summary (Wayland/X11 session, platform)
- Backend info (GDK display/clipboard backends)
- Quick hints to verify History and CLI behavior
- Log tail (recent lines) with manual Refresh

---

## Key terms

- Wayland/X11 session: Your desktop session type (`$XDG_SESSION_TYPE`). Wayland limits global key grabs by design.
- GDK Display / Clipboard backend: GTK/GDK types in use (confirms which backends are active).
- Log tail: Recent lines from the application log file:
  ```
  ~/.local/state/wbridge/bridge.log
  ```
- Health check: Quick HTTP GET to verify your configured HTTP trigger endpoint (see Settings).

---

## Process (overview)

1) Check Environment summary to confirm session/backend.
2) Review GDK Display/Clipboard info to ensure expected backends are active.
3) Open the Status log tail and press Refresh when testing behaviors.
4) Reproduce your workflow (selection, trigger, shortcut) and observe log entries.
5) Use hints to correlate actions with logs; switch to relevant pages if needed.

---

## Step‑by‑step (quick diagnosis loop)

1) Open Status and glance at Environment
   - Confirm Wayland session (or X11 if applicable).
   - Note platform bits relevant to clipboard behavior.

2) Verify GDK backends
   - Ensure the display/clipboard entries make sense for your session.
   - If unavailable, the page shows an explanatory message.

3) Keep the log tail visible
   - Press “Refresh” to reload.
   - Look for new entries while you trigger actions.

4) Reproduce an action
   - In Actions, Run an HTTP or Shell action.
   - Or via CLI:
     ```
     wbridge selection get --which clipboard
     wbridge action run --name "Your Action" --from-primary
     ```
   - Observe the Status log for operation results or errors.

5) Narrow down
   - If HTTP fails: verify Base URL/paths in Settings and run Health check.
   - If shortcuts fail: visit Shortcuts to check conflicts and PATH hints.
   - If clipboard/primary seems off: use History to Get/Set/Swap and confirm.

---

## Examples

Run selection commands while watching the log
```
wbridge selection get --which clipboard
wbridge selection set --which primary "hello"
wbridge history list --which clipboard --limit 5
```

Invoke actions/triggers
```
wbridge trigger prompt --from-primary
wbridge action run --name "Post to local API" --from-clipboard
```
Keep the Status page open and hit Refresh after each command to correlate user actions with log output.

---

## Good practices

- One place for truth: Use the Status page as your ground control for environment + logs.
- Correlate: Run your CLI commands with Status open to see immediate effects.
- Small steps: Change one thing at a time (e.g., Base URL), then Refresh and re‑test.
- Cross‑check pages: Use History for buffer checks; Shortcuts for conflicts; Settings for HTTP health.

---

## Troubleshooting

No log output
- Ensure the app can write to `~/.local/state/wbridge/`.
- Create the directory if your environment requires it; then try again.
- Press Refresh and reproduce the action.

Health check / HTTP issues
- Verify Base URL and Trigger Path in Settings.
- Ensure the endpoint is running and reachable.
- Look for connection errors or timeouts in the log tail.

Clipboard anomalies
- Confirm whether your workflow uses Clipboard or Primary Selection.
- Use History to Set/Get/Swap and validate behavior.
- Remember: middle‑click paste typically uses Primary.

Shortcuts not working
- Ensure `wbridge` is on PATH or use an absolute command in the shortcut.
- Check for binding conflicts (Shortcuts page).
- If dconf writes lag, click Reload or restart GNOME Shell/session.

---

## Glossary & links

- History: Apply/swap recent selection values — `help/en/history.md`
- Actions: Create and run HTTP/Shell actions — `help/en/actions.md`
- Triggers: Alias → Action mapping — `help/en/triggers.md`
- Shortcuts: GNOME keybindings management — `help/en/shortcuts.md`
- Settings: HTTP trigger, profiles, shortcuts, autostart — `help/en/settings.md`
