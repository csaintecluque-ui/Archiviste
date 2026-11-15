#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archiviste — gestionnaire de fichiers + IA locale (Ollama).

Serveur local sans aucune dépendance (bibliothèque standard Python 3.10+).
Lancement :  python3 archiviste.py      puis ouvrir http://127.0.0.1:8765

Données (réglages, prompts, agents, discussions, journal des tris) :
    ~/.local/share/archiviste/
"""
from __future__ import annotations

import ast
import base64
import datetime as dt
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import select
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from fnmatch import fnmatch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archives  # noqa: E402  (zip, tar, 7z… : archives.py, à côté)

VERSION = "1.6.1"
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
HOME = Path.home()
XDG_DATA = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local" / "share")
DATA_DIR = Path(os.environ.get("ARCHIVISTE_DATA") or XDG_DATA / "archiviste")
TRASH_DIR = XDG_DATA / "Trash"
HOST = os.environ.get("ARCHIVISTE_HOST", "127.0.0.1")
PORT = int(os.environ.get("ARCHIVISTE_PORT", "8765"))
TOKEN = secrets.token_urlsafe(24)
MAX_ROUNDS = 12
UPDATE_REPO = os.environ.get("ARCHIVISTE_REPO", "csaintecluque-ui/Archiviste")
RELAUNCH_HOOK = None  # renseigné par fenetre.py : relance l'appli après une mise à jour
MAX_VERSIONS = 300
MAX_VERSIONS_BYTES = 2 * 1024 ** 3

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# ════════════════════════════════════════════════════════════════════
#  Erreurs
# ════════════════════════════════════════════════════════════════════
PUSH_HOOK = None  # renseigné par fenetre.py : prévient le bureau qu'un état a changé, sans attendre son sondage


def push(kind: str) -> None:
    hook = PUSH_HOOK
    if hook is not None:
        try:
            hook(kind)
        except Exception:  # noqa: BLE001
            pass


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class OllamaError(Exception):
    def __init__(self, message: str, status: int = 500):
        super().__init__(message)
        self.status = status


class ClientGone(Exception):
    """Le navigateur a coupé la connexion (bouton Stop, onglet fermé…)."""
    partial: dict | None = None


# ════════════════════════════════════════════════════════════════════
#  Stockage JSON
# ════════════════════════════════════════════════════════════════════
class Store:
    def __init__(self, root: Path):
        self.root = root
        self.lock = threading.RLock()
        for sub in ("", "conversations", "versions"):
            (root / sub).mkdir(parents=True, exist_ok=True)

    def read(self, name: str, default):
        path = self.root / name
        with self.lock:
            try:
                return json.loads(path.read_text("utf-8"))
            except FileNotFoundError:
                return default() if callable(default) else default
            except (json.JSONDecodeError, UnicodeDecodeError):
                stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                try:
                    path.rename(path.with_name(f"{path.name}.corrompu-{stamp}"))
                except OSError:
                    pass
                return default() if callable(default) else default

    def write(self, name: str, data) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with self.lock:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
            os.replace(tmp, path)
        if name == "bureau.json" or name.startswith("conversations/"):
            push("etat")  # raccourcis, réglages du bureau, discussion du volet : le bureau se met à jour tout de suite

    def update(self, name: str, default, fn):
        """Lecture, modification puis écriture d'un seul tenant : aucune autre requête ne s'intercale."""
        with self.lock:
            data = self.read(name, default)
            out = fn(data)
            self.write(name, data)
            return out

    def delete(self, name: str) -> None:
        with self.lock:
            try:
                (self.root / name).unlink()
            except FileNotFoundError:
                pass


store = Store(DATA_DIR)


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    return prefix + uuid.uuid4().hex[:10]


def date_fr(d: dt.datetime | None = None) -> str:
    d = d or dt.datetime.now()
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}, {d:%H:%M}"


def human_size(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    for unit in ("octets", "Ko", "Mo", "Go", "To"):
        if n < 1024 or unit == "To":
            if unit == "octets":
                return f"{int(n)} octets"
            return f"{n:.1f} {unit}".replace(".", ",").replace(",0 ", " ")
        n /= 1024
    return f"{n} To"


def to_bool(v, default=False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v).strip().lower() in ("1", "true", "vrai", "oui", "yes", "on")


# ════════════════════════════════════════════════════════════════════
#  Réglages
# ════════════════════════════════════════════════════════════════════
DEFAULT_SETTINGS = {
    "ollama_url": "http://127.0.0.1:11434",
    "model": "qwen3.5:4b",
    "num_ctx": 8192,
    "temperature": 0.6,
    "think": False,
    "keep_alive": "15m",
    "prenom": "Cyril",
    "system_prompt": (
        "Tu es l'Archiviste, l'assistant personnel de {prenom}. Tu tournes en local "
        "sur son PC Linux Mint. Réponds toujours en français, de façon claire, directe "
        "et structurée. Si tu ne sais pas, dis-le simplement."
    ),
    "roots": [str(HOME)],
    "show_hidden": False,
    "theme": "auto",
    "maj_auto": True,
    "index_contenu": True,   # la recherche instantanée lit aussi le texte des documents (PDF, Word, notes…)
    "maj_ignoree": "",       # version qu'on a quittée en revenant à la précédente : elle n'est plus proposée d'office
    "gestionnaire_precedent": "",  # gestionnaire de fichiers d'avant Archiviste (rendu si on revient en arrière)
}


def keep_alive(s: dict):
    """Ollama attend un nombre pour « toujours » (-1) et une durée texte sinon."""
    ka = str(s.get("keep_alive", "15m")).strip()
    return -1 if ka in ("-1", "toujours") else ka


def get_settings() -> dict:
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    s.update(store.read("settings.json", dict))
    return s


def save_settings(body: dict) -> dict:
    with store.lock:
        return _save_settings(body)


def _save_settings(body: dict) -> dict:
    s = get_settings()
    for key in DEFAULT_SETTINGS:
        if key in body:
            s[key] = body[key]
    # validations
    s["ollama_url"] = str(s["ollama_url"]).strip().rstrip("/") or DEFAULT_SETTINGS["ollama_url"]
    s["model"] = str(s["model"]).strip() or DEFAULT_SETTINGS["model"]
    try:
        s["num_ctx"] = max(2048, min(262144, int(s["num_ctx"])))
    except (TypeError, ValueError):
        s["num_ctx"] = DEFAULT_SETTINGS["num_ctx"]
    try:
        s["temperature"] = max(0.0, min(2.0, float(s["temperature"])))
    except (TypeError, ValueError):
        s["temperature"] = DEFAULT_SETTINGS["temperature"]
    s["think"] = to_bool(s["think"])
    s["show_hidden"] = to_bool(s["show_hidden"])
    s["maj_auto"] = to_bool(s.get("maj_auto"), True)
    s["index_contenu"] = to_bool(s.get("index_contenu"), True)
    s["maj_ignoree"] = str(s.get("maj_ignoree") or "")[:20]
    s["gestionnaire_precedent"] = str(s.get("gestionnaire_precedent") or "")[:200]
    s["prenom"] = str(s["prenom"]).strip()[:40] or "Cyril"
    roots = []
    for r in s.get("roots") or []:
        rp = os.path.realpath(os.path.expanduser(str(r).strip()))
        if not os.path.isdir(rp):
            raise ApiError(f"Le dossier autorisé « {r} » n'existe pas.")
        if rp == "/":
            raise ApiError("Autoriser tout le disque (« / ») est trop risqué : choisis des dossiers précis.")
        if rp not in roots:
            roots.append(rp)
    s["roots"] = roots or [str(HOME)]
    store.write("settings.json", s)
    return s


# ════════════════════════════════════════════════════════════════════
#  Sécurité des chemins
# ════════════════════════════════════════════════════════════════════
def allowed_roots(settings: dict | None = None, volumes_too: bool = True) -> list[str]:
    s = settings or get_settings()
    out = []
    for r in s.get("roots") or []:
        rp = os.path.realpath(os.path.expanduser(r))
        if os.path.isdir(rp):
            out.append(rp)
    out = out or [os.path.realpath(str(HOME))]
    desk = desktop_dir()  # le bureau reste toujours accessible
    if desk != "/" and os.path.isdir(desk) and not any(within(desk, r) for r in out):
        out.append(desk)
    if volumes_too:  # clés USB et disques branchés : on peut y ranger, copier, extraire, comme dans Nemo
        for v in volumes():
            if not any(within(v["path"], r) for r in out):
                out.append(v["path"])
    return out


def within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def safe_path(p, base: str | None = None, roots: list[str] | None = None,
              must_exist: bool = False, nofollow: bool = False) -> str:
    """Chemin réel, vérifié dans les dossiers autorisés. Avec nofollow, un lien symbolique reste le lien
    lui-même (pour le renommer, le déplacer ou le mettre à la corbeille sans toucher à sa cible)."""
    roots = roots or allowed_roots()
    p = str(p or "").strip()
    if "\x00" in p:
        raise ApiError("Chemin invalide.")
    if not p or p == ".":
        p = base or roots[0]
    if p.startswith("~"):
        p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.join(base or roots[0], p)
    real = lexical_path(p) if nofollow else os.path.realpath(p)
    if not any(within(real, r) for r in roots):
        raise ApiError(f"Accès refusé : « {p} » est en dehors des dossiers autorisés.", 403)
    if must_exist and not os.path.lexists(real):
        raise ApiError(f"Introuvable : « {p} ».", 404)
    return real


def lexical_path(p: str) -> str:
    """Dossier parent résolu (liens suivis), dernier élément gardé tel quel : désigne un lien, pas sa cible."""
    p = os.path.normpath(p)
    folder, name = os.path.split(p)
    if not name:
        return os.path.realpath(p)
    return os.path.join(os.path.realpath(folder), name)


def link_target(link: str) -> str:
    """Cible d'un lien symbolique, en chemin absolu."""
    t = os.readlink(link)
    return t if os.path.isabs(t) else os.path.normpath(os.path.join(os.path.dirname(link), t))


def move_entry(src: str, target: str) -> None:
    """Déplace un élément. Un lien symbolique relatif changé de dossier est recréé vers la même cible,
    sinon il ne mènerait plus nulle part."""
    if os.path.islink(src) and not os.path.isabs(os.readlink(src)) \
            and os.path.dirname(target) != os.path.dirname(src):
        os.symlink(link_target(src), target)
        os.unlink(src)
    else:
        shutil.move(src, target)


def is_root(path: str, roots: list[str] | None = None) -> bool:
    return path in (roots or allowed_roots())


