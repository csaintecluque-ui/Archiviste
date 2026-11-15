"""Tests directs de quelques fonctions du serveur (sans passer par le réseau)."""
import os, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import archiviste as A  # noqa: E402

HOME = os.environ["HOME"]
fails = 0


def check(cond, label):
    global fails
    print(("  ok  " if cond else "  ÉCHEC ") + label)
    if not cond:
        fails += 1


print("— fonctions")
base = HOME + "/Documents/gros"
for d in range(40):
    os.makedirs(f"{base}/d{d:02d}", exist_ok=True)
    for f in range(50):
        open(f"{base}/d{d:02d}/fichier{f}.txt", "w").close()
open(f"{base}/d39/zz-cible.txt", "w").close()
r = A.fs_search(base, "zz-cible", False)
check(len(r["results"]) == 1 and r["incomplet"] is None, "recherche menée jusqu'au bout")
r = A.fs_search(base, "zz-cible", False, delay=0)
check(not r["results"] and r["incomplet"] == "temps" and r["tronque"], "recherche arrêtée par le temps : signalée")
etat = {}
n = sum(1 for _ in A.walk_files(base, False, 100, etat=etat))
check(n == 100 and etat.get("coupe") == "limite", "parcours coupé à la limite : signalé")
etat = {}
n = sum(1 for _ in A.walk_files(f"{base}/d00", False, 50, etat=etat))
check(n == 50 and not etat, "parcours complet pile à la limite : rien à signaler")
os.symlink(base, HOME + "/Documents/lien-gros")
check(A.lexical_path(HOME + "/Documents/lien-gros") == HOME + "/Documents/lien-gros"
      and A.safe_path(HOME + "/Documents/lien-gros") == os.path.realpath(base), "un lien se désigne lui-même ou sa cible, au choix")
os.unlink(HOME + "/Documents/lien-gros")
c = {"modifie": "2020-01-01T00:00:00"}
check(A.conv_idle_hours(c) > 1000 and A.conv_idle_hours({"modifie": A.now_iso()}) < 1, "durée d'inactivité d'une discussion")

print("— fenêtres ouvertes (dock du volet)")


def app(aid, name, exe, wmclass=""):
    e = {"Name": name, "Exec": exe, "Type": "Application"}
    if wmclass:
        e["StartupWMClass"] = wmclass
    return A.app_info(aid, "/usr/share/applications/" + aid, e)


APPS = [app("firefox.desktop", "Firefox", "firefox %u"),
        app("webapp-Gmail1234.desktop", "Gmail", "firefox --class WebApp-Gmail1234 --profile x https://mail.example", "WebApp-Gmail1234"),
        app("org.gnome.Terminal.desktop", "Terminal", "gnome-terminal"),
        app("libreoffice-writer.desktop", "LibreOffice Writer", "libreoffice --writer %U", "libreoffice-writer"),
        app("libreoffice-calc.desktop", "LibreOffice Calc", "libreoffice --calc %U", "libreoffice-calc"),
        app("nemo.desktop", "Fichiers", "nemo %U"),
        app("claude-desktop.desktop", "Claude", "claude-desktop %u"),
        app("org.mozilla.Thunderbird.desktop", "Thunderbird", "/usr/bin/flatpak run --command=thunderbird org.mozilla.Thunderbird")]


def owner(cls, inst):
    a = A.window_app({"cls": cls, "inst": inst, "pid": 0}, APPS)
    return a["id"] if a else None


cases = [("firefox", "Navigator", "firefox.desktop"), ("WebApp-Gmail1234", "Navigator", "webapp-Gmail1234.desktop"),
         ("Gnome-terminal", "gnome-terminal-server", "org.gnome.Terminal.desktop"),
         ("libreoffice-calc", "libreoffice", "libreoffice-calc.desktop"), ("Nemo", "nemo", "nemo.desktop"),
         ("Claude", "claude", "claude-desktop.desktop"), ("thunderbird", "Mail", "org.mozilla.Thunderbird.desktop"),
         ("Xmessage", "xmessage", None), ("", "", None)]
bad = [(c, i, owner(c, i), want) for c, i, want in cases if owner(c, i) != want]
check(not bad, f"chaque fenêtre est rattachée à la bonne appli ({bad or len(cases)})")


class FauxSuivi:
    """Remplace le suivi GTK : une liste de fenêtres, et la mémoire de ce qu'on lui demande."""
    def __init__(self, wins):
        self.version, self.wins, self.asked = 1, wins, []

    def snapshot(self):
        return list(self.wins)

    def act(self, xids, action):
        self.asked.append((list(xids), action))


check(A.window_groups() == {"dispo": False, "groupes": [], "sig": ""} and not A.raise_app("x.desktop")
      and A.window_action("app:x.desktop", "basculer")["ouverte"] is False, "sans suivi des fenêtres : tout marche comme avant")
os.makedirs(HOME + "/.local/share/applications", exist_ok=True)
open(HOME + "/.local/share/applications/editeur-essai.desktop", "w").write(
    "[Desktop Entry]\nType=Application\nName=Éditeur d'essai\nExec=editeur-essai %F\nIcon=editeur\n")
w = lambda xid, cls, reduit=False, soi=False, titre="": {"xid": xid, "titre": titre or cls, "cls": cls, "inst": cls.lower(),  # noqa: E731
                                                          "pid": 0, "reduit": reduit, "soi": soi}
suivi = FauxSuivi([w(1, "Editeur-essai", titre="notes.md"), w(2, "Xmessage"), w(3, "Editeur-essai", reduit=True), w(4, "archiviste", soi=True, reduit=True)])
A.WINDOWS_HOOK = suivi
g = {x["cle"]: x for x in A.window_groups()["groupes"]}
ed = g.get("app:editeur-essai.desktop", {})
check(list(g) == ["app:editeur-essai.desktop", "win:xmessage", "archiviste"] and ed.get("n") == 2 and ed.get("devant")
      and not ed.get("reduit") and ed.get("nom") == "Éditeur d'essai" and "xids" not in ed, f"fenêtres regroupées par appli ({list(g)})")
check(g["archiviste"]["reduit"] and not g["archiviste"]["devant"] and g["win:xmessage"]["app"] is None, "fenêtre d'Archiviste et appli inconnue reconnues")
r = A.window_action("app:editeur-essai.desktop", "basculer")
check(r["action"] == "reduire" and suivi.asked[-1] == ([1, 3], "reduire"), "clic sur une appli devant : elle est réduite")
r = A.window_action("win:xmessage", "basculer")
check(r["action"] == "afficher" and suivi.asked[-1] == ([2], "afficher"), "clic sur une appli derrière : elle revient devant")
suivi.wins = [w(2, "Xmessage"), w(1, "Editeur-essai", reduit=True), w(3, "Editeur-essai", reduit=True)]
r = A.window_action("app:editeur-essai.desktop", "basculer")
check(r["action"] == "afficher" and suivi.asked[-1] == ([1, 3], "afficher"), "clic sur une appli réduite : elle revient devant")
n = len(suivi.asked)
check(A.raise_app("editeur-essai.desktop") and suivi.asked[-1][1] == "afficher" and not A.raise_app("absente.desktop")
      and len(suivi.asked) == n + 1, "« ouvre X » : ramène une appli déjà ouverte, lance les autres")
check(A.window_action("app:absente.desktop", "basculer") == {"ok": False, "ouverte": False, "dispo": True}, "appli fermée entre-temps : signalée")
A.WINDOWS_HOOK = None

print(f"\n{'TOUT EST BON' if not fails else str(fails) + ' ÉCHEC(S)'}")
sys.exit(1 if fails else 0)
