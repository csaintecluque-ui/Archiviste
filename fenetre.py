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
    archiviste DOSSIER         ouvre ce dossier (ou montre ce fichier) : c'est ainsi que Mint l'appelle quand
                               Archiviste est le gestionnaire de fichiers par défaut
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import traceback
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
try:  # suivi des fenêtres ouvertes (repères sur les raccourcis du volet) : facultatif
    gi.require_version("Wnck", "3.0")
    from gi.repository import Wnck
except (ImportError, ValueError):
    Wnck = None

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
#  Fenêtres ouvertes sur le bureau (libwnck, X11)
# ════════════════════════════════════════════════════════════════════
class SuiviFenetres:
    """Sait quelles applis ont une fenêtre ouverte, réduite ou devant, et peut les ramener, les réduire ou les
    fermer : le volet du bureau s'en sert comme d'un dock (repère sur le raccourci, clic pour ramener ou réduire).
    Tout se passe dans la boucle GTK ; le serveur ne lit que la dernière photo (snapshot), sans attendre."""

    def __init__(self, on_change, x_time):
        self.version = 0
        self._snap: list[dict] = []
        self._recent: list[int] = []   # identifiants X, de la fenêtre la plus récemment active à la plus ancienne
        self._watched: set[int] = set()
        self._timer = 0
        self._on_change = on_change
        self._x_time = x_time
        # « pager » : nos demandes sont traitées comme celles d'une barre des tâches (pas d'anti-vol de focus)
        Wnck.set_client_type(Wnck.ClientType.PAGER)
        self.screen = Wnck.Screen.get_default()
        if self.screen is None:
            raise RuntimeError("écran X11 introuvable")
        self.screen.connect("window-opened", self._opened)
        self.screen.connect("window-closed", self._later)
        self.screen.connect("active-window-changed", self._active)
        self.screen.force_update()
        self._recent = [w.get_xid() for w in reversed(self.screen.get_windows_stacked()) if self._shown(w)]
        for w in self.screen.get_windows():
            self._watch(w)
        self._rebuild()

    @staticmethod
    def _shown(w) -> bool:
        """Une fenêtre « de barre des tâches » : normale, pas le bureau, pas un panneau, pas une boîte flottante."""
        return w.get_window_type() == Wnck.WindowType.NORMAL and not w.is_skip_tasklist()

    def _watch(self, w) -> None:
        xid = w.get_xid()
        if xid in self._watched:
            return
        self._watched.add(xid)
        for sig in ("state-changed", "name-changed", "class-changed", "type-changed"):
            try:
                w.connect(sig, self._later)
            except TypeError:
                pass  # signal absent de cette version de libwnck

    def _opened(self, screen, w) -> None:
        self._watch(w)
        self._later()

    def _active(self, *args) -> None:
        w = self.screen.get_active_window()
        if w is not None and self._shown(w):
            xid = w.get_xid()
            if not self._recent or self._recent[0] != xid:
                self._recent = [xid] + [x for x in self._recent if x != xid]
        self._later()

    def _later(self, *args) -> None:
        if not self._timer:
            self._timer = GLib.timeout_add(120, self._rebuild)

    def _rebuild(self) -> bool:
        self._timer = 0
        try:
            wins = {w.get_xid(): w for w in self.screen.get_windows() if self._shown(w)}
            self._watched &= {w.get_xid() for w in self.screen.get_windows()}
            self._recent = [x for x in self._recent if x in wins] + [x for x in wins if x not in self._recent]
            me = os.getpid()
            snap = []
            for xid in self._recent:
                w = wins[xid]
                snap.append({"xid": xid, "titre": w.get_name() or "", "cls": w.get_class_group_name() or "",
                             "inst": w.get_class_instance_name() or "", "pid": w.get_pid() or 0,
                             "reduit": bool(w.is_minimized()), "soi": w.get_pid() == me})
            if snap != self._snap:
                self._snap = snap  # remplacé d'un coup : lisible sans verrou depuis les requêtes du serveur
                self.version += 1
                self._on_change()
        except Exception:  # noqa: BLE001 — un souci de suivi ne doit jamais gêner le bureau
            traceback.print_exc()
        return False

    def snapshot(self) -> list[dict]:
        return list(self._snap)

    def act(self, xids, action: str) -> None:
        """afficher, reduire ou fermer ces fenêtres (appelé depuis le serveur : exécuté dans la boucle GTK)."""
        GLib.idle_add(self._act, list(xids), action)

    def _act(self, xids: list, action: str) -> bool:
        try:
            ts = self._x_time()
            wins = {w.get_xid(): w for w in self.screen.get_windows()}
            targets = [wins[x] for x in xids if x in wins]
            if action == "reduire":
                for w in targets:
                    w.minimize()
            elif action == "fermer":
                for w in targets:
                    w.close(ts)
            else:  # afficher : la plus récente en dernier, pour qu'elle finisse devant les autres
                for w in reversed(targets):
                    ws = w.get_workspace()
                    if ws is not None and ws != self.screen.get_active_workspace():
                        ws.activate(ts)
                    if w.is_minimized():
                        w.unminimize(ts)
                    w.activate(ts)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════════════
