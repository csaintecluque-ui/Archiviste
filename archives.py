# -*- coding: utf-8 -*-
"""
Archiviste — archives : lire leur contenu, les extraire, en créer.

Zip (et .cbz), tar (.tar, .tar.gz, .tgz, .tar.bz2, .tar.xz) et fichiers compressés seuls (.gz, .bz2,
.xz) sont traités en Python. 7z, rar (.cbr), .tar.zst… passent par l'outil installé : 7-Zip (`7z`,
`7zz`), sinon `unrar` pour les rar, sinon `bsdtar`.

Une extraction se fait d'abord dans un dossier caché, à côté de l'archive : annulée ou ratée, elle ne
laisse rien derrière elle ; réussie, son résultat prend sa place d'un coup. Comme Nemo :
- l'archive ne contient qu'un dossier (ou qu'un fichier) : il arrive tel quel à côté d'elle ;
- elle contient plusieurs éléments : ils sont rangés dans un dossier qui porte son nom.
Rien ne peut s'écrire en dehors de ce dossier (chemins en « ../ » ou absolus, liens qui sortent).

Les fonctions longues reçoivent `avance(octets, detail)` et `annule()` : la première fait avancer la
barre de progression, la seconde dit si l'utilisateur a demandé l'arrêt (on lève alors Annule).
"""
import bz2
import errno
import gzip
import lzma
import os
import re
import shutil
import stat
import subprocess
import tarfile
import time
import zipfile
import zlib

CHUNK = 1 << 20
MARGE = 64 * 1024 * 1024          # place à laisser libre sur un disque (moins sur une petite clé USB)


