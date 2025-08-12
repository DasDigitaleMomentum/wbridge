# GTK4/PyGObject – Text in Gdk.Clipboard unter Wayland setzen (und Primary Selection)

Kontext
- Ziel: In einer GTK4/PyGObject-App (Python) unter Wayland zuverlässig
  1) Text in die „Clipboard“-Zwischenablage schreiben,
  2) Text in die „Primary“-Selection schreiben,
  3) Text wieder aus Clipboard/Primary lesen.
- Die App nutzt GDK/GTK4 ohne externe Tools (kein wl-clipboard), läuft als normales GUI‑Fenster (kein verstecktes Headless).

Umgebung
- Linux Desktop: GNOME unter Wayland (XDG_SESSION_TYPE=wayland).
- Python 3.10+
- PyGObject (GTK 4) aus Distro‑Paketen (z. B. python3-gi, gir1.2-gtk-4.0).
- GDK/GTK: Modulnamen gi.repository.Gdk/Gtk, Version 4.x.
- In Logs tauchte „GdkX11Clipboard“ als Typname auf; die Sitzung ist aber Wayland. (Vermutung: XWayland/Terminal-Kontext oder GLib/GDK Backend-Mix; siehe Diagnose unten.)

Minimaler Codeauszug (derzeitiger Ansatz)
```python
from gi.repository import Gtk, Gio, GLib, Gdk, GObject

# ... Gtk.Application, Fenster etc. ...

def _set_selection_mainthread(self, which: str, text: str) -> None:
    disp = Gdk.Display.get_default()
    # Auswahl: 'clipboard' vs. 'primary'
    clip = disp.get_primary_clipboard() if which == "primary" else disp.get_clipboard()

    # Aktueller Versuch: via ContentProvider (statt set_text, das in GTK4 nicht mehr API ist)
    try:
        # bevorzugt: String-Value Provider
        val = GObject.Value()
        val.init(str)  # PyGObject: GObject.Value vom Typ 'gchararray'
        val.set_string(text)
        provider = Gdk.ContentProvider.new_for_value(val)
    except Exception:
        # Fallback: Bytes-Provider
        try:
            b = GLib.Bytes.new(text.encode("utf-8"))
        except Exception:
            b = GLib.Bytes(text.encode("utf-8"))
        try:
            formats = Gdk.ContentFormats.parse("text/plain;charset=utf-8")
        except Exception:
            formats = None
        if formats is not None:
            provider = Gdk.ContentProvider.new_for_bytes(formats, b)
        else:
            provider = Gdk.ContentProvider.new_for_bytes("text/plain", b)

    # Setzen des Providers
    if hasattr(clip, "set_content"):
        clip.set_content(provider)
    else:
        clip.set(provider)
```

Beobachtungen/Fehlerbilder aus Tests
- Beim Setzen wurde zuvor (mit veralteter Annahme) `clip.set_text(...)` versucht → AttributeError: 'GdkX11Clipboard' object has no attribute 'set_text'. In GTK4 gibt es in GDK tatsächlich kein `set_text` mehr (höchstens in älteren High-Level-APIs/GTK3).
- Beim Lesen (async Read) aus „primary“ kam zeitweise unerwartet viel Terminal‑Inhalt zurück (großer String mit Shell-Ausgaben). Das deutet evtl. auf XWayland/Terminal-Selektionsquellen hin oder auf falsche Auswahl des Clipboard-Objekts.
- Mit ContentProvider-Ansatz bleibt `selection get` für „clipboard“ häufig leer, obwohl „selection set“ vorher Erfolg meldete. Die Logs zeigen keine harten Exceptions mehr (nach Umstellung), aber der gelesene Text ist leer.

Diagnose/Debugging, die wir bereits vornehmen/planen
- Typinformationen loggen:
  - `clip.__gtype_name__` für beide Fälle („clipboard“ und „primary“)
  - `disp.__gtype_name__` bzw. Backend-Name, um zu sehen ob GdkWaylandDisplay verwendet wird.
