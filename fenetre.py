#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archiviste — fenêtre d'application (GTK 3 + WebKitGTK).

Lance le serveur d'Archiviste à l'intérieur du programme, sur un port libre,
et l'affiche dans sa propre fenêtre : pas de navigateur, pas d'onglet.
Une seule fenêtre à la fois : relancer Archiviste ramène la fenêtre au premier plan.
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
except (ImportError, ValueError) as err:
    sys.stderr.write(
        f"Archiviste : il manque le moteur d'affichage ({err}).\n"
        "Installe-le avec :  sudo apt install python3-gi gir1.2-webkit2-4.1\n")
    sys.exit(1)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import archiviste as A  # noqa: E402

APP_ID = "fr.csc.Archiviste"
STATE_FILE = A.DATA_DIR / "fenetre.json"
ZOOMS = [0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0]

GLib.set_prgname("archiviste")
GLib.set_application_name("Archiviste")
Gdk.set_program_class("archiviste")


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
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


class Fenetre(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, base: str):
        super().__init__(application=app, title="Archiviste")
        self.base = base
        self.state = load_state()
        self.set_default_size(int(self.state.get("w", 1440)), int(self.state.get("h", 900)))
        self.set_position(Gtk.WindowPosition.CENTER)
        if self.state.get("max"):
            self.maximize()
        icon = HERE / "static" / "icon-512.png"
        if Gtk.IconTheme.get_default().has_icon("archiviste"):
            self.set_icon_name("archiviste")
        elif icon.exists():
            self.set_icon_from_file(str(icon))

        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "archiviste"
        wdm = WebKit2.WebsiteDataManager(base_data_directory=str(A.DATA_DIR / "webkit"),
                                         base_cache_directory=str(cache / "webkit"))
        ctx = WebKit2.WebContext.new_with_website_data_manager(wdm)
        ctx.connect("download-started", self.on_download)
        self.view = WebKit2.WebView.new_with_context(ctx)
        st = self.view.get_settings()
        st.set_enable_developer_extras(True)
        st.set_javascript_can_access_clipboard(True)
        st.set_enable_back_forward_navigation_gestures(False)
        st.set_enable_smooth_scrolling(True)
        st.set_media_playback_requires_user_gesture(True)
        self.view.set_background_color(Gdk.RGBA(0.09, 0.07, 0.06, 1.0))
        self.view.set_zoom_level(float(self.state.get("zoom", 1.0)))
        self.view.connect("decide-policy", self.on_policy)
        self.view.connect("create", self.on_create)
        self.view.connect("context-menu", self.on_context_menu)
        self.view.connect("load-failed", self.on_load_failed)
        self.add(self.view)

        self.connect("key-press-event", self.on_key)
        self.connect("delete-event", self.on_close)
        self.view.load_uri(self.base + "?bureau=1")
        self.show_all()

    # ── navigation : tout ce qui n'est pas Archiviste s'ouvre à l'extérieur ──
    def internal(self, uri: str) -> bool:
        return uri.startswith(self.base)

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
                "<p>Ferme la fenêtre et relance Archiviste.</p></body>", None)
            return True
        return False

    # ── téléchargements (export, etc.) : boîte « Enregistrer sous » ──
    def on_download(self, ctx, download):
        download.connect("decide-destination", self.on_destination)

    def on_destination(self, download, suggested):
        dlg = Gtk.FileChooserNative.new("Enregistrer", self, Gtk.FileChooserAction.SAVE, "_Enregistrer", "_Annuler")
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

    # ── raccourcis : zoom, rechargement, plein écran, inspecteur ──
    def zoom(self, step: int) -> None:
        cur = self.view.get_zoom_level()
        if step == 0:
            z = 1.0
        else:
            idx = min(range(len(ZOOMS)), key=lambda i: abs(ZOOMS[i] - cur))
            z = ZOOMS[max(0, min(len(ZOOMS) - 1, idx + step))]
        self.view.set_zoom_level(z)
        self.state["zoom"] = z

    def on_key(self, widget, ev):
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
        elif k == Gdk.KEY_F11:
            if self.get_window() and self.get_window().get_state() & Gdk.WindowState.FULLSCREEN:
                self.unfullscreen()
            else:
                self.fullscreen()
        elif k == Gdk.KEY_F12:
            self.view.get_inspector().show()
        elif ctrl and k == Gdk.KEY_q:
            self.close()
        else:
            return False
        return True

    def on_close(self, *args):
        maximized = self.is_maximized()
        self.state["max"] = maximized
        if not maximized:
            w, h = self.get_size()
            self.state["w"], self.state["h"] = w, h
        save_state(self.state)
        return False


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.window = None
        self.base = None

    def do_startup(self):
        Gtk.Application.do_startup(self)
        cleanup_old_install()
        A.prepare()
        srv = A.Server(("127.0.0.1", 0), A.Handler)
        threading.Thread(target=srv.serve_forever, name="serveur", daemon=True).start()
        self.base = f"http://127.0.0.1:{srv.server_address[1]}/"
        A.RELAUNCH_HOOK = lambda: GLib.idle_add(self.relaunch)
        if os.environ.get("ARCHIVISTE_DEBUG"):
            print(f"Archiviste {A.VERSION} — {self.base}", flush=True)

    def relaunch(self):
        """Après une mise à jour : relance la nouvelle version une fois celle-ci fermée."""
        cmd = "sleep 1; exec archiviste" if shutil.which("archiviste") else \
            f"sleep 1; exec '{sys.executable}' '{HERE / 'fenetre.py'}'"
        subprocess.Popen(["sh", "-c", cmd], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if self.window:
            self.window.on_close()
        self.quit()
        return False

    def do_activate(self):
        if self.window is None:
            self.window = Fenetre(self, self.base)
        self.window.present()


def main():
    sys.exit(Application().run(sys.argv))


if __name__ == "__main__":
    main()
