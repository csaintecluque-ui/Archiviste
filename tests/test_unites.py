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

print(f"\n{'TOUT EST BON' if not fails else str(fails) + ' ÉCHEC(S)'}")
sys.exit(1 if fails else 0)