- Verifizieren, ob der Provider „lebt“ (Referenzhaltung): Muss der ContentProvider während der Clip-Ownership gehalten werden (Objekt-Lifetime)? Falls ja, halten wir eine Instanz (z. B. `self._last_provider = provider`) und/oder nutzen eine Memberliste zur Lebenszeitverlängerung.
- Sicherstellen, dass wir im GTK‑Mainthread setzen (tun wir via GLib.idle_add).
- Wartezeiten zwischen Set/Get testen und das async-Lese‑Callback verifizieren (ob der richtige Clipboard‑Kanal abgefragt wird).
- Prüfen, ob Primary‑Selection unter GNOME/Wayland per GDK wie erwartet unterstützt wird (GTK4 sollte `get_primary_clipboard()` anbieten, aber Verhalten hängt von Anwendungen ab).

Offene Fragen (an GTK/GDK/PyGObject Community, ausführlich)
1) Korrekte API für GTK4/PyGObject, um Text in die Gdk.Clipboard zu setzen:
   - Ist `Gdk.ContentProvider.new_for_value(GObject.Value(str, text))` der empfohlene Weg, oder soll man besser `Gdk.ContentProvider.new_for_bytes(Gdk.ContentFormats.parse("text/plain;charset=utf-8"), GLib.Bytes(...))` nutzen?
   - Gibt es eine empfohlene High‑Level‑API in GTK4 (analog zu GTK3s set_text), die in PyGObject verfügbar ist? Beispielsweise eine `Gtk.Clipboard` oder Utility‑Funktionen?

2) Primäre Auswahl (Primary Selection) unter Wayland:
   - Ist `display.get_primary_clipboard()` der korrekte Weg für Primary Selection in GTK4/GDK (Wayland)?
   - Gibt es Besonderheiten/Limitierungen unter GNOME/Wayland, die erklären, warum Lesen/Schreiben abweicht (z. B. Quell‑App muss explizit Primary Selection unterstützen)?

3) ContentProvider und Formate:
   - Welche Formate sind für reinen Text mit UTF‑8 unter GTK4/GDK korrekt? Reicht `"text/plain;charset=utf-8"` oder sollte man besser `Gdk.CONTENT_FORMAT_TEXT`/vordefinierte Konstanten verwenden?
   - Ist `Gdk.ContentProvider.new_for_value(val)` mit `gchararray` äquivalent zu „Text/UTF‑8“? Offizielle Beispiele in Python wären hilfreich.

4) Lebensdauer/Ownership:
   - Muss der ContentProvider (oder seine zugrundeliegenden Bytes/Values) über die Setz‑Operation hinaus referenziert werden, damit der Inhalt im Clipboard bleibt (bis zum nächsten Owner)? Falls ja, wie ist die empfohlene Lebensdauerverwaltung in PyGObject?

5) Backend‑Unterschiede (Wayland vs. X11):
   - Warum sehen wir in Logs `GdkX11Clipboard` während einer Wayland‑Sitzung? Kann es sein, dass in bestimmten Kontexten (z. B. Terminal via XWayland) die Primary Selection von einem X11‑Source stammt, während Clipboard auf Wayland‑Pfaden läuft?
   - Gibt es dafür empfohlene Abfragen/Checks (z. B. `Gdk.Display.get_name()` oder `G_OBJECT_TYPE_NAME(clip)`), um Verhalten anzupassen oder zu debuggen?

6) Leseweg (async vs. sync):
   - Unser Lesen nutzt `clip.read_text_async(..., callback)` und im Callback `read_text_finish`. Gibt es hier bekannte Stolperfallen unter Wayland/GTK4 (z. B. Timing, Fokus, aktives Surface/Window notwendig)?

