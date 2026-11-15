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

print("— index de recherche")
import indexeur  # noqa: E402
import shutil  # noqa: E402
ibase = HOME + "/Documents/index-essai"
shutil.rmtree(ibase, ignore_errors=True)
os.makedirs(ibase + "/Factures/2026")
os.makedirs(ibase + "/.cache-secret")
os.makedirs(ibase + "/node_modules/paquet")
open(ibase + "/Factures/2026/Facture EDF février.txt", "w").write("Montant à régler : 84,20 euros avant le 15 mars.")
open(ibase + "/Factures/contrat_assurance.md", "w").write("# Contrat\nNuméro de police AB-4471, résiliation possible à échéance.")
open(ibase + "/photo_vacances.jpg", "wb").write(b"\xff\xd8\xff")
open(ibase + "/.cache-secret/cache.txt", "w").write("x")
open(ibase + "/node_modules/paquet/index.js", "w").write("x")
ix = indexeur.Indexeur(HOME + "/.unites/index-essai.sqlite", lambda: [ibase], A.SKIP_DIRS, A.extract_text, A._fold, A.index_text_ok)
ix._init()
ix.roots = ix._roots()
ix._scan(full=True)
while ix._read_texts():
    pass
names = lambda q, **k: sorted(os.path.basename(p) for p, _ in ix.search(ibase, q, **k)["noms"])  # noqa: E731
check(ix.ready and ix.stats["fichiers"] == 3 and ix.stats["dossiers"] == 2, f"dossiers cachés et ignorés laissés de côté ({ix.stats['fichiers']} fichiers, {ix.stats['dossiers']} dossiers)")
check(names("fevrier") == ["Facture EDF février.txt"] and names("FACTURE") == ["Facture EDF février.txt", "Factures"], "recherche sans accents ni majuscules")
check(names("*.md") == ["contrat_assurance.md"] and names("contrat_assuranc?.md") == ["contrat_assurance.md"] and names("100%") == [], "jokers ; un « % » tapé reste un caractère ordinaire")
check([os.path.basename(p) for p, _ in ix.search(ibase, "factur")["noms"]][0] == "Factures", "le nom qui commence par la recherche passe d'abord")
t = ix.search(ibase, "police ab-4471", contenu=True)["textes"]
check(len(t) == 1 and t[0][0].endswith("contrat_assurance.md") and "AB-4471" in t[0][1], f"recherche dans le texte des documents, avec extrait ({t})")
check(ix.search(ibase, "regler", contenu=True)["textes"] and not ix.search(ibase + "/Factures/2026", "police", contenu=True)["textes"], "contenu sans accents ; limité au dossier demandé")
os.rename(ibase + "/Factures", ibase + "/Papiers")
open(ibase + "/nouveau.txt", "w").write("x")
os.unlink(ibase + "/photo_vacances.jpg")
ix._scan(full=False)
check(names("nouveau") == ["nouveau.txt"] and names("vacances") == [] and names("Factures") == []
      and [p for p, _ in ix.search(ibase, "edf")["noms"]] == [ibase + "/Papiers/2026/Facture EDF février.txt"],
      "passage léger : ajout, suppression et dossier renommé pris en compte")
open(ibase + "/Papiers/contrat_assurance.md", "w").write("# Contrat\nNouvelle police ZZ-9000 depuis janvier.")
ix._scan_dirs([ibase + "/Papiers"])
while ix._read_texts():
    pass
check(ix.search(ibase, "zz-9000", contenu=True)["textes"] and not ix.search(ibase, "ab-4471", contenu=True)["textes"], "fichier modifié : son texte est relu, l'ancien oublié")
ix.roots_fn = lambda: [ibase + "/Papiers"]
ix.roots = ix._roots()
ix._scan(full=True)
check(names("nouveau") == [] and not ix.covers(ibase) and ix.covers(ibase + "/Papiers/2026"), "dossier retiré des dossiers autorisés : il sort de l'index")
shutil.rmtree(ibase, ignore_errors=True)

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
g = {x["cle"]: x for x in A.window_groups()["groupes"]}["app:editeur-essai.desktop"]
check([w["id"] for w in g["fenetres"]] == [1, 3] and all(w["reduit"] for w in g["fenetres"]), "fenêtres d'une appli listées une à une")
r = A.window_action("app:editeur-essai.desktop", "afficher", fenetre=3)
check(r["ouverte"] and suivi.asked[-1] == ([3], "afficher"), "ramener une seule fenêtre d'une appli")
check(not A.window_action("app:editeur-essai.desktop", "afficher", fenetre=2)["ouverte"], "fenêtre d'une autre appli : refusée")
A.WINDOWS_HOOK = None

print(f"\n{'TOUT EST BON' if not fails else str(fails) + ' ÉCHEC(S)'}")
sys.exit(1 if fails else 0)
