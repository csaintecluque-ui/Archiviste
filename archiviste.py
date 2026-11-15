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

import base64
import datetime as dt
import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import shutil
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

VERSION = "1.3.0"
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

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# ════════════════════════════════════════════════════════════════════
#  Erreurs
# ════════════════════════════════════════════════════════════════════
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
def allowed_roots(settings: dict | None = None) -> list[str]:
    s = settings or get_settings()
    out = []
    for r in s.get("roots") or []:
        rp = os.path.realpath(os.path.expanduser(r))
        if os.path.isdir(rp):
            out.append(rp)
    return out or [os.path.realpath(str(HOME))]


def within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def safe_path(p, base: str | None = None, roots: list[str] | None = None,
              must_exist: bool = False) -> str:
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
    real = os.path.realpath(p)
    if not any(within(real, r) for r in roots):
        raise ApiError(f"Accès refusé : « {p} » est en dehors des dossiers autorisés.", 403)
    if must_exist and not os.path.lexists(real):
        raise ApiError(f"Introuvable : « {p} ».", 404)
    return real


def is_root(path: str, roots: list[str] | None = None) -> bool:
    return path in (roots or allowed_roots())


def check_name(name: str) -> str:
    name = str(name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\x00" in name:
        raise ApiError("Nom invalide (pas de « / », pas vide).")
    if len(name.encode("utf-8")) > 255:
        raise ApiError("Nom trop long.")
    return name


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
    return {"path": real, "root": root, "parent": parent, "entries": entries}


def backup_version(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    vdir = DATA_DIR / "versions"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = vdir / f"{stamp}__{os.path.basename(path)}"
    shutil.copy2(path, dest)
    (vdir / f"{dest.name}.origine").write_text(path, "utf-8")
    olds = sorted(p for p in vdir.iterdir() if not p.name.endswith(".origine"))
    for p in olds[:-MAX_VERSIONS]:
        p.unlink(missing_ok=True)
        (vdir / f"{p.name}.origine").unlink(missing_ok=True)
    return str(dest)


def fs_write(path: str, content: str, roots=None, base=None, mode: str = "remplacer") -> dict:
    real = safe_path(path, base=base, roots=roots)
    if os.path.isdir(real):
        raise ApiError("Impossible d'écrire : c'est un dossier.")
    existed = os.path.exists(real)
    os.makedirs(os.path.dirname(real), exist_ok=True)
    version = backup_version(real) if existed else None
    if mode == "ajouter" and existed:
        with open(real, "a", encoding="utf-8") as f:
            f.write(content)
    else:
        tmp = real + ".archiviste-tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        if existed:
            shutil.copymode(real, tmp)
        os.replace(tmp, real)
    return {"path": real, "cree": not existed, "ancienne_version": version, "taille": os.path.getsize(real)}


def fs_mkdir(path: str, roots=None, base=None) -> dict:
    real = safe_path(path, base=base, roots=roots)
    if os.path.exists(real):
        if os.path.isdir(real):
            return {"path": real, "existait": True}
        raise ApiError("Un fichier porte déjà ce nom.")
    os.makedirs(real)
    return {"path": real, "existait": False}


def fs_move(src: str, dest: str, roots=None, base=None, copy: bool = False) -> dict:
    roots = roots or allowed_roots()
    s = safe_path(src, base=base, roots=roots, must_exist=True)
    if is_root(s, roots) and not copy:
        raise ApiError("On ne déplace pas un dossier racine autorisé.")
    d = safe_path(dest, base=base, roots=roots)
    if os.path.isdir(d):
        target = os.path.join(d, os.path.basename(s))
    else:
        target = d
        os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.isdir(s) and within(os.path.realpath(target), s):
        raise ApiError("Impossible de mettre un dossier dans lui-même.")
    if os.path.realpath(target) == s:
        return {"de": s, "vers": s, "inchange": True}
    target = unique_path(target)
    if copy:
        if os.path.isdir(s):
            shutil.copytree(s, target, symlinks=True)
        else:
            shutil.copy2(s, target)
    else:
        shutil.move(s, target)
    return {"de": s, "vers": target}


def fs_rename(path: str, new_name: str, roots=None, base=None) -> dict:
    roots = roots or allowed_roots()
    s = safe_path(path, base=base, roots=roots, must_exist=True)
    if is_root(s, roots):
        raise ApiError("On ne renomme pas un dossier racine autorisé.")
    new_name = check_name(new_name)
    target = os.path.join(os.path.dirname(s), new_name)
    if os.path.lexists(target) and target != s:
        raise ApiError(f"« {new_name} » existe déjà ici.")
    os.rename(s, target)
    return {"de": s, "vers": target}


# ── Corbeille (norme freedesktop : visible et restaurable depuis Nemo) ──
def trash(path: str, roots=None, base=None) -> dict:
    roots = roots or allowed_roots()
    real = safe_path(path, base=base, roots=roots, must_exist=True)
    if is_root(real, roots):
        raise ApiError("On ne met pas un dossier racine autorisé à la corbeille.")
    if within(str(TRASH_DIR), real):
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
def walk_files(base: str, show_hidden: bool, max_items: int = 20000, deadline: float | None = None):
    count = 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames
                             if d not in SKIP_DIRS and (show_hidden or not d.startswith(".")))
        for name in sorted(filenames):
            if not show_hidden and name.startswith("."):
                continue
            yield dirpath, dirnames, name
            count += 1
            if count >= max_items or (deadline and time.time() > deadline):
                return


def fs_search(base: str, query: str, in_content: bool, roots=None, show_hidden=False, limit=300) -> dict:
    real = safe_path(base, roots=roots, must_exist=True)
    q = (query or "").strip()
    if not q:
        raise ApiError("Que faut-il chercher ?")
    wildcard = any(c in q for c in "*?[")
    ql = q.casefold()
    results, deadline = [], time.time() + 12
    # dossiers dont le nom correspond
    for dirpath, dirnames, _ in os.walk(real):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and (show_hidden or not d.startswith("."))]
        for d in dirnames:
            if (fnmatch(d.casefold(), ql) if wildcard else ql in d.casefold()):
                results.append(entry_info(os.path.join(dirpath, d), d))
        if len(results) >= limit // 3 or time.time() > deadline:
            break
    for dirpath, _, name in walk_files(real, show_hidden, 100000, deadline):
        full = os.path.join(dirpath, name)
        hit = fnmatch(name.casefold(), ql) if wildcard else ql in name.casefold()
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
            e = entry_info(full, name)
            if snippet:
                e["extrait"] = snippet
            results.append(e)
            if len(results) >= limit:
                break
    return {"base": real, "query": q, "results": results, "tronque": len(results) >= limit}


