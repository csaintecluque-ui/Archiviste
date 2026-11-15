#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archiviste — fenêtres d'application (GTK 3 + WebKitGTK).

Lance le serveur d'Archiviste à l'intérieur du programme, sur un port libre, et l'affiche
dans ses propres fenêtres : pas de navigateur, pas d'onglet. Une seule instance à la fois.

    archiviste                 fenêtre principale
    archiviste --bureau        bureau Archiviste (remplace les icônes de Nemo, volet à droite)
    archiviste --demander      petite fenêtre « Demander à l'Archiviste » (Super + Espace)
    archiviste --sans-bureau   rend le bureau à Nemo (en cas de souci)
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

# WebKitGTK + pilote NVIDIA propriétaire : évite la fenêtre blanche connue.
os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")

try:
    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    try:
        gi.require_version("WebKit2", "4.1")
    except ValueError:
        gi.require_version("WebKit2", "4.0")
    from gi.repository import Gdk, Gio, GLib, Gtk, WebKit2
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
except (ImportError, ValueError) as err:
    sys.stderr.write(
        f"Archiviste : il manque le moteur d'affichage ({err}).\n"
        "Installe-le avec :  sudo apt install python3-gi gir1.2-webkit2-4.1\n")
    sys.exit(1)
try:
    gi.require_version("GdkX11", "3.0")
    from gi.repository import GdkX11
except (ImportError, ValueError):
    GdkX11 = None

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archiviste as A  # noqa: E402

APP_ID = "fr.csc.Archiviste"
STATE_FILE = A.DATA_DIR / "fenetre.json"
ZOOMS = [0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]
TRANSPARENT = Gdk.RGBA(0, 0, 0, 0)
ENCRE = Gdk.RGBA(0.09, 0.07, 0.06, 1.0)

GLib.set_prgname("archiviste")
GLib.set_application_name("Archiviste")
Gdk.set_program_class("archiviste")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(patch: dict) -> None:
    state = load_state()
    state.update(patch)
    try:
        STATE_FILE.write_text(json.dumps(state), "utf-8")
    except OSError:
        pass


