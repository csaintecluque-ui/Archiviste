# Archiviste

Gestionnaire de fichiers + assistant IA **100 % local** pour Linux Mint, branché sur ton modèle Ollama (`qwen3.5:4b` par défaut).
Rien ne quitte ta machine.

| Onglet | Ce que tu peux faire |
|---|---|
| **Fichiers** | Parcourir, créer, renommer, déplacer, copier, importer (glisser-déposer depuis Nemo), ouvrir avec l'application par défaut, afficher dans Nemo, mettre à la corbeille. Aperçu des images, vidéos, PDF (première page), textes et documents Office. Éditeur de texte avec **« Demande à l'IA »** (corriger, traduire, compléter…). Résumé d'un fichier en un clic. |
| **Tri intelligent** | Range un dossier : l'IA propose un sous-dossier pour chaque fichier, ou tri instantané par type ou par date. **Tu valides le plan avant que quoi que ce soit ne bouge**, et chaque tri peut être annulé. |
| **Discussion** | Chat avec ton IA, en direct, avec historique. Joins des fichiers (texte, PDF, Word, Excel…) ou des images (qwen3.5 les voit). Mode « Réflexion » activable. |
| **Agents** | Assistants spécialisés : consignes + outils (lister, lire, chercher, écrire, déplacer, renommer, mettre à la corbeille, trouver les doublons) + un dossier de travail dont ils ne sortent pas. 4 agents fournis : Rangeur, Lecteur, Rédacteur, Nettoyeur. |
| **Prompts** | Bibliothèque de consignes réutilisables, avec variables `{{comme_ceci}}` demandées au moment de l'utilisation. |
| **Corbeille** | La même que celle de Nemo : restaurer ou supprimer définitivement. |
| **Bureau** | En option, Archiviste remplace les icônes du bureau de Mint : tes fichiers, et un volet à droite (discussion, fichiers à ranger, et tes raccourcis en colonne sur le bord). La discussion sert aussi de lanceur : « ouvre Grimoire » l'ouvre tout de suite, et elle propose tes applis et tes fichiers pendant que tu tapes. Clic droit sur une appli, un dossier ou un fichier → **Épingler aux raccourcis**. <kbd>Super</kbd>+<kbd>Espace</kbd> pose une question depuis n'importe quelle fenêtre. |
| **Grimoire** | Si l'appli de bureau Grimoire est installée : les .docx et .xlsx s'ouvrent dedans d'un double-clic, « Fichier ▾ » crée un document Word ou un classeur qui s'y ouvre, et chaque réponse de l'IA peut partir dans Grimoire en document mis en forme (titres, listes, tableaux) ou, si elle contient des tableaux, en classeur. Les agents ont un outil « Créer un document Word/Excel ». |

## Installation

1. Télécharge le dernier paquet **`archiviste_X.Y.Z_all.deb`** sur la page [Releases](https://github.com/csaintecluque-ui/Archiviste/releases/latest).
2. Double-clique dessus puis « Installer » (ou `sudo apt install ./archiviste_X.Y.Z_all.deb`). Le paquet installe ce qu'il faut (moteur d'affichage WebKitGTK de GNOME, lecture des PDF, suivi des fenêtres ouvertes).
3. Menu → **Archiviste** : l'appli s'ouvre dans sa propre fenêtre, avec son icône dans la barre des tâches.

