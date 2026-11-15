# Nouveautés

## 1.4.6
- **Le volet sert de dock** : un repère apparaît sur le raccourci quand l'appli est ouverte (trait long si elle est devant, petit rond si elle est réduite, et le nombre de fenêtres s'il y en a plusieurs). Un clic ramène sa fenêtre au lieu d'en lancer une autre ; si elle est déjà devant, il la réduit. Les applis ouvertes sans raccourci (ton navigateur, par exemple) s'ajoutent à la colonne tant qu'elles sont ouvertes : une fenêtre réduite ne « disparaît » plus. Clic droit : Réduire, Nouvelle fenêtre, Fermer, Épingler. « ouvre Firefox » ramène aussi Firefox s'il est déjà ouvert.
- **Liens symboliques** : mettre à la corbeille, renommer, déplacer ou copier un lien agit maintenant sur le lien, plus sur le dossier ou le fichier qu'il vise. Avant, « Suppr » sur un lien du bureau envoyait le vrai dossier à la corbeille.
- **Corbeille depuis le bureau** : une confirmation est demandée pour un dossier ou pour plusieurs éléments, comme dans la fenêtre principale.
- **Les erreurs de l'IA restent affichées** (volet, « Demander », fenêtre principale) : si Ollama est arrêté ou si le modèle manque, le message ne disparaît plus au bout d'une seconde. Un bouton **Réessayer** relance la même demande, et la pastille de statut passe au rouge tout de suite.
- **Volet à largeur réglable** : glisse son bord gauche pour l'élargir ou le rétrécir (double-clic : largeur d'origine). La largeur est mémorisée.
- **Les icônes du bureau ne passent plus sous le volet** : la grille s'arrête à son bord. S'il y en a trop, une flèche apparaît et la molette les fait défiler.
- **Nouvelle discussion après une longue pause** : quand tu te remets à écrire dans le volet après plus de 4 heures, il repart sur une discussion neuve, pour qu'un vieux sujet ne pollue pas la question suivante. « Reprendre la discussion précédente » la rouvre en un clic ; le délai se règle dans Réglages → Bureau (ou « jamais »).
- **Recherche incomplète signalée** : quand une recherche s'arrête avant d'avoir tout parcouru (dossier très volumineux), Archiviste le dit au lieu d'afficher « aucun résultat ». La recherche parcourt aussi les dossiers une seule fois au lieu de deux.
- **Plus de réglages perdus** : épingler un raccourci pendant qu'un autre réglage s'enregistre ne l'efface plus, et une seule réponse à la fois s'écrit dans une discussion (changer d'agent pendant une réponse n'efface plus l'affichage).
- Le volet suit la discussion quand tu poses une question par Super + Espace, et l'icône de l'onglet Prompts est revenue.
- Sous le capot : des tests pilotent désormais le volet et la fenêtre principale dans un vrai navigateur avant chaque publication.

## 1.4.5
- **Raccourcis en colonne à droite du volet** : la discussion prend maintenant toute la hauteur du volet. Les raccourcis s'empilent sur le bord droit et la colonne défile quand il y en a beaucoup (un fondu en haut ou en bas indique qu'il en reste).
- En bas de la colonne : « + » pour ajouter une appli, un dossier ou un fichier, et le crayon pour en retirer plusieurs. Clic droit sur un raccourci : « Monter » / « Descendre ».

## 1.4.4
- **Les dossiers avant les applis** : « ouvre téléchargements », « ouvre mes documents », « ouvre le dossier images » ouvrent le dossier, et non plus Transmission ou le Numériseur de documents. Même règle pour l'IA.
- **Glisser sur les raccourcis** : glisser une icône du bureau (un lanceur comme Claude, un dossier, un fichier) sur les raccourcis du volet l'épingle enfin ; glisser sur la discussion la joint au message.
- **Icônes des applis** : Archiviste cherche les icônes exactement comme Cinnamon (thème, héritages, liens), donc celles de Firefox, de Claude, etc. s'affichent.