def cleanup_old_install() -> None:
    """Retire l'ancienne version « script » (service + raccourci qui ouvrait le navigateur).
    Les agents, prompts et discussions (~/.local/share/archiviste) sont conservés."""
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    old_desktop = data / "applications" / "archiviste.desktop"
    try:
        if old_desktop.exists() and "archiviste-app/lancer.sh" in old_desktop.read_text("utf-8", "replace"):
            old_desktop.unlink()
            subprocess.run(["systemctl", "--user", "disable", "--now", "archiviste.service"],
                           capture_output=True, timeout=15)
            (Path.home() / ".config" / "systemd" / "user" / "archiviste.service").unlink(missing_ok=True)
            subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=15)
            shutil.rmtree(data / "archiviste-app", ignore_errors=True)
            for rel in ("scalable/apps/archiviste.svg", "192x192/apps/archiviste.png", "512x512/apps/archiviste.png"):
                (data / "icons" / "hicolor" / rel).unlink(missing_ok=True)
            subprocess.run(["update-desktop-database", str(data / "applications")], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass


def launch_default(uri: str) -> None:
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except GLib.Error:
        subprocess.Popen(["xdg-open", uri], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def raise_window(win: Gtk.Window) -> None:
    """Met la fenêtre au premier plan, même quand la demande vient du bureau (anti-vol de focus)."""
    gw = win.get_window()
    if GdkX11 is not None and gw is not None and isinstance(gw, GdkX11.X11Window):
        win.present_with_time(GdkX11.x11_get_server_time(gw))
    else:
        win.present()


def transparent_window(win: Gtk.Window) -> bool:
    """Fond de fenêtre transparent si l'écran est composité (Cinnamon l'est toujours)."""
    screen = win.get_screen()
    visual = screen.get_rgba_visual()
    if visual is None or not screen.is_composited():
        return False
    win.set_visual(visual)
    win.set_app_paintable(True)
    css = Gtk.CssProvider()
    css.load_from_data(b"window.archiviste-transparent { background-color: transparent; }")
    win.get_style_context().add_provider(css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    win.get_style_context().add_class("archiviste-transparent")
    return True


def primary_monitor(at_pointer: bool = False):
    disp = Gdk.Display.get_default()
    if at_pointer:
        seat = disp.get_default_seat()
        if seat is not None and seat.get_pointer() is not None:
            _, x, y = seat.get_pointer().get_position()
            mon = disp.get_monitor_at_point(x, y)
            if mon is not None:
                return mon
    return disp.get_primary_monitor() or disp.get_monitor(0)


def icon_lookup(name: str, size: int) -> dict:
    """Cherche une icône comme Cinnamon (thème actuel, héritages, liens, tailles) : appelé depuis le serveur,
    exécuté dans la boucle GTK. Renvoie {"path": fichier png/svg} ou {"png": octets}."""
    done, out = threading.Event(), {}

    def png_of(pb):
        ok, data = pb.save_to_bufferv("png", [], [])
        if ok:
            out["png"] = data

    def work():
        try:
            if os.path.isabs(name):
                if os.path.isfile(name):
                    png_of(GdkPixbuf.Pixbuf.new_from_file_at_size(name, size, size))
            else:
                theme = Gtk.IconTheme.get_default()
                info = theme.lookup_icon(name, size, Gtk.IconLookupFlags(0))
                if info is None and name.lower().endswith((".png", ".svg", ".xpm")):
                    info = theme.lookup_icon(name[:-4], size, Gtk.IconLookupFlags(0))
                if info is not None:
                    fn = info.get_filename()
                    if fn and fn.lower().endswith((".png", ".svg")) and os.access(fn, os.R_OK):
                        out["path"] = fn
                    else:
                        png_of(info.load_icon())
        except (GLib.Error, TypeError, ValueError):
            pass
        done.set()
        return False

    GLib.idle_add(work)
    done.wait(3)
    return out


# ════════════════════════════════════════════════════════════════════
#  Comportement commun des fenêtres web
# ════════════════════════════════════════════════════════════════════
class VueWeb:
    """Navigation : tout ce qui n'est pas Archiviste s'ouvre à l'extérieur. Raccourcis communs."""
    app: "Application"
    view: WebKit2.WebView
    zoom_key = "zoom"

    def setup_view(self, background: Gdk.RGBA) -> WebKit2.WebView:
        view = WebKit2.WebView.new_with_context(self.app.ctx)
        st = view.get_settings()
        st.set_enable_developer_extras(True)
        st.set_javascript_can_access_clipboard(True)
        st.set_enable_back_forward_navigation_gestures(False)
        st.set_enable_smooth_scrolling(True)
        st.set_media_playback_requires_user_gesture(True)
        view.set_background_color(background)
        view.set_zoom_level(float(load_state().get(self.zoom_key, 1.0)))
        view.connect("decide-policy", self.on_policy)
        view.connect("create", self.on_create)
        view.connect("context-menu", self.on_context_menu)
        view.connect("load-failed", self.on_load_failed)
        self.view = view
        return view

    def internal(self, uri: str) -> bool:
        return uri.startswith(self.app.base)

    def open_outside(self, uri: str) -> None:
        parts = urllib.parse.urlsplit(uri)
        if self.internal(uri) and parts.path == "/api/fs/raw":
            path = urllib.parse.parse_qs(parts.query).get("path", [""])[0]
            if path and os.path.exists(path):
                launch_default(Gio.File.new_for_path(path).get_uri())
            return
        if parts.scheme in ("http", "https", "mailto"):
            launch_default(uri)

    def on_policy(self, view, decision, kind):
        if kind == WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION:
            self.open_outside(decision.get_navigation_action().get_request().get_uri())
            decision.ignore()
            return True
        if kind == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            uri = decision.get_navigation_action().get_request().get_uri()
            if not self.internal(uri) and not uri.startswith(("blob:", "data:", "about:")):
                self.open_outside(uri)
                decision.ignore()
                return True
        return False

    def on_create(self, view, action):
        self.open_outside(action.get_request().get_uri())
        return None

    def on_context_menu(self, view, menu, event, hit):
        A_ = WebKit2.ContextMenuAction
        drop = {getattr(A_, n, None) for n in (
            "GO_BACK", "GO_FORWARD", "STOP", "RELOAD", "OPEN_LINK_IN_NEW_WINDOW", "DOWNLOAD_LINK_TO_DISK",
            "OPEN_IMAGE_IN_NEW_WINDOW", "DOWNLOAD_IMAGE_TO_DISK", "OPEN_FRAME_IN_NEW_WINDOW",
            "OPEN_VIDEO_IN_NEW_WINDOW", "OPEN_AUDIO_IN_NEW_WINDOW", "DOWNLOAD_VIDEO_TO_DISK",
            "DOWNLOAD_AUDIO_TO_DISK", "COPY_VIDEO_LINK_TO_CLIPBOARD", "COPY_AUDIO_LINK_TO_CLIPBOARD")}
        for item in list(menu.get_items()):
            if item.get_stock_action() in drop:
                menu.remove(item)
        items = menu.get_items()
        while items and items[0].is_separator():
            menu.remove(items[0])
            items = menu.get_items()
        return menu.get_n_items() == 0

    def on_load_failed(self, view, event, uri, error):
        if self.internal(uri):
            view.load_html(
                "<body style='font:15px sans-serif;background:#17120f;color:#ede2d0;padding:60px'>"
                f"<h2>Archiviste ne répond pas</h2><p>{GLib.markup_escape_text(error.message)}</p>"
                "<p>Relance Archiviste.</p></body>", None)
            return True
        return False

    def run_js(self, script: str) -> None:
        if hasattr(self.view, "evaluate_javascript"):
            self.view.evaluate_javascript(script, -1, None, None, None, None, None)
        else:
            self.view.run_javascript(script, None, None, None)

    def zoom(self, step: int) -> None:
        cur = self.view.get_zoom_level()
        if step == 0:
            z = 1.0
        else:
            idx = min(range(len(ZOOMS)), key=lambda i: abs(ZOOMS[i] - cur))
            z = ZOOMS[max(0, min(len(ZOOMS) - 1, idx + step))]
        self.view.set_zoom_level(z)
        save_state({self.zoom_key: z})

    def common_key(self, ev) -> bool:
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        k = ev.keyval
        if ctrl and k in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
            self.zoom(+1)
        elif ctrl and k in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.zoom(-1)
        elif ctrl and k in (Gdk.KEY_0, Gdk.KEY_KP_0, Gdk.KEY_agrave):
            self.zoom(0)
        elif k == Gdk.KEY_F5 or (ctrl and k == Gdk.KEY_r):
            self.view.reload()
        elif k == Gdk.KEY_F12:
            self.view.get_inspector().show()
        else:
            return False
        return True


# ════════════════════════════════════════════════════════════════════
#  Fenêtre principale
# ════════════════════════════════════════════════════════════════════
class Fenetre(VueWeb, Gtk.ApplicationWindow):
    def __init__(self, app: "Application", hash_: str = ""):
        Gtk.ApplicationWindow.__init__(self, application=app, title="Archiviste")
        self.app = app
        state = load_state()
        self.set_default_size(int(state.get("w", 1440)), int(state.get("h", 900)))
        self.set_position(Gtk.WindowPosition.CENTER)
        if state.get("max"):
            self.maximize()
        app.set_icon(self)
        self.add(self.setup_view(ENCRE))
        self.connect("key-press-event", self.on_key)
        self.connect("delete-event", self.on_close)
        self.connect("destroy", lambda *_: app.forget(self))
        self.view.load_uri(app.base + (hash_ or ""))
        self.show_all()

    def naviguer(self, data: dict) -> None:
        self.run_js(f"window.archivisteNaviguer && archivisteNaviguer({json.dumps(data)})")

    def on_key(self, widget, ev):
        if self.common_key(ev):
            return True
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        if ev.keyval == Gdk.KEY_F11:
            if self.get_window() and self.get_window().get_state() & Gdk.WindowState.FULLSCREEN:
                self.unfullscreen()
            else:
                self.fullscreen()
        elif ctrl and ev.keyval == Gdk.KEY_q:
            self.close()
        else:
            return False
        return True

    def on_close(self, *args):
        maximized = self.is_maximized()
        patch = {"max": maximized}
        if not maximized:
            patch["w"], patch["h"] = self.get_size()
        save_state(patch)
        return False


# ════════════════════════════════════════════════════════════════════
#  Bureau : fenêtre de type « bureau », sous toutes les autres
# ════════════════════════════════════════════════════════════════════
class Bureau(VueWeb, Gtk.ApplicationWindow):
    zoom_key = "zoom_bureau"

    def __init__(self, app: "Application"):
        Gtk.ApplicationWindow.__init__(self, application=app, title="Bureau Archiviste")
        self.app = app
        self.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(True)
        self.set_role("archiviste-bureau")
        self.stick()
        app.set_icon(self)
        self.composite = transparent_window(self)
        self.margins = None
        self.setup_view(TRANSPARENT if self.composite else ENCRE)
        self.add(self.view)
        self.connect("delete-event", lambda *_: True)  # Alt+F4 ne ferme pas le bureau
        self.connect("key-press-event", lambda w, ev: self.common_key(ev))
        self.connect("destroy", lambda *_: app.forget(self))
        screen = self.get_screen()
        screen.connect("monitors-changed", lambda *_: self.place())
        screen.connect("size-changed", lambda *_: self.place())
        GLib.timeout_add_seconds(5, self.place)  # le panneau de Cinnamon peut arriver après nous
        self.place()
        self.load()
        self.show_all()

    def draw_own_wallpaper(self) -> bool:
        return not self.composite or A.bureau_state().get("fond") == "archiviste"

    def load(self) -> None:
        q = {"fond": "1" if self.draw_own_wallpaper() else "0"}
        q.update({k: str(v) for k, v in (self.margins or {}).items()})
        self.view.set_background_color(ENCRE if self.draw_own_wallpaper() else TRANSPARENT)
        self.view.load_uri(self.app.base + "bureau?" + urllib.parse.urlencode(q))

    def place(self) -> bool:
        mon = primary_monitor()
        if mon is None:
            return True
        g, wa = mon.get_geometry(), mon.get_workarea()
        self.move(g.x, g.y)
        self.resize(g.width, g.height)
        self.set_size_request(g.width, g.height)
        m = {"h": max(0, wa.y - g.y), "g": max(0, wa.x - g.x),
             "b": max(0, g.y + g.height - wa.y - wa.height), "d": max(0, g.x + g.width - wa.x - wa.width)}
        if m != self.margins:
            self.margins = m
            self.run_js(f"window.archivisteMarges && archivisteMarges({json.dumps(m)})")
        return True

    def on_context_menu(self, view, menu, event, hit):
        if hit.context_is_editable() or hit.context_is_selection():
            return VueWeb.on_context_menu(self, view, menu, event, hit)
        return True  # le bureau affiche son propre menu


# ════════════════════════════════════════════════════════════════════
#  « Demander à l'Archiviste » : petite fenêtre flottante (Super + Espace)
# ════════════════════════════════════════════════════════════════════
class Demande(VueWeb, Gtk.ApplicationWindow):
    W = 760
    zoom_key = "zoom_bureau"

    def __init__(self, app: "Application"):
        Gtk.ApplicationWindow.__init__(self, application=app, title="Demander à l'Archiviste")
        self.app = app
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        app.set_icon(self)
        composite = transparent_window(self)
        self.setup_view(TRANSPARENT if composite else ENCRE)
        ucm = self.view.get_user_content_manager()
        ucm.register_script_message_handler("archiviste")
        ucm.connect("script-message-received::archiviste", self.on_message)
        self.add(self.view)
        self.height = 96
        self.set_default_size(self.W, self.height)
        self.connect("key-press-event", self.on_key)
        self.connect("focus-out-event", self.on_focus_out)
        self.connect("delete-event", lambda *_: self.dismiss() or True)
        self.connect("destroy", lambda *_: app.forget(self))
        self.view.load_uri(app.base + "bureau?mode=demander&fond=" + ("0" if composite else "1"))
        self.place()
        self.show_all()

    def place(self) -> None:
        mon = primary_monitor(at_pointer=True)
        if mon is None:
            return
        g = mon.get_workarea()
        self.move(g.x + (g.width - self.W) // 2, g.y + int(g.height * 0.14))

    def on_message(self, ucm, res):
        val = res.get_js_value() if hasattr(res, "get_js_value") else res
        try:
            msg = json.loads(val.to_string())
        except (ValueError, TypeError):
            return
        if msg.get("t") == "taille":
            self.height = max(60, min(int(msg.get("h", 96)), 720))
            self.resize(self.W, self.height)
        elif msg.get("t") == "fermer":
            self.dismiss()

    def on_key(self, widget, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.dismiss()
            return True
        return self.common_key(ev)

    def on_focus_out(self, *args):
        GLib.timeout_add(150, self._focus_check)
        return False

    def _focus_check(self):
        if not self.is_active() and self.get_visible():
            self.dismiss()
        return False

    def show_again(self) -> None:
        self.place()
        self.show_all()
        raise_window(self)
        self.run_js("window.archivisteMontrer && archivisteMontrer()")

    def dismiss(self) -> None:
        """Masque la fenêtre (réouverture instantanée) ; la ferme si rien d'autre n'est ouvert."""
        if self.app.bureau is None and self.app.window is None:
            self.destroy()
        else:
            self.hide()


# ════════════════════════════════════════════════════════════════════
#  Application (une seule instance : les lignes de commande vont à la première)
# ════════════════════════════════════════════════════════════════════
class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.bureau = None
        self.demande = None
        self.base = None
        self.ctx = None
        for name, desc in (("bureau", "Afficher le bureau Archiviste"),
                           ("demander", "Ouvrir « Demander à l'Archiviste »"),
                           ("fenetre", "Ouvrir la fenêtre principale"),
                           ("sans-bureau", "Rendre le bureau à Nemo")):
            self.add_main_option(name, 0, GLib.OptionFlags.NONE, GLib.OptionArg.NONE, desc, None)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        cleanup_old_install()
        A.prepare()
        srv = A.Server(("127.0.0.1", 0), A.Handler)
        threading.Thread(target=srv.serve_forever, name="serveur", daemon=True).start()
        self.base = f"http://127.0.0.1:{srv.server_address[1]}/"
        A.RELAUNCH_HOOK = lambda: GLib.idle_add(self.relaunch)
        A.UI_HOOK = lambda action, data=None: GLib.idle_add(self.on_ui, action, data or {})
        A.ICON_HOOK = icon_lookup
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "archiviste"
        wdm = WebKit2.WebsiteDataManager(base_data_directory=str(A.DATA_DIR / "webkit"),
                                         base_cache_directory=str(cache / "webkit"))
        self.ctx = WebKit2.WebContext.new_with_website_data_manager(wdm)
        self.ctx.connect("download-started", self.on_download)
        if os.environ.get("ARCHIVISTE_DEBUG"):
            print(f"Archiviste {A.VERSION} — {self.base}", flush=True)

    def set_icon(self, win: Gtk.Window) -> None:
        icon = HERE / "static" / "icon-512.png"
        if Gtk.IconTheme.get_default().has_icon("archiviste"):
            win.set_icon_name("archiviste")
        elif icon.exists():
            win.set_icon_from_file(str(icon))

    def forget(self, win) -> None:
        for attr in ("window", "bureau", "demande"):
            if getattr(self, attr) is win:
                setattr(self, attr, None)
        # une fenêtre « Demander » masquée ne doit pas garder Archiviste ouvert pour rien
        if self.window is None and self.bureau is None and self.demande is not None \
                and not self.demande.get_visible():
            self.demande.destroy()

    # ── ligne de commande ──
    def do_command_line(self, cmdline):
        opts = cmdline.get_options_dict().end().unpack()
        if opts.get("sans-bureau"):
            A.bureau_activer(False)
            return 0
        shown = False
        if opts.get("bureau"):
            shown = True
            if A.bureau_state().get("actif"):
                self.show_bureau()
            else:
                print("Le bureau Archiviste est désactivé (Réglages › Bureau).", file=sys.stderr)
        if opts.get("demander"):
            shown = True
            self.toggle_demande()
        if opts.get("fenetre") or not shown:
            self.open_main()
        return 0

    def do_activate(self):
        self.open_main()

    # ── fenêtres ──
    def open_main(self, data: dict | None = None) -> None:
        if self.window is None:
            self.window = Fenetre(self, self.hash_for(data) if data else "")
        elif data:
            self.window.naviguer(data)
        raise_window(self.window)

    @staticmethod
    def hash_for(d: dict) -> str:
        vue = d.get("vue", "files")
        if vue in ("files", "sort") and d.get("chemin"):
            h = f"#/{vue}?p={urllib.parse.quote(d['chemin'], safe='')}"
            if d.get("select"):
                h += f"&s={urllib.parse.quote(d['select'], safe='')}"
            return h
        if vue == "chat" and d.get("conv"):
            return f"#/chat/{d['conv']}"
        return f"#/{vue}"

    def show_bureau(self) -> None:
        if self.bureau is None:
            self.bureau = Bureau(self)
        self.bureau.show_all()

    def hide_bureau(self) -> None:
        if self.bureau is not None:
            win, self.bureau = self.bureau, None
            win.destroy()

    def toggle_demande(self, close: bool = False) -> None:
        if self.demande is None:
            if not close:
                self.demande = Demande(self)
                raise_window(self.demande)
            return
        if close or (self.demande.get_visible() and self.demande.is_active()):
            self.demande.dismiss()
        else:
            self.demande.show_again()

    def on_ui(self, action: str, data: dict) -> bool:
        if action == "bureau":
            if data.get("actif"):
                self.show_bureau()
            else:
                self.hide_bureau()
        elif action == "ouvrir":
            self.open_main(data)
            if self.demande is not None and self.demande.get_visible():
                self.demande.dismiss()
        elif action == "demander":
            self.toggle_demande(close=bool(data.get("fermer")))
        elif action == "fond" and self.bureau is not None:
            self.bureau.load()
        return False

    # ── téléchargements (export, etc.) : boîte « Enregistrer sous » ──
    def on_download(self, ctx, download):
        download.connect("decide-destination", self.on_destination)

    def on_destination(self, download, suggested):
        dlg = Gtk.FileChooserNative.new("Enregistrer", self.window, Gtk.FileChooserAction.SAVE,
                                        "_Enregistrer", "_Annuler")
        dlg.set_current_name(suggested or "fichier")
        dlg.set_do_overwrite_confirmation(True)
        folder = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DOWNLOAD) or str(Path.home())
        dlg.set_current_folder(folder)
        if dlg.run() == Gtk.ResponseType.ACCEPT:
            download.set_allow_overwrite(True)
            download.set_destination(dlg.get_uri())
        else:
            download.cancel()
        return True

    def relaunch(self):
        """Après une mise à jour : relance la nouvelle version (mêmes fenêtres) une fois celle-ci fermée."""
        args = (["--bureau"] if self.bureau else []) + (["--fenetre"] if self.window or not self.bureau else [])
        exe = "archiviste" if shutil.which("archiviste") else f"'{sys.executable}' '{HERE / 'fenetre.py'}'"
        subprocess.Popen(["sh", "-c", f"sleep 1; exec {exe} {' '.join(args)}"], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.window:
            self.window.on_close()
        self.quit()
        return False


def main():
    sys.exit(Application().run(sys.argv))


if __name__ == "__main__":
    main()
