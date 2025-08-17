# Status

Inspect your runtime environment and tail the application log for quick diagnostics.

This page provides:
- Environment summary (platform/Wayland/X11 context)
- Backend info (GDK display, clipboard backend)
- Quick hints about using the History page and CLI
- Log tail (last 200 lines) with a manual Refresh

---

## Environment and backend

- Environment: A compact summary of key platform details (display/server, session, etc.) useful for support and debugging.
- GDK Display / Clipboard: The GTK/GDK types in use for the display and clipboard. These confirm which backends are active in your current session.

If GDK information is unavailable, an explanatory message is shown.

---

## Log tail

The log viewer shows the last 200 lines from:
```
~/.local/state/wbridge/bridge.log
```

- Refresh: Click "Refresh" to reload the view from disk.
- Read-only: The viewer is read-only and monospaced for easier scanning.

Use the log tail to monitor:
- Actions and Triggers events
- HTTP integration status and requests
- Shortcuts install/remove operations
- Errors and warnings from background components

---

## Related pages

- History: Apply and swap recent selection values. Useful when verifying clipboard/primary behavior alongside the logs.
- Settings: Configure the HTTP trigger and run a Health check. If the Health check fails, consult the log tail here.

---

## CLI equivalents

Many operations have CLI counterparts that also produce log entries:
- Examples:
  - `wbridge selection get --which clipboard`
  - `wbridge selection set --which primary "text"`
  - `wbridge actions run --name "Action Name" --which clipboard`

Running these commands while keeping the Status page open helps correlate user actions with log output.

---

## Troubleshooting

- No log output:
  - Ensure the app has permission to write to `~/.local/state/wbridge/`.
  - Try creating the directory and file manually if your environment requires it.
- Health check or HTTP issues:
  - Verify Base URL/Trigger Path in Settings.
  - Look for connection errors or timeouts in the log.
- Clipboard anomalies:
  - Confirm whether your workflow uses Clipboard or Primary Selection.
  - Check the History page to verify values and use Swap/Apply to reproduce issues.
- Shortcuts not working:
  - Confirm `wbridge` is on PATH (see Settings and Shortcuts pages for hints).
  - Inspect the binding install/remove messages in the log.