#  org.freedesktop.FileManager1 : « afficher dans le dossier » depuis les autres applis
# ════════════════════════════════════════════════════════════════════
FM1_XML = """<node><interface name="org.freedesktop.FileManager1">
  <method name="ShowFolders"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
  <method name="ShowItems"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
  <method name="ShowItemProperties"><arg type="as" name="URIs" direction="in"/><arg type="s" name="StartupId" direction="in"/></method>
</interface></node>"""


class ServiceFichiers:
    """Quand Archiviste est le gestionnaire de fichiers par défaut, il répond à la place de Nemo aux
    applis qui demandent d'« afficher dans le dossier » un fichier (Firefox après un téléchargement…).
    Si Nemo tient déjà ce nom sans vouloir le céder, on n'insiste pas : rien ne change."""

    def __init__(self, app):
        self.app = app
        self.owner = 0
        self.reg = 0
        self.conn = None
        self.actif = False

    def demarrer(self) -> None:
        if self.owner:
            return
        try:
            self.owner = Gio.bus_own_name(
                Gio.BusType.SESSION, "org.freedesktop.FileManager1",
                Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT | Gio.BusNameOwnerFlags.REPLACE,
                self.on_bus, self.on_acquired, self.on_lost)
        except Exception:  # noqa: BLE001 — pas de bus de session : rien à faire
            self.owner = 0

    def arreter(self) -> None:
        if self.conn is not None and self.reg:
            self.conn.unregister_object(self.reg)
        if self.owner:
            Gio.bus_unown_name(self.owner)
        self.owner = self.reg = 0
        self.conn = None
        self.actif = False

    def on_bus(self, conn, name) -> None:
        try:
            iface = Gio.DBusNodeInfo.new_for_xml(FM1_XML).interfaces[0]
            self.reg = conn.register_object("/org/freedesktop/FileManager1", iface, self.on_call, None, None)
            self.conn = conn
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    def on_acquired(self, conn, name) -> None:
        self.actif = True

    def on_lost(self, conn, name) -> None:
        self.actif = False

    def on_call(self, conn, sender, path, iface, method, params, invocation) -> None:
        try:
            uris = params.unpack()[0]
            paths = [p for p in (Gio.File.new_for_uri(u).get_path() for u in uris) if p and os.path.exists(p)]
            if paths:
                if method == "ShowFolders":
                    self.app.show_path(paths[0])
                elif method == "ShowItemProperties":
                    self.app.show_path(paths[0], props=True)
                else:  # ShowItems : le dossier qui le contient, l'élément choisi
                    self.app.open_main({"vue": "files", "chemin": os.path.dirname(paths[0]) or "/", "select": paths[0]})
            invocation.return_value(None)
        except Exception as e:  # noqa: BLE001
            invocation.return_dbus_error("org.freedesktop.DBus.Error.Failed", str(e))


