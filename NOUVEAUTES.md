# Nouveautés

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