def find_duplicates(base: str, roots=None, show_hidden=False) -> dict:
    real = safe_path(base, roots=roots, must_exist=True)
    by_size: dict[int, list[str]] = {}
    for dirpath, _, name in walk_files(real, show_hidden, 30000, time.time() + 40):
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
            "place_recuperable": human_size(gain)}


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
}


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
            if to_bool(a.get("recursif")):
                for dirpath, dirnames, name_ in walk_files(path, hidden, 300):
                    full = os.path.join(dirpath, name_)
                    e = entry_info(full, name_)
                    items.append({"nom": os.path.relpath(full, path), "taille": human_size(e["size"]),
                                  "modifie": dt.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d")})
            else:
                for e in fs_list(path, hidden)["entries"][:300]:
                    items.append({"nom": e["name"] + ("/" if e["dir"] else ""),
                                  "type": "dossier" if e["dir"] else (e["ext"] or "fichier"),
                                  "taille": None if e["dir"] else human_size(e["size"]),
                                  "modifie": dt.datetime.fromtimestamp(e["mtime"]).strftime("%Y-%m-%d")})
            res = {"dossier": _short(path, base), "nombre": len(items), "elements": items}
            return res, f"{len(items)} élément(s) dans « {_short(path, base)} »", True
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
            return {"motif": r["query"], "nombre": len(items), "resultats": items}, f"{len(items)} résultat(s)", True
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
            return ({"groupes": groups, "nb_groupes": r["nb_groupes"],
                     "place_recuperable": r["place_recuperable"]},
                    f"{r['nb_groupes']} groupe(s) de doublons, {r['place_recuperable']} récupérables", True)
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
    data = store.read("prompts.json", None)
    if data is None:
        data = default_prompts()
        store.write("prompts.json", data)
    return data


def get_agents() -> list[dict]:
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
            "allowed": set((agent or {}).get("outils") or [])}


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


def run_chat(h, body: dict) -> None:
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

    h.start_stream()
    h.emit({"t": "start", "model": model, "agent": (agent or {}).get("nom")})

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
        save_conv(conv)

    # 2) Régénérer : on retire la dernière réponse
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
        ctx_text, atts, images = expand_attachments(attachments, s) if attachments else ("", [], [])
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
        save_conv(conv)
        h.emit({"t": "user_saved", "titre": conv["titre"]})

    if not conv["messages"]:
        h.emit({"t": "error", "d": "Message vide."})
        return

    tools = tool_schemas((agent or {}).get("outils") or [])
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
                save_conv(conv)
            raise
        except OllamaError as e:
            low = str(e).lower()
            malformed = any(k in low for k in ("parse", "expected element", "unexpected", "invalid character"))
            if tools and not parse_retry and malformed and "support" not in low:
                parse_retry = True
                rnd -= 1
                h.emit({"t": "notice", "d": "Le modèle a mal formé un appel d'outil, nouvelle tentative…"})
                continue
            h.emit({"t": "error", "d": str(e)})
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
        save_conv(conv)
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
            save_conv(conv)
            h.emit({"t": "confirm", "pending": [
                {"id": c["id"], "name": c["name"], "label": c["label"], "description": c["description"],
                 "args": c["args"]} for c in calls if c["needs"]]})
            return
        for c in calls:
            conv["messages"].append(tool_message(c))
        save_conv(conv)

    h.emit({"t": "error", "d": f"Arrêt de sécurité : l'agent a enchaîné {MAX_ROUNDS} étapes sans conclure."})


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
        if e["dir"]:
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
            src = safe_path(mv.get("path"), must_exist=True)
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
        except (ApiError, OSError) as e:
            errors.append({"fichier": mv.get("path"), "erreur": str(e)})
    jid = None
    if moves:
        journal = store.read("journal.json", list)
        jid = new_id("j_")
        journal.insert(0, {"id": jid, "date": now_iso(), "base": base, "mode": body.get("mode", ""),
                           "moves": moves, "crees": created, "annule": False})
        store.write("journal.json", journal[:60])
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
            ok += 1
        except (ApiError, OSError) as e:
            errors.append({"fichier": mv["vers"], "erreur": str(e)})
    for d in sorted(entry.get("crees", []), key=len, reverse=True):
        try:
            os.rmdir(d)
        except OSError:
            pass
    entry["annule"] = True
    entry["annule_le"] = now_iso()
    store.write("journal.json", journal)
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
    return {
        "actuelle": VERSION, "installee": inst,
        "relancer": parse_version(inst) > parse_version(VERSION),
        "disponible": bool(lt and lt.get("deb") and parse_version(lt["version"]) > parse_version(max(VERSION, inst, key=parse_version))),
        "derniere": lt, "erreur": UPDATE_STATE["error"], "verifie": UPDATE_STATE["checked"],
        "depot": UPDATE_REPO, "relance_possible": RELAUNCH_HOOK is not None,
        "paquet": str(APP_DIR) == "/opt/archiviste",
    }


def check_update() -> dict:
    url = os.environ.get("ARCHIVISTE_MAJ_API") or f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"Archiviste/{VERSION}"})
    latest, err = None, None
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8"))
        asset = next((a for a in data.get("assets") or [] if DEB_NAME_RE.match(a.get("name", ""))), None)
        latest = {"version": str(data.get("tag_name", "")).lstrip("vV"), "notes": (data.get("body") or "")[:6000],
                  "page": data.get("html_url"), "date": data.get("published_at"),
                  "deb": asset and asset.get("browser_download_url"), "nom": asset and asset.get("name"),
                  "taille": asset and asset.get("size"), "digest": asset and asset.get("digest")}
    except urllib.error.HTTPError as e:
        err = "Aucune version publiée pour l'instant." if e.code == 404 else f"GitHub a répondu {e.code}."
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        err = "Pas de connexion à GitHub."
    with _update_lock:
        UPDATE_STATE.update(checked=time.time(), latest=latest, error=err)
    return update_info()