# ════════════════════════════════════════════════════════════════════
#  Dossiers surveillés : le bureau se met à jour tout de suite
# ════════════════════════════════════════════════════════════════════
class Surveillance:
    """Prévient le bureau dès qu'un dossier qu'il affiche change (bureau, corbeille, clés USB, téléchargements),
    au lieu d'attendre son prochain sondage. Signale aussi le changement à l'index de recherche."""

    def __init__(self, on_change):
        self._on_change = on_change
        self._monitors = []
        self._timers: dict[str, int] = {}
        user = os.environ.get("USER") or Path.home().name
        trash = A.TRASH_DIR / "files"
        try:
            trash.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        watch = [("bureau", A.desktop_dir()), ("bureau", str(trash)), ("telechargements", A.downloads_dir())]
        watch += [("bureau", d) for d in (f"/media/{user}", f"/run/media/{user}")]
        for kind, path in watch:
            if not os.path.isdir(path):
                continue
            try:
                mon = Gio.File.new_for_path(path).monitor_directory(Gio.FileMonitorFlags.WATCH_MOVES, None)
                mon.connect("changed", self._changed, kind, path)
                self._monitors.append(mon)  # gardé en vie : un moniteur libéré ne prévient plus
            except GLib.Error:
                pass

    def _changed(self, mon, f, other, event, kind, path) -> None:
        key = f"{kind}|{path}"
        if key not in self._timers:  # une rafale de changements (copie de 50 fichiers) ne fait qu'un seul signal
            self._timers[key] = GLib.timeout_add(180, self._fire, key, kind, path)

    def _fire(self, key, kind, path) -> bool:
        self._timers.pop(key, None)
        try:
            A.changed(os.path.join(path, "x"))
            self._on_change(kind)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        return False