## 1.4.3
- **Le Terminal est trouvé** : les applis marquées pour GNOME (dont le Terminal de Mint) sont maintenant reconnues, comme dans le menu de Cinnamon. Elles réapparaissent aussi dans « + Ajouter ».
- **Orthographe approchée** : « terminale », « grimio », « firefoks », « libre office », « ouvrr le terminal »… trouvent quand même la bonne appli, dans la discussion comme pour l'IA.

## 1.4.2
- **Mises à jour plus fiables** : Archiviste installe lui-même la nouvelle version (ton mot de passe est demandé par la fenêtre de Mint) au lieu de passer par l'installateur de paquets, qui pouvait échouer avec « erreur logicielle dans aptkit ». Si une autre installation est en cours, il attend qu'elle se termine ; en cas d'échec, il affiche la vraie raison et propose de réessayer.

## 1.4.1
- **Une seule saisie sur le bureau** : la barre du haut disparaît, tout passe par la discussion du volet. Pendant que tu tapes, elle propose tes applis, tes fichiers et tes dossiers ; taper n'importe où sur le bureau y écrit directement.
- **« ouvre Grimoire », « lance Firefox », « ouvre mes téléchargements »** : ouvert tout de suite, sans attendre l'IA.
- L'IA sait maintenant **ouvrir une application, un fichier ou un dossier** (nouveaux outils, aussi dans la fenêtre principale et pour les agents), et n'a plus le droit de prétendre avoir lancé quelque chose sans l'avoir fait.
- Les applis s'ouvrent sans terminal : si un ancien lanceur (script lancé dans un terminal) masque l'appli installée par son paquet, Archiviste lance l'appli du paquet.

## 1.4.0
- **Bureau Archiviste** (Réglages → Bureau → « Activer ») : il remplace les icônes du bureau de Nemo. Tes fichiers du dossier Bureau, avec double-clic, clic droit (ouvrir avec…, Grimoire, résumer, en discuter, renommer, corbeille), sélection au lasso, glisser-déposer, clés USB et corbeille.
- En haut, la barre **« Demande à l'Archiviste… »** : elle trouve aussi tes applis et tes fichiers pendant que tu tapes, et Entrée pose la question à l'IA. Taper n'importe où sur le bureau y écrit directement.
- À droite, un **volet** repliable : tes raccourcis, les fichiers en vrac à ranger, et une discussion qui reste ouverte (agents et validations compris).
- **Épingler aux raccourcis** : clic droit sur une appli, un dossier ou un fichier — sur le bureau, dans les résultats de recherche, dans Fichiers — ou bouton « + » qui liste toutes tes applis (favoris du menu en premier). Les raccourcis se réordonnent en les glissant.
- **Super + Espace** ouvre « Demander à l'Archiviste » par-dessus n'importe quelle fenêtre.
- Un clic pour revenir au bureau de Mint (Réglages → Bureau), ou `archiviste --sans-bureau` dans un terminal.

## 1.3.0
- **Mises à jour automatiques** : Archiviste vérifie les nouvelles versions sur GitHub (au démarrage puis toutes les 6 heures), télécharge le paquet, vérifie son empreinte et ouvre l'installateur de paquets de Mint. Une fois installée, il propose de redémarrer.
- Réglages → À propos : « Vérifier maintenant » et choix de la vérification automatique.

## 1.2.0
- **Lien avec Grimoire** : les documents Word et Excel s'ouvrent dans Grimoire d'un double-clic ; « Fichier ▾ » crée un document ou un classeur qui s'y ouvre.
- Les réponses de l'IA partent dans Grimoire en document mis en forme (titres, listes, tableaux) ou, si elles contiennent des tableaux, en classeur.
- Nouvel outil d'agent « Créer un document Word/Excel ».

## 1.1.0
- **Vraie fenêtre d'application** (GTK + WebKit), installée par un paquet .deb : plus de navigateur.
- « Ouvrir » lance l'application par défaut de Mint ; « Afficher dans Nemo » ; aperçu des PDF (première page).
- Zoom, plein écran, taille de fenêtre mémorisée.

## 1.0.0
- Première version : fichiers, tri intelligent, discussion, agents avec validation, prompts, corbeille.