def check_name(name: str) -> str:
    name = str(name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\x00" in name:
        raise ApiError("Nom invalide (pas de « / », pas vide).")
    if len(name.encode("utf-8")) > 255:
        raise ApiError("Nom trop long.")
    return name


def changed(*paths: str) -> None:
    """À appeler après avoir créé, modifié, déplacé ou supprimé un élément : l'index de recherche relit
    tout de suite son dossier (sinon il ne le verrait qu'à son prochain passage)."""
    idx = INDEX
    if idx is not None:
        try:
            idx.touch(*{os.path.dirname(p) for p in paths if p})
        except Exception:  # noqa: BLE001 — l'index ne doit jamais faire échouer une opération sur les fichiers
            pass


INDEX = None  # index de recherche (indexeur.py), mis en route par prepare()


def unique_path(path: str) -> str:
    if not os.path.lexists(path):
        return path
    folder, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    if not stem:
        stem, ext = name, ""
    i = 2
    while True:
        cand = os.path.join(folder, f"{stem} ({i}){ext}")
        if not os.path.lexists(cand):
            return cand
        i += 1


# ════════════════════════════════════════════════════════════════════
#  Types de fichiers
# ════════════════════════════════════════════════════════════════════
CATEGORIES = [
    ("Images", "image", "jpg jpeg png gif webp heic heif bmp svg tif tiff avif raw cr2 cr3 nef arw dng ico psd xcf kra"),
    ("Vidéos", "video", "mp4 mov mkv avi webm m4v wmv flv mpg mpeg 3gp mts m2ts"),
    ("Musique", "audio", "mp3 flac wav ogg oga opus m4a aac wma aiff mid midi"),
    ("Documents", "doc", "pdf doc docx odt rtf txt md markdown tex wpd pages"),
    ("Tableurs", "sheet", "xls xlsx xlsm ods csv tsv numbers"),
    ("Présentations", "slides", "ppt pptx odp key"),
    ("Livres", "book", "epub mobi azw azw3 fb2 cbz cbr djvu"),
    ("Archives", "archive", "zip rar 7z tar gz tgz bz2 xz zst lz lzma"),
    ("Code", "code", "py js mjs cjs ts tsx jsx html htm css scss sass less json yaml yml toml xml sh bash zsh fish "
                     "ps1 bat cmd c h cpp hpp cc cs java kt go rs rb php sql lua r ipynb vue svelte dart swift pl"),
    ("Logiciels", "app", "exe msi deb rpm appimage flatpakref snap dmg apk iso img run"),
    ("Plans et 3D", "cad", "dwg dxf stl obj step stp 3mf blend fbx skp ifc gcode"),
    ("Polices", "font", "ttf otf woff woff2"),
]
EXT_KIND: dict[str, str] = {}
EXT_CAT: dict[str, str] = {}
for _cat, _kind, _exts in CATEGORIES:
    for _e in _exts.split():
        EXT_KIND[_e] = _kind
        EXT_CAT[_e] = _cat

TEXT_EXTS = set(
    "txt md markdown rst log ini conf cfg cnf env properties desktop service srt vtt sub csv tsv json jsonl yaml "
    "yml toml xml svg html htm css scss sass less js mjs cjs ts tsx jsx py pyw sh bash zsh fish ps1 bat cmd c h "
    "cpp hpp cc cs java kt go rs rb php sql lua r tex bib gitignore dockerfile makefile vue svelte dart swift pl "
    "gcode ics vcf nfo".split()
)
IMAGE_EXTS_VISION = {"png", "jpg", "jpeg", "webp"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".cache", ".venv", "venv", ".mypy_cache", ".pytest_cache",
             ".Trash", ".Trash-1000", "Trash", ".npm", ".cargo", ".rustup", ".local", ".steam", ".wine"}


def ext_of(name: str) -> str:
    base = name.lower()
    if base in ("makefile", "dockerfile"):
        return base
    if base.endswith((".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst")):
        return base.rsplit(".", 1)[1]
    return os.path.splitext(base)[1].lstrip(".")


def entry_info(path: str, name: str | None = None) -> dict:
    name = name or os.path.basename(path) or path
    try:
        st = os.stat(path)
        broken = False
    except OSError:
        st = os.lstat(path)
        broken = True
    is_dir = stat.S_ISDIR(st.st_mode)
    ext = "" if is_dir else ext_of(name)
    return {
        "name": name,
        "path": path,
        "dir": is_dir,
        "size": None if is_dir else st.st_size,
        "mtime": st.st_mtime,
        "ext": ext,
        "kind": "folder" if is_dir else EXT_KIND.get(ext, "text" if ext in TEXT_EXTS else "file"),
        "hidden": name.startswith("."),
        "link": os.path.islink(path),
        "broken": broken,
    }


def sort_key(e: dict):
    return (not e["dir"], e["name"].casefold())


# ════════════════════════════════════════════════════════════════════
#  Lecture du contenu (texte, PDF, Word, LibreOffice, Excel, PowerPoint)
# ════════════════════════════════════════════════════════════════════
def _xml_text(xml: str, para_tags: list[str], extra: dict | None = None) -> str:
    for tag in para_tags:
        xml = xml.replace(f"</{tag}>", f"</{tag}>\n")
    for k, v in (extra or {}).items():
        xml = re.sub(k, v, xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _xlsx_text(z: zipfile.ZipFile, limit: int) -> str:
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        sx = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
        for si in re.findall(r"<si>(.*?)</si>", sx, re.S):
            shared.append(html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", si, re.S))))
    sheets = sorted(
        (n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)),
        key=lambda n: int(re.search(r"(\d+)", n.rsplit("/", 1)[1]).group(1)),
    )
    out, total = [], 0
    for sn in sheets:
        out.append(f"--- Feuille {sn.rsplit('sheet', 1)[1][:-4]} ---")
        xml = z.read(sn).decode("utf-8", "replace")
        for row in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S)[:1000]:
            vals = []
            for attrs, inner in re.findall(r"<c\b([^>]*?)>(.*?)</c>", row, re.S):
                t = re.search(r'\bt="(\w+)"', attrs)
                v = re.search(r"<v>(.*?)</v>", inner, re.S)
                if t and t.group(1) == "s" and v:
                    try:
                        vals.append(shared[int(v.group(1))])
                    except (ValueError, IndexError):
                        vals.append("")
                elif t and t.group(1) == "inlineStr":
                    vals.append(html.unescape("".join(re.findall(r"<t[^>]*>(.*?)</t>", inner, re.S))))
                elif v:
                    vals.append(html.unescape(v.group(1)))
            line = "\t".join(vals)
            out.append(line)
            total += len(line)
            if total > limit:
                return "\n".join(out)
    return "\n".join(out)


def extract_text(path: str, limit: int = 12000) -> tuple[str | None, str]:
    """Renvoie (texte, note). texte=None si le fichier n'est pas lisible comme du texte."""
    ext = ext_of(path)
    try:
        if ext == "pdf":
            if not shutil.which("pdftotext"):
                return None, "PDF : installe « poppler-utils » pour lire les PDF (sudo apt install poppler-utils)."
            r = subprocess.run(["pdftotext", "-layout", "-l", "40", path, "-"],
                               capture_output=True, timeout=60)
            txt = r.stdout.decode("utf-8", "replace").strip()
            if not txt:
                return None, "PDF sans texte (probablement scanné)."
            return txt[:limit], "PDF"
        if ext in ("docx", "docm", "dotx"):
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            txt = _xml_text(xml, ["w:p"], {r"<w:tab/>": "\t", r"<w:br/>": "\n"})
            return txt[:limit], "Word"
        if ext in ("odt", "ods", "odp", "ott"):
            with zipfile.ZipFile(path) as z:
                xml = z.read("content.xml").decode("utf-8", "replace")
            txt = _xml_text(xml, ["text:p", "text:h", "table:table-row"],
                            {r"<text:tab/>": "\t", r"<text:line-break/>": "\n", r"<text:s[^>]*/>": " ",
                             r"</table:table-cell>": "\t"})
            return txt[:limit], "LibreOffice"
        if ext in ("xlsx", "xlsm"):
            with zipfile.ZipFile(path) as z:
                return _xlsx_text(z, limit)[:limit], "Excel"
        if ext == "pptx":
            with zipfile.ZipFile(path) as z:
                slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                                key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
                parts = []
                for i, sn in enumerate(slides, 1):
                    parts.append(f"--- Diapo {i} ---\n" + _xml_text(z.read(sn).decode("utf-8", "replace"), ["a:p"]))
            return "\n".join(parts)[:limit], "PowerPoint"
        if EXT_KIND.get(ext) in ("image", "video", "audio", "archive", "app", "font") and ext not in TEXT_EXTS:
            return None, "Fichier binaire (pas de texte à lire)."
        with open(path, "rb") as f:
            raw = f.read(limit * 4 + 4)
        if b"\x00" in raw[:8192]:
            return None, "Fichier binaire (pas de texte à lire)."
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                txt = raw[:-3].decode("utf-8")
            except UnicodeDecodeError:
                txt = raw.decode("latin-1")
        return txt[:limit], "texte"
    except (zipfile.BadZipFile, KeyError):
        return None, "Document illisible ou abîmé."
    except subprocess.TimeoutExpired:
        return None, "Lecture du PDF trop longue."
    except PermissionError:
        return None, "Permission refusée."
    except OSError as e:
        return None, f"Lecture impossible : {e.strerror or e}"


# ════════════════════════════════════════════════════════════════════
#  Opérations sur les fichiers
# ════════════════════════════════════════════════════════════════════
def fs_list(path: str, show_hidden: bool) -> dict:
    roots = allowed_roots()
    real = safe_path(path, roots=roots, must_exist=True)
    if not os.path.isdir(real):
        raise ApiError("Ce n'est pas un dossier.")
    entries = []
    try:
        with os.scandir(real) as it:
            for de in it:
                if not show_hidden and de.name.startswith("."):
                    continue
                try:
                    entries.append(entry_info(de.path, de.name))
                except OSError:
                    continue
    except PermissionError:
        raise ApiError("Permission refusée sur ce dossier.", 403)
    entries.sort(key=sort_key)
    root = next((r for r in roots if within(real, r)), roots[0])
    parent = os.path.dirname(real) if real != root else None
    return {"path": real, "root": root, "parent": parent, "entries": entries, "volumes": volumes()}


def backup_version(path: str) -> str | None:
    """Copie de l'état actuel d'un fichier, avant de le modifier. Gardées : les 300 dernières, 2 Go au plus."""
    if not os.path.isfile(path):
        return None
    vdir = DATA_DIR / "versions"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = vdir / f"{stamp}__{os.path.basename(path)}"
    k = 1
    while dest.exists():  # deux modifications dans la même seconde : aucune ne remplace l'autre
        k += 1
        dest = vdir / f"{stamp}-{k}__{os.path.basename(path)}"
    shutil.copy2(path, dest)
    (vdir / f"{dest.name}.origine").write_text(path, "utf-8")
    olds = sorted(p for p in vdir.iterdir() if not p.name.endswith(".origine"))
    drop = olds[:-MAX_VERSIONS] if len(olds) > MAX_VERSIONS else []
    keep = olds[len(drop):]
    total = 0
    for i in range(len(keep) - 1, -1, -1):  # des plus récentes aux plus anciennes, jusqu'à la limite de place
        try:
            total += keep[i].stat().st_size
        except OSError:
            continue
        if total > MAX_VERSIONS_BYTES and i < len(keep) - 1:
            drop += keep[:i + 1]
            break
    for p in drop:
        p.unlink(missing_ok=True)
        (vdir / f"{p.name}.origine").unlink(missing_ok=True)
    return str(dest)


VERSION_RE = re.compile(r"^(\d{8})-(\d{6})(?:-(\d+))?__(.+)$")


def _version_file(vid: str) -> tuple[Path, str]:
    """Fichier d'une ancienne version et chemin du fichier d'origine (vérifié dans les dossiers autorisés)."""
    if "/" in vid or not VERSION_RE.match(vid or ""):
        raise ApiError("Version invalide.", 404)
    f = DATA_DIR / "versions" / vid
    try:
        orig = (DATA_DIR / "versions" / f"{vid}.origine").read_text("utf-8").strip()
    except OSError:
        raise ApiError("Cette version n'existe plus.", 404)
    if not f.is_file():
        raise ApiError("Cette version n'existe plus.", 404)
    return f, safe_path(orig)


def list_versions(path: str) -> dict:
    """Anciennes versions d'un fichier, de la plus récente à la plus ancienne."""
    real = safe_path(path)
    vdir = DATA_DIR / "versions"
    out = []
    for o in vdir.glob("*.origine"):
        vid = o.name[:-len(".origine")]
        m = VERSION_RE.match(vid)
        f = vdir / vid
        try:
            if not m or o.read_text("utf-8").strip() != real or not f.is_file():
                continue
            d = dt.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            out.append({"id": vid, "date": d.isoformat(timespec="seconds"), "taille": f.stat().st_size,
                        "rang": int(m.group(3) or 1)})
        except (OSError, ValueError):
            continue
    out.sort(key=lambda v: (v["date"], v["rang"]), reverse=True)
    cur = None
    if os.path.isfile(real):
        st = os.stat(real)
        cur = {"taille": st.st_size, "date": dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
    return {"path": real, "nom": os.path.basename(real), "actuelle": cur, "versions": out}


def restore_version(vid: str) -> dict:
    """Remet une ancienne version à la place du fichier. L'état actuel est d'abord gardé : rien n'est perdu."""
    f, dest = _version_file(vid)
    if os.path.isdir(dest):
        raise ApiError("Un dossier porte maintenant ce nom.")
    saved = backup_version(dest) if os.path.isfile(dest) else None
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".archiviste-tmp"
    shutil.copy2(f, tmp)
    os.replace(tmp, dest)
    changed(dest)
    return {"path": dest, "version": vid, "sauvegarde": bool(saved)}


def file_encoding(path: str) -> str:
    """« utf-8 », ou « latin-1 » pour un vieux fichier texte (Windows, anciens logiciels) qui n'est pas en UTF-8."""
    try:
        with open(path, "rb") as f:
            raw = f.read(2_000_000)
    except OSError:
        return "utf-8"
    for cut in (0, 1, 2, 3):  # la lecture a pu couper un caractère en deux
        try:
            raw[:len(raw) - cut].decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            continue
    return "latin-1"


def fs_write(path: str, content: str, roots=None, base=None, mode: str = "remplacer",
             encoding: str | None = None) -> dict:
    """Écrit un fichier texte. Un fichier existant garde son encodage (latin-1 reste latin-1) tant que le
    texte le permet ; sinon il passe en UTF-8, et « encodage » le dit."""
    real = safe_path(path, base=base, roots=roots)
    if os.path.isdir(real):
        raise ApiError("Impossible d'écrire : c'est un dossier.")
    existed = os.path.exists(real)
    os.makedirs(os.path.dirname(real), exist_ok=True)
    wanted = str(encoding or (file_encoding(real) if existed else "utf-8")).lower()
    enc = "utf-8"
    if wanted in ("latin-1", "latin1", "iso-8859-1"):
        try:
            content.encode("latin-1")
            enc = "latin-1"
        except UnicodeEncodeError:
            enc = "utf-8"  # un caractère absent du latin-1 (€, œ, émoji…) : on ne peut plus le garder
    version = backup_version(real) if existed else None
    if mode == "ajouter" and existed and enc == file_encoding(real):
        with open(real, "a", encoding=enc) as f:
            f.write(content)
    else:
        if mode == "ajouter" and existed:  # changement d'encodage : on réécrit tout pour ne pas mélanger les deux
            with open(real, encoding=file_encoding(real), errors="replace") as f:
                content = f.read() + content
        tmp = real + ".archiviste-tmp"
        with open(tmp, "w", encoding=enc) as f:
            f.write(content)
        if existed:
            shutil.copymode(real, tmp)
        os.replace(tmp, real)
    changed(real)
    return {"path": real, "cree": not existed, "ancienne_version": version, "taille": os.path.getsize(real),
            "encodage": enc}


def fs_mkdir(path: str, roots=None, base=None) -> dict:
    real = safe_path(path, base=base, roots=roots)
    if os.path.exists(real):
        if os.path.isdir(real):
            return {"path": real, "existait": True}
        raise ApiError("Un fichier porte déjà ce nom.")
    os.makedirs(real)
    changed(real, os.path.join(real, "x"))
    return {"path": real, "existait": False}


def move_plan(src: str, dest: str, roots=None, base=None, copy: bool = False) -> tuple[str, str | None]:
    """Vérifie un déplacement ou une copie et choisit le nom d'arrivée (None : rien à faire, déjà là)."""
    roots = roots or allowed_roots()
    s = safe_path(src, base=base, roots=roots, must_exist=True, nofollow=True)
    if is_root(s, roots) and not copy:
        raise ApiError("On ne déplace pas un dossier racine autorisé.")
    d = safe_path(dest, base=base, roots=roots)
    if os.path.isdir(d):
        target = os.path.join(d, os.path.basename(s))
    else:
        target = d
        os.makedirs(os.path.dirname(target), exist_ok=True)
    if not os.path.islink(s) and os.path.isdir(s) and within(os.path.realpath(target), s):
        raise ApiError("Impossible de mettre un dossier dans lui-même.")
    if lexical_path(target) == s and not copy:
        return s, None
    return s, unique_path(target)


def fs_move(src: str, dest: str, roots=None, base=None, copy: bool = False) -> dict:
    roots = roots or allowed_roots()
    s = safe_path(src, base=base, roots=roots, must_exist=True, nofollow=True)  # un lien : le lien, pas sa cible
    if is_root(s, roots) and not copy:
        raise ApiError("On ne déplace pas un dossier racine autorisé.")
    d = safe_path(dest, base=base, roots=roots)
    if os.path.isdir(d):
        target = os.path.join(d, os.path.basename(s))
    else:
        target = d
        os.makedirs(os.path.dirname(target), exist_ok=True)
    link = os.path.islink(s)
    if not link and os.path.isdir(s) and within(os.path.realpath(target), s):
        raise ApiError("Impossible de mettre un dossier dans lui-même.")
    if lexical_path(target) == s and not copy:
        return {"de": s, "vers": s, "inchange": True}
    target = unique_path(target)  # copié dans son propre dossier : un double, « nom (2) »
    if copy:
        if link:
            os.symlink(link_target(s), target)
        elif os.path.isdir(s):
            shutil.copytree(s, target, symlinks=True)
        else:
            shutil.copy2(s, target)
    else:
        move_entry(s, target)
    changed(s, target, os.path.join(target, "x"))
    return {"de": s, "vers": target}


def fs_rename(path: str, new_name: str, roots=None, base=None) -> dict:
    roots = roots or allowed_roots()
    s = safe_path(path, base=base, roots=roots, must_exist=True, nofollow=True)
    if is_root(s, roots):
        raise ApiError("On ne renomme pas un dossier racine autorisé.")
    new_name = check_name(new_name)
    target = os.path.join(os.path.dirname(s), new_name)
    if os.path.lexists(target) and target != s:
        raise ApiError(f"« {new_name} » existe déjà ici.")
    os.rename(s, target)
    changed(s, os.path.join(target, "x"))
    return {"de": s, "vers": target}


# ── Corbeille (norme freedesktop : visible et restaurable depuis Nemo) ──
def trash(path: str, roots=None, base=None) -> dict:
    roots = roots or allowed_roots()
    real = safe_path(path, base=base, roots=roots, must_exist=True, nofollow=True)
    if is_root(real, roots):
        raise ApiError("On ne met pas un dossier racine autorisé à la corbeille.")
    if not os.path.islink(real) and within(str(TRASH_DIR), real):
        raise ApiError("Ce dossier contient la corbeille elle-même.")
    files, info = TRASH_DIR / "files", TRASH_DIR / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    name = os.path.basename(real)
    stem, ext = os.path.splitext(name)
    cand, i = name, 1
    while True:
        try:
            fd = os.open(info / f"{cand}.trashinfo", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            break
        except FileExistsError:
            i += 1
            cand = f"{stem}.{i}{ext}"
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("[Trash Info]\n")
        f.write("Path=" + urllib.parse.quote(real) + "\n")
        f.write("DeletionDate=" + dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S") + "\n")
    try:
        shutil.move(real, files / cand)
    except Exception:
        (info / f"{cand}.trashinfo").unlink(missing_ok=True)
        raise
    changed(real)
    return {"path": real, "corbeille": cand}


def trash_list() -> list[dict]:
    info = TRASH_DIR / "info"
    out = []
    if not info.is_dir():
        return out
    for p in info.glob("*.trashinfo"):
        tid = p.name[: -len(".trashinfo")]
        orig, date = "", ""
        try:
            for line in p.read_text("utf-8", "replace").splitlines():
                if line.startswith("Path="):
                    orig = urllib.parse.unquote(line[5:])
                elif line.startswith("DeletionDate="):
                    date = line[13:]
        except OSError:
            continue
        f = TRASH_DIR / "files" / tid
        if not os.path.lexists(f):
            continue
        is_dir = f.is_dir()
        size = None if is_dir else (f.stat().st_size if f.exists() else 0)
        out.append({"id": tid, "name": os.path.basename(orig) or tid, "origine": orig, "date": date,
                    "dir": is_dir, "size": size, "ext": "" if is_dir else ext_of(tid)})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def _trash_item(tid: str) -> tuple[Path, Path]:
    if "/" in tid or tid in ("", ".", ".."):
        raise ApiError("Élément de corbeille invalide.")
    return TRASH_DIR / "files" / tid, TRASH_DIR / "info" / f"{tid}.trashinfo"


def trash_restore(tid: str) -> dict:
    f, i = _trash_item(tid)
    if not os.path.lexists(f):
        raise ApiError("Élément introuvable dans la corbeille.", 404)
    orig = ""
    for line in i.read_text("utf-8", "replace").splitlines():
        if line.startswith("Path="):
            orig = urllib.parse.unquote(line[5:])
    if not orig:
        raise ApiError("Origine inconnue.")
    dest = safe_path(orig)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    dest = unique_path(dest)
    shutil.move(str(f), dest)
    i.unlink(missing_ok=True)
    changed(dest, os.path.join(dest, "x"))
    return {"restaure": dest}


def trash_purge(tid: str) -> dict:
    f, i = _trash_item(tid)
    if f.is_dir() and not f.is_symlink():
        shutil.rmtree(f)
    elif os.path.lexists(f):
        f.unlink()
    i.unlink(missing_ok=True)
    return {"supprime": tid}


# ── Recherche & doublons ──
def walk_files(base: str, show_hidden: bool, max_items: int = 20000, deadline: float | None = None,
               etat: dict | None = None):
    """Parcourt les fichiers d'un dossier. Si le parcours s'arrête avant la fin, etat["coupe"] dit pourquoi :
    « temps » (délai dépassé) ou « limite » (trop de fichiers)."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and (show_hidden or not d.startswith(".")))
        for name in sorted(filenames):
            if not show_hidden and name.startswith("."):
                continue
            if count >= max_items or (deadline and time.time() > deadline):
                if etat is not None:
                    etat["coupe"] = "limite" if count >= max_items else "temps"
                return
            yield dirpath, dirnames, name
            count += 1


def index_text_ok(name: str, size: int) -> bool:
    """Documents dont l'index retient le texte : notes et textes, PDF, Word, LibreOffice, Excel, PowerPoint."""
    ext = ext_of(name)
    if ext == "pdf":
        return size < 40_000_000
    if ext in ("docx", "docm", "dotx", "odt", "ods", "odp", "ott", "xlsx", "xlsm", "pptx"):
        return size < 25_000_000
    return ext in TEXT_EXTS and size < 2_000_000


def start_index() -> None:
    """Met en route l'index de recherche (indexeur.py). Sans lui, la recherche reparcourt le disque comme avant."""
    global INDEX
    if INDEX is not None or os.environ.get("ARCHIVISTE_SANS_INDEX"):
        return
    try:
        import indexeur
        # les clés USB ne sont pas indexées : elles vont et viennent, et peuvent être énormes
        INDEX = indexeur.Indexeur(DATA_DIR / "index.sqlite", lambda: allowed_roots(volumes_too=False), SKIP_DIRS, extract_text, _fold,
                                  index_text_ok, lambda: bool(get_settings().get("index_contenu", True)))
        INDEX.start()
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        INDEX = None


def _index_search(idx, real: str, q: str, in_content: bool, limit: int, fresh: bool) -> dict:
    """Recherche par l'index : immédiate, sur tout le dossier. « fresh » : on vérifie d'abord (1,5 s au plus)
    que rien n'a bougé dans ce dossier, pour trouver aussi ce qui vient d'être créé ailleurs que dans Archiviste."""
    # bloquant pour une vraie recherche ; pour la saisie du volet (réponse immédiate), simple demande de
    # vérification en arrière-plan, au plus toutes les 20 secondes : la frappe suivante en profite
    a_jour = idx.refresh(real, max_age=0) if fresh else idx.refresh(real, timeout=0, max_age=20)
    r = idx.search(real, q, contenu=in_content, limit=limit)
    results = []
    for path, extrait in [(p, None) for p, _ in r["noms"]] + r["textes"]:
        try:
            e = entry_info(path)  # tailles et dates relues sur le disque ; un élément disparu est écarté
        except OSError:
            continue
        if extrait:
            e["extrait"] = extrait
        results.append(e)
    cut = "limite" if r["coupe"] else ("contenu" if in_content and r["a_lire"] else None)
    return {"base": real, "query": q, "results": results, "tronque": r["coupe"], "incomplet": cut,
            "delai": 0, "index": True, "a_lire": r["a_lire"], "verifie": a_jour}


def fs_search(base: str, query: str, in_content: bool, roots=None, show_hidden=False, limit=300,
              delay: float = 12, fresh: bool = True) -> dict:
    """Cherche par nom (et dans le contenu si demandé). Par l'index de recherche quand il est prêt (réponse
    immédiate) ; sinon en parcourant le disque, en un seul passage. Si la recherche n'a pas tout vu,
    « incomplet » dit pourquoi : « temps » (délai dépassé), « limite » (trop de résultats) ou « contenu »
    (l'index n'a pas encore lu tous les documents)."""
    real = safe_path(base, roots=roots, must_exist=True)
    q = (query or "").strip()
    if not q:
        raise ApiError("Que faut-il chercher ?")
    wildcard = any(c in q for c in "*?[")
    idx = INDEX
    if idx is not None and not show_hidden and "[" not in q and idx.covers(real):
        return _index_search(idx, real, q, in_content and not wildcard, limit, fresh)
    ql = q.casefold()
    match = (lambda n: fnmatch(n.casefold(), ql)) if wildcard else (lambda n: ql in n.casefold())
    results, cut, deadline = [], None, time.time() + delay
    max_dirs, ndirs = max(1, limit // 3), 0
    for dirpath, dirnames, filenames in os.walk(real):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and (show_hidden or not d.startswith(".")))
        for d in dirnames:
            if ndirs < max_dirs and match(d):
                try:
                    results.append(entry_info(os.path.join(dirpath, d), d))
                    ndirs += 1
                except OSError:
                    pass
        for name in sorted(filenames):
            if not show_hidden and name.startswith("."):
                continue
            if time.time() > deadline:
                cut = "temps"
                break
            full = os.path.join(dirpath, name)
            hit = match(name)
            snippet = None
            if not hit and in_content and not wildcard:
                try:
                    if os.path.getsize(full) < 3_000_000:
                        txt, _ = extract_text(full, 200000)
                        if txt:
                            pos = txt.casefold().find(ql)
                            if pos >= 0:
                                hit = True
                                snippet = txt[max(0, pos - 60): pos + 100].replace("\n", " ")
                except OSError:
                    pass
            if hit:
                try:
                    e = entry_info(full, name)
                except OSError:
                    continue
                if snippet:
                    e["extrait"] = snippet
                results.append(e)
                if len(results) >= limit:
                    cut = "limite"
                    break
        if cut:
            break
        if time.time() > deadline:
            cut = "temps"
            break
    results.sort(key=lambda e: not e["dir"])  # dossiers d'abord, sans changer l'ordre du reste
    return {"base": real, "query": q, "results": results, "tronque": cut is not None, "incomplet": cut,
            "delai": delay}


def find_duplicates(base: str, roots=None, show_hidden=False) -> dict:
    real = safe_path(base, roots=roots, must_exist=True)
    by_size: dict[int, list[str]] = {}
    etat: dict = {}
    for dirpath, _, name in walk_files(real, show_hidden, 30000, time.time() + 40, etat):
        full = os.path.join(dirpath, name)
        try:
            if os.path.islink(full):
                continue
            sz = os.path.getsize(full)
        except OSError:
            continue
        if sz > 0:
            by_size.setdefault(sz, []).append(full)

    def digest(p, partial):
        h = hashlib.sha1()
        with open(p, "rb") as f:
            if partial:
                h.update(f.read(65536))
            else:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        return h.hexdigest()

    groups = []
    for sz, paths in by_size.items():
        if len(paths) < 2:
            continue
        first: dict[str, list[str]] = {}
        for p in paths:
            try:
                first.setdefault(digest(p, True), []).append(p)
            except OSError:
                pass
        for cands in first.values():
            if len(cands) < 2:
                continue
            full: dict[str, list[str]] = {}
            for p in cands:
                try:
                    full.setdefault(digest(p, sz <= 65536), []).append(p)
                except OSError:
                    pass
            for same in full.values():
                if len(same) > 1:
                    groups.append({"taille": sz, "taille_lisible": human_size(sz), "fichiers": same})
    groups.sort(key=lambda g: g["taille"] * (len(g["fichiers"]) - 1), reverse=True)
    gain = sum(g["taille"] * (len(g["fichiers"]) - 1) for g in groups)
    return {"dossier": real, "groupes": groups[:100], "nb_groupes": len(groups),
            "place_recuperable": human_size(gain), "incomplet": etat.get("coupe")}


# ════════════════════════════════════════════════════════════════════
#  Ollama
# ════════════════════════════════════════════════════════════════════
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def ollama_open(path: str, payload=None, timeout: float = 900):
    s = get_settings()
    url = s["ollama_url"].rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        return _opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            msg = json.loads(body).get("error", body)
        except json.JSONDecodeError:
            msg = body
        raise OllamaError(_explain_ollama_error(msg, payload), e.code)
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        raise OllamaError(
            f"Ollama est injoignable à {s['ollama_url']} ({reason}). "
            "Vérifie qu'il tourne : « systemctl status ollama » ou lance « ollama serve ».", 0)


def _explain_ollama_error(msg: str, payload) -> str:
    low = (msg or "").lower()
    model = (payload or {}).get("model", "")
    if "not found" in low and "model" in low:
        return f"Le modèle « {model} » n'est pas installé. Dans un terminal : ollama pull {model}"
    if "does not support tools" in low:
        return (f"Le modèle « {model} » ne gère pas les outils : choisis un autre modèle pour cet agent, "
                "ou décoche ses outils.")
    return msg


def ollama_json(path: str, payload=None, timeout: float = 900) -> dict:
    payload = dict(payload) if payload else payload
    try:
        resp = ollama_open(path, payload, timeout)
    except OllamaError as e:
        if payload and "think" in payload and "think" in str(e).lower():
            payload.pop("think")
            resp = ollama_open(path, payload, timeout)
        else:
            raise
    with resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_status() -> dict:
    s = get_settings()
    out = {"ok": False, "url": s["ollama_url"], "model": s["model"], "models": [], "model_present": False}
    try:
        out["version"] = ollama_json("/api/version", timeout=4).get("version")
        tags = ollama_json("/api/tags", timeout=6).get("models", [])
        out["models"] = [{"name": m.get("name"), "size": m.get("size"),
                          "taille": human_size(m.get("size")),
                          "params": (m.get("details") or {}).get("parameter_size"),
                          "quant": (m.get("details") or {}).get("quantization_level")} for m in tags]
        names = {m["name"] for m in out["models"]}
        out["model_present"] = s["model"] in names or f"{s['model']}:latest" in names
        out["ok"] = True
    except OllamaError as e:
        out["error"] = str(e)
    return out


def ollama_chat_stream(payload: dict, on_thinking, on_content) -> dict:
    payload = dict(payload)
    try:
        resp = ollama_open("/api/chat", payload)
    except OllamaError as e:
        if "think" in payload and "think" in str(e).lower():
            payload.pop("think")
            resp = ollama_open("/api/chat", payload)
        else:
            raise
    content, thinking, tool_calls, stats = [], [], [], {}
    try:
        for raw in resp:
            line = raw.strip()
            if not line:
                continue
            chunk = json.loads(line)
            if chunk.get("error"):
                raise OllamaError(_explain_ollama_error(chunk["error"], payload))
            msg = chunk.get("message") or {}
            if msg.get("thinking"):
                thinking.append(msg["thinking"])
                on_thinking(msg["thinking"])
            if msg.get("content"):
                content.append(msg["content"])
                on_content(msg["content"])
            if msg.get("tool_calls"):
                tool_calls.extend(msg["tool_calls"])
            if chunk.get("done"):
                stats = {k: chunk.get(k) for k in
                         ("eval_count", "eval_duration", "prompt_eval_count", "total_duration", "done_reason")}
    except ClientGone as cg:
        cg.partial = {"content": "".join(content), "thinking": "".join(thinking)}
        raise
    finally:
        resp.close()
    return {"content": "".join(content), "thinking": "".join(thinking),
            "tool_calls": tool_calls, "stats": stats}


# ════════════════════════════════════════════════════════════════════
#  Outils des agents
# ════════════════════════════════════════════════════════════════════
def _p(desc, typ="string", enum=None):
    d = {"type": typ, "description": desc}
    if enum:
        d["enum"] = enum
    return d


TOOLS = {
    "lister_dossier": {
        "label": "Lister un dossier", "modifie": False,
        "description": "Liste le contenu d'un dossier : noms, types, tailles et dates.",
        "properties": {"chemin": _p("Dossier à lister (relatif au dossier de travail, ou vide pour celui-ci)."),
                       "recursif": _p("true pour inclure les sous-dossiers (300 éléments max).", "boolean")},
        "required": [],
    },
    "lire_fichier": {
        "label": "Lire un fichier", "modifie": False,
        "description": "Lit le texte d'un fichier (txt, md, code, PDF, Word, LibreOffice, Excel, PowerPoint…).",
        "properties": {"chemin": _p("Fichier à lire."),
                       "max_caracteres": _p("Nombre maximum de caractères (défaut 8000).", "integer")},
        "required": ["chemin"],
    },
    "chercher_fichiers": {
        "label": "Chercher des fichiers", "modifie": False,
        "description": "Cherche des fichiers par nom (ex : facture, *.pdf) et, si demandé, dans leur contenu.",
        "properties": {"motif": _p("Mot ou motif à chercher (ex : facture, *.jpg)."),
                       "dossier": _p("Dossier où chercher (défaut : dossier de travail)."),
                       "dans_contenu": _p("true pour chercher aussi dans le texte des fichiers.", "boolean")},
        "required": ["motif"],
    },
    "infos_fichier": {
        "label": "Infos sur un fichier", "modifie": False,
        "description": "Donne la taille, les dates et le type d'un fichier ou d'un dossier.",
        "properties": {"chemin": _p("Fichier ou dossier.")},
        "required": ["chemin"],
    },
    "trouver_doublons": {
        "label": "Trouver les doublons", "modifie": False,
        "description": "Trouve les fichiers identiques (même contenu) dans un dossier et ses sous-dossiers.",
        "properties": {"dossier": _p("Dossier à analyser (défaut : dossier de travail).")},
        "required": [],
    },
    "creer_dossier": {
        "label": "Créer un dossier", "modifie": True,
        "description": "Crée un dossier (et ses parents si besoin).",
        "properties": {"chemin": _p("Dossier à créer.")},
        "required": ["chemin"],
    },
    "ecrire_fichier": {
        "label": "Écrire un fichier", "modifie": True,
        "description": "Crée ou modifie un fichier texte. L'ancienne version est sauvegardée automatiquement.",
        "properties": {"chemin": _p("Fichier à écrire."),
                       "contenu": _p("Texte complet à écrire."),
                       "mode": _p("remplacer (défaut) ou ajouter à la fin.", enum=["remplacer", "ajouter"])},
        "required": ["chemin", "contenu"],
    },
    "deplacer": {
        "label": "Déplacer", "modifie": True,
        "description": "Déplace un fichier ou dossier. Si la destination est un dossier existant, l'élément va dedans.",
        "properties": {"source": _p("Élément à déplacer."),
                       "destination": _p("Dossier de destination, ou nouveau chemin complet.")},
        "required": ["source", "destination"],
    },
    "copier": {
        "label": "Copier", "modifie": True,
        "description": "Copie un fichier ou dossier vers une destination.",
        "properties": {"source": _p("Élément à copier."),
                       "destination": _p("Dossier de destination, ou nouveau chemin complet.")},
        "required": ["source", "destination"],
    },
    "renommer": {
        "label": "Renommer", "modifie": True,
        "description": "Renomme un fichier ou dossier sans le déplacer.",
        "properties": {"chemin": _p("Élément à renommer."), "nouveau_nom": _p("Nouveau nom (avec l'extension).")},
        "required": ["chemin", "nouveau_nom"],
    },
    "creer_document": {
        "label": "Créer un document Word/Excel", "modifie": True,
        "description": ("Crée un document Word (.docx) ou un classeur Excel (.xlsx) qui s'ouvre dans Grimoire. "
                        "Le contenu s'écrit en Markdown : titres #, listes -, gras **, tableaux |. "
                        "Pour un .xlsx, chaque tableau Markdown devient un onglet."),
        "properties": {"chemin": _p("Fichier à créer, terminé par .docx ou .xlsx."),
                       "contenu": _p("Contenu en Markdown.")},
        "required": ["chemin", "contenu"],
    },
    "supprimer": {
        "label": "Mettre à la corbeille", "modifie": True,
        "description": "Met un fichier ou dossier à la corbeille (restaurable).",
        "properties": {"chemin": _p("Élément à mettre à la corbeille.")},
        "required": ["chemin"],
    },
    "ouvrir_application": {
        "label": "Ouvrir une application", "modifie": False,
        "description": ("Lance une application installée sur le PC (ex : Grimoire, Firefox, Terminal, "
                        "Calculatrice, LibreOffice). Utilise-le dès qu'on te demande d'ouvrir ou de lancer une appli. "
                        "Le nom peut être approximatif ou mal orthographié : l'outil trouve l'appli la plus proche."),
        "properties": {"nom": _p("Nom de l'application, tel que l'utilisateur l'a dit (ex : grimoire).")},
        "required": ["nom"],
    },
    "ouvrir": {
        "label": "Ouvrir un fichier ou un dossier", "modifie": False,
        "description": ("Ouvre un fichier avec son application (Word et Excel dans Grimoire) ou affiche un dossier. "
                        "Si tu ne connais pas le chemin exact, cherche d'abord avec chercher_fichiers."),
        "properties": {"chemin": _p("Fichier ou dossier à ouvrir.")},
        "required": ["chemin"],
    },
}
# Outils de la discussion libre (sans agent) : ouvrir des applis et des fichiers, chercher. Rien qui modifie.
FREE_TOOLS = ["ouvrir_application", "ouvrir", "chercher_fichiers"]


def tool_schemas(names: list[str]) -> list[dict]:
    out = []
    for n in names:
        t = TOOLS.get(n)
        if not t:
            continue
        out.append({"type": "function", "function": {
            "name": n, "description": t["description"],
            "parameters": {"type": "object", "properties": t["properties"], "required": t["required"]}}})
    return out


def _short(path: str, base: str | None) -> str:
    if base and within(path, base):
        rel = os.path.relpath(path, base)
        return "." if rel == "." else rel
    return path.replace(str(HOME), "~", 1)


def describe_action(name: str, args: dict) -> str:
    a = args or {}
    g = lambda k: str(a.get(k, "") or "")
    return {
        "creer_dossier": f"Créer le dossier « {g('chemin')} »",
        "ecrire_fichier": (f"Ajouter du texte à « {g('chemin')} »" if g("mode") == "ajouter"
                           else f"Écrire le fichier « {g('chemin')} » ({len(g('contenu'))} caractères)"),
        "deplacer": f"Déplacer « {g('source')} » vers « {g('destination')} »",
        "copier": f"Copier « {g('source')} » vers « {g('destination')} »",
        "renommer": f"Renommer « {g('chemin')} » en « {g('nouveau_nom')} »",
        "supprimer": f"Mettre « {g('chemin')} » à la corbeille",
        "creer_document": f"Créer le document « {g('chemin')} »",
        "lister_dossier": f"Lister « {g('chemin') or '.'} »",
        "lire_fichier": f"Lire « {g('chemin')} »",
        "chercher_fichiers": f"Chercher « {g('motif')} »",
        "infos_fichier": f"Infos sur « {g('chemin')} »",
        "trouver_doublons": f"Chercher les doublons dans « {g('dossier') or '.'} »",
        "ouvrir_application": f"Ouvrir l'application « {g('nom')} »",
        "ouvrir": f"Ouvrir « {g('chemin')} »",
    }.get(name, f"{name}({json.dumps(a, ensure_ascii=False)[:120]})")


def execute_tool(name: str, args: dict, ctx: dict) -> tuple[dict, str, bool]:
    """Exécute un outil. Renvoie (résultat, résumé lisible, succès)."""
    roots, base, hidden = ctx["roots"], ctx["base"], ctx["show_hidden"]
    a = args or {}
    try:
        if name not in ctx["allowed"]:
            raise ApiError(f"L'outil « {name} » n'est pas autorisé pour cet agent.")
        if name == "lister_dossier":
            path = safe_path(a.get("chemin"), base=base, roots=roots, must_exist=True)
            if not os.path.isdir(path):
                raise ApiError("Ce n'est pas un dossier.")
            items = []
            etat: dict = {}
            if to_bool(a.get("recursif")):
                for dirpath, dirnames, name_ in walk_files(path, hidden, 300, etat=etat):
                    full = os.path.join(dirpath, name_)
                    e = entry_info(full, name_)
                    items.append({"nom": os.path.relpath(full, path), "taille": human_size(e["size"]),
                                  "modifie": dt.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d")})
            else:
                entries = fs_list(path, hidden)["entries"]
                if len(entries) > 300:
                    etat["coupe"] = "limite"
                for e in entries[:300]:
                    items.append({"nom": e["name"] + ("/" if e["dir"] else ""),
                                  "type": "dossier" if e["dir"] else (e["ext"] or "fichier"),
                                  "taille": None if e["dir"] else human_size(e["size"]),
                                  "modifie": dt.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d")})
            res = {"dossier": _short(path, base), "nombre": len(items), "elements": items}
            if etat.get("coupe"):
                res["incomplet"] = "Liste coupée à 300 éléments : il y en a d'autres."
            return res, (f"{len(items)} élément(s) dans « {_short(path, base)} »"
                         + (" — liste incomplète" if etat.get("coupe") else "")), True
        if name == "lire_fichier":
            path = safe_path(a.get("chemin"), base=base, roots=roots, must_exist=True)
            if os.path.isdir(path):
                raise ApiError("C'est un dossier : utilise lister_dossier.")
            try:
                limit = max(500, min(30000, int(a.get("max_caracteres") or 8000)))
            except (TypeError, ValueError):
                limit = 8000
            txt, note = extract_text(path, limit)
            if txt is None:
                return {"fichier": _short(path, base), "erreur": note}, note, False
            full_len = os.path.getsize(path)
            res = {"fichier": _short(path, base), "format": note, "contenu": txt,
                   "tronque": len(txt) >= limit}
            return res, f"{len(txt)} caractères lus ({note})" + (" — tronqué" if res["tronque"] else ""), True
        if name == "chercher_fichiers":
            folder = a.get("dossier") or base
            r = fs_search(safe_path(folder, base=base, roots=roots), a.get("motif", ""),
                          to_bool(a.get("dans_contenu")), roots=roots, show_hidden=hidden, limit=60)
            items = [{"chemin": _short(e["path"], base), "taille": human_size(e["size"]),
                      **({"extrait": e["extrait"]} if e.get("extrait") else {})} for e in r["results"]]
            res = {"motif": r["query"], "nombre": len(items), "resultats": items}
            if r["incomplet"]:
                res["incomplet"] = {
                    "temps": "Recherche arrêtée avant la fin (dossier trop volumineux) : d'autres fichiers "
                             "peuvent correspondre. Cherche dans un sous-dossier plus précis.",
                    "contenu": "Le texte de certains documents n'est pas encore indexé : d'autres fichiers peuvent "
                               "contenir ce mot.",
                }.get(r["incomplet"], "Seuls les premiers résultats sont listés : précise le motif.")
            return res, f"{len(items)} résultat(s)" + (" — recherche incomplète" if r["incomplet"] else ""), True
        if name == "infos_fichier":
            path = safe_path(a.get("chemin"), base=base, roots=roots, must_exist=True)
            e = entry_info(path)
            st = os.stat(path)
            res = {"chemin": _short(path, base), "type": "dossier" if e["dir"] else (e["ext"] or "fichier"),
                   "taille": human_size(e["size"]),
                   "modifie": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                   "cree_ou_change": dt.datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M")}
            if e["dir"]:
                try:
                    res["nombre_elements"] = len(os.listdir(path))
                except OSError:
                    pass
            return res, f"{res['type']}, {res['taille']}", True
        if name == "trouver_doublons":
            r = find_duplicates(safe_path(a.get("dossier") or base, base=base, roots=roots),
                                roots=roots, show_hidden=hidden)
            groups = [{"taille": g["taille_lisible"], "fichiers": [_short(p, base) for p in g["fichiers"]]}
                      for g in r["groupes"][:40]]
            res = {"groupes": groups, "nb_groupes": r["nb_groupes"], "place_recuperable": r["place_recuperable"]}
            if r["incomplet"]:
                res["incomplet"] = "Dossier trop volumineux : tous les fichiers n'ont pas été comparés."
            return (res, f"{r['nb_groupes']} groupe(s) de doublons, {r['place_recuperable']} récupérables"
                    + (" — analyse incomplète" if r["incomplet"] else ""), True)
        if name == "creer_dossier":
            r = fs_mkdir(a.get("chemin"), roots=roots, base=base)
            return r, ("Existait déjà : " if r["existait"] else "Créé : ") + _short(r["path"], base), True
        if name == "ecrire_fichier":
            mode = "ajouter" if str(a.get("mode", "")).lower().startswith("ajout") else "remplacer"
            r = fs_write(a.get("chemin"), str(a.get("contenu", "")), roots=roots, base=base, mode=mode)
            verb = "Créé" if r["cree"] else ("Complété" if mode == "ajouter" else "Modifié")
            extra = " (ancienne version sauvegardée)" if r["ancienne_version"] else ""
            return ({"fichier": _short(r["path"], base), "cree": r["cree"], "taille": human_size(r["taille"])},
                    f"{verb} : {_short(r['path'], base)}{extra}", True)
        if name in ("deplacer", "copier"):
            r = fs_move(a.get("source"), a.get("destination"), roots=roots, base=base, copy=(name == "copier"))
            if r.get("inchange"):
                return {"info": "Déjà à cet emplacement."}, "Déjà à cet emplacement", True
            verb = "Copié" if name == "copier" else "Déplacé"
            return ({"de": _short(r["de"], base), "vers": _short(r["vers"], base)},
                    f"{verb} vers {_short(r['vers'], base)}", True)
        if name == "renommer":
            r = fs_rename(a.get("chemin"), a.get("nouveau_nom"), roots=roots, base=base)
            return ({"de": _short(r["de"], base), "vers": _short(r["vers"], base)},
                    f"Renommé en {os.path.basename(r['vers'])}", True)
        if name == "creer_document":
            chemin = str(a.get("chemin") or "")
            kind = "xlsx" if chemin.lower().endswith((".xlsx", ".xls")) else "docx"
            r = create_office(chemin, kind, str(a.get("contenu", "")), roots=roots, base=base, unique=True)
            return ({"fichier": _short(r["path"], base), "type": kind},
                    f"Créé : {_short(r['path'], base)} (s'ouvre dans Grimoire)", True)
        if name == "supprimer":
            r = trash(a.get("chemin"), roots=roots, base=base)
            return {"corbeille": _short(r["path"], base)}, f"Mis à la corbeille : {_short(r['path'], base)}", True
        if name == "ouvrir_application":
            sc, app, proches = match_app_scored(str(a.get("nom") or ""))
            folder = match_special_dir(str(a.get("nom") or ""))
            if folder and (app is None or sc >= 2):  # « téléchargements » est un dossier, pas l'appli Transmission
                how = open_path(folder)
                return ({"dossier": _short(folder, base), "ouvert": True, "info": "C'est un dossier : ouvert."},
                        f"Dossier ouvert : {_short(folder, base)} ({how})", True)
            if not app:
                msg = f"Aucune application installée ne s'appelle « {a.get('nom', '')} »."
                return ({"erreur": msg, "applications_proches": proches},
                        msg + (f" Proches : {', '.join(proches)}" if proches else ""), False)
            if raise_app(app["id"]):
                return ({"application": app["nom"], "deja_ouverte": True, "affichee": True},
                        f"Déjà ouverte, ramenée devant : {app['nom']}", True)
            launch_app(app)
            return {"application": app["nom"], "lancee": True}, f"Lancée : {app['nom']}", True
        if name == "ouvrir":
            try:
                path = safe_path(a.get("chemin"), base=base, roots=roots, must_exist=True)
            except ApiError:
                path = match_special_dir(str(a.get("chemin") or ""))
                if not path:
                    raise
                path = safe_path(path, roots=roots, must_exist=True)
            how = open_path(path)
            return {"ouvert": _short(path, base), "avec": how}, f"Ouvert : {_short(path, base)} ({how})", True
        raise ApiError(f"Outil inconnu : {name}")
    except ApiError as e:
        return {"erreur": str(e)}, str(e), False
    except PermissionError:
        return {"erreur": "Permission refusée."}, "Permission refusée", False
    except OSError as e:
        msg = f"Erreur système : {e.strerror or e}"
        return {"erreur": msg}, msg, False


# ════════════════════════════════════════════════════════════════════
#  Prompts & agents par défaut
# ════════════════════════════════════════════════════════════════════
def default_prompts() -> list[dict]:
    t = now_iso()
    items = [
        ("Résumer un document", "Lecture",
         "Résume ce document en 5 points clés maximum, puis liste les actions à mener s'il y en a."),
        ("Corriger l'orthographe", "Rédaction",
         "Corrige l'orthographe, la grammaire et la ponctuation du texte suivant, sans changer le sens ni le "
         "style. Renvoie uniquement le texte corrigé.\n\n{{texte}}"),
        ("Rédiger un mail", "Rédaction",
         "Rédige un mail {{ton}} à {{destinataire}} pour {{objet}}. Court, clair, en français, avec un objet."),
        ("Expliquer un script", "Code",
         "Explique simplement ce que fait ce script, étape par étape, et signale tout ce qui pourrait être "
         "risqué (suppression, droits administrateur, accès réseau…)."),
        ("Tri : par thème puis par année", "Tri",
         "Range par grands thèmes (Administratif, Travail, Photos, Projets perso, Loisirs…) puis par année "
         "quand c'est utile. Les factures et relevés vont dans Administratif/Factures."),
        ("Tri : dossier Téléchargements", "Tri",
         "Range des téléchargements : installateurs dans Logiciels, PDF selon leur sujet, images dans Images, "
         "archives dans Archives. Ce qui est visiblement temporaire va dans « À supprimer »."),
    ]
    return [{"id": new_id("p_"), "titre": a, "categorie": b, "contenu": c, "favori": False,
             "utilisations": 0, "cree": t, "modifie": t} for a, b, c in items]


def default_agents() -> list[dict]:
    t = now_iso()
    base = {"modele": "", "dossier": "", "confirmer": True, "think": False, "temperature": 0.3, "cree": t}
    return [
        {**base, "id": new_id("a_"), "nom": "Rangeur", "icone": "🗂️",
         "description": "Organise un dossier : crée des sous-dossiers et y range les fichiers.",
         "consignes": ("Tu es le Rangeur, l'agent de rangement de {prenom}. Commence toujours par lister le "
                       "dossier concerné. Propose ensuite un plan clair (quels sous-dossiers, quels fichiers où), "
                       "puis exécute-le avec les outils, un fichier à la fois. Ne supprime jamais rien : en cas de "
                       "doute, range dans « À trier ». Termine par un compte rendu court."),
         "outils": ["lister_dossier", "infos_fichier", "chercher_fichiers", "creer_dossier", "deplacer", "renommer"]},
        {**base, "id": new_id("a_"), "nom": "Lecteur", "icone": "📖",
         "description": "Lit tes fichiers pour résumer, comparer ou retrouver une information. Ne modifie rien.",
         "consignes": ("Tu es le Lecteur. Tu lis les fichiers de {prenom} pour répondre à ses questions, résumer "
                       "ou extraire des informations. Cherche et lis les fichiers avant de répondre ; cite toujours "
                       "le nom du fichier d'où vient une information. Tu ne modifies jamais rien."),
         "outils": ["lister_dossier", "lire_fichier", "chercher_fichiers", "infos_fichier"]},
        {**base, "id": new_id("a_"), "nom": "Rédacteur", "icone": "✍️",
         "description": "Écrit et modifie des fichiers texte : notes, listes, scripts, Markdown.",
         "consignes": ("Tu es le Rédacteur. Tu crées et modifies des fichiers texte pour {prenom} (notes .md, "
                       "listes, scripts). Lis toujours un fichier existant avant de le modifier, et écris son "
                       "contenu complet. Une ancienne version est sauvegardée automatiquement à chaque modification."),
         "outils": ["lister_dossier", "lire_fichier", "chercher_fichiers", "creer_dossier", "ecrire_fichier",
                    "creer_document", "renommer"]},
        {**base, "id": new_id("a_"), "nom": "Nettoyeur", "icone": "🧹",
         "description": "Fait de la place : doublons, gros fichiers, fichiers inutiles (corbeille uniquement).",
         "consignes": ("Tu es le Nettoyeur. Tu aides {prenom} à faire de la place : doublons, gros fichiers, "
                       "fichiers temporaires ou obsolètes. Analyse d'abord, présente ce que tu proposes de retirer "
                       "avec la place gagnée, puis agis. Les suppressions vont toujours à la corbeille. Dans un "
                       "groupe de doublons, garde toujours un exemplaire."),
         "outils": ["lister_dossier", "chercher_fichiers", "infos_fichier", "trouver_doublons", "supprimer",
                    "creer_dossier", "deplacer"]},
    ]


def get_prompts() -> list[dict]:
    with store.lock:
        data = store.read("prompts.json", None)
        if data is None:
            data = default_prompts()
            store.write("prompts.json", data)
        return data


def get_agents() -> list[dict]:
    with store.lock:
        data = store.read("agents.json", None)
        if data is None:
            data = default_agents()
            store.write("agents.json", data)
        return data


def find_agent(aid: str | None) -> dict | None:
    if not aid:
        return None
    return next((a for a in get_agents() if a["id"] == aid), None)


def upsert(kind: str, item: dict) -> dict:
    with store.lock:
        return _upsert(kind, item)


def _upsert(kind: str, item: dict) -> dict:
    file = f"{kind}.json"
    items = get_prompts() if kind == "prompts" else get_agents()
    t = now_iso()
    if kind == "prompts":
        clean = {"titre": str(item.get("titre", "")).strip()[:120] or "Sans titre",
                 "categorie": str(item.get("categorie", "")).strip()[:40] or "Divers",
                 "contenu": str(item.get("contenu", "")),
                 "favori": to_bool(item.get("favori"))}
    else:
        outils = [o for o in (item.get("outils") or []) if o in TOOLS]
        dossier = str(item.get("dossier", "") or "").strip()
        if dossier:
            dossier = safe_path(dossier, must_exist=True)
            if not os.path.isdir(dossier):
                raise ApiError("Le dossier de travail doit être un dossier.")
        try:
            temp = max(0.0, min(2.0, float(item.get("temperature", 0.3))))
        except (TypeError, ValueError):
            temp = 0.3
        clean = {"nom": str(item.get("nom", "")).strip()[:60] or "Agent",
                 "icone": str(item.get("icone", "") or "🤖").strip()[:8],
                 "description": str(item.get("description", "")).strip()[:300],
                 "consignes": str(item.get("consignes", "")),
                 "modele": str(item.get("modele", "") or "").strip(),
                 "dossier": dossier, "outils": outils,
                 "confirmer": to_bool(item.get("confirmer"), True),
                 "think": to_bool(item.get("think")), "temperature": temp}
    iid = item.get("id")
    for it in items:
        if it["id"] == iid:
            it.update(clean)
            it["modifie"] = t
            store.write(file, items)
            return it
    new = {"id": new_id("p_" if kind == "prompts" else "a_"), **clean, "cree": t, "modifie": t}
    if kind == "prompts":
        new["utilisations"] = 0
    items.append(new)
    store.write(file, items)
    return new


def remove(kind: str, iid: str) -> dict:
    with store.lock:
        items = get_prompts() if kind == "prompts" else get_agents()
        items = [i for i in items if i["id"] != iid]
        store.write(f"{kind}.json", items)
    return {"ok": True}


# ════════════════════════════════════════════════════════════════════
#  Discussions
# ════════════════════════════════════════════════════════════════════
CONV_RE = re.compile(r"^c_[0-9a-f]{10}$")


def conv_path(cid: str) -> str:
    if not CONV_RE.match(cid or ""):
        raise ApiError("Discussion invalide.", 404)
    return f"conversations/{cid}.json"


def load_conv(cid: str) -> dict:
    c = store.read(conv_path(cid), None)
    if c is None:
        raise ApiError("Discussion introuvable.", 404)
    return c


def save_conv(c: dict) -> None:
    c["modifie"] = now_iso()
    store.write(conv_path(c["id"]), c)


def list_convs() -> list[dict]:
    out = []
    for p in (DATA_DIR / "conversations").glob("c_*.json"):
        try:
            c = json.loads(p.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"id": c["id"], "titre": c.get("titre") or "Nouvelle discussion",
                    "agent_id": c.get("agent_id"), "modifie": c.get("modifie"),
                    "nb": sum(1 for m in c.get("messages", []) if m.get("role") == "user")})
    out.sort(key=lambda x: x.get("modifie") or "", reverse=True)
    return out


def create_conv(body: dict) -> dict:
    agent_id = body.get("agent_id") or None
    if agent_id and not find_agent(agent_id):
        raise ApiError("Agent introuvable.")
    ws = str(body.get("workspace") or "").strip()
    if ws:
        ws = safe_path(ws, must_exist=True)
    c = {"id": new_id("c_"), "titre": str(body.get("titre") or "").strip()[:100],
         "agent_id": agent_id, "modele": str(body.get("modele") or ""), "workspace": ws,
         "think": body.get("think"), "cree": now_iso(), "messages": [], "pending": None}
    save_conv(c)
    return c


def conv_context(conv: dict, agent: dict | None, s: dict) -> dict:
    roots = allowed_roots(s)
    ws = conv.get("workspace") or (agent or {}).get("dossier") or ""
    if ws:
        ws = safe_path(ws, roots=roots, must_exist=True)
        if not os.path.isdir(ws):
            raise ApiError("Le dossier de travail n'est pas un dossier.")
        agent_roots = [ws]
    else:
        ws = roots[0]
        agent_roots = roots
    return {"roots": agent_roots, "base": ws, "show_hidden": s["show_hidden"],
            "allowed": set((agent or {}).get("outils") or []) if agent else set(FREE_TOOLS)}


def build_system(agent: dict | None, s: dict, ctx: dict) -> str:
    prenom = s["prenom"]
    text = (agent.get("consignes") if agent and agent.get("consignes") else s["system_prompt"])
    text = text.replace("{prenom}", prenom)
    parts = [text, f"Nous sommes le {date_fr()}."]
    if agent and agent.get("outils"):
        roots_txt = ", ".join(_short(r, None) for r in ctx["roots"])
        parts.append(
            f"Tu disposes d'outils pour agir sur les fichiers de {prenom}. Dossier de travail : {ctx['base']}. "
            f"Les chemins relatifs partent de ce dossier ; tu ne peux agir que dans : {roots_txt}. "
            "Utilise les outils au lieu de deviner, et n'invente jamais le contenu d'un fichier. "
            "Quand c'est fini, fais un compte rendu bref en français.")
        if agent.get("confirmer", True):
            parts.append(f"Chaque action qui modifie des fichiers est soumise à la validation de {prenom} ; "
                         "s'il refuse une action, n'insiste pas et propose une autre solution.")
    elif not agent:
        parts.append(
            f"Tu peux ouvrir une application (outil ouvrir_application), ouvrir un fichier ou un dossier (outil "
            f"ouvrir, par exemple « Téléchargements » ou « Documents ») et chercher des fichiers (outil "
            f"chercher_fichiers) sur le PC de {prenom}. Un dossier s'ouvre avec ouvrir, jamais avec ouvrir_application. Quand il te demande "
            "d'ouvrir ou de lancer quelque chose, appelle l'outil au lieu de répondre en texte. Pour le reste, "
            "réponds simplement, sans outil.")
    parts.append("Règle absolue : n'affirme jamais avoir ouvert, lancé, cherché, créé ou modifié quoi que ce soit "
                 "sans avoir réellement appelé l'outil correspondant et reçu son résultat. Si tu ne peux pas le faire, "
                 "dis-le franchement.")
    return "\n\n".join(parts)


def build_messages(conv: dict, system: str, num_ctx: int) -> list[dict]:
    budget = int(num_ctx * 2.8) - len(system)
    out, used = [], 0
    msgs = conv.get("messages", [])
    recent_image_floor = max(0, len(msgs) - 6)
    for idx in range(len(msgs) - 1, -1, -1):
        m = msgs[idx]
        role = m.get("role")
        if role not in ("user", "assistant", "tool"):
            continue
        content = m.get("ctx") or m.get("content") or ""
        om = {"role": role, "content": content}
        if role == "assistant" and m.get("tool_calls"):
            om["tool_calls"] = m["tool_calls"]
        if role == "tool":
            om["tool_name"] = m.get("tool_name", "")
        cost = len(content) + (len(json.dumps(m.get("tool_calls"))) if m.get("tool_calls") else 0)
        if m.get("images") and idx >= recent_image_floor:
            imgs = []
            for p in m["images"]:
                try:
                    with open(p, "rb") as f:
                        imgs.append(base64.b64encode(f.read()).decode("ascii"))
                    cost += 2500
                except OSError:
                    pass
            if imgs:
                om["images"] = imgs
        if out and used + cost > budget:
            break
        used += cost
        out.append(om)
    out.reverse()
    while out and out[0]["role"] != "user":
        out.pop(0)
    return [{"role": "system", "content": system}] + out


def expand_attachments(paths: list[str], s: dict) -> tuple[str, list[dict], list[str]]:
    blocks, atts, images = [], [], []
    budget = int(s["num_ctx"] * 2.2)
    per_file = max(2000, budget // max(1, len(paths)))
    for p in paths[:8]:
        real = safe_path(p, must_exist=True)
        name = os.path.basename(real)
        ext = ext_of(name)
        if os.path.isdir(real):
            listing = fs_list(real, s["show_hidden"])["entries"][:200]
            lines = [("📁 " if e["dir"] else "• ") + e["name"] for e in listing]
            blocks.append(f"[Dossier joint : {real}]\n" + "\n".join(lines))
            atts.append({"path": real, "name": name, "kind": "folder"})
            continue
        if ext in IMAGE_EXTS_VISION and os.path.getsize(real) < 15_000_000:
            images.append(real)
            atts.append({"path": real, "name": name, "kind": "image"})
            continue
        txt, note = extract_text(real, per_file)
        if txt is None:
            blocks.append(f"[Fichier joint : {real} — {note}]")
        else:
            trunc = " (extrait, tronqué)" if len(txt) >= per_file else ""
            blocks.append(f"[Fichier joint : {real}{trunc}]\n```\n{txt}\n```")
        atts.append({"path": real, "name": name, "kind": EXT_KIND.get(ext, "text")})
    return "\n\n".join(blocks), atts, images


# ════════════════════════════════════════════════════════════════════
#  Boucle de discussion / agent (flux NDJSON)
# ════════════════════════════════════════════════════════════════════
def tool_message(call: dict) -> dict:
    return {"role": "tool", "tool_name": call["name"], "call_id": call["id"],
            "content": json.dumps(call["result"], ensure_ascii=False)[:24000],
            "args": call["args"], "description": call["description"],
            "summary": call.get("summary", ""), "ok": call.get("ok", False),
            "refuse": call.get("refuse", False), "ts": now_iso()}


# Une seule réponse à la fois par discussion : deux fenêtres (volet, « Demander », fenêtre principale) qui
# écriraient en même temps dans le même fichier se feraient perdre des messages.
_RUNS: dict[str, object] = {}  # identifiant de discussion → requête (Handler) qui y écrit en ce moment
_RUNS_LOCK = threading.RLock()


def _client_gone(h) -> bool:
    """Le navigateur a-t-il coupé la connexion de cette requête (bouton Stop, fenêtre fermée) ?"""
    try:
        sock = h.connection
        if not select.select([sock], [], [], 0)[0]:
            return False
        return sock.recv(1, socket.MSG_PEEK) == b""
    except (OSError, ValueError):
        return True


def conv_busy(cid: str) -> bool:
    with _RUNS_LOCK:
        return cid in _RUNS


def conv_claim(cid: str, h=None) -> bool:
    """Réserve la discussion pour la requête h (ou vérifie seulement qu'elle est libre si h est None).
    Une réponse dont le navigateur est parti est écartée : elle n'écrira plus rien."""
    with _RUNS_LOCK:
        old = _RUNS.get(cid)
        if old is not None:
            if not (old.cancelled or _client_gone(old)):
                return False
            old.cancelled = True
            del _RUNS[cid]
        if h is not None:
            _RUNS[cid] = h
        return True


def conv_release(cid: str, h=None) -> None:
    """Libère la discussion. Sans h : écarte aussi la réponse en cours (discussion supprimée)."""
    with _RUNS_LOCK:
        old = _RUNS.get(cid)
        if old is not None and (h is None or old is h):
            if h is None:
                old.cancelled = True
            del _RUNS[cid]


def run_chat(h, body: dict) -> None:
    cid = str(body.get("conv_id") or "")
    conv_path(cid)
    if not conv_claim(cid, h):
        raise ApiError("Une réponse est déjà en cours dans cette discussion : attends-la ou arrête-la.", 409)
    try:
        _run_chat(h, body)
    finally:
        conv_release(cid, h)


def _run_chat(h, body: dict) -> None:
    s = get_settings()
    conv = load_conv(body.get("conv_id", ""))
    agent = find_agent(conv.get("agent_id"))
    if conv.get("agent_id") and not agent:
        conv["agent_id"] = None
    model = conv.get("modele") or (agent or {}).get("modele") or s["model"]
    think = body.get("think")
    if think is None:
        think = conv.get("think")
    if think is None:
        think = (agent or {}).get("think", s["think"]) if agent else s["think"]
    think = to_bool(think)
    temperature = (agent or {}).get("temperature", s["temperature"]) if agent else s["temperature"]
    confirm = (agent or {}).get("confirmer", True)
    ctx = conv_context(conv, agent, s)

    def save() -> None:
        with _RUNS_LOCK:
            if h.cancelled:  # une autre requête a repris cette discussion : ne rien écraser
                raise ClientGone()
            save_conv(conv)

    def fail(msg: str, retry: bool = True) -> None:
        """L'erreur est gardée dans la discussion : elle reste à l'écran au lieu de disparaître au rafraîchissement."""
        conv["messages"].append({"role": "error", "content": msg, "reessayer": retry, "ts": now_iso()})
        save()
        h.emit({"t": "error", "d": msg, "reessayer": retry})

    h.start_stream()
    h.emit({"t": "start", "model": model, "agent": (agent or {}).get("nom")})
    try:
        _chat_turn(h, body, s, conv, agent, model, think, temperature, confirm, ctx, save, fail)
    except ClientGone:
        raise
    except (ApiError, OllamaError) as e:
        fail(str(e))
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        fail(f"Erreur interne : {e}")


def _chat_turn(h, body, s, conv, agent, model, think, temperature, confirm, ctx, save, fail) -> None:
    # 1) Décisions sur les actions en attente
    pending = conv.get("pending")
    if pending:
        decisions = body.get("decisions") or {}
        for call in pending:
            if "result" in call:
                continue
            if decisions.get(call["id"]) is True:
                res, summary, ok = execute_tool(call["name"], call["args"], ctx)
                call.update(result=res, summary=summary, ok=ok)
            else:
                call.update(result={"refus": f"{s['prenom']} a refusé cette action."},
                            summary="Refusé", ok=False, refuse=True)
            h.emit({"t": "tool_result", "id": call["id"], "name": call["name"], "ok": call["ok"],
                    "summary": call["summary"], "refuse": call.get("refuse", False)})
        for call in pending:
            conv["messages"].append(tool_message(call))
        conv["pending"] = None
        save()

    # 2) Régénérer / réessayer : on retire la dernière réponse (ou la dernière erreur)
    if body.get("regenerate"):
        while conv["messages"] and conv["messages"][-1].get("role") != "user":
            conv["messages"].pop()
        if not conv["messages"]:
            h.emit({"t": "error", "d": "Rien à régénérer."})
            return

    # 3) Nouveau message
    message = str(body.get("message") or "").strip()
    attachments = body.get("attachments") or []
    if message or attachments:
        att_err = None
        try:
            ctx_text, atts, images = expand_attachments(attachments, s) if attachments else ("", [], [])
        except (ApiError, OSError) as e:
            ctx_text, atts, images = "", [], []
            att_err = str(e) if isinstance(e, ApiError) else f"lecture impossible ({e.strerror or e})"
        if message or atts:
            um = {"role": "user", "content": message, "ts": now_iso()}
            if ctx_text:
                um["ctx"] = (message + "\n\n" + ctx_text).strip()
            if atts:
                um["attachments"] = atts
            if images:
                um["images"] = images
            conv["messages"].append(um)
            if not conv.get("titre"):
                conv["titre"] = (message or atts[0]["name"])[:70]
            save()
            h.emit({"t": "user_saved", "titre": conv["titre"]})
        if att_err:
            fail(f"Pièce jointe refusée : {att_err}", retry=False)
            return

    if not conv["messages"]:
        h.emit({"t": "error", "d": "Message vide."})
        return

    tools = tool_schemas((agent or {}).get("outils") or [] if agent else FREE_TOOLS)
    system = build_system(agent, s, ctx)
    parse_retry = False
    rnd = 0
    while rnd < MAX_ROUNDS:
        rnd += 1
        payload = {"model": model, "messages": build_messages(conv, system, s["num_ctx"]), "stream": True,
                   "options": {"num_ctx": s["num_ctx"], "temperature": temperature},
                   "keep_alive": keep_alive(s), "think": think}
        if tools:
            payload["tools"] = tools
        try:
            res = ollama_chat_stream(payload,
                                     lambda d: h.emit({"t": "thinking", "d": d}),
                                     lambda d: h.emit({"t": "content", "d": d}))
        except ClientGone as cg:
            part = cg.partial or {}
            if part.get("content") or part.get("thinking"):
                conv["messages"].append({"role": "assistant", "content": part.get("content", ""),
                                         "thinking": part.get("thinking", ""), "interrompu": True,
                                         "ts": now_iso()})
                try:
                    save()
                except ClientGone:
                    pass
            raise
        except OllamaError as e:
            low = str(e).lower()
            malformed = any(k in low for k in ("parse", "expected element", "unexpected", "invalid character"))
            if tools and not parse_retry and malformed and "support" not in low:
                parse_retry = True
                rnd -= 1
                h.emit({"t": "notice", "d": "Le modèle a mal formé un appel d'outil, nouvelle tentative…"})
                continue
            fail(str(e))
            return

        msg = {"role": "assistant", "content": res["content"], "ts": now_iso(), "model": model}
        if res["thinking"]:
            msg["thinking"] = res["thinking"]
        if res["tool_calls"]:
            msg["tool_calls"] = res["tool_calls"]
        st = res["stats"] or {}
        if st.get("eval_count") and st.get("eval_duration"):
            msg["vitesse"] = round(st["eval_count"] / (st["eval_duration"] / 1e9), 1)
        conv["messages"].append(msg)
        save()
        h.emit({"t": "message_end", "vitesse": msg.get("vitesse"), "tokens": st.get("eval_count")})

        if not res["tool_calls"]:
            h.emit({"t": "done"})
            return

        calls = []
        for tc in res["tool_calls"]:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_brut": args}
            meta = TOOLS.get(name, {})
            needs = bool(meta.get("modifie")) and confirm and name in ctx["allowed"]
            call = {"id": new_id("t_"), "name": name, "args": args, "needs": needs,
                    "description": describe_action(name, args), "label": meta.get("label", name)}
            h.emit({"t": "tool_call", "id": call["id"], "name": name, "label": call["label"], "args": args,
                    "needs_confirm": needs, "description": call["description"]})
            if not needs:
                result, summary, ok = execute_tool(name, args, ctx)
                call.update(result=result, summary=summary, ok=ok)
                h.emit({"t": "tool_result", "id": call["id"], "name": name, "ok": ok, "summary": summary})
            calls.append(call)

        if any(c["needs"] for c in calls):
            conv["pending"] = calls
            save()
            h.emit({"t": "confirm", "pending": [
                {"id": c["id"], "name": c["name"], "label": c["label"], "description": c["description"],
                 "args": c["args"]} for c in calls if c["needs"]]})
            return
        for c in calls:
            conv["messages"].append(tool_message(c))
        save()

    fail(f"Arrêt de sécurité : l'agent a enchaîné {MAX_ROUNDS} étapes sans conclure.")


def run_oneshot(h, body: dict) -> None:
    """Génération ponctuelle (éditeur, résumé rapide) — sans historique."""
    s = get_settings()
    prompt = str(body.get("prompt") or "").strip()
    if not prompt:
        raise ApiError("Consigne vide.")
    system = str(body.get("system") or s["system_prompt"]).replace("{prenom}", s["prenom"])
    user = prompt
    images = []
    if body.get("attachments"):
        ctx_text, _, images = expand_attachments(body["attachments"], s)
        user = (prompt + "\n\n" + ctx_text).strip()
    if body.get("texte"):
        user += "\n\n---\n" + str(body["texte"])
    um = {"role": "user", "content": user}
    if images:
        um["images"] = []
        for p in images:
            with open(p, "rb") as f:
                um["images"].append(base64.b64encode(f.read()).decode("ascii"))
    payload = {"model": body.get("model") or s["model"],
               "messages": [{"role": "system", "content": system}, um], "stream": True,
               "options": {"num_ctx": s["num_ctx"], "temperature": float(body.get("temperature", 0.4))},
               "keep_alive": keep_alive(s), "think": to_bool(body.get("think"), False)}
    h.start_stream()
    try:
        res = ollama_chat_stream(payload, lambda d: h.emit({"t": "thinking", "d": d}),
                                 lambda d: h.emit({"t": "content", "d": d}))
        h.emit({"t": "done", "tokens": (res["stats"] or {}).get("eval_count")})
    except OllamaError as e:
        h.emit({"t": "error", "d": str(e)})


# ════════════════════════════════════════════════════════════════════
#  Tri (règles et IA)
# ════════════════════════════════════════════════════════════════════
def sort_scan(base: str, recursive: bool, with_content: bool, show_hidden: bool) -> dict:
    real = safe_path(base, must_exist=True)
    if not os.path.isdir(real):
        raise ApiError("Choisis un dossier.")
    files = []
    if recursive:
        it = ((dp, n) for dp, _, n in walk_files(real, show_hidden, 3000))
    else:
        it = ((real, de.name) for de in sorted(os.scandir(real), key=lambda d: d.name.casefold())
              if de.is_file() and (show_hidden or not de.name.startswith(".")))
    for dirpath, name in it:
        full = os.path.join(dirpath, name)
        try:
            e = entry_info(full, name)
        except OSError:
            continue
        if e["dir"] or e["link"]:  # un lien symbolique reste où il est : le déplacer pourrait le casser
            continue
        e["rel"] = os.path.relpath(full, real)
        e["categorie"] = EXT_CAT.get(e["ext"], "Autres")
        if with_content and (e["size"] or 0) < 25_000_000:
            txt, _ = extract_text(full, 600)
            if txt:
                e["extrait"] = re.sub(r"\s+", " ", txt)[:350]
        files.append(e)
        if len(files) >= 3000:
            break
    existing = sorted((d.name for d in os.scandir(real)
                       if d.is_dir() and (show_hidden or not d.name.startswith("."))), key=str.casefold)
    return {"base": real, "files": files, "existants": existing, "tronque": len(files) >= 3000}


def rule_folder(e: dict, mode: str) -> str:
    cat = EXT_CAT.get(e["ext"], "Autres")
    d = dt.datetime.fromtimestamp(e["mtime"])
    if mode == "type":
        return cat
    if mode == "date":
        return f"{d.year}/{d.year}-{d.month:02d}"
    if mode == "annee":
        return str(d.year)
    return f"{cat}/{d.year}"  # type_date


FOLDER_BAD = re.compile(r'[<>:"|?*\x00-\x1f]')


def clean_folder(s) -> str | None:
    if not s:
        return None
    parts = []
    for part in re.split(r"[\\/]+", str(s)):
        part = FOLDER_BAD.sub("", part).strip().strip(".").strip()
        if part and part not in (".", ".."):
            parts.append(part[:60])
    return "/".join(parts[:3]) or None


SORT_SCHEMA = {
    "type": "object",
    "properties": {"classement": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "dossier": {"type": "string"}, "raison": {"type": "string"}},
        "required": ["n", "dossier"]}}},
    "required": ["classement"],
}


def _parse_json_loose(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            return json.loads(text[a: b + 1])
        raise


def ai_sort_batch(body: dict) -> dict:
    s = get_settings()
    files = body.get("files") or []
    if not files:
        return {"resultats": []}
    instructions = str(body.get("consignes") or "").strip() or \
        "Range de façon logique, par thème ou par type de document, avec des noms de dossiers clairs."
    existing = body.get("existants") or []
    proposed = body.get("proposes") or []
    lines = []
    for i, f in enumerate(files, 1):
        d = dt.datetime.fromtimestamp(f.get("mtime") or 0).strftime("%Y-%m-%d")
        line = f"{i}. {f.get('rel') or f.get('name')} ({human_size(f.get('size'))}, modifié le {d})"
        if f.get("extrait"):
            line += f" — début : « {f['extrait'][:300]} »"
        lines.append(line)
    system = ("Tu es l'Archiviste, expert du rangement de fichiers. On te donne une liste numérotée de fichiers. "
              "Pour CHAQUE fichier, choisis un sous-dossier de destination : chemin relatif court (1 ou 2 niveaux, "
              "séparés par /), noms en français, sans date inventée. Réutilise en priorité les dossiers existants "
              "ou déjà proposés, avec exactement la même orthographe. Si tu hésites, mets « À trier ». "
              "Réponds uniquement avec le JSON demandé.")
    user = (f"Consignes de {s['prenom']} : {instructions}\n\n"
            f"Dossiers déjà présents : {', '.join(existing) if existing else 'aucun'}\n"
            f"Dossiers déjà proposés : {', '.join(proposed) if proposed else 'aucun'}\n\n"
            "Fichiers à ranger :\n" + "\n".join(lines) +
            '\n\nRéponds au format : {"classement": [{"n": 1, "dossier": "Nom/Sous-dossier", "raison": "courte"}]}')
    payload = {"model": body.get("model") or s["model"],
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
               "stream": False, "format": SORT_SCHEMA, "think": False, "keep_alive": keep_alive(s),
               "options": {"temperature": 0.2, "num_ctx": max(s["num_ctx"], 8192)}}
    t0 = time.time()
    data = ollama_json("/api/chat", payload)
    content = (data.get("message") or {}).get("content", "")
    try:
        parsed = _parse_json_loose(content)
    except (json.JSONDecodeError, ValueError):
        raise ApiError("La réponse de l'IA n'était pas exploitable (JSON invalide). Relance l'analyse.")
    out = [None] * len(files)
    for it in (parsed.get("classement") or []):
        try:
            n = int(it.get("n"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(files):
            folder = clean_folder(it.get("dossier"))
            if folder:
                out[n - 1] = {"dossier": folder, "raison": str(it.get("raison") or "")[:200]}
    return {"resultats": out, "duree": round(time.time() - t0, 1)}


def sort_apply(body: dict) -> dict:
    base = safe_path(body.get("base"), must_exist=True)
    moves, errors, created = [], [], []
    for mv in body.get("moves") or []:
        try:
            src = safe_path(mv.get("path"), must_exist=True, nofollow=True)
            if os.path.islink(src):
                raise ApiError("lien symbolique laissé en place")
            if not within(src, base) or not os.path.isfile(src):
                raise ApiError("fichier hors du dossier trié")
            folder = clean_folder(mv.get("dossier"))
            if not folder:
                raise ApiError("dossier de destination vide")
            dest_dir = safe_path(os.path.join(base, folder))
            if not within(dest_dir, base):
                raise ApiError("destination hors du dossier trié")
            if os.path.dirname(src) == dest_dir:
                continue
            if not os.path.isdir(dest_dir):
                # mémoriser les dossiers créés (du plus haut au plus profond)
                probe, chain = dest_dir, []
                while not os.path.exists(probe) and within(probe, base):
                    chain.append(probe)
                    probe = os.path.dirname(probe)
                os.makedirs(dest_dir, exist_ok=True)
                created.extend(reversed(chain))
            target = unique_path(os.path.join(dest_dir, os.path.basename(src)))
            shutil.move(src, target)
            moves.append({"de": src, "vers": target})
            changed(src, target, dest_dir)
        except (ApiError, OSError) as e:
            errors.append({"fichier": mv.get("path"), "erreur": str(e)})
    jid = None
    if moves:
        jid = new_id("j_")
        entry = {"id": jid, "date": now_iso(), "base": base, "mode": body.get("mode", ""),
                 "moves": moves, "crees": created, "annule": False}

        def add(journal):
            journal.insert(0, entry)
            del journal[60:]
        store.update("journal.json", list, add)
    return {"deplaces": len(moves), "erreurs": errors, "journal_id": jid}


def sort_undo(jid: str) -> dict:
    journal = store.read("journal.json", list)
    entry = next((j for j in journal if j["id"] == jid), None)
    if not entry:
        raise ApiError("Tri introuvable dans le journal.", 404)
    if entry.get("annule"):
        raise ApiError("Ce tri a déjà été annulé.")
    ok, errors = 0, []
    for mv in reversed(entry["moves"]):
        try:
            src = safe_path(mv["vers"])
            dst = safe_path(mv["de"])
            if not os.path.exists(src):
                raise ApiError("le fichier n'est plus là")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, unique_path(dst))
            changed(src, dst)
            ok += 1
        except (ApiError, OSError) as e:
            errors.append({"fichier": mv["vers"], "erreur": str(e)})
    for d in sorted(entry.get("crees", []), key=len, reverse=True):
        try:
            os.rmdir(d)
        except OSError:
            pass
    def mark(current):  # relu au dernier moment : un tri fait entre-temps n'est pas perdu
        for j in current:
            if j["id"] == jid:
                j["annule"] = True
                j["annule_le"] = now_iso()
    store.update("journal.json", list, mark)
    return {"restaures": ok, "erreurs": errors}


# ════════════════════════════════════════════════════════════════════
#  Grimoire + documents Office (Word .docx / Excel .xlsx)
# ════════════════════════════════════════════════════════════════════
GRIMOIRE_EXTS = {"docx", "xlsx", "xlsm", "xls", "ods", "csv", "txt", "md", "pdf"}


def grimoire_bin() -> str | None:
    """Chemin de l'appli de bureau Grimoire si elle est installée (.deb)."""
    for cand in (shutil.which("grimoire"), "/opt/Grimoire/grimoire", "/usr/bin/grimoire"):
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def _x(s: str) -> str:
    return html.escape(str(s), quote=False)


_INLINE_RE = re.compile(r"(\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+`|\*[^*\s][^*\n]*?\*|\[[^\]\n]+\]\([^)\s]+\))")


def _run(t: str, bold=False, italic=False, code=False) -> str:
    if not t:
        return ""
    rpr = ""
    if code:
        rpr += '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
    if bold:
        rpr += "<w:b/>"
    if italic:
        rpr += "<w:i/>"
    rp = f"<w:rPr>{rpr}</w:rPr>" if rpr else ""
    return f'<w:r>{rp}<w:t xml:space="preserve">{_x(t)}</w:t></w:r>'


def _runs(text: str, bold=False) -> str:
    out, pos = [], 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            out.append(_run(text[pos:m.start()], bold=bold))
        tok = m.group(0)
        if tok.startswith(("**", "__")):
            out.append(_run(tok[2:-2], bold=True))
        elif tok.startswith("`"):
            out.append(_run(tok[1:-1], bold=bold, code=True))
        elif tok.startswith("["):
            label, url = re.match(r"\[([^\]]+)\]\(([^)]+)\)", tok).groups()
            out.append(_run(label if label == url else f"{label} ({url})", bold=bold))
        else:
            out.append(_run(tok[1:-1], bold=bold, italic=True))
        pos = m.end()
    if pos < len(text):
        out.append(_run(text[pos:], bold=bold))
    return "".join(out)


def _para(runs: str, style: str | None = None, numpr: str = "", ppr_extra: str = "") -> str:
    ppr = ""
    if style or numpr or ppr_extra:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{style}"/>' if style else "") + numpr + ppr_extra + "</w:pPr>"
    return f"<w:p>{ppr}{runs}</w:p>"


_LIST_RE = re.compile(r"^(\s*)([-*+•]|\d+[.)])\s+(.*)$")
_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_tables(md: str) -> list[list[list[str]]]:
    lines = (md or "").replace("\r\n", "\n").split("\n")
    tables, i = [], 0
    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and _SEP_RE.match(lines[i + 1]):
            rows = [_cells(lines[i])]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            tables.append(rows)
        else:
            i += 1
    return tables


def _docx_table(rows: list[list[str]]) -> str:
    ncols = max(len(r) for r in rows)
    w = 9000 // max(1, ncols)
    b = "".join(f'<w:{k} w:val="single" w:sz="4" w:space="0" w:color="BFB3A3"/>'
                for k in ("top", "left", "bottom", "right", "insideH", "insideV"))
    out = (f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/>'
           f'<w:tblBorders>{b}</w:tblBorders><w:tblLook w:val="04A0"/></w:tblPr><w:tblGrid>'
           + "".join(f'<w:gridCol w:w="{w}"/>' for _ in range(ncols)) + "</w:tblGrid>")
    for ri, row in enumerate(rows):
        out += "<w:tr>"
        for ci in range(ncols):
            txt = row[ci] if ci < len(row) else ""
            shd = '<w:shd w:val="clear" w:color="auto" w:fill="EFE4D2"/>' if ri == 0 else ""
            out += (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shd}</w:tcPr>'
                    + _para(_runs(txt, bold=(ri == 0)), ppr_extra='<w:spacing w:after="0"/>') + "</w:tc>")
        out += "</w:tr>"
    return out + "</w:tbl>" + _para("")


def markdown_to_docx_body(md: str) -> tuple[str, list[int]]:
    """Convertit du Markdown simple en corps de document Word. Renvoie (xml, numéros des listes numérotées)."""
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out, ordered_ids = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            for c in code or [""]:
                out.append(_para(_run(c, code=True),
                                 ppr_extra='<w:shd w:val="clear" w:color="auto" w:fill="F2ECE2"/><w:spacing w:after="0"/>'))
            out.append(_para(""))
            continue
        if not s:
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            out.append(_para(_runs(m.group(2).strip("# ")), style=f"Heading{min(3, len(m.group(1)))}"))
            i += 1
            continue
        if re.match(r"^([-*_])(\s*\1){2,}$", s):
            out.append(_para("", ppr_extra='<w:pBdr><w:bottom w:val="single" w:sz="6" w:space="1" w:color="BFB3A3"/></w:pBdr>'))
            i += 1
            continue
        if s.startswith(">"):
            while i < len(lines) and lines[i].strip().startswith(">"):
                q = lines[i].strip()[1:].strip()
                if q:
                    out.append(_para(_runs(q), style="Quote"))
                i += 1
            continue
        if "|" in line and i + 1 < len(lines) and _SEP_RE.match(lines[i + 1]):
            rows = [_cells(line)]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_cells(lines[i]))
                i += 1
            out.append(_docx_table(rows))
            continue
        if _LIST_RE.match(line):
            num_for_list = None
            while i < len(lines) and (_LIST_RE.match(lines[i]) or (lines[i].strip() and re.match(r"^\s{2,}\S", lines[i]))):
                lm = _LIST_RE.match(lines[i])
                if not lm:  # suite d'un élément sur la ligne suivante
                    out.append(_para(_runs(lines[i].strip()), style="ListParagraph"))
                    i += 1
                    continue
                indent = len(lm.group(1).replace("\t", "    "))
                lvl = min(8, indent // 2)
                if lm.group(2)[0].isdigit():
                    if num_for_list is None:
                        num_for_list = 2 + len(ordered_ids)
                        ordered_ids.append(num_for_list)
                    nid = num_for_list
                else:
                    nid = 1
                text = re.sub(r"^\[([ xX])\]\s+", lambda mm: "☐ " if mm.group(1) == " " else "☑ ", lm.group(3))
                numpr = f'<w:numPr><w:ilvl w:val="{lvl}"/><w:numId w:val="{nid}"/></w:numPr>'
                out.append(_para(_runs(text), style="ListParagraph", numpr=numpr))
                i += 1
            continue
        buf = [s]
        i += 1
        while i < len(lines):
            n = lines[i]
            ns = n.strip()
            if (not ns or ns.startswith(("```", ">")) or re.match(r"^#{1,6}\s", ns) or _LIST_RE.match(n)
                    or ("|" in n and i + 1 < len(lines) and _SEP_RE.match(lines[i + 1]))):
                break
            buf.append(ns)
            i += 1
        out.append(_para("<w:r><w:br/></w:r>".join(_runs(b) for b in buf)))
    return "".join(out) or _para(""), ordered_ids


_W_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
         'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')
_XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def _core_xml(title: str) -> str:
    t = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (_XML + '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            f'<dc:title>{_x(title)}</dc:title><dc:creator>Archiviste</dc:creator>'
            f'<dcterms:created xsi:type="dcterms:W3CDTF">{t}</dcterms:created>'
            f'<dcterms:modified xsi:type="dcterms:W3CDTF">{t}</dcterms:modified></cp:coreProperties>')


def make_docx(markdown: str, title: str) -> bytes:
    body, ordered = markdown_to_docx_body(markdown)
    document = (_XML + f"<w:document {_W_NS}><w:body>{body}"
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" '
                'w:left="1417" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>')

    def heading(n, size):
        return (f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/><w:basedOn w:val="Normal"/>'
                f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="{360 if n == 1 else 240}" w:after="120"/>'
                f'<w:outlineLvl w:val="{n - 1}"/></w:pPr><w:rPr><w:b/><w:color w:val="2B211C"/><w:sz w:val="{size}"/>'
                f'<w:szCs w:val="{size}"/></w:rPr></w:style>')
    styles = (_XML + f'<w:styles {_W_NS}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" '
              'w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="fr-FR"/></w:rPr>'
              '</w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="259" w:lineRule="auto"/></w:pPr>'
              '</w:pPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
              + heading(1, 32) + heading(2, 27) + heading(3, 24) +
              '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>'
              '<w:qFormat/><w:pPr><w:spacing w:after="40"/><w:ind w:left="720"/><w:contextualSpacing/></w:pPr></w:style>'
              '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:qFormat/>'
              '<w:pPr><w:ind w:left="567"/></w:pPr><w:rPr><w:i/><w:color w:val="5E5048"/></w:rPr></w:style>'
              '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>'
              + "".join(f'<w:{k} w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
                        for k in ("top", "left", "bottom", "right", "insideH", "insideV"))
              + '</w:tblBorders></w:tblPr></w:style></w:styles>')
    bullets = ["•", "◦", "▪"]
    fmts = ["decimal", "lowerLetter", "lowerRoman"]

    def lvl(level, bullet):
        fmt = "bullet" if bullet else fmts[level % 3]
        txt = bullets[level % 3] if bullet else f"%{level + 1}."
        return (f'<w:lvl w:ilvl="{level}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/><w:lvlText w:val="{txt}"/>'
                f'<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="{720 * (level + 1)}" w:hanging="360"/></w:pPr></w:lvl>')
    numbering = (_XML + f'<w:numbering {_W_NS}>'
                 + "".join(f'<w:abstractNum w:abstractNumId="{a}"><w:multiLevelType w:val="hybridMultilevel"/>'
                           + "".join(lvl(L, a == 0) for L in range(9)) + "</w:abstractNum>" for a in (0, 1))
                 + '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
                 + "".join(f'<w:num w:numId="{n}"><w:abstractNumId w:val="1"/><w:lvlOverride w:ilvl="0">'
                           f'<w:startOverride w:val="1"/></w:lvlOverride></w:num>' for n in (ordered or [2]))
                 + "</w:numbering>")
    ctypes = (_XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '</Types>')
    rels = (_XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>')
    doc_rels = (_XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>'
                '</Relationships>')
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", styles)
        z.writestr("word/numbering.xml", numbering)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("docProps/core.xml", _core_xml(title))
    return buf.getvalue()


_NUM_RE = re.compile(r"^-?\d{1,3}(?:[   ]?\d{3})*(?:[.,]\d+)?$|^-?\d+(?:[.,]\d+)?$")


def _col_letter(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def make_xlsx(tables: list[list[list[str]]], title: str) -> bytes:
    """Classeur Excel : un onglet par tableau (vide si aucun), première ligne en gras."""
    tables = tables or [[]]
    sheets = []
    for rows in tables:
        xml_rows = []
        for ri, row in enumerate(rows):
            cells = []
            for ci, val in enumerate(row):
                ref = f"{_col_letter(ci)}{ri + 1}"
                v = re.sub(r"[*_`]", "", str(val)).strip()
                style = ' s="1"' if ri == 0 and len(rows) > 1 else ""
                raw = v.replace("€", "").replace("%", "").strip()
                if ri > 0 and raw and _NUM_RE.match(raw):
                    num = re.sub(r"[   ]", "", raw).replace(",", ".")
                    cells.append(f'<c r="{ref}"{style}><v>{num}</v></c>')
                elif v:
                    cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{_x(v)}</t></is></c>')
            xml_rows.append(f'<row r="{ri + 1}">' + "".join(cells) + "</row>")
        sheets.append(_XML + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                      f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    names = ["Feuille1"] if len(sheets) == 1 else [f"Tableau {k + 1}" for k in range(len(sheets))]
    ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    workbook = (_XML + f'<workbook xmlns="{ns_main}" xmlns:r="{ns_rel}"><sheets>'
                + "".join(f'<sheet name="{_x(n)}" sheetId="{k + 1}" r:id="rId{k + 1}"/>' for k, n in enumerate(names))
                + "</sheets></workbook>")
    wb_rels = (_XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               + "".join(f'<Relationship Id="rId{k + 1}" Type="{ns_rel}/worksheet" Target="worksheets/sheet{k + 1}.xml"/>'
                         for k in range(len(sheets)))
               + f'<Relationship Id="rId{len(sheets) + 1}" Type="{ns_rel}/styles" Target="styles.xml"/></Relationships>')
    styles = (_XML + f'<styleSheet xmlns="{ns_main}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    ctypes = (_XML + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/>'
              '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
              + "".join(f'<Override PartName="/xl/worksheets/sheet{k + 1}.xml" '
                        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                        for k in range(len(sheets)))
              + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '</Types>')
    rels = (_XML + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{ns_rel}/officeDocument" Target="xl/workbook.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '</Relationships>')
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/styles.xml", styles)
        for k, sh in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{k + 1}.xml", sh)
        z.writestr("docProps/core.xml", _core_xml(title))
    return buf.getvalue()


def open_in_grimoire(path: str) -> bool:
    gb = grimoire_bin()
    return bool(gb) and _launch([gb, path])


def create_office(path: str, kind: str, content: str = "", roots=None, base=None, unique=False) -> dict:
    """Crée un .docx (depuis du Markdown) ou un .xlsx (depuis des tableaux Markdown)."""
    kind = "xlsx" if str(kind).lower().startswith("x") else "docx"
    real = safe_path(path, base=base, roots=roots)
    if not real.lower().endswith("." + kind):
        real = os.path.splitext(real)[0] + "." + kind
    if os.path.exists(real):
        if not unique:
            raise ApiError(f"« {os.path.basename(real)} » existe déjà.")
        real = unique_path(real)
    check_name(os.path.basename(real))
    title = os.path.splitext(os.path.basename(real))[0]
    data = make_xlsx(markdown_tables(content), title) if kind == "xlsx" else make_docx(content, title)
    os.makedirs(os.path.dirname(real), exist_ok=True)
    with open(real, "wb") as f:
        f.write(data)
    changed(real)
    return {"path": real, "kind": kind, "tableaux": len(markdown_tables(content)) if kind == "xlsx" else None}


# ════════════════════════════════════════════════════════════════════
#  Mises à jour (releases GitHub)
# ════════════════════════════════════════════════════════════════════
UPDATE_STATE = {"checked": 0.0, "latest": None, "error": None}
_update_lock = threading.Lock()
DEB_NAME_RE = re.compile(r"^archiviste_[0-9][\w.+~-]*_all\.deb$")


def parse_version(v: str) -> tuple:
    nums = [int(x) for x in re.findall(r"\d+", str(v or ""))[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def installed_version() -> str:
    """Version présente sur le disque : différente de celle qui tourne juste après une mise à jour."""
    try:
        m = re.search(r'^VERSION = "([^"]+)"', (APP_DIR / "archiviste.py").read_text("utf-8"), re.M)
        return m.group(1) if m else VERSION
    except OSError:
        return VERSION


def update_info() -> dict:
    lt = UPDATE_STATE["latest"]
    inst = installed_version()
    newer = bool(lt and lt.get("deb") and parse_version(lt["version"]) > parse_version(max(VERSION, inst, key=parse_version)))
    ignored = newer and parse_version(lt["version"]) == parse_version(get_settings().get("maj_ignoree") or "0")
    return {
        "actuelle": VERSION, "installee": inst,
        "relancer": parse_version(inst) != parse_version(VERSION),  # plus récente (mise à jour) ou plus ancienne (retour)
        "disponible": newer and not ignored,
        "ignoree": ignored,  # c'est la version qu'on a quittée en revenant en arrière : plus proposée d'office
        "derniere": lt, "erreur": UPDATE_STATE["error"], "verifie": UPDATE_STATE["checked"],
        "depot": UPDATE_REPO, "relance_possible": RELAUNCH_HOOK is not None,
        "paquet": str(APP_DIR) == "/opt/archiviste",
    }


def releases_api() -> str:
    return (os.environ.get("ARCHIVISTE_MAJ_API") or f"https://api.github.com/repos/{UPDATE_REPO}/releases").rstrip("/")


def _releases_get(path: str):
    req = urllib.request.Request(releases_api() + path, headers={"Accept": "application/vnd.github+json",
                                                                 "User-Agent": f"Archiviste/{VERSION}"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode("utf-8"))


def _release_info(data: dict) -> dict:
    asset = next((a for a in data.get("assets") or [] if DEB_NAME_RE.match(a.get("name", ""))), None)
    return {"version": str(data.get("tag_name", "")).lstrip("vV"), "notes": (data.get("body") or "")[:6000],
            "page": data.get("html_url"), "date": data.get("published_at"),
            "deb": asset and asset.get("browser_download_url"), "nom": asset and asset.get("name"),
            "taille": asset and asset.get("size"), "digest": asset and asset.get("digest")}


def check_update() -> dict:
    latest, err = None, None
    try:
        latest = _release_info(_releases_get("/latest"))
    except urllib.error.HTTPError as e:
        err = "Aucune version publiée pour l'instant." if e.code == 404 else f"GitHub a répondu {e.code}."
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        err = "Pas de connexion à GitHub."
    with _update_lock:
        UPDATE_STATE.update(checked=time.time(), latest=latest, error=err)
    return update_info()


UPDATE_HELPER = os.environ.get("ARCHIVISTE_MAJ_HELPER") or "/usr/lib/archiviste/installer-maj"
_install_lock = threading.Lock()


def updates_dir() -> Path:
    folder = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "archiviste" / "mises-a-jour"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _deb_version(name: str) -> str | None:
    m = re.match(r"^archiviste_([0-9][\w.+~-]*)_all\.deb$", name)
    return m.group(1) if m else None


def download_deb(lt: dict) -> Path:
    """Télécharge le paquet d'une version (ou reprend celui déjà sur le PC s'il est intact) et vérifie son
    empreinte. Les deux versions précédentes sont gardées, pour pouvoir y revenir."""
    name = os.path.basename(lt.get("nom") or "")
    allowed = ("https://github.com/",) + ((os.environ["ARCHIVISTE_MAJ_DEPOT"],) if os.environ.get("ARCHIVISTE_MAJ_DEPOT") else ())
    if not DEB_NAME_RE.match(name) or not str(lt.get("deb")).startswith(allowed):
        raise ApiError("Fichier de mise à jour inattendu : téléchargement annulé.")
    folder = updates_dir()
    dest, tmp = folder / name, folder / (name + ".part")
    digest = str(lt.get("digest") or "")
    if dest.is_file() and digest.startswith("sha256:"):
        h = hashlib.sha256()
        with open(dest, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() == digest[7:].lower():
            return dest
    sha = hashlib.sha256()
    req = urllib.request.Request(lt["deb"], headers={"User-Agent": f"Archiviste/{VERSION}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = 0
            for chunk in iter(lambda: r.read(1 << 16), b""):
                total += len(chunk)
                if total > 300_000_000:
                    raise ApiError("Fichier anormalement gros : téléchargement annulé.")
                sha.update(chunk)
                f.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        tmp.unlink(missing_ok=True)
        raise ApiError(f"Téléchargement impossible : {getattr(e, 'reason', e)}")
    except ApiError:
        tmp.unlink(missing_ok=True)
        raise
    with open(tmp, "rb") as f:
        magic = f.read(8)
    if magic != b"!<arch>\n" or (digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest()):
        tmp.unlink(missing_ok=True)
        raise ApiError("Le fichier téléchargé est abîmé (empreinte différente) : rien n'a été installé.")
    os.replace(tmp, dest)
    debs = sorted((p for p in folder.glob("archiviste_*_all.deb") if _deb_version(p.name)),
                  key=lambda p: parse_version(_deb_version(p.name)), reverse=True)
    for old in debs[3:]:
        if old != dest:
            old.unlink(missing_ok=True)
    return dest


def fetch_update() -> tuple[Path, dict]:
    """Télécharge le paquet de la dernière version."""
    info = update_info() if UPDATE_STATE["latest"] else check_update()
    lt = UPDATE_STATE["latest"]
    if not (info["disponible"] or info["ignoree"]):
        raise ApiError("Aucune mise à jour disponible.")
    return download_deb(lt), lt


def previous_release() -> dict | None:
    """Version précédente vers laquelle on peut revenir : un paquet gardé sur le PC, sinon la dernière
    version publiée plus ancienne que celle-ci."""
    cur = parse_version(installed_version())
    local = [(parse_version(v), v, p) for p in updates_dir().glob("archiviste_*_all.deb")
             if (v := _deb_version(p.name)) and parse_version(v) < cur]
    if local:
        _, v, p = max(local)
        return {"version": v, "fichier": str(p), "source": "pc"}
    try:
        rels = _releases_get("?per_page=20")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise ApiError("Pas de connexion à GitHub, et aucune version précédente gardée sur ce PC.")
    older = [r for r in (_release_info(x) for x in rels if isinstance(x, dict) and not x.get("draft"))
             if r["deb"] and parse_version(r["version"]) < cur]
    if not older:
        return None
    best = max(older, key=lambda r: parse_version(r["version"]))
    return {**best, "source": "github"}


def rollback_update() -> dict:
    """Revient à la version précédente d'Archiviste (réglages, agents, prompts et discussions sont gardés).
    La version quittée n'est plus proposée d'office ensuite."""
    if not _install_lock.acquire(blocking=False):
        raise ApiError("Une installation est déjà en cours.")
    try:
        prev = previous_release()
        if not prev:
            raise ApiError("Aucune version précédente n'a été trouvée.")
        dest = Path(prev["fichier"]) if prev["source"] == "pc" else download_deb(prev)
        left = installed_version()
        res = run_installer(dest)
        if res is None:
            opener = shutil.which("xdg-open")
            return {"fichier": str(dest), "ouvert": bool(opener) and _launch([opener, str(dest)]), "version": prev["version"]}
        if res["installe"]:
            patch = {"maj_ignoree": left}
            if parse_version(prev["version"]) < (1, 5, 0):
                patch["maj_auto"] = False  # ces versions ne savent pas ignorer une version : on coupe la vérification
            save_settings(patch)
        res.update(fichier=str(dest), version=prev["version"], quittee=left, relancer=update_info()["relancer"],
                   maj_auto=get_settings()["maj_auto"])
        return res
    finally:
        _install_lock.release()


def _apt_tail(out: str, n: int = 25) -> str:
    lines = [l for l in out.replace("\r", "\n").splitlines()
             if l.strip() and not re.match(r"^\(?(Lecture de la base|Reading database)", l)]
    return "\n".join(lines[-n:])


def _apt_explain(out: str, code: int) -> str:
    low = out.lower()
    if code == 126:
        return "Installation annulée : le mot de passe n'a pas été saisi."
    if code == 127:
        return "Autorisation refusée par le système (ou aucune fenêtre de mot de passe disponible)."
    if "could not get lock" in low or "verrou" in low or "lock-frontend" in low:
        return ("Une autre installation occupe le gestionnaire de paquets (gestionnaire de mises à jour, "
                "installateur encore ouvert…). Ferme-la ou attends une minute, puis réessaie.")
    if "unmet dependencies" in low or "dépendances non satisfaites" in low or "--fix-broken" in low:
        return ("Les paquets du système sont dans un état incohérent. Dans un terminal : "
                "sudo apt --fix-broken install, puis réessaie.")
    if "n'est pas archiviste" in low or "not archiviste" in low:
        return "Le paquet téléchargé n'est pas celui d'Archiviste : installation refusée."
    return "L'installation a échoué."


def run_installer(deb: Path) -> dict | None:
    """Installe le paquet avec apt-get, après le mot de passe demandé par la fenêtre de Mint (pkexec).
    apt-get attend qu'une autre installation se termine au lieu d'échouer. Renvoie None si impossible ici."""
    import tempfile
    pk = os.environ.get("ARCHIVISTE_PKEXEC") or shutil.which("pkexec")
    apt = shutil.which("apt-get")
    if not pk or not apt:
        return None
    work = tempfile.mkdtemp(prefix="archiviste-maj-")
    try:
        os.chmod(work, 0o755)  # lisible par l'utilisateur « _apt » d'apt
        copy = os.path.join(work, deb.name)
        shutil.copyfile(deb, copy)
        os.chmod(copy, 0o644)
        if os.access(UPDATE_HELPER, os.X_OK):
            cmd = [pk, UPDATE_HELPER, copy]
        else:
            cmd = [pk, "/usr/bin/env", "DEBIAN_FRONTEND=noninteractive", apt, "install", "-y", "--no-remove",
                   "--allow-downgrades", "-o", "DPkg::Lock::Timeout=180", copy]
        try:
            r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=1500)
        except subprocess.TimeoutExpired:
            return {"installe": False, "erreur": "L'installation prend trop de temps : vérifie le gestionnaire de paquets.",
                    "sortie": ""}
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        ok = r.returncode == 0
        return {"installe": ok, "erreur": None if ok else _apt_explain(out, r.returncode),
                "sortie": _apt_tail(out), "code": r.returncode}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def download_update(mode: str = "auto") -> dict:
    """Télécharge puis installe la mise à jour. mode « installateur » : ouvre plutôt l'installateur de Mint."""
    if not _install_lock.acquire(blocking=False):
        raise ApiError("Une installation est déjà en cours.")
    try:
        dest, lt = fetch_update()
        if mode != "installateur":
            res = run_installer(dest)
            if res is not None:
                if res["installe"] and get_settings().get("maj_ignoree"):
                    save_settings({"maj_ignoree": ""})  # on a choisi d'y retourner : elle n'est plus mise de côté
                res.update(fichier=str(dest), version=lt["version"], relancer=update_info()["relancer"])
                return res
        opener = shutil.which("xdg-open")
        opened = bool(opener) and _launch([opener, str(dest)])
        return {"fichier": str(dest), "ouvert": opened, "version": lt["version"]}
    finally:
        _install_lock.release()


def _update_loop() -> None:
    time.sleep(20)
    while True:
        try:
            if get_settings().get("maj_auto", True):
                check_update()
        except Exception:  # noqa: BLE001 — une vérification ratée ne doit jamais gêner l'appli
            pass
        time.sleep(6 * 3600)


# ════════════════════════════════════════════════════════════════════
#  Bureau : remplace le bureau de Nemo (icônes, raccourcis, volet IA)
# ════════════════════════════════════════════════════════════════════
UI_HOOK = None  # renseigné par fenetre.py : UI_HOOK(action, données) agit sur les fenêtres GTK
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
AUTOSTART = CONFIG_HOME / "autostart" / "archiviste-bureau.desktop"
LANG_KEYS = [k for k in dict.fromkeys(
    [(os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or "fr_FR")
     .split(".")[0].split("@")[0]]) if k and k not in ("C", "POSIX")]
if LANG_KEYS and "_" in LANG_KEYS[0]:
    LANG_KEYS.append(LANG_KEYS[0].split("_")[0])
CUR_DESKTOPS = [d.strip() for d in (os.environ.get("XDG_CURRENT_DESKTOP") or "X-Cinnamon").split(":") if d.strip()]
# Comme le menu de Cinnamon : les applis marquées « GNOME » (ex. le Terminal, OnlyShowIn=GNOME;Unity;) y apparaissent aussi.
if any("CINNAMON" in d.upper() for d in CUR_DESKTOPS) and "GNOME" not in CUR_DESKTOPS:
    CUR_DESKTOPS.append("GNOME")

BUREAU_DEFAUT = {
    "actif": False,            # le bureau Archiviste remplace celui de Nemo
    "volet": True,             # volet de droite déplié
    "conv": None,              # discussion du volet
    "tri": "nom",              # nom | date | type
    "dossiers": "archiviste",  # un dossier du bureau s'ouvre dans : archiviste | systeme
    "fond": "auto",            # auto | archiviste : dessiner soi-même le fond d'écran
    "nemo_avant": None,        # réglage du bureau de Nemo avant activation (pour le rétablir)
    "touche": None,            # raccourci clavier « Demander à l'Archiviste » posé dans Cinnamon
    "volet_largeur": None,     # largeur du volet en pixels (None : largeur d'origine)
    "conv_heures": 4,          # après tant d'heures sans échange, le volet repart sur une nouvelle discussion (0 : jamais)
    "conv_precedente": None,   # discussion du volet d'avant, pour « Reprendre la précédente »
    "volet_cote": "droite",    # bord de l'écran où se tient le volet : droite | gauche
    "ecran": None,             # écran qui porte le bureau Archiviste (None : l'écran principal)
    "dock_bord": True,         # souris poussée contre le bord du volet : les raccourcis apparaissent par-dessus les applis
}
MONITORS_HOOK = None  # renseigné par fenetre.py : liste des écrans branchés
CONV_HEURES = (0, 1, 4, 12, 24)
VOLET_MIN, VOLET_MAX = 440, 900


def bureau_state() -> dict:
    st = dict(BUREAU_DEFAUT)
    st.update(store.read("bureau.json", dict))
    return st


def bureau_patch(**changes) -> dict:
    """Change quelques réglages du bureau sans écraser ce qu'une autre fenêtre vient d'écrire (raccourcis…)."""
    return store.update("bureau.json", dict, lambda st: st.update(changes) or dict(st))


def user_dir(key: str, *fallbacks: str) -> str:
    """Dossiers spéciaux de xdg-user-dirs : DESKTOP → ~/Bureau, DOWNLOAD → ~/Téléchargements…"""
    try:
        for line in (CONFIG_HOME / "user-dirs.dirs").read_text("utf-8").splitlines():
            m = re.match(r'^\s*XDG_%s_DIR\s*=\s*"(.*)"\s*$' % key, line)
            if m:
                return os.path.realpath(os.path.expanduser(m.group(1).replace("$HOME", str(HOME))))
    except OSError:
        pass
    for name in fallbacks:
        if (HOME / name).is_dir():
            return os.path.realpath(HOME / name)
    return os.path.realpath(HOME / fallbacks[0])


def desktop_dir() -> str:
    return user_dir("DESKTOP", "Bureau", "Desktop")


def downloads_dir() -> str:
    return user_dir("DOWNLOAD", "Téléchargements", "Downloads")


def path_label(p: str) -> str:
    rp = os.path.realpath(p) if p else p
    if rp == os.path.realpath(HOME):
        return "Dossier personnel"
    if rp == desktop_dir():
        return "Bureau"
    return os.path.basename(rp.rstrip("/")) or rp


# ── commandes système ──
def gs(*args, timeout: float = 6):
    exe = shutil.which("gsettings")
    if not exe:
        return None
    try:
        return subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def gv(s):
    """Valeur GVariant au format texte (chaîne, booléen, nombre, liste) → Python."""
    if s is None:
        return None
    s = s.strip()
    if s.startswith("@"):
        s = s.split(" ", 1)[1] if " " in s else ""
    if s in ("true", "false"):
        return s == "true"
    try:
        return ast.literal_eval(s)
    except (ValueError, SyntaxError):
        return s


def gv_quote(s: str) -> str:
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def gv_list(items) -> str:
    return "[" + ", ".join(gv_quote(x) for x in items) + "]" if items else "@as []"


def gs_get(schema: str, key: str):
    r = gs("get", schema, key)
    return gv(r.stdout) if r is not None and r.returncode == 0 else None


def gs_set(schema: str, key: str, value: str) -> bool:
    r = gs("set", schema, key, value)
    return r is not None and r.returncode == 0


def gs_has(schema: str, key: str | None = None) -> bool:
    r = gs("list-keys", schema)
    return r is not None and r.returncode == 0 and (key is None or key in r.stdout.split())


# ── lanceurs .desktop ──
_DESK_ESC = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\", ";": ";"}


def _desk_unescape(v: str) -> str:
    return re.sub(r"\\(.)", lambda m: _DESK_ESC.get(m.group(1), m.group(0)), v)


def read_ini_section(path: str, section: str = "Desktop Entry") -> dict | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(300_000)
    except OSError:
        return None
    entry, inside = {}, False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            if inside:
                break
            inside = line[1:-1] == section
            continue
        if inside and "=" in line:
            k, v = line.split("=", 1)
            entry.setdefault(k.strip(), v.strip())
    return entry or None


def desk_val(e: dict, key: str, localized: bool = True) -> str:
    if localized:
        for lk in LANG_KEYS:
            v = e.get(f"{key}[{lk}]")
            if v:
                return _desk_unescape(v)
    return _desk_unescape(e.get(key, ""))


def desk_list(e: dict, key: str, localized: bool = False) -> list[str]:
    raw = ""
    if localized:
        raw = next((e[f"{key}[{lk}]"] for lk in LANG_KEYS if e.get(f"{key}[{lk}]")), "")
    raw = raw or e.get(key, "")
    return [_desk_unescape(x).strip() for x in re.split(r"(?<!\\);", raw) if x.strip()]


def shown_here(e: dict) -> bool:
    only = desk_list(e, "OnlyShowIn")
    if only and not any(d in only for d in CUR_DESKTOPS):
        return False
    return not any(d in desk_list(e, "NotShowIn") for d in CUR_DESKTOPS)


def app_visible(e: dict, any_desktop: bool = False) -> bool:
    if e.get("Type", "Application") != "Application":
        return False
    if to_bool(e.get("NoDisplay")) or to_bool(e.get("Hidden")):
        return False
    if not any_desktop and not shown_here(e):
        return False
    tx = e.get("TryExec")
    if tx and not (os.access(tx, os.X_OK) if os.path.isabs(tx) else shutil.which(tx)):
        return False
    return bool(e.get("Exec"))


def app_dirs() -> list[str]:
    dirs = [XDG_DATA / "applications"]
    for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if d.strip():
            dirs.append(Path(d.strip()) / "applications")
    dirs += [XDG_DATA / "flatpak/exports/share/applications", Path("/var/lib/flatpak/exports/share/applications"),
             Path("/var/lib/snapd/desktop/applications")]
    out = []
    for d in dirs:
        rp = os.path.realpath(d)
        if rp not in out and os.path.isdir(rp):
            out.append(rp)
    return out


def app_info(aid: str, path: str, e: dict) -> dict:
    return {"id": aid, "nom": desk_val(e, "Name") or aid[:-8], "generique": desk_val(e, "GenericName"),
            "description": desk_val(e, "Comment"), "icone": e.get("Icon", ""), "fichier": path,
            "categories": desk_list(e, "Categories"), "mots": desk_list(e, "Keywords", True),
            "mime": desk_list(e, "MimeType"), "exec": e.get("Exec", ""), "terminal": to_bool(e.get("Terminal")),
            "wmclass": e.get("StartupWMClass", "")}


def public_app(a: dict) -> dict:
    return {**{k: a[k] for k in ("id", "nom", "generique", "description", "icone", "categories", "mots")},
            "cmd": _exec_cmd(a)}


_APPS = {"sig": None, "list": [], "by_id": {}, "ailleurs": []}
_APPS_LOCK = threading.Lock()


def apps_index() -> dict:
    """Applications installées (menu de Mint), lues dans les fichiers .desktop, mises en cache."""
    dirs = app_dirs()
    sig = []
    for d in dirs:
        try:
            sig.append((d, os.stat(d).st_mtime_ns))
        except OSError:
            pass
    sig = tuple(sig)
    with _APPS_LOCK:
        if _APPS["sig"] == sig:
            return _APPS
        by_id, seen, ailleurs = {}, set(), []
        for d in dirs:
            for dirpath, _, files in os.walk(d):
                for fn in sorted(files):
                    if not fn.endswith(".desktop"):
                        continue
                    full = os.path.join(dirpath, fn)
                    aid = os.path.relpath(full, d).replace(os.sep, "-")
                    e = read_ini_section(full)
                    if aid in seen:  # même appli plus bas dans la liste (ex. celle du paquet, masquée)
                        if aid in by_id and e and app_visible(e):
                            by_id[aid].setdefault("alts", []).append(app_info(aid, full, e))
                        continue
                    seen.add(aid)
                    if e and app_visible(e):
                        by_id[aid] = app_info(aid, full, e)
                    elif e and app_visible(e, any_desktop=True):  # prévue pour un autre bureau : dernier recours
                        ailleurs.append(app_info(aid, full, e))
        for aid, a in list(by_id.items()):
            # un lanceur « terminal » qui masque l'appli du paquet (vieux script…) : on affiche et lance l'appli
            alt = next((x for x in a.get("alts", []) if not x["terminal"]), None) if a["terminal"] else None
            if alt:
                rest = [x for x in a["alts"] if x is not alt]
                by_id[aid] = {**alt, "alts": [{k: v for k, v in a.items() if k != "alts"}] + rest}
        _APPS.update(sig=sig, by_id=by_id, list=sorted(by_id.values(), key=lambda a: a["nom"].casefold()),
                     ailleurs=ailleurs)
        return _APPS


def _exec_cmd(a: dict) -> str:
    return os.path.basename((a.get("exec") or "").split(" ", 1)[0].strip('"'))


def launch_entry(a: dict) -> dict:
    """Entrée .desktop à lancer. Un lanceur qui s'ouvre dans un terminal (vieux script, copie modifiée…)
    et qui masque l'appli installée par son paquet : on lance plutôt l'appli, sans terminal."""
    if a.get("terminal"):
        for alt in a.get("alts", []):
            if not alt["terminal"]:
                return alt
    return a


def launch_app(a: dict, files: list[str] | None = None) -> None:
    launch_desktop(launch_entry(a)["fichier"], files)


_ART_RE = re.compile(r"^(?:l['’]\s*appli(?:cation)?\b|l['’]\s*app\b|le\s+logiciel\b|le\s+programme\b|"
                     r"(?:la|le|les|mon|ma|mes)\s+|l['’]\s*)\s*", re.I)
APP_SYNONYMES = {"navigateur": "WebBrowser", "internet": "WebBrowser", "web": "WebBrowser",
                 "terminal": "TerminalEmulator", "console": "TerminalEmulator",
                 "fichiers": "FileManager", "explorateur": "FileManager", "gestionnaire de fichiers": "FileManager",
                 "mail": "Email", "courriel": "Email", "messagerie": "Email"}


def _fold(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFD", str(t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def _osa(a: str, b: str) -> int:
    """Distance d'édition (fautes de frappe, lettre en trop/en moins, deux lettres inversées)."""
    if a == b:
        return 0
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


def _tolerance(n: int) -> int:
    return 0 if n <= 2 else 1 if n <= 5 else 2 if n <= 9 else 3


def _compact(t: str) -> str:
    return re.sub(r"[^a-z0-9]", "", t)


def _fuzzy_word(w: str, tokens: set, strict: bool = False) -> int | None:
    """Meilleure distance entre un mot tapé et les mots d'une appli (début de mot compris : « grimio » → grimoire)."""
    tol = _tolerance(len(w)) - (1 if strict else 0)
    best = None
    for t in tokens:
        if len(t) < 2:
            continue
        d = _osa(w, t)
        if len(t) > len(w) >= 3:
            d = min(d, _osa(w, t[:len(w)]) + (0 if t.startswith(w[:2]) else 1))
        if d <= tol and (best is None or d < best):
            best = d
    return best


def _app_tokens(a: dict) -> tuple[set, set]:
    name = _fold(a["nom"])
    words = {_compact(w) for w in re.split(r"[\s\-_.]+", name)}
    words |= {_compact(_fold(a["id"][:-8].rsplit(".", 1)[-1])), _compact(_fold(_exec_cmd(a)))}
    extra = {_compact(w) for w in re.split(r"[\s\-_.]+", _fold(a["generique"]))}
    extra |= {_compact(_fold(m)) for m in a["mots"]}
    return {w for w in words if w}, {w for w in extra if w}


def _score_apps(q: str, apps: list[dict]) -> list:
    """(score, terminal?, longueur, appli) : 0 exact … 4 mot-clé, 6+ orthographe approchée, 9 synonyme."""
    qc = _compact(q)
    qwords = [_compact(w) for w in q.split() if _compact(w)]
    scored = []
    for a in apps:
        name = _fold(a["nom"])
        stem = _fold(a["id"][:-8].rsplit(".", 1)[-1])
        cmd = _fold(_exec_cmd(a))
        gen = _fold(a["generique"])
        if q in (name, stem, cmd, gen) or qc in (_compact(name), _compact(stem)):
            sc = 0
        elif name.startswith(q) or stem.startswith(q) or _compact(name).startswith(qc):
            sc = 1
        elif any(w.startswith(q) for w in name.split()):
            sc = 2
        elif q in name or q in stem:
            sc = 3
        elif q in gen or any(_fold(m).startswith(q) for m in a["mots"]):
            sc = 4
        else:
            sc = None
            main, extra = _app_tokens(a)
            if qwords:
                ds = [_fuzzy_word(w, main) for w in qwords]
                if all(d is not None for d in ds):
                    sc = 6 + sum(ds)
                else:
                    ds = [_fuzzy_word(w, main) if _fuzzy_word(w, main) is not None else _fuzzy_word(w, extra, strict=True)
                          for w in qwords]
                    if all(d is not None for d in ds):
                        sc = 7.5 + sum(ds)
            if sc is None and len(qc) >= 4 and _osa(qc, _compact(name)) <= _tolerance(len(qc)):
                sc = 6 + _osa(qc, _compact(name))
            if sc is None:
                continue
        scored.append((sc, bool(a.get("terminal")), len(name), a))
    if not scored and q in APP_SYNONYMES:
        cat = APP_SYNONYMES[q]
        scored = [(9, bool(a.get("terminal")), 0, a) for a in apps if cat in a["categories"]]
    return scored


def _clean_query(query: str) -> str:
    q = _fold(query).strip(" .!?\"'«»")
    for _ in range(3):
        q = _ART_RE.sub("", q).strip()
    return q


def match_app_scored(query: str) -> tuple[float | None, dict | None, list[str]]:
    q = _clean_query(query)
    if not q:
        return None, None, []
    idx = apps_index()
    found = _score_apps(q, idx["list"]) or _score_apps(q, idx["ailleurs"])
    if not found:
        qc = _compact(q)
        near = sorted(idx["list"], key=lambda a: _osa(qc, _compact(_fold(a["nom"]))[:len(qc) + 2]))[:4]
        return None, None, [a["nom"] for a in near]
    found.sort(key=lambda x: (x[0], x[1], x[2]))
    return found[0][0], found[0][3], [x[3]["nom"] for x in found[1:5]]


def match_app(query: str) -> tuple[dict | None, list[str]]:
    """Trouve l'appli la plus proche d'un nom dit par l'utilisateur, même mal orthographié
    (« grimoire », « le terminale », « firefoks », « libre office »…)."""
    _, app, proches = match_app_scored(query)
    return app, proches


def special_dirs() -> list[tuple[tuple, str]]:
    return [
        (("bureau", "desktop"), desktop_dir()),
        (("telechargements", "telechargement", "downloads"), downloads_dir()),
        (("documents", "document", "docs"), user_dir("DOCUMENTS", "Documents")),
        (("images", "image", "photos", "pictures"), user_dir("PICTURES", "Images", "Pictures")),
        (("musique", "musiques", "music"), user_dir("MUSIC", "Musique", "Music")),
        (("videos", "video", "films"), user_dir("VIDEOS", "Vidéos", "Videos")),
        (("dossier personnel", "dossierpersonnel", "maison", "home", "perso"), os.path.realpath(HOME)),
    ]


def match_special_dir(query: str) -> str | None:
    """« téléchargements », « mes documents », « le dossier telechargement » → le dossier spécial correspondant."""
    q = re.sub(r"^(?:dossiers?|repertoires?)\s+(?:des?\s+|du\s+)?", "", _clean_query(query)).strip()
    q = _clean_query(q)
    qc = _compact(q)
    if len(qc) < 3:
        return None
    for keys, path in special_dirs():
        if not os.path.isdir(path):
            continue
        for k in keys:
            kc = _compact(k)
            if qc == kc or (len(qc) >= 4 and _osa(qc, kc) <= _tolerance(len(kc))):
                return path
    return None


def open_path(path: str) -> str:
    """Ouvre un fichier (Grimoire pour Word/Excel) ou un dossier (Archiviste ou Nemo selon le réglage du bureau)."""
    if os.path.isdir(path):
        if bureau_state().get("dossiers") != "systeme" and UI_HOOK is not None:
            UI_HOOK("ouvrir", {"vue": "files", "chemin": path})
            return "Archiviste"
    elif ext_of(path) in ("docx", "xlsx", "xlsm", "xls", "ods") and open_in_grimoire(path):
        return "Grimoire"
    opener = shutil.which("xdg-open")
    if not opener or not _launch([opener, path]):
        raise ApiError("Ouverture impossible : xdg-open est introuvable.")
    return "application par défaut"


def find_app(*names: str) -> str | None:
    """Identifiant d'une appli installée d'après son nom de commande ou de fichier .desktop."""
    apps = apps_index()["by_id"]
    want = {n.lower() for n in names}
    for a in apps.values():
        stem = a["id"][:-8].lower()
        if stem in want or stem.rsplit(".", 1)[-1] in want or _exec_cmd(a).lower() in want:
            return a["id"]
    return None


def terminal_app() -> str | None:
    pref = gs_get("org.cinnamon.desktop.default-applications.terminal", "exec")
    found = find_app(os.path.basename(pref)) if isinstance(pref, str) and pref else None
    if found:
        return found
    found = find_app("gnome-terminal", "org.gnome.terminal", "xfce4-terminal", "tilix", "konsole", "mate-terminal")
    if found:
        return found
    return next((a["id"] for a in apps_index()["list"] if "TerminalEmulator" in a["categories"]), None)



_GIO_LAUNCH = None


def gio_launch_ok() -> bool:
    global _GIO_LAUNCH
    if _GIO_LAUNCH is None:
        exe = shutil.which("gio")
        try:
            _GIO_LAUNCH = bool(exe) and subprocess.run([exe, "help", "launch"], capture_output=True,
                                                       timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            _GIO_LAUNCH = False
    return _GIO_LAUNCH


def exec_argv(e: dict, path: str, files: list[str]) -> list[str]:
    """Commande d'un lanceur (codes %f, %U… remplacés), si « gio launch » n'est pas disponible."""
    import shlex
    try:
        args = shlex.split(e.get("Exec", ""))
    except ValueError:
        raise ApiError("La commande de ce lanceur est illisible.")
    out = []
    for a in args:
        if a in ("%f", "%u"):
            out += files[:1]
        elif a in ("%F", "%U"):
            out += files
        elif a == "%i":
            if e.get("Icon"):
                out += ["--icon", e["Icon"]]
        elif a == "%c":
            out.append(desk_val(e, "Name"))
        elif a == "%k":
            out.append(path)
        else:
            a = re.sub(r"%([a-zA-Z%])", lambda m: "%" if m.group(1) == "%" else "", a)
            if a:
                out.append(a)
    if not out:
        raise ApiError("Ce lanceur n'a pas de commande.")
    if to_bool(e.get("Terminal")):
        term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
        if term:
            out = [term, "-e"] + out
    return out


def launch_desktop(path: str, files: list[str] | None = None) -> None:
    import tempfile
    files = files or []
    e = read_ini_section(path)
    if not e:
        raise ApiError("Lanceur illisible.")
    if e.get("Type") == "Link":
        url = e.get("URL", "")
        if not url.startswith(("http://", "https://", "file://")):
            raise ApiError("Lien non pris en charge.")
        opener = shutil.which("xdg-open")
        if not opener or not _launch([opener, url]):
            raise ApiError("Impossible d'ouvrir ce lien.")
        return
    if gio_launch_ok():
        with tempfile.TemporaryFile() as err:
            try:
                r = subprocess.run(["gio", "launch", path, *files], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=err, timeout=10, start_new_session=True)
                if r.returncode == 0:
                    return
            except subprocess.TimeoutExpired:
                return
            except OSError:
                pass
    if not _launch(exec_argv(e, path, files)):
        raise ApiError("Le lancement a échoué.")


def mime_of(path: str) -> str:
    if os.path.isdir(path):
        return "inode/directory"
    exe = shutil.which("gio")
    if exe:
        try:
            r = subprocess.run([exe, "info", "-a", "standard::content-type", path],
                               capture_output=True, text=True, timeout=5)
            m = re.search(r"standard::content-type:\s*(\S+)", r.stdout)
            if m:
                return m.group(1)
        except (OSError, subprocess.SubprocessError):
            pass
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def apps_for(path: str) -> dict:
    mime = mime_of(path)
    idx = apps_index()
    defaut = None
    exe = shutil.which("xdg-mime")
    if exe:
        try:
            r = subprocess.run([exe, "query", "default", mime], capture_output=True, text=True, timeout=5)
            defaut = r.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):
            pass
    family = mime.split("/")[0] + "/*"
    apps = [a for a in idx["list"] if mime in a["mime"] or family in a["mime"]]
    if mime.startswith("text/") and mime != "text/plain":
        apps += [a for a in idx["list"] if "text/plain" in a["mime"] and a not in apps]
    apps.sort(key=lambda a: (a["id"] != defaut, a["nom"].casefold()))
    return {"mime": mime, "defaut": defaut if defaut in idx["by_id"] else None, "apps": [public_app(a) for a in apps]}


# ── fenêtres ouvertes (le volet sert de dock : repère « appli ouverte », ramener ou réduire d'un clic) ──
WINDOWS_HOOK = None  # renseigné par fenetre.py : suivi des fenêtres du bureau — .version, .snapshot(), .act(xids, action)
_GENERIC_CMDS = {"env", "sh", "bash", "dash", "python", "python3", "flatpak", "snap", "gtk-launch", "xdg-open",
                 "electron", "java", "wine", "node", "perl", "ruby", "exo-open", "gio", "pkexec", "sudo"}


def _proc_names(pid) -> set[str]:
    """Noms sous lesquels tourne un processus (exécutable, premiers arguments), pour le rattacher à une appli."""
    out = set()
    try:
        out.add(os.path.basename(os.readlink(f"/proc/{int(pid)}/exe")))
    except (OSError, TypeError, ValueError):
        pass
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as f:
            args = f.read(4096).split(b"\0")
        for a in args[:2]:
            a = a.decode("utf-8", "replace")
            if a and not a.startswith("-"):
                out.add(os.path.basename(a))
    except (OSError, TypeError, ValueError):
        pass
    return {_compact(_fold(n)) for n in out if n and n.lower() not in _GENERIC_CMDS} - {""}


def _app_wm_names(a: dict) -> tuple[str, str, str]:
    """Nom du fichier .desktop (entier et dernier segment) et commande, réduits à leurs lettres et chiffres."""
    aid = os.path.basename(a["id"])
    stem = aid[:-8] if aid.endswith(".desktop") else aid
    cmd = _exec_cmd(a)
    return (_compact(_fold(stem)), _compact(_fold(stem.rsplit(".", 1)[-1])),
            "" if cmd.lower() in _GENERIC_CMDS else _compact(_fold(cmd)))


def window_app(win: dict, cands: list[dict]) -> dict | None:
    """Appli (.desktop) à laquelle appartient une fenêtre, d'après sa classe X11, comme le fait une barre des
    tâches : StartupWMClass d'abord, puis nom du fichier .desktop, commande, processus, enfin début de nom commun."""
    cls, inst = _fold(win.get("cls") or ""), _fold(win.get("inst") or "")
    ccls, cinst = _compact(cls), _compact(inst)
    if not (ccls or cinst):
        return None
    procs = None
    best, best_score = None, 99.0
    for a in cands:
        wc = _fold(a.get("wmclass") or "")
        stem, last, cmd = _app_wm_names(a)
        if wc and wc in (cls, inst):
            score = 0
        elif ccls and ccls in (stem, last):
            score = 1
        elif cinst and cinst in (stem, last):
            score = 2
        elif cmd and cmd == ccls:
            score = 3
        elif cmd and cmd == cinst:
            score = 4
        else:
            if procs is None:
                procs = _proc_names(win.get("pid")) if win.get("pid") else set()
            if cmd and cmd in procs:
                score = 5
            else:
                score = None
                for k in {stem, last, cmd} - {""}:
                    for c in {ccls, cinst} - {""}:
                        short, long_ = sorted((k, c), key=len)
                        if len(short) >= 4 and long_.startswith(short):
                            sc = 6 + (len(long_) - len(short)) / 100
                            score = sc if score is None else min(score, sc)
                if score is None:
                    continue
        if score < best_score:
            best, best_score = a, score
    return best


def window_groups(internal: bool = False) -> dict:
    """Fenêtres ouvertes, regroupées par appli, de la plus récemment utilisée à la plus ancienne.
    Clés : « app:<id du raccourci> », « archiviste » (la fenêtre principale), « win:<classe> » (appli inconnue)."""
    hook = WINDOWS_HOOK
    if hook is None:
        return {"dispo": False, "groupes": [], "sig": ""}
    wins = hook.snapshot()
    idx = apps_index()
    pinned = []
    for sc in store.read("bureau.json", dict).get("raccourcis") or []:  # lanceurs épinglés par leur fichier
        c = sc.get("cible", "")
        if sc.get("type") == "app" and os.path.isabs(c):
            e = read_ini_section(c)
            if e:
                pinned.append(app_info(c, c, e))
    cands = pinned + idx["list"] + idx["ailleurs"]
    groups: dict[str, dict] = {}
    for w in wins:
        if w.get("soi"):
            key, nom, icone, app = "archiviste", "Archiviste", "", None
        else:
            a = window_app(w, cands)
            if a:
                key, nom, icone, app = "app:" + a["id"], a["nom"], a["icone"], a["id"]
            else:
                cls = w.get("cls") or w.get("inst") or "Fenêtre"
                key, nom, icone, app = "win:" + cls.casefold(), cls, (w.get("inst") or cls).lower(), None
        g = groups.setdefault(key, {"cle": key, "app": app, "nom": nom, "icone": icone, "n": 0, "reduit": True,
                                    "devant": False, "titres": [], "xids": [], "fenetres": []})
        g["n"] += 1
        g["titres"].append(str(w.get("titre") or "")[:90])
        g["xids"].append(w["xid"])
        g["fenetres"].append({"id": w["xid"], "titre": str(w.get("titre") or "")[:90], "reduit": bool(w.get("reduit"))})
        if not w.get("reduit"):
            g["reduit"] = False
    top = next((w for w in wins if not w.get("reduit")), None)
    if top is not None:
        next(g for g in groups.values() if top["xid"] in g["xids"])["devant"] = True
    out = list(groups.values())
    sig = hashlib.sha1(json.dumps([[g["cle"], g["n"], g["reduit"], g["devant"], g["titres"]] for g in out])
                       .encode()).hexdigest()[:12]
    if not internal:
        out = [{k: v for k, v in g.items() if k != "xids"} for g in out]
    return {"dispo": True, "groupes": out, "sig": sig}


def window_action(cle: str, action: str, fenetre=None) -> dict:
    """basculer : ramène l'appli devant, ou la réduit si elle y est déjà (comme un dock) ; afficher, reduire,
    fermer. Avec « fenetre » : seulement cette fenêtre de l'appli."""
    if WINDOWS_HOOK is None:
        return {"ok": False, "ouverte": False, "dispo": False}
    if action not in ("basculer", "afficher", "reduire", "fermer"):
        raise ApiError("Action inconnue.")
    g = next((g for g in window_groups(internal=True)["groupes"] if g["cle"] == cle), None)
    if g is None:
        return {"ok": False, "ouverte": False, "dispo": True}
    xids = g["xids"]
    if fenetre is not None:
        try:
            xids = [x for x in xids if x == int(fenetre)]
        except (TypeError, ValueError):
            xids = []
        if not xids:
            return {"ok": False, "ouverte": False, "dispo": True}
    if action == "basculer":
        action = "reduire" if g["devant"] and not g["reduit"] else "afficher"
    WINDOWS_HOOK.act(xids, action)
    return {"ok": True, "ouverte": True, "dispo": True, "action": action, "nom": g["nom"]}


def raise_app(app_id: str) -> bool:
    """Si l'appli est déjà ouverte, ramène sa fenêtre devant (au lieu d'en lancer une autre). Vrai si c'est fait."""
    try:
        return bool(window_action("app:" + app_id, "afficher").get("ouverte"))
    except Exception:  # noqa: BLE001 — le suivi des fenêtres ne doit jamais empêcher de lancer une appli
        return False


# ── icônes du thème (Mint-Y…) ──
_ICON_IDX: dict = {}
_ICON_LOCK = threading.Lock()
_ICON_THEME = {"name": None, "t": 0.0}
ICON_DIR_RE = re.compile(r"^(\d+)(?:x\d+)?(?:@(\d+)x?)?$")
ICON_FILE_EXTS = (".png", ".svg")


def icon_bases() -> list[str]:
    bases = [str(HOME / ".icons"), str(XDG_DATA / "icons")]
    for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"):
        if d.strip():
            bases.append(os.path.join(d.strip(), "icons"))
    bases += [str(XDG_DATA / "flatpak/exports/share/icons"), "/var/lib/flatpak/exports/share/icons"]
    out = []
    for b in bases:
        rp = os.path.realpath(b)
        if rp not in out and os.path.isdir(rp):
            out.append(rp)
    return out


def icon_theme_name() -> str:
    if _ICON_THEME["name"] and time.time() - _ICON_THEME["t"] < 60:
        return _ICON_THEME["name"]
    name = None
    for schema in ("org.cinnamon.desktop.interface", "org.gnome.desktop.interface"):
        v = gs_get(schema, "icon-theme")
        if isinstance(v, str) and v:
            name = v
            break
    if not name:
        ini = read_ini_section(str(CONFIG_HOME / "gtk-3.0" / "settings.ini"), "Settings") or {}
        name = ini.get("gtk-icon-theme-name") or "hicolor"
    _ICON_THEME.update(name=name, t=time.time())
    return name


def theme_chain(name: str) -> list[str]:
    chain, todo = [], [name]
    while todo:
        t = todo.pop(0)
        if t in chain or len(chain) > 12:
            continue
        chain.append(t)
        for b in icon_bases():
            idx = read_ini_section(os.path.join(b, t, "index.theme"), "Icon Theme")
            if idx is not None:
                todo += [x.strip() for x in idx.get("Inherits", "").split(",") if x.strip()]
                break
    for t in ("Mint-Y", "Adwaita", "hicolor"):
        if t not in chain:
            chain.append(t)
    return chain


def theme_index(theme: str) -> dict:
    with _ICON_LOCK:
        if theme in _ICON_IDX:
            return _ICON_IDX[theme]
        idx: dict[str, list] = {}
        for b in icon_bases():
            root = os.path.join(b, theme)
            if not os.path.isdir(root):
                continue
            for dirpath, _, files in os.walk(root):
                rel = os.path.relpath(dirpath, root).split(os.sep)
                size = 0
                for part in rel:
                    m = ICON_DIR_RE.match(part)
                    if m:
                        size = int(m.group(1)) * int(m.group(2) or 1)
                for fn in files:
                    stem, ext = os.path.splitext(fn)
                    ext = ext.lower()
                    if ext in ICON_FILE_EXTS:
                        idx.setdefault(stem, []).append((10_000 if ext == ".svg" else size, os.path.join(dirpath, fn)))
        _ICON_IDX[theme] = idx
        return idx


def find_icon(name: str, size: int = 48) -> str | None:
    name = (name or "").strip()
    if not name or "\x00" in name:
        return None
    if os.path.isabs(name):
        ok = os.path.splitext(name)[1].lower() in (".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif", ".ico")
        return name if ok and os.path.isfile(name) and os.path.getsize(name) < 4_000_000 else None
    stem = name[:-4] if name.lower().endswith((".png", ".svg", ".xpm")) else name
    want = max(16, min(512, size)) * 2  # net sur écran HiDPI ou avec zoom
    for theme in theme_chain(icon_theme_name()):
        # les thèmes façon macOS contiennent beaucoup de liens : on ignore ceux qui sont cassés
        cands = [c for c in theme_index(theme).get(stem) or [] if os.access(c[1], os.R_OK)]
        if not cands:
            continue
        svg = [p for s, p in cands if s == 10_000]
        if svg:
            return svg[0]
        bigger = sorted(c for c in cands if c[0] >= want)
        return (bigger[0] if bigger else max(cands))[1]
    for d in ("/usr/share/pixmaps", str(XDG_DATA / "pixmaps")):
        for ext in ICON_FILE_EXTS:
            p = os.path.join(d, stem + ext)
            if os.path.isfile(p):
                return p
    return None


_ICON_PATHS = {"sig": None, "paths": set(), "desk": (0.0, set())}


def icon_path_allowed(path: str) -> bool:
    """Une icône donnée par son chemin complet n'est servie que si elle est dans un dossier autorisé, ou si
    c'est bien l'icône d'une appli installée ou d'un lanceur du bureau : /api/icone ne sert pas à lire
    n'importe quelle image du disque."""
    real = os.path.realpath(path)
    if any(within(real, r) for r in allowed_roots()):
        return True
    idx = apps_index()
    if _ICON_PATHS["sig"] != idx["sig"]:
        paths = set()
        for a in idx["list"] + idx["ailleurs"]:
            for x in [a] + a.get("alts", []):
                if os.path.isabs(x.get("icone") or ""):
                    paths.add(os.path.realpath(x["icone"]))
        _ICON_PATHS.update(sig=idx["sig"], paths=paths)
    if real in _ICON_PATHS["paths"]:
        return True
    t, desk = _ICON_PATHS["desk"]
    if real not in desk and time.time() - t > 1.5:  # lanceurs posés sur le bureau, ou épinglés par leur fichier
        desk = set()
        files = []
        try:
            files += [de.path for de in os.scandir(desktop_dir()) if de.name.endswith(".desktop")]
        except OSError:
            pass
        files += [sc.get("cible", "") for sc in store.read("bureau.json", dict).get("raccourcis") or []
                  if sc.get("type") == "app" and os.path.isabs(sc.get("cible", ""))]
        for f in files:
            ic = (read_ini_section(f) or {}).get("Icon", "")
            if os.path.isabs(ic):
                desk.add(os.path.realpath(ic))
        _ICON_PATHS["desk"] = (time.time(), desk)
    return real in desk


ICON_HOOK = None  # renseigné par fenetre.py : même recherche d'icône que Cinnamon (Gtk.IconTheme)
_ICON_CACHE: dict = {}


def resolve_icon(name: str, size: int) -> tuple[str | None, bytes | None]:
    """Fichier d'icône (png/svg) ou image PNG prête à l'emploi pour un nom d'icône d'appli."""
    name = (name or "").strip()
    size = max(16, min(512, size))
    key = (name, size)
    hit = _ICON_CACHE.get(key)
    if hit and time.time() - hit[2] < 600:
        return hit[0], hit[1]
    path, png = None, None
    if name and "\x00" not in name:
        if os.path.isabs(name):
            if not icon_path_allowed(name):
                raise ApiError("Icône hors des dossiers autorisés.", 403)
            path = find_icon(name, size)
        if not path and ICON_HOOK is not None:
            r = ICON_HOOK(name, size * 2) or {}
            path, png = r.get("path"), r.get("png")
        if not path and not png:
            path = find_icon(name, size)
    if len(_ICON_CACHE) > 600:
        _ICON_CACHE.clear()
    _ICON_CACHE[key] = (path, png, time.time())
    return path, png


# ── fond d'écran ──
WALL_EXTS = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "svg"}


def wallpaper_info() -> dict:
    uri = opts = color = None
    for schema in ("org.cinnamon.desktop.background", "org.gnome.desktop.background"):
        uri = gs_get(schema, "picture-uri")
        if isinstance(uri, str):
            opts = gs_get(schema, "picture-options")
            color = gs_get(schema, "primary-color")
            break
    path = None
    if isinstance(uri, str) and uri.startswith("file://"):
        path = urllib.parse.unquote(urllib.parse.urlsplit(uri).path)
        if not os.path.isfile(path) or ext_of(path) not in WALL_EXTS:
            path = None
    return {"chemin": path, "options": opts if isinstance(opts, str) else "zoom",
            "couleur": color if isinstance(color, str) and color.startswith("#") else "#1b1512",
            "mtime": os.path.getmtime(path) if path else 0}


# ── contenu du bureau ──
def volumes() -> list[dict]:
    """Clés USB et disques montés (comme les icônes de volumes du bureau de Nemo)."""
    user = os.environ.get("USER") or HOME.name
    out = []
    for base in (f"/media/{user}", f"/run/media/{user}"):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for n in names:
            p = os.path.join(base, n)
            if os.path.ismount(p):
                out.append({"nom": n, "path": p})
    return out


def trash_count() -> int:
    try:
        return len(os.listdir(TRASH_DIR / "files"))
    except OSError:
        return 0


def bureau_sig() -> str:
    parts = []
    for p in (desktop_dir(), str(TRASH_DIR / "files")):
        try:
            parts.append(str(os.stat(p).st_mtime_ns))
        except OSError:
            parts.append("0")
    parts.append(",".join(v["nom"] for v in volumes()))
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def launcher_info(path: str) -> dict | None:
    e = read_ini_section(path)
    if not e:
        return None
    return {"nom": desk_val(e, "Name") or os.path.basename(path)[:-8], "icone": e.get("Icon", ""),
            "description": desk_val(e, "Comment"), "type": e.get("Type", "Application"),
            "fiable": os.access(path, os.X_OK)}


def bureau_elements() -> dict:
    desk = desktop_dir()
    os.makedirs(desk, exist_ok=True)
    items = []
    with os.scandir(desk) as it:
        for de in it:
            if de.name.startswith(".") or de.name.endswith(".archiviste-part"):
                continue
            e = entry_info(de.path, de.name)
            if not e["dir"] and e["ext"] == "desktop":
                e["lanceur"] = launcher_info(de.path)
            items.append(e)
    return {"dossier": desk, "elements": items, "volumes": volumes(), "corbeille": trash_count(),
            "home": str(HOME), "sig": bureau_sig()}


def a_ranger() -> dict:
    """Fichiers « en vrac » dans Téléchargements et sur le bureau."""
    out = {}
    for key, path in (("telechargements", downloads_dir()), ("bureau", desktop_dir())):
        n, oldest, size = 0, None, 0
        try:
            with os.scandir(path) as it:
                for de in it:
                    if de.name.startswith(".") or de.name.endswith((".desktop", ".part", ".crdownload",
                                                                    ".archiviste-part")):
                        continue
                    try:
                        if de.is_dir():
                            continue
                        st = de.stat()
                    except OSError:
                        continue
                    n += 1
                    size += st.st_size
                    oldest = st.st_mtime if oldest is None else min(oldest, st.st_mtime)
        except OSError:
            pass
        out[key] = {"chemin": path, "fichiers": n, "depuis": oldest, "taille": size}
    return out


# ── raccourcis du volet ──
MAX_SHORTCUTS = 32


def default_shortcuts() -> list[dict]:
    sc = [{"type": "archiviste", "cible": ""}]
    g = find_app("grimoire")
    if g:
        sc.append({"type": "app", "cible": g})
    sc.append({"type": "dossier", "cible": os.path.realpath(HOME)})
    for key, fb in (("DOCUMENTS", ("Documents",)), ("DOWNLOAD", ("Téléchargements", "Downloads"))):
        p = user_dir(key, *fb)
        if os.path.isdir(p) and p != os.path.realpath(HOME):
            sc.append({"type": "dossier", "cible": p})
    t = terminal_app()
    if t:
        sc.append({"type": "app", "cible": t})
    for s in sc:
        s["id"] = new_id("r_")
    return sc


def shortcuts_raw() -> list[dict]:
    with store.lock:
        st = store.read("bureau.json", dict)
        if not isinstance(st.get("raccourcis"), list):
            st["raccourcis"] = default_shortcuts()
            store.write("bureau.json", st)
        return st["raccourcis"]


def shortcuts_save(lst: list[dict]) -> None:
    bureau_patch(raccourcis=lst)


def resolve_shortcut(s: dict) -> dict:
    r = {"id": s.get("id"), "type": s.get("type"), "cible": s.get("cible", ""), "nom": s.get("nom") or ""}
    t = r["type"]
    if t == "archiviste":
        r.update(titre=r["nom"] or "Archiviste", ok=True, description="Ouvrir la fenêtre d'Archiviste")
    elif t == "app":
        c = r["cible"]
        if os.path.isabs(c):
            li = launcher_info(c) if os.path.isfile(c) else None
            r.update(titre=r["nom"] or (li["nom"] if li else os.path.basename(c)), icone=li["icone"] if li else "",
                     ok=bool(li), description=(li or {}).get("description", ""))
        else:
            a = apps_index()["by_id"].get(c)
            r.update(titre=r["nom"] or (a["nom"] if a else c.removesuffix(".desktop")), icone=a["icone"] if a else "",
                     ok=bool(a), description=a["description"] if a else "")
    else:
        p = r["cible"]
        ok = os.path.exists(p)
        r.update(titre=r["nom"] or path_label(p), ok=ok, description=p)
        if ok:
            e = entry_info(p)
            r.update(ext=e["ext"], kind=e["kind"], dir=e["dir"])
    if not r.get("ok"):
        r["description"] = "Introuvable : " + (r.get("description") or r["cible"])
    return r


def shortcuts() -> list[dict]:
    return [resolve_shortcut(s) for s in shortcuts_raw()]


def shortcut_add(b: dict) -> dict:
    t = str(b.get("type") or "")
    cible = str(b.get("cible") or "")
    if t == "archiviste":
        cible = ""
    elif t == "app":
        if os.path.isabs(cible):
            cible = os.path.realpath(cible)
            if not cible.endswith(".desktop") or not os.path.isfile(cible):
                raise ApiError("Lanceur introuvable.", 404)
            # copie d'une appli du menu (« Ajouter au bureau ») : on épingle l'appli elle-même
            ex = (read_ini_section(cible) or {}).get("Exec")
            bn = os.path.basename(cible).lower()
            same = next((a for a in apps_index()["list"] if a["id"].lower() == bn or (ex and a["exec"] == ex)), None)
            if same:
                cible = same["id"]
        elif cible not in apps_index()["by_id"]:
            raise ApiError("Cette application n'est pas installée.", 404)
    elif t in ("dossier", "fichier"):
        cible = safe_path(cible, must_exist=True)
        t = "dossier" if os.path.isdir(cible) else "fichier"
    else:
        raise ApiError("Type de raccourci inconnu.")
    with store.lock:  # vérifier puis ajouter d'un seul tenant : deux épinglages simultanés ne se marchent pas dessus
        lst = shortcuts_raw()
        for s in lst:
            if s.get("type") == t and s.get("cible", "") == cible:
                return {"deja": True, "raccourci": resolve_shortcut(s), "raccourcis": shortcuts()}
        if len(lst) >= MAX_SHORTCUTS:
            raise ApiError(f"Le volet est plein ({MAX_SHORTCUTS} raccourcis) : retires-en un d'abord.")
        item = {"id": new_id("r_"), "type": t, "cible": cible}
        nom = str(b.get("nom") or "").strip()[:60]
        if nom:
            item["nom"] = nom
        lst.append(item)
        shortcuts_save(lst)
    return {"deja": False, "raccourci": resolve_shortcut(item), "raccourcis": shortcuts()}


# ── activation : démarrage auto, bureau de Nemo, raccourci clavier ──
KB_BASE = "org.cinnamon.desktop.keybindings"
KB_RELOC = "org.cinnamon.desktop.keybindings.custom-keybinding"
KB_NAME = "archiviste-demander"
KB_CANDIDATS = ["<Super>space", "<Primary><Alt>space", "<Super><Alt>space"]


def launcher_cmd() -> str:
    if shutil.which("archiviste"):
        return "archiviste"
    return f'"{sys.executable}" "{APP_DIR / "fenetre.py"}"'


def accel_label(a: str | None) -> str:
    if not a:
        return ""
    names = {"super": "Super", "primary": "Ctrl", "control": "Ctrl", "alt": "Alt", "shift": "Maj"}
    mods = [names.get(m.lower(), m) for m in re.findall(r"<([^>]+)>", a)]
    key = re.sub(r"<[^>]+>", "", a)
    key = {"space": "Espace"}.get(key.lower(), key.upper() if len(key) == 1 else key)
    return " + ".join(mods + [key])


def _norm_accel(a: str) -> str:
    return re.sub(r"<(control|ctrl)>", "<primary>", a.strip().lower())


def _kb_path(name: str) -> str:
    return f"/org/cinnamon/desktop/keybindings/custom-keybindings/{name}/"


def used_accels() -> set[str]:
    acc: set[str] = set()
    for schema in (KB_BASE, KB_BASE + ".wm", KB_BASE + ".media-keys"):
        r = gs("list-recursively", schema)
        if r is None or r.returncode != 0:
            continue
        for line in r.stdout.splitlines():
            parts = line.split(" ", 2)
            if len(parts) == 3:
                v = gv(parts[2])
                for x in (v if isinstance(v, list) else [v]):
                    if isinstance(x, str) and x.startswith("<"):
                        acc.add(_norm_accel(x))
    for name in gs_get(KB_BASE, "custom-list") or []:
        if name == KB_NAME:
            continue
        v = gs_get(f"{KB_RELOC}:{_kb_path(name)}", "binding")
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str) and x:
                acc.add(_norm_accel(x))
    return acc


def set_keybinding(on: bool, st: dict) -> dict:
    step = {"etape": "touche", "titre": "Raccourci clavier « Demander à l'Archiviste »"}
    if not gs_has(KB_BASE, "custom-list"):
        st["touche"] = None
        return {**step, "ok": None, "message": "Raccourcis personnalisés de Cinnamon introuvables."}
    reloc = f"{KB_RELOC}:{_kb_path(KB_NAME)}"
    cur = [x for x in (gs_get(KB_BASE, "custom-list") or []) if isinstance(x, str)]
    if not on:
        ok = True
        if KB_NAME in cur:
            ok = gs_set(KB_BASE, "custom-list", gv_list([x for x in cur if x != KB_NAME]))
        for k in ("name", "command", "binding"):
            gs("reset", reloc, k)
        st["touche"] = None
        return {**step, "ok": ok, "message": "Raccourci retiré." if ok else "Impossible de retirer le raccourci."}
    used = used_accels()
    accel = next((a for a in KB_CANDIDATS if _norm_accel(a) not in used), None)
    if not accel:
        return {**step, "ok": False, "message": "Super + Espace et ses variantes sont déjà pris : choisis une touche "
                                                "dans Paramètres système › Clavier (commande : archiviste --demander)."}
    rng = gs("range", reloc, "binding")
    single = rng is not None and rng.returncode == 0 and rng.stdout.split()[-1:] == ["s"]
    ok = (gs_set(reloc, "name", gv_quote("Archiviste — demander"))
          and gs_set(reloc, "command", gv_quote(launcher_cmd() + " --demander"))
          and gs_set(reloc, "binding", gv_quote(accel) if single else gv_list([accel])))
    if ok and KB_NAME not in cur:
        ok = gs_set(KB_BASE, "custom-list", gv_list(cur + [KB_NAME]))
    st["touche"] = accel if ok else None
    return {**step, "ok": ok, "message": f"{accel_label(accel)} ouvre « Demander à l'Archiviste » partout."
            if ok else "Le raccourci n'a pas pu être enregistré dans Cinnamon."}


def set_nemo_desktop(show: bool, st: dict) -> dict:
    step = {"etape": "nemo", "titre": "Icônes du bureau de Nemo"}
    schema = "org.nemo.desktop"
    if gs_has(schema, "desktop-layout"):
        cur = gs_get(schema, "desktop-layout")
        if show:
            val = st.get("nemo_avant") or "true::false"
            if not isinstance(val, str) or val.startswith("false::false"):
                val = "true::false"
            ok = gs_set(schema, "desktop-layout", gv_quote(val))
            if ok:
                st["nemo_avant"] = None
            return {**step, "ok": ok, "message": "Bureau de Nemo rétabli." if ok else "Impossible de rétablir Nemo."}
        if isinstance(cur, str) and not cur.startswith("false::false"):
            st["nemo_avant"] = cur
        ok = gs_set(schema, "desktop-layout", "'false::false'")
        return {**step, "ok": ok, "message": "Les icônes de Nemo laissent la place à Archiviste." if ok
                else "Impossible de masquer les icônes de Nemo."}
    if gs_has(schema, "show-desktop-icons"):
        ok = gs_set(schema, "show-desktop-icons", "true" if show else "false")
        return {**step, "ok": ok, "message": "Réglage de Nemo mis à jour." if ok else "Réglage de Nemo impossible."}
    return {**step, "ok": None, "message": "Bureau de Nemo non détecté : rien à masquer."}


def set_autostart(on: bool) -> dict:
    step = {"etape": "demarrage", "titre": "Démarrage avec la session"}
    try:
        if on:
            AUTOSTART.parent.mkdir(parents=True, exist_ok=True)
            AUTOSTART.write_text(
                "[Desktop Entry]\nType=Application\nName=Archiviste — bureau\n"
                "Comment=Bureau Archiviste : icônes, raccourcis et IA locale\n"
                f"Exec={launcher_cmd()} --bureau\nIcon=archiviste\nTerminal=false\n"
                "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Phase=Desktop\n", "utf-8")
            return {**step, "ok": True, "message": "Le bureau Archiviste s'affichera à chaque ouverture de session."}
        AUTOSTART.unlink(missing_ok=True)
        return {**step, "ok": True, "message": "Démarrage automatique retiré."}
    except OSError as e:
        return {**step, "ok": False, "message": f"Fichier de démarrage impossible : {e}"}


def bureau_activer(on: bool) -> dict:
    st = bureau_state()
    rapport = [set_autostart(on), set_nemo_desktop(not on, st), set_keybinding(on, st)]
    bureau_patch(actif=on, nemo_avant=st.get("nemo_avant"), touche=st.get("touche"))
    if UI_HOOK:
        UI_HOOK("bureau", {"actif": on})
    return {"actif": on, "rapport": rapport, "fenetre": UI_HOOK is not None,
            "touche": st.get("touche"), "touche_label": accel_label(st.get("touche"))}


def bureau_public() -> dict:
    st = bureau_state()
    st.pop("raccourcis", None)
    st.update(dossier=desktop_dir(), telechargements=downloads_dir(), documents=user_dir("DOCUMENTS", "Documents"),
              images=user_dir("PICTURES", "Images", "Pictures"), musique=user_dir("MUSIC", "Musique", "Music"),
              videos=user_dir("VIDEOS", "Vidéos", "Videos"),
              home=str(HOME), touche_label=accel_label(st.get("touche")), demarrage=AUTOSTART.exists(),
              fenetre=UI_HOOK is not None, cinnamon="CINNAMON" in ":".join(CUR_DESKTOPS).upper(),
              fenetres=WINDOWS_HOOK is not None, ecrans=MONITORS_HOOK() if MONITORS_HOOK is not None else [])
    return st


def conv_idle_hours(c: dict) -> float:
    try:
        last = dt.datetime.fromisoformat(c.get("modifie") or c.get("cree") or "")
    except (TypeError, ValueError):
        return 0.0
    return (dt.datetime.now() - last).total_seconds() / 3600


def _previous_conv(st: dict, current: str | None) -> str | None:
    pid = st.get("conv_precedente")
    if not pid or pid == current:
        return None
    try:
        return pid if load_conv(pid).get("messages") else None
    except ApiError:
        return None


def bureau_conv(new: bool = False, agent_id=None, rotation: bool = True) -> dict:
    """Discussion du volet (et de « Demander »). Après une longue pause (réglage conv_heures), on repart sur une
    discussion neuve : un vieux sujet ne pollue pas la question suivante. L'ancienne reste dans la liste des
    discussions et peut être reprise (« precedente »)."""
    with store.lock:
        st = bureau_state()
        cur, auto = None, False
        if st.get("conv"):
            try:
                cur = load_conv(st["conv"])
            except ApiError:
                cur = None
        if cur is not None and not new:
            hours = st.get("conv_heures") or 0
            auto = bool(rotation and hours and cur.get("messages") and not cur.get("pending")
                        and not conv_busy(cur["id"]) and conv_idle_hours(cur) >= hours)
            if not auto:
                return {**cur, "precedente": None if cur.get("messages") else _previous_conv(st, cur["id"])}
        if cur is not None and not cur.get("messages") and not conv_busy(cur["id"]):
            # « + » sur une discussion encore vide : on la garde au lieu d'en empiler des vides
            if (cur.get("agent_id") or None) != (agent_id or None):
                if agent_id and not find_agent(agent_id):
                    raise ApiError("Agent introuvable.")
                cur.update(agent_id=agent_id or None, workspace="", pending=None)
                save_conv(cur)
            return {**cur, "precedente": _previous_conv(st, cur["id"])}
        prev = cur["id"] if cur is not None and cur.get("messages") else st.get("conv_precedente")
        c = create_conv({"agent_id": agent_id} if agent_id else {})
        st = bureau_patch(conv=c["id"], conv_precedente=prev)
        return {**c, "precedente": _previous_conv(st, c["id"]), "auto": auto}


def bureau_conv_resume() -> dict:
    """Revient à la discussion d'avant dans le volet."""
    with store.lock:
        st = bureau_state()
        pid = _previous_conv(st, st.get("conv"))
        if not pid:
            raise ApiError("La discussion précédente n'existe plus.", 404)
        c = load_conv(pid)
        cur = st.get("conv")
        if cur and conv_busy(cur):
            raise ApiError("Une réponse est en cours : attends-la ou arrête-la.", 409)
        if cur and cur != pid:
            try:
                if not load_conv(cur).get("messages"):
                    store.delete(conv_path(cur))  # la discussion vide qu'on quitte ne sert à rien
            except ApiError:
                pass
        if not conv_busy(pid):
            save_conv(c)  # « modifiée maintenant » : elle ne sera pas remplacée au prochain message
        bureau_patch(conv=pid, conv_precedente=None)
        return {**c, "precedente": None}


SETTINGS_MODULES = {"backgrounds", "display", "desktop", "keyboard", "themes", "panel", "applets"}


def open_system_settings(module: str) -> bool:
    if module not in SETTINGS_MODULES:
        raise ApiError("Réglage inconnu.")
    if shutil.which("cinnamon-settings"):
        return _launch(["cinnamon-settings", module])
    if shutil.which("gnome-control-center"):
        return _launch(["gnome-control-center", {"backgrounds": "background"}.get(module, module)])
    return False


# ════════════════════════════════════════════════════════════════════
#  Serveur HTTP
# ════════════════════════════════════════════════════════════════════
ROUTES: list[tuple[str, re.Pattern, object, str]] = []


def route(method: str, pattern: str, kind: str = "json"):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn, kind))
        return fn
    return deco


def q1(q: dict, key: str, default: str = "") -> str:
    return (q.get(key) or [default])[0]


# ── Statut, réglages ──
@route("GET", "/api/status")
def r_status(h, q, b):
    st = ollama_status()
    st["app_version"] = VERSION
    st["pdftotext"] = bool(shutil.which("pdftotext"))
    st["pdftoppm"] = bool(shutil.which("pdftoppm"))
    st["grimoire"] = grimoire_bin()
    return st


@route("GET", "/api/settings")
def r_settings(h, q, b):
    s = get_settings()
    s["home"] = str(HOME)
    s["data_dir"] = str(DATA_DIR)
    return s


@route("POST", "/api/settings")
def r_settings_save(h, q, b):
    return save_settings(b)


@route("GET", "/api/tools")
def r_tools(h, q, b):
    return [{"name": k, "label": v["label"], "description": v["description"], "modifie": v["modifie"]}
            for k, v in TOOLS.items()]


# ── Fichiers ──
@route("GET", "/api/fs/roots")
def r_roots(h, q, b):
    return [{"path": r, "label": "Dossier personnel" if r == str(HOME) else os.path.basename(r) or r}
            for r in allowed_roots()]


@route("GET", "/api/fs/list")
def r_list(h, q, b):
    hidden = q1(q, "hidden") == "1" or get_settings()["show_hidden"]
    return fs_list(q1(q, "path"), hidden)


@route("GET", "/api/fs/read")
def r_read(h, q, b):
    path = safe_path(q1(q, "path"), must_exist=True)
    if os.path.isdir(path):
        raise ApiError("C'est un dossier.")
    size = os.path.getsize(path)
    ext = ext_of(path)
    editable = False
    if ext in TEXT_EXTS or EXT_KIND.get(ext) is None:
        with open(path, "rb") as f:
            raw = f.read(2_000_001)
        if b"\x00" not in raw[:8192]:
            editable = size <= 2_000_000
            try:
                content = raw[:2_000_000].decode("utf-8")
                enc = "utf-8"
            except UnicodeDecodeError:
                content = raw[:2_000_000].decode("latin-1")
                enc = "latin-1"
            return {"path": path, "size": size, "editable": editable, "encoding": enc,
                    "content": content, "tronque": size > 2_000_000, "format": "texte"}
    txt, note = extract_text(path, 60000)
    return {"path": path, "size": size, "editable": False, "content": txt, "format": note,
            "tronque": bool(txt and len(txt) >= 60000)}


def _launch(cmd: list[str]) -> bool:
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except (OSError, ValueError):
        return False


@route("POST", "/api/fs/open")
def r_open(h, q, b):
    """Ouvre un élément avec l'application par défaut de Mint, ou le montre dans Nemo."""
    path = safe_path(b.get("path"), must_exist=True)
    if b.get("app") == "grimoire":
        if ext_of(path) not in GRIMOIRE_EXTS:
            raise ApiError("Grimoire n'ouvre pas ce type de fichier.")
        if not grimoire_bin():
            raise ApiError("Grimoire n'est pas installé sur ce PC (paquet .deb de l'appli de bureau).")
        if not open_in_grimoire(path):
            raise ApiError("Grimoire n'a pas pu être lancé.")
        return {"ok": True, "app": "grimoire"}
    if to_bool(b.get("reveal")) and fm_is_archiviste():  # sinon Archiviste se répondrait à lui-même
        for fm in ("nemo", "nautilus", "caja", "thunar"):
            if shutil.which(fm) and _launch([fm, path]):
                return {"ok": True}
    if to_bool(b.get("reveal")) and not os.path.isdir(path):
        uri = Path(path).as_uri()
        if shutil.which("gdbus"):
            r = subprocess.run(["gdbus", "call", "--session", "--dest", "org.freedesktop.FileManager1",
                                "--object-path", "/org/freedesktop/FileManager1",
                                "--method", "org.freedesktop.FileManager1.ShowItems", f"['{uri}']", ""],
                               capture_output=True, timeout=8)
            if r.returncode == 0:
                return {"ok": True}
        for fm in ("nemo", "nautilus", "caja", "thunar"):
            if shutil.which(fm) and _launch([fm, path]):
                return {"ok": True}
        path = os.path.dirname(path)
    opener = shutil.which("xdg-open") or shutil.which("gio")
    if not opener:
        raise ApiError("Impossible d'ouvrir : xdg-open est introuvable.")
    cmd = [opener, path] if opener.endswith("xdg-open") else [opener, "open", path]
    if not _launch(cmd):
        raise ApiError("L'ouverture a échoué.")
    return {"ok": True}


@route("GET", "/api/update")
def r_update(h, q, b):
    return update_info()


@route("POST", "/api/update/check")
def r_update_check(h, q, b):
    return check_update()


@route("POST", "/api/update/install")
def r_update_install(h, q, b):
    return download_update(str(b.get("mode") or "auto"))


@route("GET", "/api/update/precedente")
def r_update_previous(h, q, b):
    p = previous_release()
    return {"trouvee": bool(p), **({k: p.get(k) for k in ("version", "source", "date", "taille")} if p else {}),
            "actuelle": installed_version()}


@route("POST", "/api/update/revenir")
def r_update_rollback(h, q, b):
    return rollback_update()


@route("POST", "/api/app/relaunch")
def r_relaunch(h, q, b):
    if RELAUNCH_HOOK is None:
        return {"ok": False, "message": "Ferme Archiviste puis rouvre-le pour utiliser la nouvelle version."}
    RELAUNCH_HOOK()
    return {"ok": True}


@route("POST", "/api/office/new")
def r_office_new(h, q, b):
    """Nouveau document Word / classeur Excel (vide, ou depuis du Markdown), ouvert dans Grimoire si demandé."""
    if b.get("dir") is not None:
        folder = safe_path(b.get("dir"), must_exist=True)
        path = os.path.join(folder, check_name(b.get("name")))
    else:
        path = b.get("path")
    r = create_office(path, b.get("kind", "docx"), str(b.get("content") or ""), unique=to_bool(b.get("unique")))
    r["ouvert"] = None
    if to_bool(b.get("open")):
        if open_in_grimoire(r["path"]):
            r["ouvert"] = "grimoire"
        else:
            opener = shutil.which("xdg-open")
            if opener and _launch([opener, r["path"]]):
                r["ouvert"] = "defaut"
    return r


@route("GET", "/api/fs/thumb", kind="raw")
def r_thumb(h, q, b):
    """Aperçu image de la première page d'un PDF (poppler-utils)."""
    path = safe_path(q1(q, "path"), must_exist=True)
    if ext_of(path) != "pdf" or not shutil.which("pdftoppm"):
        raise ApiError("Pas d'aperçu disponible.", 404)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="archiviste-") as tmp:
        base = os.path.join(tmp, "page")
        r = subprocess.run(["pdftoppm", "-png", "-f", "1", "-l", "1", "-scale-to", "900", "-singlefile", path, base],
                           capture_output=True, timeout=40)
        png = base + ".png"
        if r.returncode != 0 or not os.path.exists(png):
            raise ApiError("Aperçu du PDF impossible (fichier protégé ou abîmé ?).", 404)
        h.send_file(png)


@route("GET", "/api/fs/raw", kind="raw")
def r_raw(h, q, b):
    path = safe_path(q1(q, "path"), must_exist=True)
    if os.path.isdir(path):
        raise ApiError("C'est un dossier.")
    h.send_file(path, download=q1(q, "dl") == "1")


@route("POST", "/api/fs/write")
def r_write(h, q, b):
    path = safe_path(b.get("path"))
    if b.get("create_only") and os.path.exists(path):
        raise ApiError(f"« {os.path.basename(path)} » existe déjà.")
    if b.get("create_only"):
        check_name(os.path.basename(path))
    return fs_write(path, str(b.get("content", "")), encoding=b.get("encoding") or None)


@route("GET", "/api/fs/versions")
def r_versions(h, q, b):
    return list_versions(q1(q, "path"))


@route("GET", "/api/fs/versions/texte")
def r_version_text(h, q, b):
    f, orig = _version_file(q1(q, "id"))
    import tempfile
    # même lecture que pour un fichier ordinaire (PDF, Word…) : on lui rend son vrai nom le temps de la lire
    with tempfile.TemporaryDirectory(prefix="archiviste-") as tmp:
        link = os.path.join(tmp, os.path.basename(orig))
        os.symlink(f, link)
        txt, note = extract_text(link, 60000)
    return {"id": q1(q, "id"), "content": txt, "format": note, "tronque": bool(txt and len(txt) >= 60000)}


@route("POST", "/api/fs/versions/restaurer")
def r_version_restore(h, q, b):
    return restore_version(str(b.get("id") or ""))


@route("POST", "/api/fs/mkdir")
def r_mkdir(h, q, b):
    parent = safe_path(b.get("dir"), must_exist=True)
    name = check_name(b.get("name"))
    target = os.path.join(parent, name)
    if os.path.exists(target):
        raise ApiError(f"« {name} » existe déjà.")
    return fs_mkdir(target)


@route("POST", "/api/fs/rename")
def r_rename(h, q, b):
    return fs_rename(b.get("path"), b.get("new_name"))


@route("POST", "/api/fs/move")
def r_move(h, q, b):
    return transfer(b.get("paths") or [], b.get("dest_dir"), copy=bool(b.get("copy")))


# ════════════════════════════════════════════════════════════════════
#  Tâches de fond : extractions, compressions, longues copies
# ════════════════════════════════════════════════════════════════════
# Elles tournent dans leur propre fil : la fenêtre reste utilisable, la progression se suit en bas à droite
# (GET /api/taches) et chacune peut être annulée. Rien de ce qu'une tâche annulée a commencé ne reste à moitié.
class Tache:
    def __init__(self, genre: str, titre: str, dossier: str):
        self.id = uuid.uuid4().hex[:12]
        self.genre, self.titre, self.dossier = genre, titre, dossier
        self.fait, self.total, self.pourcent = 0, 0, False
        self.detail, self.erreur, self.mdp = "", None, False
        self.etat = "en cours"
        self.resultat: list[str] = []
        self.source = None
        self.debut, self.fin = time.time(), None
        self.stop = threading.Event()

    def avance(self, n: int, detail=None, fait=None, total=None, pourcent=False) -> None:
        if total is not None:
            self.total = total
        if fait is not None:
            self.fait = fait
        else:
            self.fait += n
        if detail:
            self.detail = detail
        if pourcent:
            self.pourcent = True

    def annulee(self) -> bool:
        return self.stop.is_set()

    def dict(self) -> dict:
        return {"id": self.id, "genre": self.genre, "titre": self.titre, "dossier": self.dossier, "etat": self.etat,
                "fait": self.fait, "total": self.total, "pourcent": self.pourcent, "detail": self.detail,
                "erreur": self.erreur, "mdp": self.mdp, "resultat": self.resultat, "source": self.source,
                "debut": self.debut, "fin": self.fin, "maintenant": time.time()}


TACHES: dict[str, Tache] = {}
_taches_lock = threading.Lock()


def lancer_tache(t: Tache, travail) -> Tache:
    def run():
        try:
            travail(t)
            t.etat = "annulee" if t.stop.is_set() else "finie"
        except archives.Annule:
            t.etat = "annulee"
        except archives.MotDePasse as e:
            t.etat, t.erreur, t.mdp = "erreur", str(e), True
        except (ApiError, archives.ErreurArchive) as e:
            t.etat, t.erreur = "erreur", str(e)
        except OSError as e:
            t.etat, t.erreur = "erreur", archives.message_os(e)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            t.etat, t.erreur = "erreur", f"Erreur inattendue : {e}"
        finally:
            t.fin = time.time()
            changed(t.dossier, os.path.join(t.dossier, "x"), *t.resultat)
            push("taches")

    with _taches_lock:
        old = [k for k, v in TACHES.items() if v.fin and time.time() - v.fin > 1800]
        for k in old:
            TACHES.pop(k, None)
        TACHES[t.id] = t
    threading.Thread(target=run, name=f"tache-{t.genre}", daemon=True).start()
    push("taches")
    return t


@route("GET", "/api/taches")
def r_tasks(h, q, b):
    with _taches_lock:
        return {"taches": [t.dict() for t in TACHES.values()]}


@route("POST", "/api/taches/annuler")
def r_task_cancel(h, q, b):
    t = TACHES.get(str(b.get("id") or ""))
    if t is None:
        raise ApiError("Tâche introuvable.", 404)
    t.stop.set()
    return t.dict()


@route("POST", "/api/taches/oublier")
def r_task_forget(h, q, b):
    with _taches_lock:
        t = TACHES.get(str(b.get("id") or ""))
        if t is not None and t.etat != "en cours":
            TACHES.pop(t.id, None)
    return {"ok": True}


# ── copier / déplacer : rapide tout de suite, long en tâche de fond ──
LOURD = 48 * 1024 * 1024  # au-delà, une copie se suit dans une tâche (barre de progression, Annuler)


def _poids(paths: list[str], budget: float = 1.5) -> tuple[int, int, bool]:
    """Octets et nombre d'éléments, sans suivre les liens. complet=False si le temps a manqué."""
    size, count, t0 = 0, 0, time.monotonic()
    stack = list(paths)
    while stack:
        p = stack.pop()
        try:
            st = os.lstat(p)
        except OSError:
            continue
        count += 1
        if stat.S_ISDIR(st.st_mode):
            try:
                stack.extend(os.path.join(p, n) for n in os.listdir(p))
            except OSError:
                pass
        elif stat.S_ISREG(st.st_mode):
            size += st.st_size
        if time.monotonic() - t0 > budget:
            return size, count, False
    return size, count, True


def _copy_tree(src: str, dst: str, t: Tache, base: str) -> None:
    """Copie avec progression : fichier par fichier, par morceaux, arrêt possible à tout moment."""
    if t.annulee():
        raise archives.Annule()
    if os.path.islink(src):
        os.symlink(link_target(src), dst)
        return
    st = os.lstat(src)
    if stat.S_ISDIR(st.st_mode):
        os.mkdir(dst)
        for e in sorted(os.scandir(src), key=lambda e: e.name):
            _copy_tree(e.path, os.path.join(dst, e.name), t, base)
        try:
            shutil.copystat(src, dst)
        except OSError:
            pass
    elif stat.S_ISREG(st.st_mode):
        rel = os.path.relpath(src, base)
        with open(src, "rb") as f, open(dst, "wb") as g:
            archives._copier(f, g, t.avance, t.annulee, rel)
        try:
            shutil.copystat(src, dst)  # une clé en FAT32 ne garde pas les droits : sans importance
        except OSError:
            pass


def _remove(path: str) -> None:
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
    else:
        shutil.rmtree(path)


def transfer(paths: list, dest_dir, copy: bool) -> dict:
    """Copie ou déplace des éléments dans un dossier. Un déplacement sur le même disque est immédiat ;
    une copie, ou un déplacement vers un autre disque (clé USB), passe en tâche de fond au-delà de LOURD."""
    roots = allowed_roots()
    dest = safe_path(dest_dir, must_exist=True)
    if not os.path.isdir(dest):
        raise ApiError("La destination doit être un dossier.")
    plans, errors, same = [], [], 0
    for p in paths:
        try:
            s, target = move_plan(p, dest, roots, copy=copy)
            if target is None:
                same += 1
            else:
                plans.append((s, target))
        except (ApiError, OSError) as e:
            errors.append({"path": p, "erreur": archives.message_os(e) if isinstance(e, OSError) else str(e)})
    out = {"ok": [], "erreurs": errors, "deja": same, "tache": None}
    if not plans:
        return out
    dev = os.stat(dest).st_dev
    slow = [(s, tg) for s, tg in plans if copy or os.lstat(s).st_dev != dev]
    size, count, complete = _poids([s for s, _ in slow])
    if not slow or (complete and size < LOURD and count < 3000):
        for s, target in plans:
            try:
                if copy:
                    if os.path.islink(s):
                        os.symlink(link_target(s), target)
                    elif os.path.isdir(s):
                        shutil.copytree(s, target, symlinks=True)
                    else:
                        shutil.copy2(s, target)
                else:
                    move_entry(s, target)
                changed(s, target, os.path.join(target, "x"))
                out["ok"].append({"de": s, "vers": target})
            except OSError as e:
                errors.append({"path": s, "erreur": archives.message_os(e)})
        return out
    free = shutil.disk_usage(dest).free
    if complete and size + archives.marge(dest) > free:
        raise ApiError(f"Pas assez de place : il faut {archives.taille_lisible(size)}, "
                       f"il reste {archives.taille_lisible(free)} sur ce disque.")
    n = len(plans)
    what = f"« {os.path.basename(plans[0][0])} »" if n == 1 else f"{n} éléments"
    t = Tache("copie" if copy else "deplacement",
              f"{'Copie' if copy else 'Déplacement'} de {what} vers {os.path.basename(dest) or dest}", dest)
    t.total = size if complete else 0

    def travail(t: Tache) -> None:
        for s, target in plans:
            if t.annulee():
                raise archives.Annule()
            if not copy and os.lstat(s).st_dev == dev:
                move_entry(s, target)  # même disque : instantané
            else:
                try:
                    _copy_tree(s, target, t, os.path.dirname(s))
                except BaseException:
                    if os.path.lexists(target):
                        _remove(target)  # rien à moitié copié
                    raise
                if not copy:
                    _remove(s)
            t.resultat.append(target)
            changed(s, target, os.path.join(target, "x"))

    out["tache"] = lancer_tache(t, travail).dict()
    return out


# ── archives ──
def _archive_err(e: Exception) -> ApiError:
    return ApiError(archives.message_os(e) if isinstance(e, OSError) else str(e))


@route("GET", "/api/archive")
def r_archive_list(h, q, b):
    path = safe_path(q1(q, "path"), must_exist=True)
    if archives.nature(path) is None:
        raise ApiError("Ce fichier n'est pas une archive reconnue.")
    try:
        out = archives.lister(path, limite=3000)
    except archives.ErreurArchive as e:
        raise _archive_err(e)
    out["nom"] = os.path.basename(path)
    out["dossier_final"] = out["dossier_unique"] or archives.nom_sans_extension(path)
    return out


@route("POST", "/api/archive/extraire")
def r_archive_extract(h, q, b):
    path = safe_path(b.get("path"), must_exist=True)
    if archives.nature(path) is None:
        raise ApiError("Ce fichier n'est pas une archive reconnue.")
    dest = safe_path(b.get("dest") or os.path.dirname(path), must_exist=True)
    if not os.path.isdir(dest):
        raise ApiError("La destination doit être un dossier.")
    mdp = b.get("mdp")
    mdp = str(mdp) if mdp is not None else None
    t = Tache("extraction", f"Extraction de « {os.path.basename(path)} »", dest)
    t.source = path

    def travail(t: Tache) -> None:
        r = archives.extraire(path, dest, t.avance, t.annulee, unique_path, mdp=mdp)
        t.resultat.append(r["resultat"])

    return {"tache": lancer_tache(t, travail).dict()}


@route("POST", "/api/archive/compresser")
def r_archive_compress(h, q, b):
    roots = allowed_roots()
    paths = [safe_path(p, roots=roots, must_exist=True, nofollow=True) for p in (b.get("paths") or [])][:2000]
    if not paths:
        raise ApiError("Rien à compresser.")
    fmt = "tar.gz" if b.get("format") == "tar.gz" else "zip"
    name = check_name(str(b.get("nom") or "").strip() or archives.nom_sans_extension(paths[0]))
    if not name.lower().endswith("." + fmt):
        name += "." + fmt
    dest = unique_path(os.path.join(os.path.dirname(paths[0]), name))
    safe_path(os.path.dirname(dest), roots=roots, must_exist=True)
    t = Tache("compression", f"Compression vers « {os.path.basename(dest)} »", os.path.dirname(dest))

    def travail(t: Tache) -> None:
        r = archives.compresser(paths, dest, fmt, t.avance, t.annulee)
        t.resultat.append(r["resultat"])

    return {"tache": lancer_tache(t, travail).dict()}


# ── propriétés, droits ──
def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


@route("GET", "/api/fs/proprietes")
def r_properties(h, q, b):
    import grp
    import pwd
    roots = allowed_roots()
    paths = [safe_path(p, roots=roots, must_exist=True, nofollow=True) for p in (q.get("path") or [])][:500]
    if not paths:
        raise ApiError("Aucun élément.")
    size, count, complete = 0, 0, True
    files = dirs = 0
    t0 = time.monotonic()
    for p in paths:
        stack = [p]
        while stack:
            c = stack.pop()
            try:
                st = os.lstat(c)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                dirs += c != p or len(paths) > 1
                try:
                    stack.extend(os.path.join(c, n) for n in os.listdir(c))
                except OSError:
                    pass
            else:
                files += 1
                size += st.st_size if stat.S_ISREG(st.st_mode) else 0
            if time.monotonic() - t0 > 5:
                complete = False
                stack = []
        if not complete:
            break
    out = {"nombre": len(paths), "taille": size, "fichiers": files, "dossiers": dirs, "complet": complete}
    try:
        du = shutil.disk_usage(paths[0] if os.path.isdir(paths[0]) else os.path.dirname(paths[0]))
        out["disque"] = {"libre": du.free, "total": du.total}
    except OSError:
        pass
    if len(paths) == 1:
        p = paths[0]
        lst = os.lstat(p)
        st = os.stat(p) if os.path.exists(p) else lst
        def name_of(fn, i):
            try:
                return fn(i)[0]
            except KeyError:
                return str(i)
        out.update(chemin=p, nom=os.path.basename(p), dossier=stat.S_ISDIR(st.st_mode),
                   lien=os.readlink(p) if os.path.islink(p) else None,
                   type=mime_of(p), modifie=_iso(st.st_mtime), acces=_iso(st.st_atime), change=_iso(st.st_ctime),
                   proprietaire=name_of(pwd.getpwuid, lst.st_uid), groupe=name_of(grp.getgrgid, lst.st_gid),
                   mode=stat.S_IMODE(st.st_mode), a_moi=lst.st_uid == os.getuid(),
                   modifiable=not os.path.islink(p) and lst.st_uid == os.getuid())
        if not out["dossier"]:
            try:
                a = apps_for(p)
                d = next((x for x in a["apps"] if x["id"] == a["defaut"]), None)
                out["appli"] = d["nom"] if d else None
            except Exception:  # noqa: BLE001
                out["appli"] = None
    return out


@route("POST", "/api/fs/droits")
def r_chmod(h, q, b):
    p = safe_path(b.get("path"), must_exist=True, nofollow=True)
    if os.path.islink(p):
        raise ApiError("Les droits d'un lien sont ceux de sa cible.")
    st = os.lstat(p)
    if st.st_uid != os.getuid():
        raise ApiError("Seul le propriétaire de ce fichier peut changer ses droits.")
    try:
        mode = int(b.get("mode")) & 0o777
    except (TypeError, ValueError):
        raise ApiError("Droits invalides.")
    try:
        os.chmod(p, (stat.S_IMODE(st.st_mode) & 0o7000) | mode | 0o400)  # le propriétaire garde toujours la lecture
    except OSError as e:
        raise ApiError(archives.message_os(e))
    return {"mode": stat.S_IMODE(os.stat(p).st_mode)}


# ── ouvrir un terminal ici ──
TERM_DIR = {"gnome-terminal": "--working-directory={}", "mate-terminal": "--working-directory={}",
            "xfce4-terminal": "--working-directory={}", "terminator": "--working-directory={}",
            "tilix": "--working-directory={}", "kgx": "--working-directory={}", "ptyxis": "--working-directory={}",
            "konsole": "--workdir={}", "alacritty": "--working-directory={}", "kitty": "--directory={}",
            "wezterm": None, "xterm": None, "urxvt": None, "lxterminal": "--working-directory={}"}


@route("POST", "/api/terminal")
def r_terminal(h, q, b):
    d = safe_path(b.get("path") or HOME, must_exist=True)
    if not os.path.isdir(d):
        d = os.path.dirname(d)
    pref = gs_get("org.cinnamon.desktop.default-applications.terminal", "exec")
    cands = ([pref] if isinstance(pref, str) and pref else []) + list(TERM_DIR) + ["x-terminal-emulator"]
    exe = next((shutil.which(c) for c in cands if shutil.which(c)), None)
    if not exe:
        raise ApiError("Aucun terminal trouvé sur ce PC.")
    flag = TERM_DIR.get(os.path.basename(exe))
    try:
        subprocess.Popen([exe] + ([flag.format(d)] if flag else []), cwd=d, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        raise ApiError(f"Le terminal n'a pas pu être lancé ({e.strerror}).")
    return {"ok": True, "terminal": os.path.basename(exe)}


# ── Archiviste, gestionnaire de fichiers par défaut ──
FM_ID = "fr.csc.Archiviste.desktop"
FM_HOOK = None  # renseigné par fenetre.py : répond (ou non) au service D-Bus « FileManager1 »


def fm_default() -> str | None:
    exe = shutil.which("xdg-mime")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "query", "default", "inode/directory"], capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def fm_is_archiviste() -> bool:
    return fm_default() == FM_ID


def fm_installed() -> bool:
    dirs = [Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")] + \
           [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
    return any((d / "applications" / FM_ID).is_file() for d in dirs)


@route("GET", "/api/gestionnaire")
def r_fm_get(h, q, b):
    cur = fm_default()
    return {"defaut": cur, "archiviste": cur == FM_ID, "possible": fm_installed() and bool(shutil.which("xdg-mime")),
            "service": FM_HOOK is not None and FM_HOOK("etat")}


@route("POST", "/api/gestionnaire")
def r_fm_set(h, q, b):
    exe = shutil.which("xdg-mime")
    if not exe or not fm_installed():
        raise ApiError("Il faut Archiviste installé par son paquet (.deb) pour le choisir comme gestionnaire de fichiers.")
    want = to_bool(b.get("archiviste"))
    cur = fm_default()
    if want:
        if cur and cur != FM_ID:
            save_settings({"gestionnaire_precedent": cur})
        target = FM_ID
    else:
        target = get_settings().get("gestionnaire_precedent") or "nemo.desktop"
    r = subprocess.run([exe, "default", target, "inode/directory"], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise ApiError(f"Le réglage n'a pas pu être changé : {(r.stderr or r.stdout).strip()[:200]}")
    if FM_HOOK is not None:
        FM_HOOK("marche" if want else "arret")
    return r_fm_get(h, q, b)


# ── Couper / copier / coller : un presse-papiers de fichiers commun au bureau et à la fenêtre principale ──
CLIP = {"paths": [], "mode": "copier"}
CLIP_HOOK = None  # renseigné par fenetre.py : lit les fichiers copiés ou coupés ailleurs (Nemo…)
_clip_lock = threading.Lock()


def clip_clear() -> None:
    """Le presse-papiers du système a changé (autre chose a été copié ailleurs) : le nôtre n'a plus cours."""
    with _clip_lock:
        had = bool(CLIP["paths"])
        CLIP.update(paths=[], mode="copier")
    if had:
        push("presse")


def clip_state() -> dict:
    with _clip_lock:
        paths = [p for p in CLIP["paths"] if os.path.lexists(p)]
        mode = CLIP["mode"]
    if paths:
        return {"paths": paths, "mode": mode, "source": "archiviste"}
    hook = CLIP_HOOK
    if hook is not None:  # rien de coupé dans Archiviste : ce qui a été copié ou coupé dans le gestionnaire de fichiers
        try:
            ext = hook() or {}
        except Exception:  # noqa: BLE001
            ext = {}
        roots = allowed_roots()
        paths = []
        for p in ext.get("paths") or []:
            try:
                paths.append(safe_path(p, roots=roots, must_exist=True, nofollow=True))
            except (ApiError, OSError):
                pass
        if paths:
            return {"paths": paths[:500], "mode": ext.get("mode") or "copier", "source": "systeme"}
    return {"paths": [], "mode": "copier", "source": None}


# Fichiers en train d'être glissés. Sous WebKitGTK, la page qui reçoit un fichier ne peut pas lire son
# emplacement (les adresses file:// lui sont cachées) : c'est la page de départ, ou la fenêtre GTK pour un
# fichier venu d'une autre appli (Nemo), qui le note ici ; la page d'arrivée le relit au moment du dépôt.
#
# Touche Ctrl : WebKitGTK donne à la page un état périmé pendant un glisser (une fois Ctrl utilisé, tous les
# dépôts suivants se croient « avec Ctrl » et copient au lieu de déplacer). La fenêtre GTK lit donc le clavier
# elle-même au moment du dépôt et le note ici ; la page s'y fie plutôt qu'à son propre événement.
DRAG = {"paths": [], "t": 0.0, "ctrl": None, "tc": 0.0}


def drag_set(paths) -> None:
    DRAG.update(paths=[str(p) for p in (paths or []) if isinstance(p, str)][:500], t=time.time())


def drag_key(ctrl: bool) -> None:
    DRAG.update(ctrl=bool(ctrl), tc=time.time())


@route("POST", "/api/glisse")
def r_drag_set(h, q, b):
    drag_set(b.get("paths") or [])
    return {"ok": True}


@route("GET", "/api/glisse")
def r_drag_get(h, q, b):
    now = time.time()
    return {"paths": list(DRAG["paths"]) if now - DRAG["t"] < 180 else [],
            "ctrl": DRAG["ctrl"] if now - DRAG["tc"] < 5 else None}  # None : pas d'info (hors de l'appli)


@route("GET", "/api/presse-papiers")
def r_clip_get(h, q, b):
    return clip_state()


@route("POST", "/api/presse-papiers")
def r_clip_set(h, q, b):
    mode = "couper" if b.get("mode") == "couper" else "copier"
    roots = allowed_roots()
    paths = []
    for p in (b.get("paths") or [])[:500]:
        sp = safe_path(p, roots=roots, must_exist=True, nofollow=True)
        if mode == "couper" and is_root(sp, roots):
            raise ApiError("On ne déplace pas un dossier racine autorisé.")
        paths.append(sp)
    with _clip_lock:
        CLIP.update(paths=paths, mode=mode)
    push("presse")
    return {"paths": paths, "mode": mode, "source": "archiviste" if paths else None}


@route("POST", "/api/presse-papiers/coller")
def r_clip_paste(h, q, b):
    dest = safe_path(b.get("dest"), must_exist=True)
    if not os.path.isdir(dest):
        raise ApiError("La destination doit être un dossier.")
    st = clip_state()
    if not st["paths"]:
        raise ApiError("Rien à coller : coupe ou copie d'abord un fichier (Ctrl+X, Ctrl+C).")
    cut = st["mode"] == "couper"
    r = transfer(st["paths"], dest, copy=not cut)
    done, errors, same = r["ok"], r["erreurs"], r["deja"]
    if cut and (done or same or r["tache"]):  # coupé-collé : c'est fait, le presse-papiers est vidé (un copié reste collable ailleurs)
        with _clip_lock:
            CLIP.update(paths=[], mode="copier")
        if st["source"] == "systeme" and CLIP_HOOK is not None:
            try:
                CLIP_HOOK(clear=True)
            except Exception:  # noqa: BLE001
                pass
        push("presse")
    return {"ok": done, "erreurs": errors, "mode": st["mode"], "deja": same, "tache": r["tache"]}


@route("POST", "/api/fs/trash")
def r_trash(h, q, b):
    done, errors = [], []
    for p in b.get("paths") or []:
        try:
            done.append(trash(p))
        except (ApiError, OSError) as e:
            errors.append({"path": p, "erreur": str(e)})
    return {"ok": done, "erreurs": errors}


@route("GET", "/api/fs/search")
def r_search(h, q, b):
    s = get_settings()
    if q1(q, "rapide") == "1":  # barre de recherche du bureau : peu de résultats, tout de suite
        return fs_search(q1(q, "path"), q1(q, "q"), False, show_hidden=s["show_hidden"], limit=24, delay=2.5,
                         fresh=False)
    # frais=0 : recherche au fil de la frappe (réponse immédiate, sans la vérification du disque)
    return fs_search(q1(q, "path"), q1(q, "q"), q1(q, "content") == "1", show_hidden=s["show_hidden"],
                     fresh=q1(q, "frais") != "0")


@route("GET", "/api/index")
def r_index(h, q, b):
    return INDEX.status() if INDEX is not None else {"pret": False, "etat": "désactivé", "absent": True}


@route("POST", "/api/index/reconstruire")
def r_index_rebuild(h, q, b):
    if INDEX is None:
        raise ApiError("L'index de recherche n'est pas disponible.")
    INDEX.rebuild()
    return INDEX.status()


@route("GET", "/api/fs/duplicates")
def r_dups(h, q, b):
    return find_duplicates(q1(q, "path"), show_hidden=get_settings()["show_hidden"])


@route("POST", "/api/fs/upload", kind="upload")
def r_upload(h, q, b):
    folder = safe_path(q1(q, "dir"), must_exist=True)
    if not os.path.isdir(folder):
        raise ApiError("Destination invalide.")
    name = check_name(q1(q, "name"))
    target = os.path.join(folder, name)
    if q1(q, "overwrite") != "1":
        target = unique_path(target)
    elif os.path.isfile(target):
        backup_version(target)
    length = int(h.headers.get("Content-Length") or 0)
    tmp = target + ".archiviste-part"
    try:
        with open(tmp, "wb") as f:
            remaining = length
            while remaining > 0:
                chunk = h.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    raise ApiError("Envoi interrompu.")
                f.write(chunk)
                remaining -= len(chunk)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    changed(target)
    return entry_info(target)


# ── Corbeille ──
@route("GET", "/api/trash")
def r_trash_list(h, q, b):
    return trash_list()


@route("POST", "/api/trash/restore")
def r_trash_restore(h, q, b):
    done, errors = [], []
    for t in b.get("ids") or []:
        try:
            done.append(trash_restore(str(t)))
        except (ApiError, OSError) as e:
            errors.append({"id": t, "erreur": str(e)})
    return {"ok": done, "erreurs": errors}


@route("POST", "/api/trash/purge")
def r_trash_purge(h, q, b):
    return [trash_purge(t) for t in b.get("ids") or []]


# ── Tri ──
@route("POST", "/api/sort/scan")
def r_sort_scan(h, q, b):
    return sort_scan(b.get("path"), to_bool(b.get("recursive")), to_bool(b.get("content")),
                     get_settings()["show_hidden"])


@route("POST", "/api/sort/rules")
def r_sort_rules(h, q, b):
    mode = b.get("mode") or "type"
    return [{"path": f["path"], "dossier": rule_folder(f, mode)} for f in b.get("files") or []]


@route("POST", "/api/sort/ai")
def r_sort_ai(h, q, b):
    return ai_sort_batch(b)


@route("POST", "/api/sort/apply")
def r_sort_apply(h, q, b):
    return sort_apply(b)


@route("GET", "/api/sort/journal")
def r_journal(h, q, b):
    return [{**{k: v for k, v in j.items() if k != "moves"}, "nb": len(j["moves"]),
             "apercu": [os.path.basename(m["vers"]) for m in j["moves"][:4]]}
            for j in store.read("journal.json", list)]


@route("POST", "/api/sort/undo")
def r_undo(h, q, b):
    return sort_undo(b.get("id", ""))


# ── Prompts & agents ──
@route("GET", "/api/prompts")
def r_prompts(h, q, b):
    return get_prompts()


@route("POST", "/api/prompts")
def r_prompt_save(h, q, b):
    return upsert("prompts", b)


@route("POST", "/api/prompts/([\\w-]+)/delete")
def r_prompt_del(h, q, b, pid):
    return remove("prompts", pid)


@route("POST", "/api/prompts/([\\w-]+)/used")
def r_prompt_used(h, q, b, pid):
    with store.lock:
        items = get_prompts()
        for p in items:
            if p["id"] == pid:
                p["utilisations"] = int(p.get("utilisations", 0)) + 1
        store.write("prompts.json", items)
    return {"ok": True}


@route("GET", "/api/agents")
def r_agents(h, q, b):
    return get_agents()


@route("POST", "/api/agents")
def r_agent_save(h, q, b):
    return upsert("agents", b)


@route("POST", "/api/agents/([\\w-]+)/delete")
def r_agent_del(h, q, b, aid):
    return remove("agents", aid)


@route("GET", "/api/export")
def r_export(h, q, b):
    return {"app": "Archiviste", "version": VERSION, "date": now_iso(),
            "prompts": get_prompts(), "agents": get_agents()}


@route("POST", "/api/import")
def r_import(h, q, b):
    n = {"prompts": 0, "agents": 0}
    for kind in ("prompts", "agents"):
        current = get_prompts() if kind == "prompts" else get_agents()
        ids = {i["id"] for i in current}
        for item in b.get(kind) or []:
            if not isinstance(item, dict):
                continue
            if kind == "agents" and item.get("dossier") and not os.path.isdir(str(item["dossier"])):
                item["dossier"] = ""
            if item.get("id") in ids:
                item = {**item, "id": None}
            try:
                upsert(kind, item)
                n[kind] += 1
            except ApiError:
                pass
    return n


# ── Discussions ──
@route("GET", "/api/models")
def r_models(h, q, b):
    return ollama_status().get("models", [])


@route("GET", "/api/conversations")
def r_convs(h, q, b):
    return list_convs()


@route("POST", "/api/conversations")
def r_conv_new(h, q, b):
    return create_conv(b)


@route("GET", "/api/conversations/(c_[0-9a-f]{10})")
def r_conv_get(h, q, b, cid):
    return load_conv(cid)


@route("POST", "/api/conversations/(c_[0-9a-f]{10})")
def r_conv_update(h, q, b, cid):
    if not conv_claim(cid):
        raise ApiError("Une réponse est en cours dans cette discussion : attends-la ou arrête-la.", 409)
    c = load_conv(cid)
    if "titre" in b:
        c["titre"] = str(b["titre"]).strip()[:100]
    if "agent_id" in b:
        if b["agent_id"] and not find_agent(b["agent_id"]):
            raise ApiError("Agent introuvable.")
        c["agent_id"] = b["agent_id"] or None
        c["pending"] = None
    if "modele" in b:
        c["modele"] = str(b["modele"] or "")
    if "workspace" in b:
        c["workspace"] = safe_path(b["workspace"], must_exist=True) if b["workspace"] else ""
    if "think" in b:
        c["think"] = None if b["think"] is None else to_bool(b["think"])
    save_conv(c)
    return c


@route("POST", "/api/conversations/(c_[0-9a-f]{10})/delete")
def r_conv_del(h, q, b, cid):
    conv_release(cid)  # une réponse encore en cours n'écrira plus rien
    store.delete(conv_path(cid))
    return {"ok": True}


@route("POST", "/api/chat", kind="stream")
def r_chat(h, q, b):
    run_chat(h, b)


@route("POST", "/api/ai/run", kind="stream")
def r_oneshot(h, q, b):
    run_oneshot(h, b)


# ── Bureau ──
@route("GET", "/api/bureau")
def r_bureau(h, q, b):
    return bureau_public()


@route("POST", "/api/bureau/reglages")
def r_bureau_reglages(h, q, b):
    patch = {}
    if "volet" in b:
        patch["volet"] = to_bool(b["volet"])
    if b.get("tri") in ("nom", "date", "type"):
        patch["tri"] = b["tri"]
    if b.get("dossiers") in ("archiviste", "systeme"):
        patch["dossiers"] = b["dossiers"]
    if b.get("fond") in ("auto", "archiviste"):
        patch["fond"] = b["fond"]
    if "volet_largeur" in b:
        try:
            w = int(b["volet_largeur"] or 0)
        except (TypeError, ValueError):
            w = 0
        patch["volet_largeur"] = max(VOLET_MIN, min(VOLET_MAX, w)) if w > 0 else None
    if b.get("volet_cote") in ("droite", "gauche"):
        patch["volet_cote"] = b["volet_cote"]
    if "dock_bord" in b:
        patch["dock_bord"] = to_bool(b["dock_bord"])
    if "ecran" in b:
        try:
            patch["ecran"] = None if b["ecran"] in (None, "", "principal") else max(0, int(b["ecran"]))
        except (TypeError, ValueError):
            pass
    if "conv_heures" in b:
        try:
            hours = int(b["conv_heures"])
        except (TypeError, ValueError):
            hours = -1
        if hours in CONV_HEURES:
            patch["conv_heures"] = hours
    bureau_patch(**patch)
    if "fond" in patch and UI_HOOK:
        UI_HOOK("fond", {"fond": patch["fond"]})
    if "ecran" in patch and UI_HOOK:
        UI_HOOK("ecran", {})
    return bureau_public()


@route("POST", "/api/bureau/activer")
def r_bureau_activer(h, q, b):
    return bureau_activer(to_bool(b.get("actif")))


@route("GET", "/api/bureau/elements")
def r_bureau_elements(h, q, b):
    return bureau_elements()


@route("GET", "/api/bureau/sig")
def r_bureau_sig(h, q, b):
    try:  # « rv » change quand les raccourcis ou les réglages du bureau changent (depuis l'autre fenêtre)
        rv = str(os.stat(DATA_DIR / "bureau.json").st_mtime_ns)
    except OSError:
        rv = "0"
    cid = store.read("bureau.json", dict).get("conv") or ""
    try:  # « cv » change quand la discussion du volet avance ailleurs (fenêtre « Demander », fenêtre principale)
        cv = f"{cid}:{os.stat(DATA_DIR / conv_path(cid)).st_mtime_ns}"
    except (ApiError, OSError):
        cv = ""
    hook = WINDOWS_HOOK  # « fv » change quand une fenêtre s'ouvre, se ferme, est réduite ou passe devant
    return {"sig": bureau_sig(), "rv": rv, "cv": cv, "fv": hook.version if hook is not None else -1}


@route("GET", "/api/bureau/a-ranger")
def r_bureau_a_ranger(h, q, b):
    return a_ranger()


@route("GET", "/api/bureau/fond")
def r_bureau_fond(h, q, b):
    return wallpaper_info()


@route("GET", "/api/bureau/fond/image", kind="raw")
def r_bureau_fond_image(h, q, b):
    p = wallpaper_info()["chemin"]
    if not p:
        raise ApiError("Pas de fond d'écran.", 404)
    h.send_file(p, cache=3600)


@route("GET", "/api/bureau/conv")
def r_bureau_conv(h, q, b):
    return bureau_conv(rotation=q1(q, "rotation") != "0")


@route("POST", "/api/bureau/conv/reprendre")
def r_bureau_conv_resume(h, q, b):
    return bureau_conv_resume()


@route("POST", "/api/bureau/conv/nouvelle")
def r_bureau_conv_new(h, q, b):
    return bureau_conv(new=True, agent_id=b.get("agent_id") or None)


@route("POST", "/api/bureau/volume")
def r_bureau_volume(h, q, b):
    path = os.path.realpath(str(b.get("path") or ""))
    if path not in [v["path"] for v in volumes()]:
        raise ApiError("Ce volume n'est plus monté.", 404)
    if b.get("action") == "ejecter":
        exe = shutil.which("gio")
        if not exe:
            raise ApiError("Éjection impossible : la commande gio est absente.")
        try:
            r = subprocess.run([exe, "mount", "-e", path], capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise ApiError("L'éjection prend trop de temps : un fichier est peut-être encore ouvert.")
        if r.returncode != 0:
            raise ApiError("Éjection impossible : " + (r.stderr.strip().splitlines() or ["volume occupé"])[-1])
        return {"ok": True}
    opener = shutil.which("xdg-open")
    if not opener or not _launch([opener, path]):
        raise ApiError("Ouverture impossible.")
    return {"ok": True}


@route("POST", "/api/systeme/reglages")
def r_system_settings(h, q, b):
    if not open_system_settings(str(b.get("module") or "")):
        raise ApiError("Les paramètres système de Cinnamon sont introuvables.")
    return {"ok": True}


@route("POST", "/api/app/ouvrir")
def r_app_open(h, q, b):
    """Ouvre (ou ramène) la fenêtre d'Archiviste sur une vue : files, sort, chat, settings…"""
    vue = str(b.get("vue") or "")
    if vue not in ("", "files", "sort", "chat", "agents", "prompts", "trash", "settings"):
        raise ApiError("Vue inconnue.")
    data = {"vue": vue} if vue else {}
    if b.get("chemin"):
        data["chemin"] = safe_path(b["chemin"], must_exist=True)
    if b.get("select"):
        data["select"] = safe_path(b["select"], must_exist=True)
    if b.get("conv"):
        conv_path(str(b["conv"]))
        data["conv"] = str(b["conv"])
    if UI_HOOK is None:
        return {"ok": False, "message": "Ouvre Archiviste depuis le menu."}
    UI_HOOK("ouvrir", data)
    return {"ok": True}


@route("POST", "/api/app/demander")
def r_app_ask(h, q, b):
    if UI_HOOK is None:
        return {"ok": False}
    UI_HOOK("demander", {"fermer": to_bool(b.get("fermer"))})
    return {"ok": True}


# ── Fenêtres ouvertes ──
@route("GET", "/api/fenetres")
def r_windows(h, q, b):
    return window_groups()


@route("POST", "/api/fenetres/action")
def r_windows_action(h, q, b):
    return window_action(str(b.get("cle") or ""), str(b.get("action") or "basculer"), b.get("fenetre"))


# ── Applications installées et raccourcis ──
@route("GET", "/api/apps")
def r_apps(h, q, b):
    fav = gs_get("org.cinnamon", "favorite-apps")
    idx = apps_index()
    return {"apps": [public_app(a) for a in idx["list"]],
            "favoris": [x for x in (fav if isinstance(fav, list) else []) if x in idx["by_id"]]}


@route("GET", "/api/apps/pour")
def r_apps_for(h, q, b):
    return apps_for(safe_path(q1(q, "path"), must_exist=True))


@route("POST", "/api/apps/defaut")
def r_apps_default(h, q, b):
    path = safe_path(b.get("path"), must_exist=True)
    a = apps_index()["by_id"].get(str(b.get("id") or ""))
    if not a:
        raise ApiError("Cette application n'est plus installée.", 404)
    exe = shutil.which("xdg-mime")
    if not exe:
        raise ApiError("xdg-mime est introuvable (paquet xdg-utils).")
    mime = mime_of(path)
    r = subprocess.run([exe, "default", a["id"], mime], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise ApiError("Le réglage n'a pas pu être changé.")
    return {"ok": True, "type": mime, "nom": a["nom"]}


@route("POST", "/api/apps/lancer")
def r_apps_launch(h, q, b):
    files = [safe_path(p, must_exist=True) for p in (b.get("fichiers") or [])][:50]
    if b.get("id"):
        a = apps_index()["by_id"].get(str(b["id"]))
        if not a:
            raise ApiError("Cette application n'est plus installée.", 404)
        if to_bool(b.get("ramener")) and not files and raise_app(a["id"]):
            return {"ok": True, "nom": a["nom"], "ramenee": True}  # déjà ouverte : sa fenêtre revient devant
        launch_app(a, files)
        return {"ok": True, "nom": a["nom"]}
    path = os.path.realpath(str(b.get("fichier") or ""))
    if not path.endswith(".desktop") or not os.path.isfile(path):
        raise ApiError("Lanceur introuvable.", 404)
    if not any(within(path, d) for d in app_dirs()):
        safe_path(path, must_exist=True)
        # comme Nemo : un lanceur posé sur le bureau doit être marqué « de confiance » avant de s'exécuter
        if not os.access(path, os.X_OK):
            if not to_bool(b.get("confiance")):
                li = launcher_info(path) or {}
                return {"ok": False, "confiance": True, "nom": li.get("nom") or os.path.basename(path)}
            os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
            if shutil.which("gio"):
                subprocess.run(["gio", "set", path, "metadata::trusted", "true"], capture_output=True, timeout=5)
    launch_desktop(path, files)
    return {"ok": True}


@route("GET", "/api/icone", kind="raw")
def r_icon(h, q, b):
    try:
        size = int(q1(q, "s", "48"))
    except ValueError:
        size = 48
    p, png = resolve_icon(q1(q, "n"), size)
    if png:
        h.send_response(200)
        h.send_header("Content-Type", "image/png")
        h.send_header("Content-Length", str(len(png)))
        h.send_header("Cache-Control", "private, max-age=86400")
        h.end_headers()
        h.wfile.write(png)
        return
    if not p:
        raise ApiError("Icône introuvable.", 404)
    h.send_file(p, cache=86400)


@route("GET", "/api/raccourcis")
def r_shortcuts(h, q, b):
    return shortcuts()


@route("POST", "/api/raccourcis/ajouter")
def r_shortcut_add(h, q, b):
    return shortcut_add(b)


@route("POST", "/api/raccourcis/ordre")
def r_shortcut_order(h, q, b):
    """Nouvel ordre. Un raccourci absent de la liste envoyée (épinglé entre-temps depuis une autre fenêtre)
    est gardé, à la fin : seul « retirer » en supprime."""
    ids = [str(x) for x in (b.get("ids") or [])]
    with store.lock:
        cur = {s["id"]: s for s in shortcuts_raw()}
        order = [i for i in dict.fromkeys(ids) if i in cur]
        shortcuts_save([cur[i] for i in order] + [s for i, s in cur.items() if i not in order])
    return shortcuts()


@route("POST", "/api/raccourcis/renommer")
def r_shortcut_rename(h, q, b):
    with store.lock:
        lst = shortcuts_raw()
        for s in lst:
            if s.get("id") == b.get("id"):
                nom = str(b.get("nom") or "").strip()[:60]
                if nom:
                    s["nom"] = nom
                else:
                    s.pop("nom", None)
                shortcuts_save(lst)
                return shortcuts()
    raise ApiError("Raccourci introuvable.", 404)


@route("POST", "/api/raccourcis/retirer")
def r_shortcut_remove(h, q, b):
    with store.lock:
        shortcuts_save([s for s in shortcuts_raw() if s.get("id") != b.get("id")])
    return shortcuts()


@route("POST", "/api/raccourcis/defaut")
def r_shortcut_reset(h, q, b):
    shortcuts_save(default_shortcuts())
    return shortcuts()


class Handler(BaseHTTPRequestHandler):
    server_version = "Archiviste/" + VERSION
    protocol_version = "HTTP/1.1"
    streaming = False
    cancelled = False  # vrai quand une autre requête a repris la discussion que celle-ci écrivait

    def log_message(self, fmt, *args):
        if os.environ.get("ARCHIVISTE_DEBUG"):
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ── garde-fous ──
    def host_ok(self) -> bool:
        if HOST not in ("127.0.0.1", "localhost", "::1"):
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1")

    def token_ok(self, query: dict) -> bool:
        tok = self.headers.get("X-Archiviste-Token") or q1(query, "t")
        return bool(tok) and secrets.compare_digest(tok, TOKEN)

    # ── réponses ──
    def send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def start_stream(self):
        if self.streaming:
            return
        self.streaming = True
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def emit(self, obj):
        if self.cancelled:
            raise ClientGone()
        try:
            self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            raise ClientGone()

    def send_file(self, path: str, download: bool = False, cache: int = 0):
        size = os.path.getsize(path)
        ext = ext_of(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        risky = ext in ("html", "htm", "xhtml", "svg", "xml") or "html" in ctype or "xml" in ctype
        if not risky and (ctype.startswith("text/") or ext in TEXT_EXTS):
            ctype = "text/plain; charset=utf-8"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        status = 200
        if rng and rng.startswith("bytes=") and size > 0:
            try:
                a, _, z = rng[6:].split(",")[0].partition("-")
                if a:
                    start = int(a)
                    end = int(z) if z else size - 1
                else:
                    start = max(0, size - int(z))
                end = min(end, size - 1)
                if start <= end:
                    status = 206
                else:
                    start, end = 0, size - 1
            except ValueError:
                start, end = 0, size - 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        name = os.path.basename(path)
        disp = "attachment" if download else "inline"
        self.send_header("Content-Disposition",
                         f"{disp}; filename*=UTF-8''{urllib.parse.quote(name)}")
        self.send_header("X-Content-Type-Options", "nosniff")
        if risky:  # une page HTML/SVG ouverte en aperçu ne doit pas pouvoir exécuter de script
            self.send_header("Content-Security-Policy", "sandbox")
        self.send_header("Cache-Control", f"private, max-age={cache}" if cache else "no-store")
        self.end_headers()
        if size == 0:
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(1 << 20, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def serve_static(self, rel: str):
        if rel in ("", "/"):
            rel = "index.html"
        target = (STATIC_DIR / rel.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            return self.send_json({"error": "introuvable"}, 404)
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.suffix == ".webmanifest":
            ctype = "application/manifest+json"
        if target.name in ("index.html", "bureau.html"):
            data = data.replace(b"__ARCHIVISTE_TOKEN__", TOKEN.encode())
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(data)

    # ── dispatch ──
    def handle_any(self, method: str):
        if not self.host_ok():
            return self.send_json({"error": "hote", "message": "Hôte non autorisé."}, 403)
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not path.startswith("/api/"):
            if method != "GET":
                return self.send_json({"error": "methode"}, 405)
            if path.startswith("/static/"):
                return self.serve_static(path[len("/static/"):])
            if path in ("/", "/index.html"):
                return self.serve_static("index.html")
            if path in ("/bureau", "/bureau.html"):
                return self.serve_static("bureau.html")
            if path in ("/manifest.webmanifest", "/icon.svg", "/favicon.svg"):
                return self.serve_static(path[1:])
            return self.send_json({"error": "introuvable"}, 404)

        if not self.token_ok(query):
            self._drain()
            return self.send_json({"error": "token", "message": "Session expirée : recharge la page."}, 403)

        for m, rx, fn, kind in ROUTES:
            if m != method:
                continue
            mt = rx.match(path)
            if not mt:
                continue
            body = {}
            if kind == "upload":
                self.close_connection = True  # corps lu par la route elle-même
            try:
                if method == "POST" and kind != "upload":
                    length = int(self.headers.get("Content-Length") or 0)
                    raw = self.rfile.read(length) if length else b""
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                    if not isinstance(body, dict):
                        raise ApiError("Requête invalide.")
                result = fn(self, query, body, *mt.groups())
                if kind in ("json", "upload"):
                    self.send_json(result)
            except ClientGone:
                pass
            except (ApiError, OllamaError) as e:
                status = getattr(e, "status", 400) or 502
                if self.streaming:
                    try:
                        self.emit({"t": "error", "d": str(e)})
                    except ClientGone:
                        pass
                else:
                    self.send_json({"error": "api", "message": str(e)}, status if status >= 400 else 502)
            except json.JSONDecodeError:
                self.send_json({"error": "api", "message": "Requête JSON invalide."}, 400)
            except PermissionError:
                self.send_json({"error": "api", "message": "Permission refusée par le système."}, 403)
            except FileNotFoundError as e:
                self.send_json({"error": "api", "message": f"Introuvable : {e.filename}"}, 404)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                if self.streaming:
                    try:
                        self.emit({"t": "error", "d": f"Erreur interne : {e}"})
                    except ClientGone:
                        pass
                else:
                    self.send_json({"error": "interne", "message": f"Erreur interne : {e}"}, 500)
            return
        self._drain()
        self.send_json({"error": "introuvable", "message": "Route inconnue."}, 404)

    def _drain(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if 0 < length < 50_000_000:
                self.rfile.read(length)
            elif length:
                self.close_connection = True
        except (ValueError, OSError):
            self.close_connection = True

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        self.handle_any("POST")


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def prepare() -> None:
    """Initialisation commune (serveur seul ou fenêtre d'application)."""
    mimetypes.add_type("image/svg+xml", ".svg")
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("text/markdown", ".md")
    get_settings()
    get_prompts()
    get_agents()
    if not os.environ.get("ARCHIVISTE_SANS_MAJ"):
        threading.Thread(target=_update_loop, name="mises-a-jour", daemon=True).start()
    start_index()
    if bureau_state().get("actif"):  # prépare les icônes des applis pour un bureau qui s'affiche vite
        threading.Thread(target=lambda: (apps_index(), find_icon("folder")), name="icones", daemon=True).start()


def main():
    prepare()
    try:
        srv = Server((HOST, PORT), Handler)
    except OSError as e:
        print(f"Impossible d'ouvrir le port {PORT} : {e}. Archiviste tourne peut-être déjà.", file=sys.stderr)
        sys.exit(1)
    print(f"Archiviste {VERSION} — http://{'127.0.0.1' if HOST in ('0.0.0.0', '') else HOST}:{PORT}")
    print(f"Données : {DATA_DIR}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")


if __name__ == "__main__":
    main()
