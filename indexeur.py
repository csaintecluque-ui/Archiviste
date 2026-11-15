#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archiviste — index de recherche.

Tient à jour, en arrière-plan, la liste des fichiers des dossiers autorisés (et le texte des documents)
dans une petite base SQLite : la recherche répond tout de suite et sur tout le dossier, au lieu de
reparcourir le disque à chaque fois. Bibliothèque standard uniquement.

    idx = Indexeur(chemin_base, dossiers_autorises, ignorer, lire_texte, plier)
    idx.start()
    idx.search("/home/moi", "facture", contenu=True)

Mise à jour : un passage léger toutes les quelques minutes (seuls les dossiers dont la date a changé sont
relus), un passage complet de temps en temps, tout de suite pour les dossiers signalés par touch(), et à la
demande avant une recherche (refresh) pour qu'un fichier créé à l'instant soit trouvé.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time

SCHEMA = 3
LIGHT_EVERY = 180        # secondes entre deux passages légers
FULL_EVERY = 3600        # secondes entre deux passages complets (tailles et dates des fichiers)
TEXT_MAX = 20000         # caractères de texte gardés par document
TEXT_SLICE = 150         # documents lus d'affilée avant de rendre la main


class Indexeur:
    def __init__(self, db_path, roots_fn, skip_dirs, text_fn, fold_fn, text_ok_fn, content_fn=lambda: True):
        self.db_path = str(db_path)
        self.roots_fn = roots_fn          # → liste des dossiers à indexer
        self.skip = set(skip_dirs)
        self.text_fn = text_fn            # (chemin, limite) → (texte | None, note)
        self.fold = fold_fn               # « Été » → « ete »
        self.text_ok = text_ok_fn         # (nom, taille) → ce fichier mérite-t-il qu'on lise son texte ?
        self.content_fn = content_fn      # → faut-il indexer le contenu des documents ?
        self.fts = True
        self.ready = False                # un premier passage complet a eu lieu : la recherche peut s'y fier
        self.roots: list[str] = []
        self.stats = {"fichiers": 0, "dossiers": 0, "textes": 0, "a_lire": 0, "passage": 0.0, "duree": 0.0,
                      "etat": "démarrage"}
        self._dirty: set[str] = set()
        self._asks: list[tuple[str, threading.Event]] = []  # « vérifie ce dossier avant que je cherche dedans »
        self._fresh: dict[str, float] = {}  # dossier → heure de son dernier passage (lui et ses sous-dossiers)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._flushed = threading.Event()  # les dossiers signalés par touch() ont été relus
        self._flushed.set()
        self._stop = False
        self._rebuild = False
        self._thread = None
        self._local = threading.local()

    # ── base ──
    def _db(self) -> sqlite3.Connection:
        c = getattr(self._local, "db", None)
        if c is None:
            c = sqlite3.connect(self.db_path, timeout=30)
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.db = c
        return c

    def _init(self) -> None:
        db = self._db()
        try:
            v = db.execute("SELECT v FROM meta WHERE k='schema'").fetchone()
        except sqlite3.DatabaseError:
            v = None
        if v is None or v[0] != str(SCHEMA):
            for t in ("meta", "dirs", "files", "contenu"):
                db.execute(f"DROP TABLE IF EXISTS {t}")
            db.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
            db.execute("CREATE TABLE dirs(path TEXT PRIMARY KEY, mtime INTEGER, vu INTEGER)")
            db.execute("CREATE TABLE files(id INTEGER PRIMARY KEY, dir TEXT NOT NULL, name TEXT NOT NULL, "
                       "pli TEXT NOT NULL, is_dir INTEGER NOT NULL, size INTEGER, mtime REAL, "
                       "texte INTEGER NOT NULL DEFAULT 0, UNIQUE(dir, name))")
            db.execute("CREATE INDEX files_texte ON files(texte) WHERE texte = 0")
            db.execute("INSERT INTO meta VALUES('schema', ?)", (str(SCHEMA),))
            db.commit()
        try:
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS contenu USING "
                       "fts5(corps, tokenize='unicode61 remove_diacritics 2')")
            db.commit()
        except sqlite3.OperationalError:
            self.fts = False  # SQLite sans recherche plein texte : on se passe de l'index du contenu
        row = db.execute("SELECT v FROM meta WHERE k='complet'").fetchone()
        self.ready = bool(row) and row[0] == "|".join(self._roots())
        self._count()

    def _roots(self) -> list[str]:
        try:
            roots = [os.path.realpath(r) for r in self.roots_fn()]
        except Exception:  # noqa: BLE001
            roots = []
        out = []
        for r in sorted(set(roots), key=len):  # un dossier contenu dans un autre n'est pas parcouru deux fois
            if os.path.isdir(r) and not any(r == o or r.startswith(o.rstrip("/") + "/") for o in out):
                out.append(r)
        return out

    def _count(self) -> None:
        db = self._db()
        f = db.execute("SELECT COUNT(*), SUM(is_dir), SUM(texte = 1), SUM(texte = 0 AND is_dir = 0) FROM files").fetchone()
        self.stats.update(fichiers=(f[0] or 0) - (f[1] or 0), dossiers=f[1] or 0, textes=f[2] or 0,
                          a_lire=(f[3] or 0) if (self.fts and self.content_fn()) else 0)

    # ── cycle de vie ──
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="index", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    def touch(self, *dirs: str) -> None:
        """Ces dossiers viennent de changer : à relire tout de suite."""
        with self._lock:
            self._dirty.update(d for d in dirs if d)
            self._flushed.clear()
        self._wake.set()

    def refresh(self, base: str, timeout: float = 1.5, max_age: float = 3) -> bool:
        """Passage léger sur ce dossier et ses sous-dossiers, avant une recherche : ce qui vient d'être créé,
        renommé ou supprimé (même en dehors d'Archiviste) est pris en compte. Attend au plus « timeout »
        secondes ; faux si ce n'était pas fini (la recherche se fait alors sur l'index tel qu'il est).
        Rien à faire si ce dossier (ou un dossier qui le contient) vient d'être vérifié."""
        now = time.time()
        for d, t in list(self._fresh.items()):
            if now - t <= max_age and (base == d or base.startswith(d.rstrip("/") + "/")):
                return True
        done = threading.Event()
        with self._lock:
            self._asks.append((base, done))
        self._wake.set()
        return done.wait(timeout)

    def rebuild(self) -> None:
        """Repart de zéro (bouton « Reconstruire l'index »)."""
        self._rebuild = True
        self.ready = False
        self._wake.set()

    def _run(self) -> None:
        try:
            self._init()
        except sqlite3.DatabaseError:  # base abîmée : on la refait
            try:
                self._local.db = None
                os.unlink(self.db_path)
                self._init()
            except (OSError, sqlite3.DatabaseError):
                self.stats["etat"] = "indisponible"
                return
        last_light = 0.0
        try:  # le dernier passage complet est retenu : à l'ouverture, un passage léger suffit
            last_full = float(self._meta("plein") or 0)
        except (TypeError, ValueError):
            last_full = 0.0
        while not self._stop:
            try:
                now = time.time()
                if self._rebuild:
                    self._rebuild = False
                    db = self._db()
                    for t in ("dirs", "files"):
                        db.execute(f"DELETE FROM {t}")
                    if self.fts:
                        db.execute("DELETE FROM contenu")
                    db.execute("DELETE FROM meta WHERE k='complet'")
                    db.commit()
                    last_light = last_full = 0.0
                roots = self._roots()
                if roots != self.roots:  # dossiers autorisés modifiés dans les réglages
                    self.roots = roots
                    self.ready = self.ready and self._meta("complet") == "|".join(roots)
                    last_light = last_full = 0.0
                if not self.ready or now - last_full >= FULL_EVERY:
                    self._scan(full=True)
                    last_full = last_light = time.time()
                    db = self._db()
                    db.execute("INSERT INTO meta(k, v) VALUES('plein', ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                               (str(last_full),))
                    db.commit()
                elif now - last_light >= LIGHT_EVERY:
                    self._scan(full=False)
                    last_light = time.time()
                with self._lock:
                    dirty, self._dirty = self._dirty, set()
                    asks, self._asks = self._asks, []
                if dirty:
                    self._scan_dirs(dirty)
                with self._lock:
                    if not self._dirty:
                        self._flushed.set()
                for base, done in asks:
                    try:
                        if self.ready and any(base == r or base.startswith(r.rstrip("/") + "/") for r in self.roots):
                            self._scan(full=False, base=base)
                    finally:
                        done.set()
                more = self._read_texts()
                self.stats["etat"] = "lecture des documents" if more else "à jour"
                if not more and not self._dirty and not self._asks and not self._rebuild:
                    self._wake.wait(30)
                self._wake.clear()
            except Exception as e:  # noqa: BLE001 — l'index ne doit jamais faire tomber l'appli
                self.stats["etat"] = f"erreur : {e}"
                self._local.db = None
                self._wake.wait(60)
                self._wake.clear()

    def _meta(self, k: str):
        row = self._db().execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return row[0] if row else None

    # ── parcours ──
    def _keep(self, name: str) -> bool:
        return not name.startswith(".") and name not in self.skip

    def _list_dir(self, db, d: str, gen: int) -> list[str]:
        """Relit un dossier : ajoute, met à jour et retire ses éléments dans l'index. Renvoie ses sous-dossiers."""
        try:
            st = os.stat(d)
            entries = []
            with os.scandir(d) as it:
                for e in it:
                    if not self._keep(e.name):
                        continue
                    try:
                        is_dir = e.is_dir(follow_symlinks=False)
                        es = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    entries.append((e.name, is_dir, es.st_size, es.st_mtime))
        except OSError:
            self._drop_tree(db, d)
            return []
        old = {r[0]: r for r in db.execute("SELECT name, id, is_dir, size, mtime FROM files WHERE dir=?", (d,))}
        seen = set()
        for name, is_dir, size, mtime in entries:
            seen.add(name)
            o = old.get(name)
            if o is None:
                db.execute("INSERT INTO files(dir, name, pli, is_dir, size, mtime, texte) VALUES(?,?,?,?,?,?,?)",
                           (d, name, self.fold(name), int(is_dir), size, mtime, 2 if is_dir else 0))
            elif o[2] != int(is_dir) or o[3] != size or o[4] != mtime:
                db.execute("UPDATE files SET is_dir=?, size=?, mtime=?, texte=? WHERE id=?",
                           (int(is_dir), size, mtime, 2 if is_dir else 0, o[1]))
                if self.fts:
                    db.execute("DELETE FROM contenu WHERE rowid=?", (o[1],))
        for name, o in old.items():
            if name not in seen:
                db.execute("DELETE FROM files WHERE id=?", (o[1],))
                if self.fts:
                    db.execute("DELETE FROM contenu WHERE rowid=?", (o[1],))
                if o[2]:
                    self._drop_tree(db, os.path.join(d, name))
        db.execute("INSERT INTO dirs(path, mtime, vu) VALUES(?,?,?) ON CONFLICT(path) DO UPDATE SET mtime=excluded.mtime, vu=excluded.vu",
                   (d, st.st_mtime_ns, gen))
        return [n for n, is_dir, _, _ in entries if is_dir]

    def _drop_tree(self, db, d: str) -> None:
        lo, hi = d.rstrip("/") + "/", d.rstrip("/") + "0"
        if self.fts:
            db.execute("DELETE FROM contenu WHERE rowid IN (SELECT id FROM files WHERE dir=? OR (dir>=? AND dir<?))", (d, lo, hi))
        db.execute("DELETE FROM files WHERE dir=? OR (dir>=? AND dir<?)", (d, lo, hi))
        db.execute("DELETE FROM dirs WHERE path=? OR (path>=? AND path<?)", (d, lo, hi))

    def _scan(self, full: bool, base: str | None = None) -> None:
        """Passage sur tous les dossiers (ou seulement sur « base » et ses sous-dossiers). Léger : un dossier
        dont la date n'a pas changé n'est pas relu (créer, supprimer ou renommer un élément change la date du
        dossier). Complet : tout est relu, donc les tailles et les dates des fichiers aussi."""
        t0 = time.time()
        db = self._db()
        gen = int(t0 * 1000)
        if base is None:
            self.stats["etat"] = "premier passage" if not self.ready else "mise à jour"
            where, args = "", ()
        else:
            lo, hi = base.rstrip("/") + "/", base.rstrip("/") + "0"
            where, args = " AND ({0}=? OR ({0}>=? AND {0}<?))", (base, lo, hi)
        # ce que l'index connaît déjà, chargé d'un coup : le passage léger ne coûte qu'un « stat » par dossier
        known = dict(db.execute("SELECT path, mtime FROM dirs WHERE 1" + where.format("path"), args))
        children: dict[str, list[str]] = {}
        for d, name in db.execute("SELECT dir, name FROM files WHERE is_dir=1" + where.format("dir"), args):
            children.setdefault(d, []).append(name)
        visited = set()
        n = 0
        for root in ([base] if base else self.roots):
            stack = [root]
            while stack and not self._stop:
                d = stack.pop()
                try:
                    mt = os.stat(d).st_mtime_ns
                except OSError:
                    continue  # disparu : retiré plus bas avec tout ce qu'il contenait
                visited.add(d)
                if known.get(d) == mt and not full:
                    subs = children.get(d, [])
                else:
                    subs = self._list_dir(db, d, gen)
                    n += 1
                    if n % 400 == 0:
                        db.commit()
                        if base is None:
                            self._count()
                stack.extend(os.path.join(d, x) for x in subs)
        if self._stop:
            return
        # dossiers disparus, ou qui ne font plus partie des dossiers autorisés
        for d in sorted(p for p in known if p not in visited):
            self._drop_tree(db, d)
        if base is None:
            db.execute("INSERT INTO meta(k, v) VALUES('complet', ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                       ("|".join(self.roots),))
        db.commit()
        if base is None:
            self.ready = True
            self.stats.update(passage=time.time(), duree=round(time.time() - t0, 2))
        if len(self._fresh) > 40:
            self._fresh.clear()
        for d in ([base] if base else self.roots):
            self._fresh[d] = time.time()
        self._count()

    def _inside(self, d: str) -> bool:
        """Ce dossier est-il indexé : dans un dossier autorisé, sans passer par un dossier caché ou ignoré ?"""
        for r in self.roots:
            if d == r:
                return True
            if d.startswith(r.rstrip("/") + "/"):
                return all(self._keep(part) for part in d[len(r):].strip("/").split("/"))
        return False

    def _scan_dirs(self, dirs) -> None:
        """Relit tout de suite ces dossiers. Un sous-dossier encore inconnu (créé ou déplacé là) est parcouru
        à son tour."""
        db = self._db()
        gen = int(time.time() * 1000)
        for d in sorted({os.path.realpath(x) for x in dirs}):
            if not self._inside(d):
                continue
            stack = [d]
            while stack:
                cur = stack.pop()
                for sub in self._list_dir(db, cur, gen):
                    p = os.path.join(cur, sub)
                    if not db.execute("SELECT 1 FROM dirs WHERE path=?", (p,)).fetchone():
                        stack.append(p)
        db.commit()
        self._count()

    # ── texte des documents ──
    def _read_texts(self) -> bool:
        """Lit le texte de quelques documents pas encore lus. Vrai s'il en reste."""
        if not self.fts or not self.content_fn():
            return False
        db = self._db()
        rows = db.execute("SELECT id, dir, name, size FROM files WHERE texte=0 AND is_dir=0 LIMIT ?", (TEXT_SLICE,)).fetchall()
        for fid, d, name, size in rows:
            if self._stop or self._dirty or self._asks or self._rebuild:  # une recherche attend : elle passe avant
                break
            state = 2
            if self.text_ok(name, size or 0):
                try:
                    txt, _ = self.text_fn(os.path.join(d, name), TEXT_MAX)
                except Exception:  # noqa: BLE001
                    txt = None
                if txt and txt.strip():
                    db.execute("INSERT OR REPLACE INTO contenu(rowid, corps) VALUES(?, ?)", (fid, txt))
                    state = 1
                time.sleep(0.005)  # reste discret : l'appli et le modèle passent avant
            db.execute("UPDATE files SET texte=? WHERE id=?", (state, fid))
        db.commit()
        self._count()
        return bool(db.execute("SELECT 1 FROM files WHERE texte=0 AND is_dir=0 LIMIT 1").fetchone())

    # ── recherche ──
    def covers(self, path: str) -> bool:
        return self.ready and any(path == r or path.startswith(r.rstrip("/") + "/") for r in self.roots)

    @staticmethod
    def _like(text: str) -> str:
        return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def search(self, base: str, query: str, contenu: bool = False, limit: int = 300) -> dict:
        """→ {"noms": [(chemin, est_dossier)], "textes": [(chemin, extrait)], "coupe": bool, "a_lire": n}.
        Sans joker : le nom contient la recherche. Avec * ou ? : le nom entier correspond au motif."""
        if not self._flushed.is_set():  # un fichier vient d'être modifié dans Archiviste : on laisse l'index le voir
            self._flushed.wait(0.6)
        db = self._db()
        q = self.fold(query.strip())
        if "*" in q or "?" in q:
            pat = self._like(q).replace("*", "%").replace("?", "_")
            exact = prefix = pat
        else:
            exact, prefix, pat = self._like(q), self._like(q) + "%", "%" + self._like(q) + "%"
        lo, hi = base.rstrip("/") + "/", base.rstrip("/") + "0"
        rows = db.execute(
            "SELECT dir, name, is_dir FROM files WHERE pli LIKE ? ESCAPE '\\' AND (dir=? OR (dir>=? AND dir<?)) "
            "ORDER BY (pli LIKE ? ESCAPE '\\') DESC, (pli LIKE ? ESCAPE '\\') DESC, is_dir DESC, mtime DESC LIMIT ?",
            (pat, base, lo, hi, exact, prefix, limit + 1)).fetchall()
        cut = len(rows) > limit
        names = [(os.path.join(d, n), bool(is_dir)) for d, n, is_dir in rows[:limit]]
        texts = []
        if contenu and self.fts and not ("*" in q or "?" in q):
            words = [w for w in query.replace('"', " ").split() if w]
            if words:
                match = '"' + " ".join(words) + '" *'  # la suite de mots, le dernier pouvant être un début de mot
                try:
                    found = db.execute(
                        "SELECT f.dir, f.name, snippet(contenu, 0, '', '', '…', 18) FROM contenu JOIN files f ON f.id = contenu.rowid "
                        "WHERE contenu MATCH ? AND (f.dir=? OR (f.dir>=? AND f.dir<?)) ORDER BY rank LIMIT ?",
                        (match, base, lo, hi, limit + 1)).fetchall()
                except sqlite3.OperationalError:
                    found = []
                cut = cut or len(found) > limit
                seen = {p for p, _ in names}
                texts = [(os.path.join(d, n), " ".join(str(s).split())) for d, n, s in found[:limit]
                         if os.path.join(d, n) not in seen]
        return {"noms": names, "textes": texts, "coupe": cut, "a_lire": self.stats["a_lire"] if contenu else 0}

    def status(self) -> dict:
        return {**self.stats, "pret": self.ready, "contenu": bool(self.fts and self.content_fn()),
                "plein_texte": self.fts, "dossiers_indexes": list(self.roots)}