def download_update() -> dict:
    info = update_info() if UPDATE_STATE["latest"] else check_update()
    lt = UPDATE_STATE["latest"]
    if not info["disponible"]:
        raise ApiError("Aucune mise à jour disponible.")
    name = os.path.basename(lt["nom"] or "")
    allowed = ("https://github.com/",) + ((os.environ["ARCHIVISTE_MAJ_DEPOT"],) if os.environ.get("ARCHIVISTE_MAJ_DEPOT") else ())
    if not DEB_NAME_RE.match(name) or not str(lt["deb"]).startswith(allowed):
        raise ApiError("Fichier de mise à jour inattendu : téléchargement annulé.")
    folder = Path(os.environ.get("XDG_CACHE_HOME") or HOME / ".cache") / "archiviste" / "mises-a-jour"
    folder.mkdir(parents=True, exist_ok=True)
    dest, tmp = folder / name, folder / (name + ".part")
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
    digest = str(lt.get("digest") or "")
    with open(tmp, "rb") as f:
        magic = f.read(8)
    if magic != b"!<arch>\n" or (digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest()):
        tmp.unlink(missing_ok=True)
        raise ApiError("Le fichier téléchargé est abîmé (empreinte différente) : rien n'a été installé.")
    os.replace(tmp, dest)
    for old in folder.glob("archiviste_*_all.deb"):
        if old != dest:
            old.unlink(missing_ok=True)
    opener = shutil.which("xdg-open")
    opened = bool(opener) and _launch([opener, str(dest)])
    return {"fichier": str(dest), "ouvert": opened, "version": lt["version"]}


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
    return download_update()


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
    return fs_write(path, str(b.get("content", "")))


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
    dest = safe_path(b.get("dest_dir"), must_exist=True)
    if not os.path.isdir(dest):
        raise ApiError("La destination doit être un dossier.")
    done, errors = [], []
    for p in b.get("paths") or []:
        try:
            done.append(fs_move(p, dest, copy=bool(b.get("copy"))))
        except (ApiError, OSError) as e:
            errors.append({"path": p, "erreur": str(e)})
    return {"ok": done, "erreurs": errors}


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
    return fs_search(q1(q, "path"), q1(q, "q"), q1(q, "content") == "1", show_hidden=s["show_hidden"])


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
    return entry_info(target)


# ── Corbeille ──
@route("GET", "/api/trash")
def r_trash_list(h, q, b):
    return trash_list()


@route("POST", "/api/trash/restore")
def r_trash_restore(h, q, b):
    return [trash_restore(t) for t in b.get("ids") or []]


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
    store.delete(conv_path(cid))
    return {"ok": True}


@route("POST", "/api/chat", kind="stream")
def r_chat(h, q, b):
    run_chat(h, b)


@route("POST", "/api/ai/run", kind="stream")
def r_oneshot(h, q, b):
    run_oneshot(h, b)


class Handler(BaseHTTPRequestHandler):
    server_version = "Archiviste/" + VERSION
    protocol_version = "HTTP/1.1"
    streaming = False

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
        try:
            self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            raise ClientGone()

    def send_file(self, path: str, download: bool = False):
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
        self.send_header("Cache-Control", "no-store")
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
        if target.name == "index.html":
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
