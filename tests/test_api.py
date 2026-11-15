"""Tests de bout en bout de l'API Archiviste (avec le faux Ollama)."""
import json, os, re, socket, sys, threading, time, urllib.request, urllib.parse

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
doc_dir = HOME + "/Documents"
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
r = call("POST", "/api/trash/restore", {"ids": ["n-existe-pas", tl[0]["id"]]})
check(os.path.exists(dl + "/liste-courses.md") and len(r["ok"]) == 1 and len(r["erreurs"]) == 1,
      "restaurer depuis la corbeille : un élément introuvable n'empêche pas les autres")

print("— versions précédentes, encodage")
note = dl + "/note.txt"
call("POST", "/api/fs/write", {"path": note, "content": "deuxième version"})
call("POST", "/api/fs/write", {"path": note, "content": "troisième version"})
vs = call("GET", "/api/fs/versions?path=" + urllib.parse.quote(note))
check(len(vs["versions"]) == 3 and vs["actuelle"]["taille"] == len("troisième version".encode()), f"anciennes versions listées ({len(vs['versions'])})")
txt = [call("GET", "/api/fs/versions/texte?id=" + urllib.parse.quote(v["id"]))["content"] for v in vs["versions"]]
check(txt == ["deuxième version", "modifié", "note perso\n"], f"de la plus récente à la plus ancienne, lisibles ({txt})")
r = call("POST", "/api/fs/versions/restaurer", {"id": vs["versions"][-1]["id"]})
vs2 = call("GET", "/api/fs/versions?path=" + urllib.parse.quote(note))
check(open(note).read() == "note perso\n" and r["sauvegarde"] and len(vs2["versions"]) == 4, "restaurer une version : l'état remplacé est gardé lui aussi")
call("GET", "/api/fs/versions/texte?id=" + urllib.parse.quote("../../settings.json"), expect=404)
call("POST", "/api/fs/write", {"path": note, "content": "modifié"})
old = dl + "/ancien.txt"
open(old, "wb").write("café crème\n".encode("latin-1"))
rd = call("GET", "/api/fs/read?path=" + urllib.parse.quote(old))
w = call("POST", "/api/fs/write", {"path": old, "content": rd["content"] + "thé\n", "encoding": rd["encoding"]})
check(rd["encoding"] == "latin-1" and w["encodage"] == "latin-1" and open(old, "rb").read() == "café crème\nthé\n".encode("latin-1"),
      "fichier latin-1 : il reste en latin-1 à l'enregistrement")