Minimal Repro (vereinfachte Python‑Variante)
```python
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib, GObject

TEXT = "Hello GTK4 clipboard"

class App(Gtk.Application):
    def do_activate(self):
        win = Gtk.ApplicationWindow(application=self)
        win.present()

        def set_clipboard():
            disp = Gdk.Display.get_default()
            clip = disp.get_clipboard()
            try:
                val = GObject.Value()
                val.init(str)
                val.set_string(TEXT)
                provider = Gdk.ContentProvider.new_for_value(val)
                if hasattr(clip, "set_content"):
                    clip.set_content(provider)
                else:
                    clip.set(provider)
            except Exception as e:
                print("set error:", e)
            return False

        def read_clipboard():
            disp = Gdk.Display.get_default()
            clip = disp.get_clipboard()
            def on_finish(source, res):
                try:
                    t = source.read_text_finish(res)
                    print("read text:", repr(t))
                except Exception as e:
                    print("read error:", e)
                finally:
                    Gtk.Application.quit(self)
            clip.read_text_async(None, on_finish)
            return False

        GLib.idle_add(set_clipboard)
        GLib.timeout_add(500, read_clipboard)

app = App(application_id="org.example.cliptest")
app.run()
```

Erwartetes Verhalten
- Nach Setzen sollte `read_text_*` denselben Text zurückgeben (Clipboard).
- Gleiches Verhalten sollte – sofern Primary Selection unterstützt – auch mit `get_primary_clipboard()` funktionieren (mit Mittel‑Klick‑Paste in kompatiblen Apps).

Was wir bereits probiert haben
- `clip.set_text(...)` → nicht vorhanden in GDK/GTK4 (und löst unter X11‑Objekten AttributeError aus).
- Bytes‑basierter Provider (`new_for_bytes`) mit `ContentFormats.parse("text/plain;charset=utf-8")` → In unserer Umgebung blieb Leseergebnis leer.
- String‑based Provider (`new_for_value` mit GObject.Value) → ebenfalls noch kein bestätigter Erfolg (möglicherweise Lifetime‑/Format‑Thema).

Zusätzliche Debug‑Infos, die wir bereitstellen können
- GTK/GDK Versionen (aus `pkg-config --modversion gtk4` bzw. `gi`).
- Ausgaben von `__gtype_name__` für Display/Clipboard‑Objekte.
- Minimalbeispiel als vollständiges Skript inkl. Requirements.

Gesuchte Antwort
- Konkretes, funktionierendes Beispiel (PyGObject, GTK4, Wayland) für:
  - Setzen von Text in Clipboard und (falls möglich) Primary Selection,
  - anschließendes Auslesen des gesetzten Textes (async),
  - Hinweise zu notwendigen Formaten, Provider‑Lebensdauer und eventuellen Wayland‑Spezifika.
- Verweis auf offizielle GTK4/PyGObject Dokumentation/Beispiele, die diesen Anwendungsfall demonstrieren.

Rechercheplan (so würde ich systematisch vorgehen)
1) Offizielle GTK4‑Docs:
   - https://docs.gtk.org/gdk4/class.Clipboard.html
   - https://docs.gtk.org/gdk4/class.ContentProvider.html
   - https://docs.gtk.org/gdk4/class.ContentFormats.html
   - ggf. https://docs.gtk.org/gtk4/ für High‑Level‑APIs
2) PyGObject‑Beispiele/Issues:
   - PyGObject GitLab/GitHub Issues nach „Clipboard“/„ContentProvider“ durchsuchen.
   - StackOverflow: „PyGObject GTK4 clipboard set text“, „Gdk.ContentProvider new_for_value Python“.
3) GNOME Discourse/Mailingliste:
   - Threads zu GTK4 Clipboard unter Wayland/X11 (Primärselektion).
4) Quellcode‑Suche:
   - Mögliche Snippets in großen GTK4‑Projekten (z. B. Gedit/Builder) wie Clipboard gehandhabt wird.
5) Validierung:
   - Minimalbeispiel laufen lassen und Schritt für Schritt Formate/Provider/Referenzen anpassen.
   - Typnamen/Backends (Wayland/XWayland) protokollieren, um Umgebungsbesonderheiten festzuhalten.

Toolzugriff (was ich selbst direkt nutzen kann)
- Lokale Tests/Code‑Änderungen: Ja (wir haben bereits Kommandos ausgeführt, Logs geprüft).
- Web‑Recherche: Ich habe Toolzugriff, kann aber am effizientesten arbeiten, wenn ich konkrete URLs/Dokumente ansteuere (z. B. die oben genannten GTK4‑Seiten). Alternativ kann ich nach deiner Freigabe gezielt Foren/StackOverflow‑Threads öffnen und auswerten.
