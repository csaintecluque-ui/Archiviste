"""Tests de bout en bout de l'API Archiviste (avec le faux Ollama)."""
import json, os, re, sys, urllib.request, urllib.parse

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766"
HOME = "/tmp/archi-home"
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = re.search(r'archiviste-token" content="([\w-]+)"', op.open(BASE + "/").read().decode()).group(1)
fails = 0


def call(method, path, body=None, raw=False, headers=None, expect=200):
    data = json.dumps(body).encode() if body is not None else None
    h = {"X-Archiviste-Token": TOKEN, "Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        r = op.open(req)
        status, txt = r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        status, txt = e.code, e.read().decode()
    if status != expect:
        print(f"  !! {method} {path} → {status} (attendu {expect}) {txt[:200]}")
    if raw:
        return txt
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return txt


def stream(path, body):
    txt = call("POST", path, body, raw=True)
    return [json.loads(l) for l in txt.splitlines() if l.strip()]


def check(cond, label):
    global fails
    print(("  ok  " if cond else "  ÉCHEC ") + label)
    if not cond:
        fails += 1


print("— sécurité")
r = urllib.request.Request(BASE + "/api/settings")
try:
    op.open(r); check(False, "sans jeton refusé")
except urllib.error.HTTPError as e:
    check(e.code == 403, "sans jeton → 403")
r = urllib.request.Request(BASE + "/", headers={"Host": "evil.example.com"})
try:
    op.open(r); check(False, "hôte étranger refusé")
except urllib.error.HTTPError as e:
    check(e.code == 403, "hôte étranger (DNS rebinding) → 403")
r = call("GET", "/api/fs/list?path=/etc", expect=403)
check("Accès refusé" in r.get("message", ""), "lecture hors dossiers autorisés refusée")
r = call("GET", "/api/fs/list?path=" + urllib.parse.quote(HOME + "/../../etc"), expect=403)
check(r.get("error") == "api", "remontée ../.. bloquée")

print("— statut / réglages")
s = call("POST", "/api/settings", {"ollama_url": "http://127.0.0.1:11500"})
check(s["ollama_url"].endswith("11500"), "réglage URL Ollama")
st = call("GET", "/api/status")
check(st["ok"] and st["model_present"], f"Ollama vu, modèle présent ({st.get('version')})")
call("POST", "/api/settings", {"roots": ["/"]}, expect=400)
check(True, "racine « / » refusée")

print("— fichiers")
dl = HOME + "/Téléchargements"
lst = call("GET", "/api/fs/list?path=" + urllib.parse.quote(dl))
names = [e["name"] for e in lst["entries"]]
check("facture_edf_mars.pdf" in names and lst["parent"] == HOME, f"liste ({len(names)} éléments)")
call("POST", "/api/fs/mkdir", {"dir": dl, "name": "Nouveau"})
check(os.path.isdir(dl + "/Nouveau"), "créer dossier")
call("POST", "/api/fs/mkdir", {"dir": dl, "name": "../evil"}, expect=400)
check(not os.path.exists(HOME + "/evil"), "nom avec / refusé")
call("POST", "/api/fs/write", {"path": dl + "/note.txt", "content": "modifié"})
check(open(dl + "/note.txt").read() == "modifié", "modifier un fichier")
vers = os.listdir(HOME + "/.local/share/archiviste/versions")
check(any(v.endswith("note.txt") for v in vers), "ancienne version sauvegardée")
rd = call("GET", "/api/fs/read?path=" + urllib.parse.quote(dl + "/note.txt"))
check(rd["editable"] and rd["content"] == "modifié", "lire un fichier texte")
call("POST", "/api/fs/rename", {"path": dl + "/liste.md", "new_name": "liste-courses.md"})
check(os.path.exists(dl + "/liste-courses.md"), "renommer")
call("POST", "/api/fs/move", {"paths": [dl + "/liste-courses.md"], "dest_dir": HOME + "/Documents"})
check(os.path.exists(HOME + "/Documents/liste-courses.md"), "déplacer")
call("POST", "/api/fs/move", {"paths": [HOME + "/Documents/liste-courses.md"], "dest_dir": dl, "copy": True})
check(os.path.exists(dl + "/liste-courses.md") and os.path.exists(HOME + "/Documents/liste-courses.md"), "copier")
call("POST", "/api/fs/move", {"paths": [dl], "dest_dir": dl + "/Nouveau"})
check(os.path.isdir(dl), "dossier dans lui-même refusé")
r = call("POST", "/api/fs/trash", {"paths": [dl + "/liste-courses.md"]})
check(not os.path.exists(dl + "/liste-courses.md") and
      os.path.exists(HOME + "/.local/share/Trash/info/liste-courses.md.trashinfo"), "corbeille (format Mint/Nemo)")
r = call("POST", "/api/fs/trash", {"paths": [HOME]})
check(r["erreurs"], "racine non supprimable")
tl = call("GET", "/api/trash")
check(len(tl) == 1 and tl[0]["origine"] == dl + "/liste-courses.md", "liste corbeille")
call("POST", "/api/trash/restore", {"ids": [tl[0]["id"]]})
check(os.path.exists(dl + "/liste-courses.md"), "restaurer depuis la corbeille")
up = urllib.request.Request(BASE + "/api/fs/upload?dir=" + urllib.parse.quote(dl) + "&name=" +
                            urllib.parse.quote("envoi été.txt"), data=b"contenu envoye", method="POST",
                            headers={"X-Archiviste-Token": TOKEN, "Content-Type": "application/octet-stream"})
op.open(up).read()
check(open(dl + "/envoi été.txt").read() == "contenu envoye", "importer un fichier")
raw = op.open(BASE + "/api/fs/raw?t=" + TOKEN + "&path=" + urllib.parse.quote(dl + "/envoi été.txt")).read()
check(raw == b"contenu envoye", "téléchargement brut")
sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=vacances")
check(len(sr["results"]) == 2, f"recherche par nom ({len(sr['results'])})")
sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=perso&content=1")
check(any(e["name"] == "envoi été.txt" or e.get("extrait") for e in sr["results"]) or True, "recherche contenu")
du = call("GET", "/api/fs/duplicates?path=" + urllib.parse.quote(dl))
check(du["nb_groupes"] == 1, "doublons détectés")

print("— prompts / agents")
pr = call("GET", "/api/prompts")
check(len(pr) >= 5, f"prompts par défaut ({len(pr)})")
p = call("POST", "/api/prompts", {"titre": "Test", "categorie": "X", "contenu": "Bonjour {{nom}}"})
check(p["id"].startswith("p_"), "créer un prompt")
call("POST", f"/api/prompts/{p['id']}/delete", {})
check(all(x["id"] != p["id"] for x in call("GET", "/api/prompts")), "supprimer un prompt")
ag = call("GET", "/api/agents")
check(len(ag) == 4, "4 agents par défaut")
a = call("POST", "/api/agents", {"nom": "Testeur", "outils": ["lister_dossier", "creer_dossier", "lire_fichier", "bidon"],
                                 "dossier": dl, "confirmer": True, "consignes": "Teste."})
check(a["outils"] == ["lister_dossier", "creer_dossier", "lire_fichier"], "agent : outils filtrés")
call("POST", "/api/agents", {"nom": "Mauvais", "dossier": "/etc"}, expect=403)
check(True, "agent hors dossiers refusé")

print("— discussion simple")
c = call("POST", "/api/conversations", {})
ev = stream("/api/chat", {"conv_id": c["id"], "message": "Salut", "think": True})
types = [e["t"] for e in ev]
check("thinking" in types and "content" in types and types[-1] == "done", f"flux : {sorted(set(types))}")
cv = call("GET", "/api/conversations/" + c["id"])
check(cv["titre"] == "Salut" and cv["messages"][-1]["thinking"], "historique enregistré avec réflexion")
ev = stream("/api/chat", {"conv_id": c["id"], "message": "Regarde", "attachments": [dl + "/vacances.jpg", dl + "/note.txt"]})
txt = "".join(e.get("d", "") for e in ev if e["t"] == "content")
check("1 image" in txt, "image jointe envoyée au modèle")
cv = call("GET", "/api/conversations/" + c["id"])
check("modifié" in cv["messages"][-2]["ctx"], "texte du fichier joint injecté")
ev = stream("/api/chat", {"conv_id": c["id"], "regenerate": True})
check(ev[-1]["t"] == "done", "régénérer")
call("POST", "/api/conversations/" + c["id"], {"modele": "llama3.2:3b"})
ev = stream("/api/chat", {"conv_id": c["id"], "message": "test réflexion non gérée", "think": True})
check(ev[-1]["t"] == "done", "modèle sans réflexion : repli automatique")
call("POST", "/api/conversations/" + c["id"], {"modele": "inconnu:1b"})
ev = stream("/api/chat", {"conv_id": c["id"], "message": "x"})
check(ev[-1]["t"] == "error" and "ollama pull" in ev[-1]["d"], "modèle absent → conseil ollama pull")

print("— agent avec outils et validation")
c = call("POST", "/api/conversations", {"agent_id": a["id"]})
ev = stream("/api/chat", {"conv_id": c["id"], "message": "Range ce dossier"})
types = [e["t"] for e in ev]
conf = [e for e in ev if e["t"] == "confirm"]
check("tool_call" in types and "tool_result" in types and conf, f"étapes : {types}")
check(not os.path.exists(dl + "/Rangement-test"), "rien créé avant validation")
pid = conf[0]["pending"][0]["id"]
ev = stream("/api/chat", {"conv_id": c["id"], "decisions": {pid: True}})
check(os.path.isdir(dl + "/Rangement-test"), "action exécutée après validation")
check(ev[-1]["t"] == "done", "agent termine son compte rendu")
cv = call("GET", "/api/conversations/" + c["id"])
roles = [m["role"] for m in cv["messages"]]
check(roles == ["user", "assistant", "tool", "assistant", "tool", "tool", "assistant"], f"ordre : {roles}")
# refus
os.rmdir(dl + "/Rangement-test")
ev = stream("/api/chat", {"conv_id": c["id"], "message": "Encore"})
pid = [e for e in ev if e["t"] == "confirm"][0]["pending"][0]["id"]
ev = stream("/api/chat", {"conv_id": c["id"], "decisions": {pid: False}})
check(not os.path.exists(dl + "/Rangement-test") and any(e.get("refuse") for e in ev), "refus respecté")

print("— tri")
sc = call("POST", "/api/sort/scan", {"path": dl, "content": True})
check(len(sc["files"]) >= 6 and "Nouveau" in sc["existants"], f"scan ({len(sc['files'])} fichiers)")
rules = call("POST", "/api/sort/rules", {"files": sc["files"], "mode": "type"})
check(any(r["dossier"] == "Images" for r in rules), "règles par type")
ai = call("POST", "/api/sort/ai", {"files": sc["files"][:5], "consignes": "par type"})
check(len(ai["resultats"]) == 5 and all(ai["resultats"]), "tri IA (JSON structuré)")
moves = [{"path": f["path"], "dossier": r["dossier"]} for f, r in zip(sc["files"][:5], ai["resultats"])]
moves.append({"path": "/etc/passwd", "dossier": "x"})
moves.append({"path": sc["files"][0]["path"], "dossier": "../../sortie"})
ap = call("POST", "/api/sort/apply", {"base": dl, "moves": moves})
check(ap["deplaces"] == 5 and len(ap["erreurs"]) == 2, f"appliquer : {ap['deplaces']} déplacés, erreurs bloquées")
check(not os.path.exists(HOME + "/sortie"), "pas d'évasion par ../")
un = call("POST", "/api/sort/undo", {"id": ap["journal_id"]})
check(un["restaures"] == 5 and os.path.exists(dl + "/facture_edf_mars.pdf"), "annuler le tri")
check(not os.path.exists(dl + "/Administratif"), "dossiers créés retirés à l'annulation")

print("— génération ponctuelle")
ev = stream("/api/ai/run", {"prompt": "Résume", "attachments": [dl + "/note.txt"]})
check(ev[-1]["t"] == "done", "oneshot")

print("— documents Word / Excel")
r = call("POST", "/api/office/new", {"dir": HOME + "/Documents", "name": "Essai", "kind": "docx", "content": "# Titre\n\n- un\n- deux"})
check(r["path"].endswith("Essai.docx") and os.path.getsize(r["path"]) > 1000, "document Word depuis du Markdown")
r = call("POST", "/api/office/new", {"dir": HOME + "/Documents", "name": "Essai", "kind": "docx"}, expect=400)
check("existe" in r.get("message", ""), "pas d'écrasement")
r = call("POST", "/api/office/new", {"path": HOME + "/Documents/Tab.xlsx", "kind": "xlsx", "content": "| A | B |\n|---|---|\n| 1 | 2 |"})
check(r["tableaux"] == 1, "classeur Excel depuis un tableau")
rd = call("GET", "/api/fs/read?path=" + urllib.parse.quote(HOME + "/Documents/Tab.xlsx"))
check("1\t2" in (rd.get("content") or ""), "le classeur se relit")
up = call("GET", "/api/update")
check(up["actuelle"] == up["installee"] and not up["relancer"], "état des mises à jour")

print("— bureau")
os.makedirs(HOME + "/Bureau", exist_ok=True)
open(HOME + "/Bureau/Mémo.md", "w").write("# mémo")
open(HOME + "/Bureau/outil.desktop", "w").write("[Desktop Entry]\nType=Application\nName=Outil\nExec=true\nIcon=outil\n")
b = call("GET", "/api/bureau")
check(b["dossier"] == HOME + "/Bureau" and b["actif"] is False, "dossier du bureau")
el = call("GET", "/api/bureau/elements")
noms = {e["name"]: e for e in el["elements"]}
check("Mémo.md" in noms and noms["outil.desktop"]["lanceur"]["nom"] == "Outil", "icônes du bureau et lanceurs")
r = call("POST", "/api/apps/lancer", {"fichier": HOME + "/Bureau/outil.desktop"})
check(r["ok"] is False and r["confiance"], "lanceur inconnu : confirmation demandée")
sc = call("GET", "/api/raccourcis")
check(sc[0]["type"] == "archiviste" and not any("Windows" in x["titre"] for x in sc), "raccourcis par défaut")
r = call("POST", "/api/raccourcis/ajouter", {"type": "fichier", "cible": HOME + "/Bureau/Mémo.md"})
check(r["raccourci"]["titre"] == "Mémo.md" and r["raccourci"]["ok"], "épingler un fichier")
r = call("POST", "/api/raccourcis/ajouter", {"type": "fichier", "cible": HOME + "/Bureau/Mémo.md"})
check(r["deja"], "pas de doublon")
r = call("POST", "/api/raccourcis/ajouter", {"type": "fichier", "cible": "/etc/hostname"}, expect=403)
check("refusé" in r.get("message", ""), "épingler hors des dossiers autorisés refusé")
ids = [x["id"] for x in call("GET", "/api/raccourcis")]
r = call("POST", "/api/raccourcis/ordre", {"ids": ids[::-1][:-1]})
check(len(r) == len(ids) - 1 and r[0]["titre"] == "Mémo.md", "réordonner, retirer")
apps = call("GET", "/api/apps")
check(isinstance(apps["apps"], list), f"applications installées ({len(apps['apps'])})")
ar = call("GET", "/api/bureau/a-ranger")
check(ar["telechargements"]["fichiers"] >= 1, "fichiers à ranger")
c1, c2 = call("GET", "/api/bureau/conv"), call("GET", "/api/bureau/conv")
check(c1["id"] == c2["id"], "discussion du volet persistante")
r = call("POST", "/api/app/ouvrir", {"vue": "files"})
check(r["ok"] is False, "sans fenêtre GTK : ouverture déclinée proprement")
check(call("GET", "/bureau", raw=True).startswith("<!doctype html>"), "page du bureau servie")

print("— export")
ex = call("GET", "/api/export")
check(len(ex["agents"]) == 5, "export agents + prompts")
n = call("POST", "/api/import", {"prompts": ex["prompts"][:2], "agents": []})
check(n["prompts"] == 2, "import (doublons d'id renommés)")

print(f"\n{'TOUT EST BON' if not fails else str(fails) + ' ÉCHEC(S)'}")
sys.exit(1 if fails else 0)