def marge(dossier: str) -> int:
    try:
        return min(MARGE, shutil.disk_usage(dossier).total // 50)
    except OSError:
        return MARGE
DEJA_COMPRESSES = set("jpg jpeg png gif webp heic avif mp3 mp4 m4a m4v mkv mov avi webm ogg opus flac zip rar 7z gz "
                      "bz2 xz zst cbz cbr epub docx xlsx pptx odt ods odp jar apk deb rpm".split())


class Annule(Exception):
    """L'utilisateur a arrêté l'opération."""


class ErreurArchive(Exception):
    """Message prêt à être montré."""


class MotDePasse(ErreurArchive):
    """L'archive est protégée : il faut (un autre) mot de passe."""


# ── reconnaître une archive ──
TAR_EXT = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz")
EXTERNE_EXT = (".7z", ".cb7", ".rar", ".cbr", ".tar.zst", ".tzst", ".zst", ".tar.lz", ".lz", ".lzma", ".tar.lzma")
ZIP_EXT = (".zip", ".cbz")
SIMPLE_EXT = (".gz", ".bz2", ".xz")
NOM_EXT = TAR_EXT + EXTERNE_EXT + ZIP_EXT + SIMPLE_EXT


def nature(path: str) -> str | None:
    """« zip », « tar », « simple » (un seul fichier compressé), « externe » (outil installé) ou None."""
    n = os.path.basename(path).lower()
    if n.endswith(TAR_EXT):
        return "tar"
    if n.endswith(EXTERNE_EXT):
        return "externe"
    if n.endswith(ZIP_EXT):
        return "zip"
    if n.endswith(SIMPLE_EXT):
        return "simple"
    return None


def nom_sans_extension(path: str) -> str:
    """« Photos 2024.tar.gz » → « Photos 2024 »."""
    n = os.path.basename(path)
    low = n.lower()
    for e in sorted(NOM_EXT, key=len, reverse=True):
        if low.endswith(e) and len(n) > len(e):
            return n[:-len(e)]
    return os.path.splitext(n)[0] or n


def outil(path: str) -> list[str] | None:
    """Programme capable d'ouvrir cette archive « externe » (chemin du binaire en tête), ou None."""
    n = os.path.basename(path).lower()
    for exe in ("7z", "7zz", "7za"):
        p = shutil.which(exe)
        if p:
            return [p]
    if n.endswith((".rar", ".cbr")) and shutil.which("unrar"):
        return [shutil.which("unrar")]
    if shutil.which("bsdtar"):
        return [shutil.which("bsdtar")]
    return None


def conseil_outil(path: str) -> str:
    return ("Pour ouvrir ce type d'archive, installe 7-Zip : sudo apt install 7zip"
            + (" (ou unrar pour les .rar)" if path.lower().endswith((".rar", ".cbr")) else ""))


# ── noms de fichiers ──
def _nom_zip(info: zipfile.ZipInfo) -> str:
    """Les zips faits sous Windows n'indiquent pas leur encodage : « Ã©t├® » au lieu de « été ».
    On essaie l'UTF-8 (macOS, Linux), puis la page de code 850 (Windows en français)."""
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    for enc in ("utf-8", "cp850"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return name


def morceaux(name: str) -> list[str]:
    """Chemin d'une entrée, nettoyé : ni absolu, ni « .. », ni lecteur Windows."""
    parts = [p.replace("\x00", "") for p in name.replace("\\", "/").split("/")]
    parts = [p for p in parts if p not in ("", ".", "..")]
    if parts and re.match(r"^[A-Za-z]:$", parts[0]):
        parts = parts[1:]
    return [p[:200] if len(p.encode("utf-8")) > 255 else p for p in parts]


# ── lire le contenu ──
def lister(path: str, limite: int = 2000) -> dict:
    """Contenu d'une archive : entrées (nom, taille, dossier), total, taille une fois extraite."""
    nat = nature(path)
    out = {"nature": nat, "entrees": [], "nombre": 0, "taille": 0, "taille_connue": True, "chiffree": False,
           "outil": None, "dossier_unique": None}
    tops = set()
    vus = set()  # dossiers déjà listés : beaucoup d'archives ne nomment pas leurs dossiers, seulement les fichiers

    def add(name, size, is_dir):
        parts = morceaux(name)
        if not parts:
            return
        tops.add(parts[0] + ("/" if len(parts) > 1 or is_dir else ""))
        for k in range(1, len(parts) + (1 if is_dir else 0)):
            d = "/".join(parts[:k])
            if d not in vus:
                vus.add(d)
                if len(out["entrees"]) < limite:
                    out["entrees"].append({"nom": d, "taille": None, "dossier": True})
        if is_dir:
            return
        out["nombre"] += 1
        out["taille"] += max(0, size or 0)
        if len(out["entrees"]) < limite:
            out["entrees"].append({"nom": "/".join(parts), "taille": size, "dossier": False})

    try:
        if nat == "zip":
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if info.flag_bits & 1:
                        out["chiffree"] = True
                    add(_nom_zip(info), info.file_size, info.is_dir())
        elif nat == "tar":
            with tarfile.open(path, "r:*") as tf:
                for m in tf:
                    add(m.name, m.size if m.isreg() else 0, m.isdir())
        elif nat == "simple":
            add(nom_sans_extension(path), None, False)
            out["taille_connue"] = False
            if path.lower().endswith(".gz"):  # gzip note la taille d'origine (modulo 4 Go) à la fin du fichier
                with open(path, "rb") as f:
                    f.seek(-4, 2)
                    size = int.from_bytes(f.read(4), "little")
                if size and size >= os.path.getsize(path) // 4:
                    out["entrees"][0]["taille"] = out["taille"] = size
                    out["taille_connue"] = True
        elif nat == "externe":
            cmd = outil(path)
            if not cmd:
                out["outil"] = conseil_outil(path)
                return out
            _lister_externe(cmd, path, add, out)
        else:
            raise ErreurArchive("Ce fichier n'est pas une archive reconnue.")
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, lzma.LZMAError, OSError, zlib.error) as e:
        raise ErreurArchive(f"Archive illisible ou abîmée ({e.__class__.__name__}).") from e
    if len(tops) == 1:
        out["dossier_unique"] = next(iter(tops)).rstrip("/")
    return out


def _lister_externe(cmd: list[str], path: str, add, out: dict) -> None:
    exe = os.path.basename(cmd[0])
    if exe.startswith("7z"):
        r = subprocess.run(cmd + ["l", "-slt", "-ba", "-p", path], capture_output=True, text=True,
                           timeout=120, stdin=subprocess.DEVNULL, errors="replace")
        if "Wrong password" in r.stdout + r.stderr or "Can not open encrypted archive" in r.stdout + r.stderr:
            out["chiffree"] = True
            return
        block: dict = {}
        for line in (r.stdout + "\n\n").splitlines():
            if not line.strip():
                if "Path" in block:
                    is_dir = block.get("Folder") == "+" or block.get("Attributes", "").startswith("D")
                    try:
                        size = int(block.get("Size") or 0)
                    except ValueError:
                        size = 0
                    add(block["Path"], size, is_dir)
                    if block.get("Encrypted") == "+":
                        out["chiffree"] = True
                block = {}
                continue
            k, _, v = line.partition(" = ")
            block[k.strip()] = v
        if r.returncode not in (0, 1) and not out["nombre"]:
            raise ErreurArchive("Archive illisible ou abîmée.")
    elif exe == "unrar":
        r = subprocess.run(cmd + ["lb", "-p-", path], capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL, errors="replace")
        for name in r.stdout.splitlines():
            if name.strip():
                add(name, None, False)
        out["taille_connue"] = False
    else:  # bsdtar
        r = subprocess.run(cmd + ["-tf", path], capture_output=True, text=True, timeout=120,
                           stdin=subprocess.DEVNULL, errors="replace")
        if r.returncode != 0:
            raise ErreurArchive("Archive illisible ou abîmée.")
        for name in r.stdout.splitlines():
            if name.strip():
                add(name, None, name.endswith("/"))
        out["taille_connue"] = False


# ── extraire ──
class _Compteur:
    """Fichier dont on suit la position : progression d'une archive compressée lue d'un bout à l'autre."""

    def __init__(self, f, avance):
        self.f, self.avance, self.pos = f, avance, 0

    def read(self, n=-1):
        b = self.f.read(n)
        self.pos += len(b)
        self.avance(len(b), None)
        return b

    def seek(self, *a):
        r = self.f.seek(*a)
        self.pos = self.f.tell()
        return r

    def tell(self):
        return self.f.tell()

    def seekable(self):
        return True

    def readable(self):
        return True

    def __getattr__(self, k):
        return getattr(self.f, k)


def _verifier_place(dossier: str, besoin: int) -> None:
    libre = shutil.disk_usage(dossier).free
    if besoin + marge(dossier) > libre:
        raise ErreurArchive(f"Pas assez de place : il faut {taille_lisible(besoin)}, "
                            f"il reste {taille_lisible(libre)} sur ce disque.")


def taille_lisible(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if n < 1024 or unit == "To":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return str(n)


def _copier(src, dst, avance, annule, detail, surveille: str | None = None) -> None:
    """Copie un flux par morceaux : progression, arrêt possible, place surveillée si la taille est inconnue."""
    n = 0
    while True:
        if annule():
            raise Annule()
        b = src.read(CHUNK)
        if not b:
            return
        dst.write(b)
        avance(len(b), detail)
        n += len(b)
        if surveille and n % (256 * CHUNK) < CHUNK and shutil.disk_usage(surveille).free < marge(surveille):
            raise ErreurArchive("Le disque est presque plein : extraction arrêtée.")


def _lien_sur(lien: str, cible_rel: str) -> bool:
    """Un lien créé par une archive ne doit pas sortir du dossier extrait."""
    if os.path.isabs(cible_rel):
        return False
    final = os.path.normpath(os.path.join(os.path.dirname(lien), cible_rel))
    return not (final == ".." or final.startswith("../") or final.startswith("/"))


def extraire(path: str, dest: str, avance, annule, unique, mdp: str | None = None) -> dict:
    """Extrait l'archive dans le dossier dest. Rend {"resultat": chemin créé, "elements": n}."""
    if not os.path.isdir(dest):
        raise ErreurArchive("Le dossier de destination n'existe pas.")
    nat = nature(path)
    if nat is None:
        raise ErreurArchive("Ce fichier n'est pas une archive reconnue.")
    tmp = os.path.join(dest, f".archiviste-extraction-{os.getpid()}-{int(time.time() * 1000) % 10 ** 9}")
    os.mkdir(tmp, 0o755)
    try:
        if nat == "zip":
            _extraire_zip(path, tmp, avance, annule, mdp)
        elif nat == "tar":
            _extraire_tar(path, tmp, avance, annule)
        elif nat == "simple":
            _extraire_simple(path, tmp, avance, annule)
        else:
            _extraire_externe(path, tmp, avance, annule, mdp)
        _nettoyer_liens(tmp)
        entries = os.listdir(tmp)
        if not entries:
            raise ErreurArchive("L'archive est vide.")
        if len(entries) == 1:
            final = unique(os.path.join(dest, entries[0]))
            os.rename(os.path.join(tmp, entries[0]), final)
            os.rmdir(tmp)
        else:
            final = unique(os.path.join(dest, nom_sans_extension(path)))
            os.rename(tmp, final)
        return {"resultat": final, "elements": len(entries)}
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _nettoyer_liens(root: str) -> None:
    """Dernier contrôle, quel que soit l'outil : aucun lien ne doit mener hors du dossier extrait."""
    real_root = os.path.realpath(root)
    for d, dirs, files in os.walk(root):
        for n in dirs + files:
            p = os.path.join(d, n)
            if os.path.islink(p):
                t = os.path.realpath(p)
                if not (t == real_root or t.startswith(real_root + os.sep)):
                    os.unlink(p)


def _extraire_zip(path, tmp, avance, annule, mdp):
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        chiffre = any(i.flag_bits & 1 for i in infos)
        if chiffre:
            if mdp is None:
                raise MotDePasse("Cette archive est protégée par un mot de passe.")
            if outil(path) and os.path.basename(outil(path)[0]).startswith("7z"):
                return _extraire_externe(path, tmp, avance, annule, mdp)  # 7-Zip : bien plus rapide, et l'AES
            z.setpassword(mdp.encode("utf-8"))
        total = sum(i.file_size for i in infos)
        _verifier_place(tmp, total)
        avance(0, None, fait=0, total=total)
        for info in infos:
            if annule():
                raise Annule()
            parts = morceaux(_nom_zip(info))
            if not parts:
                continue
            target = os.path.join(tmp, *parts)
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            mode = info.external_attr >> 16 if info.create_system == 3 else 0
            try:
                if stat.S_ISLNK(mode):
                    cible = z.read(info).decode("utf-8", "replace")
                    if _lien_sur(os.path.join(*parts), cible) and not os.path.lexists(target):
                        os.symlink(cible, target)
                    continue
                with z.open(info) as src, open(target, "wb") as dst:
                    _copier(src, dst, avance, annule, "/".join(parts))
            except RuntimeError as e:  # mauvais mot de passe
                if "password" in str(e).lower():
                    raise MotDePasse("Mot de passe incorrect.") from e
                raise
            except NotImplementedError as e:
                raise ErreurArchive("Cette archive utilise un chiffrement que seul 7-Zip sait lire : "
                                    "sudo apt install 7zip") from e
            except zipfile.BadZipFile as e:
                if chiffre:
                    raise MotDePasse("Mot de passe incorrect.") from e
                raise
            if mode & 0o111:
                os.chmod(target, (mode & 0o777) | 0o600)
            try:
                t = time.mktime(info.date_time + (0, 0, -1))
                os.utime(target, (t, t))
            except (OverflowError, ValueError, OSError):
                pass


def _extraire_tar(path, tmp, avance, annule):
    size = os.path.getsize(path)
    lu = [0]

    def suivi(n, _d):  # progression : octets de l'archive lus (elle est souvent compressée)
        lu[0] += n
        avance(0, None, fait=lu[0], total=size)

    flt = getattr(tarfile, "data_filter", None)
    with open(path, "rb") as raw:
        f = _Compteur(raw, suivi)
        with tarfile.open(fileobj=f, mode="r:*") as tf:
            for m in tf:
                if annule():
                    raise Annule()
                if flt is not None:
                    try:
                        m2 = flt(m, tmp)
                    except tarfile.FilterError:
                        continue  # chemin dangereux, fichier spécial : ignoré
                    if m2 is None:
                        continue
                else:
                    if not (m.isreg() or m.isdir()):
                        continue
                    m2 = m.replace(name="/".join(morceaux(m.name)))
                parts = morceaux(m2.name)
                if not parts:
                    continue
                target = os.path.join(tmp, *parts)
                if m2.isreg():
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    src = tf.extractfile(m2)
                    with open(target, "wb") as dst:
                        _copier(src, dst, lambda n, d: avance(0, d), annule, "/".join(parts), surveille=tmp)
                    os.chmod(target, (m2.mode & 0o755) | 0o600)
                    try:
                        os.utime(target, (m2.mtime, m2.mtime))
                    except (OverflowError, ValueError, OSError):
                        pass
                elif m2.isdir():
                    os.makedirs(target, exist_ok=True)
                else:
                    try:
                        tf.extract(m, tmp, set_attrs=False, **({"filter": "data"} if flt else {}))
                    except (tarfile.TarError, OSError):
                        pass


def _extraire_simple(path, tmp, avance, annule):
    low = path.lower()
    opener = gzip.open if low.endswith(".gz") else bz2.open if low.endswith(".bz2") else lzma.open
    size = os.path.getsize(path)
    name = nom_sans_extension(path)
    with open(path, "rb") as raw:
        with opener(raw) as src, open(os.path.join(tmp, name), "wb") as dst:
            while True:
                if annule():
                    raise Annule()
                b = src.read(CHUNK)
                if not b:
                    break
                dst.write(b)
                avance(0, name, fait=raw.tell(), total=size)
                if shutil.disk_usage(tmp).free < marge(tmp):
                    raise ErreurArchive("Le disque est presque plein : extraction arrêtée.")


def _extraire_externe(path, tmp, avance, annule, mdp):
    cmd = outil(path)
    if not cmd:
        raise ErreurArchive(conseil_outil(path))
    exe = os.path.basename(cmd[0])
    if exe.startswith("7z"):
        argv = cmd + ["x", "-y", "-bsp1", "-bso1", f"-o{tmp}", f"-p{mdp or ''}", "--", path]
    elif exe == "unrar":
        argv = cmd + ["x", "-y", "-o+", f"-p{mdp}" if mdp else "-p-", "--", path, tmp + "/"]
    else:
        argv = cmd + ["-xf", path, "-C", tmp]
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    sortie = b""
    try:
        os.set_blocking(proc.stdout.fileno(), False)
        while True:
            if annule():
                proc.kill()
                proc.wait()
                raise Annule()
            try:
                b = proc.stdout.read(65536)
            except BlockingIOError:
                b = None
            if b:
                sortie = (sortie + b)[-20000:]
                pcts = re.findall(rb"(\d{1,3})%", b)
                if pcts:
                    avance(0, None, fait=min(100, int(pcts[-1])), total=100, pourcent=True)
            elif proc.poll() is not None:
                break
            else:
                time.sleep(0.1)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    txt = sortie.decode("utf-8", "replace")
    low = txt.lower()
    if "wrong password" in low or "can not open encrypted archive" in low or "enter password" in low \
            or ("password" in low and ("incorrect" in low or "encrypted" in low or "needs" in low)):
        raise MotDePasse("Mot de passe incorrect." if mdp else "Cette archive est protégée par un mot de passe.")
    if proc.returncode not in (0, 1):  # 1 : simples avertissements chez 7-Zip
        if "No space left" in txt or "There is not enough space" in txt:
            raise ErreurArchive("Le disque est plein : extraction arrêtée.")
        last = [l for l in txt.splitlines() if l.strip()][-1:] or ["erreur inconnue"]
        raise ErreurArchive(f"L'extraction a échoué : {last[0].strip()[:200]}")


# ── compresser ──
def compresser(paths: list[str], dest: str, fmt: str, avance, annule) -> dict:
    """Crée l'archive dest (zip ou tar.gz) avec ces éléments, chacun sous son propre nom."""
    elements = []  # (chemin sur le disque, nom dans l'archive, genre)
    total = 0
    for p in paths:
        base = os.path.dirname(p.rstrip("/"))
        if os.path.islink(p) or not os.path.isdir(p):
            elements.append((p, os.path.relpath(p, base), "lien" if os.path.islink(p) else "fichier"))
            total += 0 if os.path.islink(p) else os.path.getsize(p)
            continue
        elements.append((p, os.path.relpath(p, base), "dossier"))
        for d, dirs, files in os.walk(p):
            for n in sorted(dirs):
                q = os.path.join(d, n)
                elements.append((q, os.path.relpath(q, base), "lien" if os.path.islink(q) else "dossier"))
            for n in sorted(files):
                q = os.path.join(d, n)
                if os.path.islink(q):
                    elements.append((q, os.path.relpath(q, base), "lien"))
                elif os.path.isfile(q):
                    elements.append((q, os.path.relpath(q, base), "fichier"))
                    total += os.path.getsize(q)
            if annule():
                raise Annule()
    _verifier_place(os.path.dirname(dest), total // 2)
    avance(0, None, fait=0, total=total)
    tmp = os.path.join(os.path.dirname(dest), "." + os.path.basename(dest) + ".part")
    try:
        if fmt == "zip":
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, allowZip64=True, compresslevel=6) as z:
                for src, arc, genre in elements:
                    if annule():
                        raise Annule()
                    if genre == "dossier":
                        z.write(src, arc + "/")
                    elif genre == "lien":
                        zi = zipfile.ZipInfo(arc, time.localtime(os.lstat(src).st_mtime)[:6])
                        zi.create_system = 3
                        zi.external_attr = (stat.S_IFLNK | 0o777) << 16
                        z.writestr(zi, os.readlink(src))
                    else:
                        zi = zipfile.ZipInfo.from_file(src, arc)
                        ext = os.path.splitext(src)[1][1:].lower()
                        zi.compress_type = zipfile.ZIP_STORED if ext in DEJA_COMPRESSES else zipfile.ZIP_DEFLATED
                        with open(src, "rb") as f, z.open(zi, "w") as dst:
                            _copier(f, dst, avance, annule, arc)
        else:
            with tarfile.open(tmp, "w:gz", compresslevel=6) as tf:
                for src, arc, genre in elements:
                    if annule():
                        raise Annule()
                    ti = tf.gettarinfo(src, arc)
                    if genre == "fichier":
                        with open(src, "rb") as f:
                            tf.addfile(ti, _Lecteur(f, avance, annule, arc))
                    else:
                        tf.addfile(ti)
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return {"resultat": dest, "elements": len(elements)}


class _Lecteur:
    """Fichier lu par tarfile pendant une compression : progression et arrêt."""

    def __init__(self, f, avance, annule, nom):
        self.f, self.avance, self.annule, self.nom = f, avance, annule, nom

    def read(self, n=-1):
        if self.annule():
            raise Annule()
        b = self.f.read(n)
        self.avance(len(b), self.nom)
        return b


def message_os(e: OSError) -> str:
    """Erreur du système, dite simplement."""
    code = getattr(e, "errno", None)
    if code == errno.ENOSPC:
        return "Le disque est plein."
    if code == errno.EFBIG:
        return ("Fichier trop gros pour ce disque : une clé USB en FAT32 n'accepte pas les fichiers de plus de "
                "4 Go. Reformate-la en exFAT (ou copie l'archive extraite, en plusieurs fichiers).")
    if code in (errno.EACCES, errno.EPERM):
        return "Permission refusée."
    if code == errno.EROFS:
        return "Ce disque est en lecture seule."
    if code == errno.ENAMETOOLONG:
        return "Nom de fichier trop long pour ce disque."
    return e.strerror or str(e)