w = call("POST", "/api/fs/write", {"path": old, "content": "prix : 12 €\n", "encoding": "latin-1"})
check(w["encodage"] == "utf-8" and open(old, encoding="utf-8").read() == "prix : 12 €\n", "caractère absent du latin-1 : passage en UTF-8, annoncé")
os.unlink(old)
import base64
open("/tmp/archi-hors-racine.png", "wb").write(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="))
r = call("GET", "/api/icone?n=" + urllib.parse.quote("/tmp/archi-hors-racine.png"), expect=403)
check("autorisés" in r.get("message", ""), "image hors des dossiers autorisés : refusée par /api/icone")
os.makedirs(HOME + "/Bureau", exist_ok=True)
open(HOME + "/Bureau/perso.desktop", "w").write("[Desktop Entry]\nType=Application\nName=Perso\nExec=true\nIcon=/tmp/archi-hors-racine.png\n")
time.sleep(1.6)
png = op.open(BASE + "/api/icone?t=" + TOKEN + "&n=" + urllib.parse.quote("/tmp/archi-hors-racine.png")).read()
check(png[:4] == b"\x89PNG", "la même image servie quand c'est l'icône d'un lanceur du bureau")
os.unlink(HOME + "/Bureau/perso.desktop")
up = urllib.request.Request(BASE + "/api/fs/upload?dir=" + urllib.parse.quote(dl) + "&name=" +
                            urllib.parse.quote("envoi été.txt"), data=b"contenu envoye", method="POST",
                            headers={"X-Archiviste-Token": TOKEN, "Content-Type": "application/octet-stream"})
op.open(up).read()
check(open(dl + "/envoi été.txt").read() == "contenu envoye", "importer un fichier")
raw = op.open(BASE + "/api/fs/raw?t=" + TOKEN + "&path=" + urllib.parse.quote(dl + "/envoi été.txt")).read()
check(raw == b"contenu envoye", "téléchargement brut")
sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=vacances")
check(len(sr["results"]) == 2, f"recherche par nom ({len(sr['results'])})")
ix = call("GET", "/api/index")
for _ in range(60):
    if ix.get("pret") and not ix.get("a_lire"):
        break
    time.sleep(0.25)
    ix = call("GET", "/api/index")
sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=" + urllib.parse.quote("contenu envoye") + "&content=1")
check([e["name"] for e in sr["results"]] == ["envoi été.txt"] and sr["results"][0].get("extrait"), "recherche dans le contenu")
check(sr["incomplet"] is None and sr["tronque"] is False, "recherche complète : rien à signaler")
check(ix.get("pret") and ix["fichiers"] >= 5 and ix["plein_texte"], f"index de recherche prêt ({ix.get('fichiers')} fichiers, {ix.get('etat')})")
for i in range(30):
    open(f"{HOME}/Documents/lot-{i:02d}.txt", "w").write("x")
os.makedirs(HOME + "/Documents/lot-dossier", exist_ok=True)
sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=lot-")
check(sr.get("index") and sr["results"][0]["dir"] and len(sr["results"]) == 31,
      "recherche par l'index : des fichiers créés à l'instant hors d'Archiviste sont trouvés")
sr = call("GET", "/api/fs/search?rapide=1&path=" + urllib.parse.quote(HOME) + "&q=lot-")
check(len(sr["results"]) == 24 and sr["incomplet"] == "limite" and sr["tronque"], "recherche coupée : signalée (limite)")
sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=" + urllib.parse.quote("LOT-0?.TXT"))
check(len(sr["results"]) == 10, f"jokers et majuscules ({len(sr['results'])})")
call("POST", "/api/fs/write", {"path": doc_dir + "/Été à Biarritz.md", "content": "Réservation de l'hôtel Régina confirmée pour le quatorze juillet."})
sr = call("GET", "/api/fs/search?rapide=1&path=" + urllib.parse.quote(HOME) + "&q=ete")
check(any(e["name"] == "Été à Biarritz.md" for e in sr["results"]), "fichier créé dans Archiviste : trouvé tout de suite, sans accents")
for _ in range(40):
    sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=" + urllib.parse.quote("hotel regina") + "&content=1")
    if sr["results"]:
        break
    time.sleep(0.25)
hit = next((e for e in sr["results"] if e["name"] == "Été à Biarritz.md"), {})
check("Régina" in hit.get("extrait", ""), f"recherche dans le contenu par l'index, avec extrait ({hit.get('extrait')})")
call("POST", "/api/fs/trash", {"paths": [doc_dir + "/Été à Biarritz.md"]})
sr = call("GET", "/api/fs/search?rapide=1&path=" + urllib.parse.quote(HOME) + "&q=biarritz")
check(not sr["results"], "fichier mis à la corbeille : il sort de la recherche")
os.rename(HOME + "/Documents/lot-dossier", HOME + "/Documents/paquet-renomme")
sr = call("GET", "/api/fs/search?path=" + urllib.parse.quote(HOME) + "&q=renomme")
check([e["name"] for e in sr["results"]] == ["paquet-renomme"], "dossier renommé hors d'Archiviste : retrouvé sous son nouveau nom")
os.rename(HOME + "/Documents/paquet-renomme", HOME + "/Documents/lot-dossier")
du = call("GET", "/api/fs/duplicates?path=" + urllib.parse.quote(dl))
check(du["nb_groupes"] == 1 and du["incomplet"] is None, "doublons détectés")

print("— liens symboliques")
doc = HOME + "/Documents"
os.makedirs(doc + "/Projet", exist_ok=True)
open(doc + "/Projet/contrat.txt", "w").write("important")
open(doc + "/rapport.txt", "w").write("rapport")
os.makedirs(HOME + "/Bureau", exist_ok=True)
os.symlink(doc + "/Projet", HOME + "/Bureau/Lien Projet")
os.symlink("../Documents/rapport.txt", HOME + "/Bureau/lien-rapport.txt")  # lien relatif
os.symlink(doc + "/n-existe-pas", HOME + "/Bureau/lien-casse")
r = call("POST", "/api/fs/rename", {"path": HOME + "/Bureau/lien-rapport.txt", "new_name": "raccourci.txt"})
check(os.path.islink(HOME + "/Bureau/raccourci.txt") and os.path.exists(doc + "/rapport.txt"), "renommer un lien : la cible ne bouge pas")
r = call("POST", "/api/fs/move", {"paths": [HOME + "/Bureau/raccourci.txt"], "dest_dir": doc + "/Projet"})
moved = doc + "/Projet/raccourci.txt"
check(os.path.islink(moved) and open(moved).read() == "rapport" and os.path.exists(doc + "/rapport.txt"),
      "déplacer un lien relatif : il mène toujours à sa cible")
r = call("POST", "/api/fs/move", {"paths": [HOME + "/Bureau/Lien Projet"], "dest_dir": dl, "copy": True})
check(os.path.islink(dl + "/Lien Projet") and os.path.islink(HOME + "/Bureau/Lien Projet"), "copier un lien : un lien, pas le dossier")
r = call("POST", "/api/fs/move", {"paths": [HOME + "/Bureau/Lien Projet"], "dest_dir": HOME + "/Bureau"})
check(os.listdir(HOME + "/Bureau").count("Lien Projet") == 1 and not os.path.lexists(HOME + "/Bureau/Lien Projet (2)"),
      "déplacer un lien là où il est déjà : rien ne change")
r = call("POST", "/api/fs/trash", {"paths": [HOME + "/Bureau/Lien Projet", dl + "/Lien Projet", HOME + "/Bureau/lien-casse"]})
check(len(r["ok"]) == 3 and not os.path.lexists(HOME + "/Bureau/Lien Projet") and not os.path.lexists(HOME + "/Bureau/lien-casse")
      and open(doc + "/Projet/contrat.txt").read() == "important", "corbeille sur un lien : le dossier visé reste intact")
tl = {t["name"]: t for t in call("GET", "/api/trash")}
call("POST", "/api/trash/restore", {"ids": [tl["Lien Projet"]["id"]]})
check(any(os.path.islink(p) for p in (HOME + "/Bureau/Lien Projet", dl + "/Lien Projet")), "lien restauré depuis la corbeille")
for p in (HOME + "/Bureau/Lien Projet", dl + "/Lien Projet"):
    if os.path.islink(p):
        os.unlink(p)
os.symlink(doc + "/rapport.txt", dl + "/lien-a-trier.txt")
sc = call("POST", "/api/sort/scan", {"path": dl})
check(not any(f["name"] == "lien-a-trier.txt" for f in sc["files"]), "tri : les liens symboliques restent en place")
os.unlink(dl + "/lien-a-trier.txt")

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
cv = call("GET", "/api/conversations/" + c["id"])
last = cv["messages"][-1]
check(last["role"] == "error" and "ollama pull" in last["content"] and last["reessayer"], "l'erreur reste dans la discussion")
call("POST", "/api/conversations/" + c["id"], {"modele": ""})
ev = stream("/api/chat", {"conv_id": c["id"], "regenerate": True})
cv = call("GET", "/api/conversations/" + c["id"])
check(ev[-1]["t"] == "done" and [m["role"] for m in cv["messages"][-2:]] == ["user", "assistant"]
      and not any(m["role"] == "error" for m in cv["messages"]), "réessayer : l'erreur laisse la place à la réponse")
ev = stream("/api/chat", {"conv_id": c["id"], "message": "avec un fichier absent", "attachments": [dl + "/absent.pdf"]})
cv = call("GET", "/api/conversations/" + c["id"])
check(ev[-1]["t"] == "error" and cv["messages"][-1]["role"] == "error" and cv["messages"][-1]["reessayer"] is False
      and cv["messages"][-2]["content"] == "avec un fichier absent", "pièce jointe introuvable : question et erreur gardées")
ev = stream("/api/chat", {"conv_id": c["id"], "message": "suite"})
check(ev[-1]["t"] == "done", "la discussion continue après une erreur")

print("— une seule réponse à la fois par discussion")
c = call("POST", "/api/conversations", {})
res = {}
t = threading.Thread(target=lambda: res.update(ev=stream("/api/chat", {"conv_id": c["id"], "message": "[lent] bonjour"})))
t.start()
time.sleep(0.5)
r = call("POST", "/api/conversations/" + c["id"], {"titre": "pendant la réponse"}, expect=409)
check("en cours" in r.get("message", ""), "modifier la discussion pendant une réponse : refusé")
r = call("POST", "/api/chat", {"conv_id": c["id"], "message": "deuxième"}, expect=409)
check("déjà en cours" in r.get("message", ""), "deuxième réponse en même temps : refusée")
t.join()
cv = call("GET", "/api/conversations/" + c["id"])
check(res["ev"][-1]["t"] == "done" and [m["role"] for m in cv["messages"]] == ["user", "assistant"], "la première réponse arrive entière")
r = call("POST", "/api/conversations/" + c["id"], {"titre": "après"})
check(r["titre"] == "après", "modifier la discussion une fois la réponse finie")
c = call("POST", "/api/conversations", {})
body = json.dumps({"conv_id": c["id"], "message": "[lent] abandonnée"}).encode()
host, port = BASE.split("//")[1].split(":")
sk = socket.create_connection((host, int(port)))
sk.sendall((f"POST /api/chat HTTP/1.1\r\nHost: {host}:{port}\r\nX-Archiviste-Token: {TOKEN}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n").encode() + body)
time.sleep(0.5)
sk.close()  # la fenêtre est fermée (ou « Stop ») pendant que le modèle réfléchit encore
ev = stream("/api/chat", {"conv_id": c["id"], "message": "après abandon"})
time.sleep(1.8)  # le temps que la réponse abandonnée se termine côté Ollama
cv = call("GET", "/api/conversations/" + c["id"])
check(ev[-1]["t"] == "done" and [m["role"] for m in cv["messages"]] == ["user", "user", "assistant"],
      f"réponse abandonnée : la suivante passe et n'est pas écrasée ({[m['role'] for m in cv['messages']]})")

print("— ouvrir une appli depuis la discussion libre")
c2 = call("POST", "/api/conversations", {})
ev = stream("/api/chat", {"conv_id": c2["id"], "message": "ouvre appli-inexistante-xyz"})
res = [e for e in ev if e["t"] == "tool_result"]
check(res and res[0]["name"] == "ouvrir_application" and not res[0]["ok"] and ev[-1]["t"] == "done",
      "outil ouvrir_application appelé, appli absente signalée")
check(any(e["t"] == "content" for e in ev), "le modèle répond après l'outil")
os.makedirs(HOME + "/.local/share/applications", exist_ok=True)
open(HOME + "/.local/share/applications/grimoire-essai.desktop", "w").write(
    "[Desktop Entry]\nType=Application\nName=Grimoire\nExec=/bin/true\nOnlyShowIn=GNOME;Unity;\n")
ev = stream("/api/chat", {"conv_id": c2["id"], "message": "ouvre grimio"})
res = [e for e in ev if e["t"] == "tool_result"]
check(res and res[0]["ok"] and "Grimoire" in res[0]["summary"], f"orthographe approchée + appli « GNOME » : {res and res[0]['summary']}")

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
check(len(r) == len(ids) and r[0]["titre"] == "Mémo.md" and r[-1]["id"] == ids[0],
      "réordonner : un raccourci absent de la liste est gardé")
r = call("POST", "/api/raccourcis/retirer", {"id": ids[0]})
check(len(r) == len(ids) - 1, "retirer un raccourci")
for i in range(25):
    open(f"{HOME}/Documents/epingle-{i}.txt", "w").write("x")
base_n, stop = len(r), []
def bascule():
    k = 0
    while not stop:
        call("POST", "/api/bureau/reglages", {"volet": k % 2 == 0, "tri": ("nom", "date")[k % 2]})
        k += 1
ths = [threading.Thread(target=bascule) for _ in range(3)]
[t.start() for t in ths]
for i in range(25):
    call("POST", "/api/raccourcis/ajouter", {"type": "fichier", "cible": f"{HOME}/Documents/epingle-{i}.txt"})
stop.append(1)
[t.join() for t in ths]
n = len(call("GET", "/api/raccourcis"))
check(n == base_n + 25, f"écritures simultanées : aucun raccourci perdu ({n - base_n}/25)")
call("POST", "/api/raccourcis/defaut", {})
b = call("POST", "/api/bureau/reglages", {"volet_largeur": 5000, "conv_heures": 12})
check(b["volet_largeur"] == 900 and b["conv_heures"] == 12, "largeur du volet bornée, délai de nouvelle discussion")
b = call("POST", "/api/bureau/reglages", {"volet_largeur": 0, "conv_heures": 4, "volet": True})
check(b["volet_largeur"] is None and b["conv_heures"] == 4, "largeur du volet remise d'origine")
b = call("POST", "/api/bureau/reglages", {"volet_cote": "gauche", "ecran": 1})
check(b["volet_cote"] == "gauche" and b["ecran"] == 1 and b["ecrans"] == [], "volet à gauche, écran choisi")
b = call("POST", "/api/bureau/reglages", {"volet_cote": "ailleurs", "ecran": "principal"})
check(b["volet_cote"] == "gauche" and b["ecran"] is None, "réglage inconnu ignoré, retour à l'écran principal")
call("POST", "/api/bureau/reglages", {"volet_cote": "droite"})
apps = call("GET", "/api/apps")
check(isinstance(apps["apps"], list), f"applications installées ({len(apps['apps'])})")
ar = call("GET", "/api/bureau/a-ranger")
check(ar["telechargements"]["fichiers"] >= 1, "fichiers à ranger")
c1, c2 = call("GET", "/api/bureau/conv"), call("GET", "/api/bureau/conv")
check(c1["id"] == c2["id"], "discussion du volet persistante")
stream("/api/chat", {"conv_id": c1["id"], "message": "question d'hier"})
check(call("GET", "/api/bureau/conv")["id"] == c1["id"], "discussion récente : gardée")
cf = f"{HOME}/.local/share/archiviste/conversations/{c1['id']}.json"
old = json.load(open(cf))
old["modifie"] = "2020-01-01T08:00:00"
json.dump(old, open(cf, "w"))
check(call("GET", "/api/bureau/conv?rotation=0")["id"] == c1["id"], "simple relecture : pas de nouvelle discussion")
c3 = call("GET", "/api/bureau/conv")
check(c3["id"] != c1["id"] and c3["auto"] and c3["precedente"] == c1["id"] and not c3["messages"],
      "longue pause : nouvelle discussion, l'ancienne reste disponible")
c4 = call("POST", "/api/bureau/conv/nouvelle", {})
check(c4["id"] == c3["id"], "« + » sur une discussion vide : pas de discussion vide en plus")
c5 = call("POST", "/api/bureau/conv/reprendre", {})
check(c5["id"] == c1["id"] and call("GET", "/api/bureau/conv")["id"] == c1["id"]
      and not os.path.exists(cf.replace(c1["id"], c3["id"])), "reprendre la discussion précédente")
call("POST", "/api/bureau/reglages", {"conv_heures": 0})
json.dump(old, open(cf, "w"))
check(call("GET", "/api/bureau/conv")["id"] == c1["id"], "délai « jamais » : la discussion est gardée")
call("POST", "/api/bureau/reglages", {"conv_heures": 4})
sg = call("GET", "/api/bureau/sig")
check(sg["cv"].startswith(c1["id"] + ":"), "signature de la discussion du volet")
r = call("POST", "/api/app/ouvrir", {"vue": "files"})
check(r["ok"] is False, "sans fenêtre GTK : ouverture déclinée proprement")
check(call("GET", "/bureau", raw=True).startswith("<!doctype html>"), "page du bureau servie")

print("— couper, copier, coller")
cdir = doc_dir + "/presse"
os.makedirs(cdir + "/A", exist_ok=True)
os.makedirs(cdir + "/B", exist_ok=True)
open(cdir + "/A/rapport.txt", "w").write("rapport")
open(cdir + "/A/photo.jpg", "w").write("photo")
c = call("POST", "/api/presse-papiers", {"paths": [cdir + "/A/rapport.txt", cdir + "/A/photo.jpg"], "mode": "couper"})
check(c["mode"] == "couper" and len(c["paths"]) == 2 and call("GET", "/api/presse-papiers")["source"] == "archiviste", "couper : deux fichiers en attente")
r = call("POST", "/api/presse-papiers/coller", {"dest": cdir + "/B"})
check(len(r["ok"]) == 2 and sorted(os.listdir(cdir + "/B")) == ["photo.jpg", "rapport.txt"] and os.listdir(cdir + "/A") == [], "coller après couper : les fichiers sont déplacés, pas copiés")
check(call("GET", "/api/presse-papiers")["paths"] == [], "le presse-papiers est vidé après un couper-coller")
r = call("POST", "/api/presse-papiers/coller", {"dest": cdir + "/A"}, expect=400)
check("Rien à coller" in str(r), "coller sans rien : message clair")
call("POST", "/api/presse-papiers", {"paths": [cdir + "/B/rapport.txt"], "mode": "copier"})
call("POST", "/api/presse-papiers/coller", {"dest": cdir + "/A"})
r = call("POST", "/api/presse-papiers/coller", {"dest": cdir + "/B"})
check(os.listdir(cdir + "/A") == ["rapport.txt"] and sorted(os.listdir(cdir + "/B")) == ["photo.jpg", "rapport (2).txt", "rapport.txt"] and r["mode"] == "copier",
      "copier : collable plusieurs fois ; dans son propre dossier, un double « (2) »")
call("POST", "/api/presse-papiers", {"paths": [cdir + "/B/photo.jpg"], "mode": "couper"})
r = call("POST", "/api/presse-papiers/coller", {"dest": cdir + "/B"})
check(r["ok"] == [] and r["deja"] == 1 and os.path.exists(cdir + "/B/photo.jpg"), "couper puis coller au même endroit : rien ne bouge")
r = call("POST", "/api/presse-papiers", {"paths": ["/etc/passwd"], "mode": "copier"}, expect=403)
check("error" in r, "fichier hors des dossiers autorisés : refusé")
call("POST", "/api/presse-papiers", {"paths": [cdir + "/B/photo.jpg"], "mode": "couper"})
os.unlink(cdir + "/B/photo.jpg")
check(call("GET", "/api/presse-papiers")["paths"] == [], "fichier coupé puis supprimé ailleurs : il sort du presse-papiers")
r = call("POST", "/api/fs/move", {"paths": [cdir + "/A/rapport.txt"], "dest_dir": cdir + "/B"})
check(r["ok"] and not os.path.exists(cdir + "/A/rapport.txt") and len(os.listdir(cdir + "/B")) == 3, "glisser dans un dossier : déplacé (pas de copie laissée derrière)")

print("— mises à jour : installer, revenir à la version précédente")
ver = call("GET", "/api/update")["actuelle"]
u = call("POST", "/api/update/check")
check(u["disponible"] and u["derniere"]["version"] == "9.9.9" and not u["ignoree"], "nouvelle version détectée")
r = call("POST", "/api/update/install", {})
logged = open("/tmp/archi-install.log").read().split()
check(r.get("installe") and logged[-1].endswith("archiviste_9.9.9_all.deb"), "paquet téléchargé, empreinte vérifiée, installateur appelé")
p = call("GET", "/api/update/precedente")
check(p["trouvee"] and p["version"] == "1.0.0" and p["source"] == "github", f"version précédente trouvée sur le dépôt ({p.get('version')})")
r = call("POST", "/api/update/revenir")
logged = open("/tmp/archi-install.log").read().split()
st = call("GET", "/api/settings")
check(r.get("installe") and r["version"] == "1.0.0" and logged[-1].endswith("archiviste_1.0.0_all.deb"), "retour à la version précédente : son paquet est installé")
check(st["maj_ignoree"] == ver and st["maj_auto"] is False and r["maj_auto"] is False, "la version quittée est mise de côté (vérification coupée pour une version trop ancienne)")
check(call("GET", "/api/update/precedente")["source"] == "pc", "le paquet précédent reste sur le PC pour la prochaine fois")
call("POST", "/api/settings", {"maj_ignoree": "9.9.9", "maj_auto": True})
u = call("POST", "/api/update/check")
check(not u["disponible"] and u["ignoree"], "une version mise de côté n'est plus proposée d'office")
call("POST", "/api/settings", {"maj_ignoree": ""})
check(call("GET", "/api/update")["disponible"], "… et l'est de nouveau quand on le demande")

print("— export")
ex = call("GET", "/api/export")
check(len(ex["agents"]) == 5, "export agents + prompts")
n = call("POST", "/api/import", {"prompts": ex["prompts"][:2], "agents": []})
check(n["prompts"] == 2, "import (doublons d'id renommés)")

print(f"\n{'TOUT EST BON' if not fails else str(fails) + ' ÉCHEC(S)'}")
sys.exit(1 if fails else 0)