> Si tu avais la toute première version (celle qui s'ouvrait dans Firefox), Archiviste la retire tout seul au premier lancement ; tes agents, prompts et discussions sont conservés.

Raccourcis de la fenêtre : <kbd>Ctrl</kbd>+<kbd>+</kbd> / <kbd>Ctrl</kbd>+<kbd>-</kbd> / <kbd>Ctrl</kbd>+<kbd>0</kbd> zoom · <kbd>F5</kbd> recharger · <kbd>F11</kbd> plein écran · <kbd>Ctrl</kbd>+<kbd>Q</kbd> quitter. La taille de la fenêtre et le zoom sont mémorisés.

Relancer Archiviste ramène la fenêtre existante au premier plan (une seule fenêtre à la fois). Le serveur tourne à l'intérieur de l'appli : fermer la fenêtre arrête tout.

> Besoin de l'ouvrir dans un navigateur ? `archiviste-serveur` puis <http://127.0.0.1:8765>.

## Bureau Archiviste

**Réglages → Bureau → Activer le bureau Archiviste.** En un clic, Archiviste :

1. masque les icônes du bureau de Nemo (réglage `org.nemo.desktop desktop-layout`, l'ancien est mémorisé) ;
2. affiche son propre bureau sous toutes les fenêtres, sur l'écran principal : les fichiers de `~/Bureau`, le dossier personnel, la corbeille, les clés USB ; le fond d'écran reste celui de Cinnamon ;
3. se lance à l'ouverture de session (`~/.config/autostart/archiviste-bureau.desktop`) ;
4. ajoute le raccourci clavier <kbd>Super</kbd>+<kbd>Espace</kbd> → « Demander à l'Archiviste » (si cette touche est déjà prise, il en choisit une autre et l'affiche dans les réglages).

| Sur le bureau | |
|---|---|
| Double-clic | ouvre (Word/Excel dans Grimoire, dossiers dans Archiviste ou Nemo selon le réglage, lanceurs .desktop) |
| Clic droit sur un élément | Ouvrir avec…, Résumer avec l'IA, En discuter, **Épingler aux raccourcis**, Renommer, Corbeille… |
| Clic droit sur le fond | nouveau dossier / document Word / classeur / fichier texte, ranger le bureau avec l'IA, trier les icônes, masquer le volet, fond d'écran |
| Beaucoup d'icônes | la grille s'arrête au bord du volet ; une flèche apparaît et la molette fait défiler les icônes qui restent |
| Clavier | <kbd>Entrée</kbd> ouvrir · <kbd>F2</kbd> renommer · <kbd>Suppr</kbd> corbeille (confirmation pour un dossier ou plusieurs éléments) · <kbd>Ctrl</kbd>+<kbd>A</kbd> · flèches · taper du texte → discussion du volet |
| Glisser-déposer | sur un dossier : déplacer (<kbd>Ctrl</kbd> : copier) · sur la corbeille · sur les raccourcis : épingler · sur la discussion : joindre · depuis Nemo : vers le bureau |

La discussion du volet : « ouvre Grimoire », « lance Firefox », « ouvre mes téléchargements » ouvrent tout de suite (sans l'IA), même avec une faute de frappe (« ouvrr le terminale ») ; pendant que tu tapes, elle propose tes applis et tes fichiers (flèches puis <kbd>Entrée</kbd>, clic droit pour épingler) ; tout le reste part à l'Archiviste, qui peut lui aussi ouvrir des applis et des fichiers.

Le volet se règle en largeur : glisse son bord gauche (double-clic pour revenir à la largeur d'origine). Quand tu te remets à écrire après une longue pause (4 heures par défaut, réglable dans **Réglages → Bureau**, ou « jamais »), il repart sur une discussion neuve ; « Reprendre la discussion précédente » la rouvre, et elle reste de toute façon dans l'onglet Discussion. Si l'IA ne peut pas répondre (Ollama arrêté, modèle absent), le message d'erreur reste affiché avec un bouton **Réessayer**.

La colonne des raccourcis sert aussi de **dock** : un repère sur le raccourci indique que l'appli est ouverte (trait long : devant ; petit rond : réduite ; un chiffre s'il y a plusieurs fenêtres). Un clic ramène sa fenêtre, ou la réduit si elle est déjà devant ; les applis ouvertes sans raccourci s'ajoutent sous un séparateur le temps qu'elles restent ouvertes. Clic droit : Réduire / Ramener devant, Nouvelle fenêtre, Fermer, Épingler.

Les raccourcis sont en colonne sur le bord droit du volet, pour laisser toute la hauteur à la discussion ; s'il y en a beaucoup, la colonne défile. Clic pour ouvrir, glisser pour réordonner, clic droit pour renommer, monter, descendre ou retirer, crayon en bas de la colonne pour en retirer plusieurs, « + » pour ajouter une application (toutes celles du menu, tes favoris en premier), un dossier ou un fichier.

Pour revenir au bureau de Mint : **Réglages → Bureau → Rendre le bureau à Nemo**, ou dans un terminal `archiviste --sans-bureau`. Tes raccourcis sont gardés.

Commandes : `archiviste` (fenêtre), `archiviste --bureau`, `archiviste --demander`, `archiviste --sans-bureau`.

## Mises à jour

Archiviste vérifie les nouvelles versions sur ce dépôt au démarrage puis toutes les 6 heures. Quand il y en a une, une pastille apparaît en bas à gauche : un clic, il télécharge le paquet, **vérifie son empreinte** et l'installe (ton mot de passe est demandé par la fenêtre de Mint ; il attend si une autre installation est en cours). Il propose ensuite de redémarrer. En cas d'échec, il affiche la raison, et « Avec l'installateur de Mint » reste possible. Réglages → À propos : « Vérifier maintenant », ou désactiver la vérification automatique.

Pour publier une nouvelle version : change `VERSION` dans `archiviste.py`, ajoute une section dans `NOUVEAUTES.md`, puis pousse sur `main`. GitHub lance les tests, construit le `.deb` et publie la release `vX.Y.Z` avec ces notes ; les Archiviste installés la proposent ensuite d'eux-mêmes. Sur une pull request, le `.deb` est construit pour essai (onglet Actions → Artifacts) sans être publié.

### Si Ollama n'est pas encore sur ce Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:4b
```

Pour que l'IA tourne sur ta RTX 3060 (et pas sur le processeur), installe le pilote NVIDIA recommandé depuis le **Gestionnaire de pilotes** de Mint, puis redémarre. `nvidia-smi` doit afficher ta carte.

## Sécurité : ce que l'appli peut et ne peut pas faire

- Elle n'écoute que **sur ton PC** (127.0.0.1). Une protection empêche les autres sites ouverts dans ton navigateur de lui envoyer des ordres.
- Elle ne voit que les **dossiers autorisés** (par défaut ton dossier personnel). Ajoute ta partition Windows ou un disque externe dans **Réglages → Dossiers autorisés**. Autoriser tout le disque (`/`) est refusé.
- **Rien n'est jamais effacé directement** : « supprimer » envoie à la corbeille de Mint.
- Sur un **lien symbolique**, renommer, déplacer, copier ou mettre à la corbeille n'agit que sur le lien : le dossier ou le fichier visé ne bouge pas. Le tri intelligent laisse les liens en place.
- Avant chaque modification d'un fichier, l'**ancienne version est sauvegardée** dans `~/.local/share/archiviste/versions` (les 300 dernières).
- Les agents **demandent ta validation** avant toute action qui modifie un fichier (sauf si tu décoches cette option pour un agent). Ils ne peuvent pas sortir de leur dossier de travail.
- Un tri ne remplace jamais un fichier existant (`nom (2).pdf`) et peut être annulé depuis le journal.

## Conseils pour qwen3.5:4b

- Un modèle de 4 milliards de paramètres est rapide mais modeste : donne-lui des **consignes courtes et précises**, et un **dossier de travail restreint** (ex. `~/Téléchargements` plutôt que tout ton dossier personnel).
- Laisse le mode **Réflexion** désactivé pour les tâches simples : il ralentit beaucoup ce modèle. Active-le pour les questions qui demandent du raisonnement.
- Contexte conseillé : **8 192 jetons** (Réglages). Au-delà, la mémoire vidéo de la 3060 (6 Go) se remplit vite.
- Pour le tri de gros dossiers, la méthode « Par type » ou « Par mois » est instantanée ; l'IA est utile quand le **nom** des fichiers dit de quoi ils parlent (factures, contrats, photos de vacances…). Coche « Lire le début de chaque fichier » pour plus de précision.
- Tu peux choisir un autre modèle par agent ou par discussion (ex. un 7B/8B pour un agent plus exigeant).

## Où sont les choses

| Quoi | Où |
|---|---|
| L'application | `/opt/archiviste/` (installée par le paquet .deb) |
| Tes réglages, agents, prompts, discussions, journal des tris | `~/.local/share/archiviste/` (simples fichiers JSON) |
| Anciennes versions des fichiers modifiés | `~/.local/share/archiviste/versions/` |

Sauvegarde / transfert de tes agents et prompts : **Réglages → Sauvegarde → Exporter**.

## Dépannage

| Problème | Solution |
|---|---|
| « Ollama hors ligne » en bas à gauche | `systemctl status ollama` puis `sudo systemctl start ollama` (ou `ollama serve`). |
| « Modèle absent » | `ollama pull qwen3.5:4b` |
| Réponses très lentes | Vérifie `nvidia-smi` pendant une réponse : si la carte ne travaille pas, installe le pilote NVIDIA. |
| « Recherche arrêtée… » ou « recherche incomplète » | Le dossier est trop volumineux pour être parcouru dans le temps imparti (12 s, 2,5 s depuis le volet) : ouvre un sous-dossier plus précis dans l'onglet Fichiers et relance. |
| Un agent n'utilise pas ses outils | Petit modèle : reformule plus directement (« liste le dossier puis range les PDF dans Factures »), baisse sa température, ou choisis un modèle plus gros pour cet agent. |
| Fenêtre blanche ou vide | Lance `archiviste` dans un terminal pour voir le message ; avec le pilote NVIDIA, essaie `WEBKIT_DISABLE_COMPOSITING_MODE=1 archiviste`. |
| Bureau : le fond reste noir | Réglages → Bureau → Fond d'écran : « Dessiné par Archiviste ». |
| Bureau : les icônes de Nemo réapparaissent par-dessus | Réglages → Bureau : désactive puis réactive (Archiviste remet `desktop-layout` à `false::false`). |
| Bureau : pas de repère sur les raccourcis des applis ouvertes | Réglages → Bureau → « Applis ouvertes » doit être coché. Sinon : `sudo apt install gir1.2-wnck-3.0`, puis relance Archiviste (le suivi des fenêtres demande une session X11, celle de Cinnamon par défaut). |
| Bureau : tout revenir comme avant | `archiviste --sans-bureau` dans un terminal. |
| Voir ce qui se passe | `ARCHIVISTE_DEBUG=1 archiviste` dans un terminal affiche les échanges. <kbd>F12</kbd> ouvre l'inspecteur. |

## Désinstallation

- **Désinstaller** : `sudo apt remove archiviste`. Tes fichiers ne sont jamais touchés ; tes agents, prompts et discussions restent dans `~/.local/share/archiviste` (supprime ce dossier pour tout effacer).

## Pour bidouiller

- `archiviste.py` — le serveur (Python, bibliothèque standard uniquement) : fichiers, corbeille, Ollama, agents et leurs outils (`TOOLS`), tri.
- `fenetre.py` — la fenêtre d'application (GTK 3 + WebKitGTK) qui embarque le serveur, et le suivi des fenêtres ouvertes (`SuiviFenetres`, libwnck) pour les repères du volet ; côté serveur : `window_groups()` et `window_app()` dans `archiviste.py`.
- Documents Office : `make_docx()` (Markdown → Word) et `make_xlsx()` (tableaux Markdown → Excel) dans `archiviste.py`, vérifiés à l'ouverture dans Grimoire.
- `construire-deb.sh` — construit `dist/archiviste_<version>_all.deb` (GitHub le fait tout seul à chaque version).
- `tests/lancer.sh` — tests de bout en bout avec un faux Ollama (lancés aussi par GitHub avant chaque publication) : l'API (`test_api.py`), quelques fonctions (`test_unites.py`), puis l'interface dans Chrome sans affichage (`test_interface.cjs` : volet du bureau et fenêtre principale). Pour ces derniers : Node.js, puis une fois `npm install --prefix tests`.
- `NOUVEAUTES.md` — ce qui change à chaque version (repris dans la release et affiché dans l'appli).
- `static/bureau.html`, `bureau.js`, `bureau.css` — le bureau et la fenêtre « Demander » (réutilisent les outils d'`app.js`). Côté serveur : section « Bureau » d'`archiviste.py` (lanceurs .desktop, icônes du thème, raccourcis, activation).
- `static/app.js` — l'interface (sans framework). `static/app.css` — le style (palette encre / cuivre / parchemin).
- Lancer à la main pour tester : `python3 fenetre.py` (fenêtre) ou `python3 archiviste.py` (navigateur) (variables : `ARCHIVISTE_PORT`, `ARCHIVISTE_DATA`, `ARCHIVISTE_DEBUG=1`).
- Ajouter un outil d'agent : une entrée dans `TOOLS` + un bloc dans `execute_tool()`. Il apparaît automatiquement dans l'éditeur d'agents.