# ════════════════════════════════════════════════════════════════════
#  Comportement commun des fenêtres web
# ════════════════════════════════════════════════════════════════════
class VueWeb:
    """Navigation : tout ce qui n'est pas Archiviste s'ouvre à l'extérieur. Raccourcis communs."""
    app: "Application"
    view: WebKit2.WebView
    zoom_key = "zoom"

    def on_drag_data(self, view, context, x, y, selection, info, time_) -> None:
        """Un fichier glissé depuis une autre appli (Nemo…) survole la page : WebKit ne dit pas à la page où il
        se trouve, alors on le note pour elle. Sans cela, elle ne pourrait que l'ignorer."""
        try:
            if Gtk.drag_get_source_widget(context) is not None:
                return  # glissé depuis une de nos fenêtres : la page de départ l'a déjà noté
            if selection.get_target().name() != "text/uri-list":
                return
            paths = [Gio.File.new_for_uri(u).get_path() for u in (selection.get_uris() or []) if u.startswith("file://")]
            A.drag_set([p for p in paths if p])
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    # La touche Ctrl pendant un glisser (Ctrl = copier, sinon déplacer). WebKitGTK en donne un état périmé à la
    # page : on lit le clavier ici, on prévient la page quand il change, et on note sa valeur au moment du dépôt.
    def _ctrl_down(self) -> bool:
        keymap = Gdk.Keymap.get_for_display(self.view.get_display())
        return bool(keymap.get_modifier_state() & Gdk.ModifierType.CONTROL_MASK)

    def on_drag_motion(self, view, context, x, y, time_) -> bool:
        try:
            ctrl = self._ctrl_down()
            if ctrl != self._drag_ctrl:
                self._drag_ctrl = ctrl
                self.run_js(f"window.archivisteCtrl && archivisteCtrl({'true' if ctrl else 'false'})")
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        return False  # la suite est l'affaire de WebKit

    def on_drag_leave(self, view, context, time_) -> None:
        self._drag_ctrl = None  # prochain glisser : l'état sera redonné à la page

    def on_drag_drop(self, view, context, x, y, time_) -> bool:
        try:
            A.drag_key(self._ctrl_down())
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        return False

    def setup_view(self, background: Gdk.RGBA) -> WebKit2.WebView:
        view = WebKit2.WebView.new_with_context(self.app.ctx)
        st = view.get_settings()
        st.set_enable_developer_extras(True)
        if os.environ.get("ARCHIVISTE_DEBUG"):  # les messages de la page (console.log, erreurs) dans le journal
            st.set_enable_write_console_messages_to_stdout(True)
        st.set_javascript_can_access_clipboard(True)
        st.set_enable_back_forward_navigation_gestures(False)
        st.set_enable_smooth_scrolling(True)
        st.set_media_playback_requires_user_gesture(True)
        view.set_background_color(background)
        view.set_zoom_level(float(load_state().get(self.zoom_key, 1.0)))
        view.connect("decide-policy", self.on_policy)
        view.connect("drag-data-received", self.on_drag_data)
        view.connect("drag-motion", self.on_drag_motion)
        view.connect("drag-leave", self.on_drag_leave)
        view.connect("drag-drop", self.on_drag_drop)
        self._drag_ctrl = None
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
        self.view.connect("load-changed", self.on_load)
        # le panneau de Cinnamon peut arriver après nous : on se replace quelques fois au démarrage, puis ce sont
        # les signaux (écrans, taille, zone de travail) qui s'en chargent — plus de minuterie permanente
        self._tries = 0
        GLib.timeout_add_seconds(3, self._place_again)
        self._watched_monitors: set[int] = set()
        self.place()
        self.load()
        self.show_all()

    def _place_again(self) -> bool:
        self._tries += 1
        self.place()
        return self._tries < 6

    def on_load(self, view, event) -> None:
        if event == WebKit2.LoadEvent.FINISHED:  # la page saura qu'on la prévient : elle sonde beaucoup moins
            self.run_js("window.archivistePousse && archivistePousse()")

    def draw_own_wallpaper(self) -> bool:
        return not self.composite or A.bureau_state().get("fond") == "archiviste"

    def load(self) -> None:
        q = {"fond": "1" if self.draw_own_wallpaper() else "0"}
        q.update({k: str(v) for k, v in (self.margins or {}).items()})
        self.view.set_background_color(ENCRE if self.draw_own_wallpaper() else TRANSPARENT)
        self.view.load_uri(self.app.base + "bureau?" + urllib.parse.urlencode(q))

    def place(self) -> bool:
        mon = self.app.desktop_monitor()
        if mon is None:
            return True
        if id(mon) not in self._watched_monitors:  # panneau déplacé, masqué ou agrandi : la zone de travail change
            self._watched_monitors.add(id(mon))
            mon.connect("notify::workarea", lambda *_: self.place())
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
        self.suivi = None
        self.surveillance = None
        self.ecrans: list[dict] = []
        self._push_timer = 0
        self._push_kinds: set[str] = set()
        self.service_fichiers = None
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
        A.PUSH_HOOK = lambda kind: GLib.idle_add(self.on_push, kind)
        A.CLIP_HOOK = self.file_clipboard
        try:  # autre chose est copié ailleurs (texte, fichiers dans Nemo) : notre « coupé » n'a plus cours
            self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            self._clipboard.connect("owner-change", lambda *_: A.clip_clear())
        except Exception:  # noqa: BLE001
            self._clipboard = None
        A.MONITORS_HOOK = lambda: list(self.ecrans)
        self.list_monitors()
        scr = Gdk.Screen.get_default()
        if scr is not None:
            scr.connect("monitors-changed", lambda *_: self.list_monitors())
        self.start_window_tracking()
        A.FM_HOOK = lambda what: self.in_gtk(lambda: self.fm_service(what)) if what != "etat" else \
            bool(self.service_fichiers and self.service_fichiers.actif)
        self.fm_service("marche" if A.fm_is_archiviste() else "arret")
        try:
            self.surveillance = Surveillance(self.on_folder_changed)
        except Exception:  # noqa: BLE001 — sans surveillance, le bureau se rafraîchit par sondage, comme avant
            traceback.print_exc()
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "archiviste"
        wdm = WebKit2.WebsiteDataManager(base_data_directory=str(A.DATA_DIR / "webkit"),
                                         base_cache_directory=str(cache / "webkit"))
        self.ctx = WebKit2.WebContext.new_with_website_data_manager(wdm)
        self.ctx.connect("download-started", self.on_download)
        if os.environ.get("ARCHIVISTE_DEBUG"):
            print(f"Archiviste {A.VERSION} — {self.base}", flush=True)

    # ── fenêtres ouvertes : repères « appli ouverte » du volet ──
    def start_window_tracking(self) -> None:
        """Facultatif : sans libwnck (paquet gir1.2-wnck-3.0) ou hors X11, le volet marche comme avant."""
        disp = Gdk.Display.get_default()
        if Wnck is None or GdkX11 is None or not isinstance(disp, GdkX11.X11Display):
            return
        try:
            self.suivi = SuiviFenetres(self.on_windows_changed, self.x_time)
            A.WINDOWS_HOOK = self.suivi
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            self.suivi = None

    def x_time(self) -> int:
        """Heure du serveur X, exigée par le gestionnaire de fenêtres pour accepter de ramener une fenêtre."""
        for win in (self.bureau, self.window, self.demande):
            gw = win.get_window() if win is not None else None
            if gw is not None and isinstance(gw, GdkX11.X11Window):
                return GdkX11.x11_get_server_time(gw)
        return Gtk.get_current_event_time()

    # ── presse-papiers du système : fichiers copiés ou coupés dans le gestionnaire de fichiers ──
    def in_gtk(self, fn, timeout: float = 1.5):
        """Exécute fn dans la boucle GTK depuis un fil du serveur, et rend son résultat (None si trop long)."""
        done = threading.Event()
        box = {}

        def run() -> bool:
            try:
                box["v"] = fn()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            done.set()
            return False

        GLib.idle_add(run)
        done.wait(timeout)
        return box.get("v")

    def file_clipboard(self, clear: bool = False):
        if self._clipboard is None:
            return None
        if clear:  # coupé-collé terminé : comme Nemo, on vide le presse-papiers
            return self.in_gtk(lambda: self._clipboard.set_text("", 0))
        return self.in_gtk(self._read_file_clipboard)

    def _read_file_clipboard(self):
        """Format de Nemo, Nautilus, Caja… : « cut » ou « copy », puis une adresse file:// par ligne."""
        sel = self._clipboard.wait_for_contents(Gdk.Atom.intern("x-special/gnome-copied-files", False))
        data = sel.get_data() if sel is not None else None
        if not data:
            return None
        lines = bytes(data).decode("utf-8", "replace").split("\n")
        paths = []
        for uri in lines[1:]:
            f = Gio.File.new_for_uri(uri.strip()) if uri.strip().startswith("file://") else None
            if f is not None and f.get_path():
                paths.append(f.get_path())
        return {"mode": "couper" if lines[0].strip() == "cut" else "copier", "paths": paths}

    # ── écrans ──
    def list_monitors(self) -> None:
        """Écrans branchés (lus dans la boucle GTK, puis servis tels quels au serveur)."""
        disp = Gdk.Display.get_default()
        out = []
        for i in range(disp.get_n_monitors() if disp is not None else 0):
            m = disp.get_monitor(i)
            g = m.get_geometry()
            out.append({"index": i, "nom": m.get_model() or f"Écran {i + 1}", "principal": bool(m.is_primary()),
                        "largeur": g.width, "hauteur": g.height})
        self.ecrans = out

    def desktop_monitor(self):
        """Écran qui porte le bureau Archiviste : celui choisi dans les réglages s'il est branché, sinon le principal."""
        disp = Gdk.Display.get_default()
        idx = A.bureau_state().get("ecran")
        if isinstance(idx, int) and disp is not None and 0 <= idx < disp.get_n_monitors():
            return disp.get_monitor(idx)
        return primary_monitor()

    # ── le bureau est prévenu des changements au lieu de les guetter ──
    def on_folder_changed(self, kind: str) -> None:
        if self.bureau is not None:
            self.bureau.run_js(f"window.archivisteChange && archivisteChange({json.dumps(kind)})")
        if kind == "taches" and self.window is not None:  # une tâche de fond commence ou se termine
            self.window.run_js("window.archivisteTaches && archivisteTaches()")

    def on_push(self, kind: str) -> bool:
        self._push_kinds.add(kind)
        if not self._push_timer:  # plusieurs écritures d'affilée (une réponse de l'IA) : un seul signal par sorte
            self._push_timer = GLib.timeout_add(150, self._push_now)
        return False

    def _push_now(self) -> bool:
        self._push_timer = 0
        kinds, self._push_kinds = self._push_kinds, set()
        for kind in sorted(kinds):
            self.on_folder_changed(kind)
        return False

    def on_windows_changed(self) -> None:
        if self.bureau is not None:
            self.bureau.run_js("window.archivisteFenetres && archivisteFenetres()")

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
        target = self.path_from_args(cmdline)
        if target is not None:
            self.show_path(target)
            return 0
        if opts.get("fenetre") or not shown:
            self.open_main()
        return 0

    @staticmethod
    def path_from_args(cmdline):
        """Premier dossier ou fichier donné en argument (chemin, relatif ou non, ou adresse file://)."""
        for arg in list(cmdline.get_arguments() or [])[1:]:
            if not arg or arg.startswith("-"):
                continue
            f = Gio.File.new_for_uri(arg) if "://" in arg else Gio.File.new_for_path(
                arg if os.path.isabs(arg) else os.path.join(cmdline.get_cwd() or str(Path.home()), arg))
            p = f.get_path()
            if p and os.path.exists(p):
                return os.path.normpath(p)
        return None

    def show_path(self, path: str, props: bool = False) -> None:
        """Ouvre un dossier dans la fenêtre principale, ou montre un fichier dans son dossier. Un dossier hors de
        ceux qu'Archiviste a le droit de toucher (/etc, /usr…) s'ouvre dans Nemo : Archiviste n'y va pas."""
        if not any(A.within(os.path.realpath(path), r) for r in A.allowed_roots()):
            for fm in ("nemo", "nautilus", "caja", "thunar"):
                if shutil.which(fm) and A._launch([fm, path]):
                    return
        if os.path.isdir(path) and not props:
            self.open_main({"vue": "files", "chemin": path})
        else:
            self.open_main({"vue": "files", "chemin": os.path.dirname(path) or "/", "select": path,
                            **({"proprietes": True} if props else {})})

    # ── service D-Bus « FileManager1 » : Firefox, Chrome, VS Code… demandent d'« afficher dans le dossier » ──
    def fm_service(self, what: str) -> bool:
        if what == "marche":
            if self.service_fichiers is None:
                self.service_fichiers = ServiceFichiers(self)
            self.service_fichiers.demarrer()
        elif what == "arret" and self.service_fichiers is not None:
            self.service_fichiers.arreter()
        return bool(self.service_fichiers and self.service_fichiers.actif)

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
            if d.get("proprietes"):
                h += "&i=1"
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
        elif action == "ecran" and self.bureau is not None:
            self.bureau.place()
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
