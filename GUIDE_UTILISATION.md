# Crack the Bot : utiliser l'application

## 1. Installer l'icône (une seule fois)

```bash
cd ~/crack-the-bot
bash launcher/installer_raccourci.sh
```

Cela ajoute l'icône « Crack the Bot » dans le menu des applications et sur le bureau, et enregistre un
**jeton admin fixe** dans `.env` (il est affiché à la fin). Si l'icône du bureau s'affiche avec un nom étrange :
clic droit > « Autoriser le lancement ». Pour l'avoir dans la barre latérale : ouvre le menu des applications,
clic droit sur l'icône > « Ajouter aux favoris ».

Prérequis : le fichier `.env` existe (`cp .env.example .env`) et `MODEL=` y contient le modèle choisi.

## 2. Lancer et arrêter

- **Lancer** : double-clique sur l'icône. Une fenêtre de terminal s'ouvre : c'est le jeu. Le lanceur démarre Ollama
  s'il ne tourne pas, vérifie que le modèle est installé, démarre le jeu et ouvre le navigateur sur la page du joueur.
  Premier message du premier joueur : quelques secondes de plus (chargement du modèle).
- **Arrêter** : `Ctrl+C` dans cette fenêtre, ou la fermer. Le classement est conservé ; une partie en cours est perdue.
- Si tu double-cliques alors que le jeu tourne déjà, il ouvre simplement la page (pas de second jeu).
- Clic droit sur l'icône (dans le menu des applications ou le dock) : raccourcis « classement » et « admin ».
- En cas d'erreur, la fenêtre reste ouverte avec le message (modèle absent, Ollama absent…).

## 3. Les trois pages

| Page | Adresse | Pour qui |
|---|---|---|
| Jeu | http://127.0.0.1:8000/ | le joueur (une équipe de 1 ou 2 à la fois) |
| Classement | http://127.0.0.1:8000/board | projecteur ou 2e écran : `F11` pour le plein écran, se met à jour toutes les 3 s, montre les 10 premiers |
| Admin | http://127.0.0.1:8000/admin | toi (jeton dans `.env`, ligne `ADMIN_TOKEN=`) |

Le joueur tape son prénom, puis joue : chrono de 3 minutes qui démarre au premier message et s'arrête pendant que le
gardien répond, 6 messages par niveau, « Valider » pour proposer un mot (voir `README.md` pour le détail des règles).
Le bouton « Nouvelle partie » de l'écran final prépare le joueur suivant.

## 4. Admin : voir, corriger, vider

Ouvre `/admin`, colle le jeton (il est mémorisé par le navigateur), clique « Charger le classement ».

- **Voir la liste** : place, joueur, niveaux, points, heure. Elle s'actualise seule toutes les 5 s.
- **Supprimer une entrée** (faute de frappe dans un prénom, test, abus) : bouton « Supprimer » de la ligne.
- **Vider tout le classement** : bouton rouge « Vider le classement ». Une copie est gardée dans
  `data/leaderboard.backup-DATE.json` : rien n'est perdu.
- La ligne en haut de la page dit si le gardien (le modèle) est prêt.

Classement : plus de niveaux d'abord, puis plus de secondes restantes, puis le premier arrivé.

## 5. Repartir propre avant l'événement

1. Joue tes essais (ils s'ajoutent au classement).
2. **Arrête le jeu** (`Ctrl+C`), puis relance-le avec l'icône : cela efface aussi les parties encore ouvertes en mémoire
   (une partie oubliée dans un onglet se terminerait plus tard et s'ajouterait au classement).
3. Dans `/admin` : « Vider le classement ». Vérifie que la liste est vide et que `/board` affiche « Personne n'a encore joué ».
4. Facultatif, pour ne garder aucune trace de tes essais : `rm ~/crack-the-bot/data/leaderboard.backup-*.json`.
   Ne supprime pas les fichiers `redteam-*.json` ni les rapports de mesure : ils servent à régler les prompts.
5. Remets le QR d'inscription : copie l'image dans `static/qr.png` (sinon un cadre vide s'affiche à la place).

## 6. Le jour J

- PC **branché sur secteur**, mode performance (`bash tools/diagnostic_pc.sh --appliquer`, à refaire après chaque
  redémarrage), navigateur avec une seule fenêtre, autres applications fermées.
- Lance l'icône **15 minutes avant** et joue une partie complète : le modèle est alors chargé en mémoire.
- Le projecteur affiche `/board`. Si c'est le laptop d'un coéquipier : lance avec `HOST=0.0.0.0` (ligne `HOST=` du
  `.env`) et ouvre `http://IP_DU_PC:8000/board` sur son laptop ; toute personne du même réseau peut alors aussi
  ouvrir le jeu. L'admin reste protégé par le jeton.
- Toutes les 30 minutes environ : copie `data/leaderboard.json` sur une clé USB (c'est tout le classement).
- Prénom mal écrit ou nom inapproprié : supprime l'entrée dans `/admin`.
- Le jeu se bloque ou le gardien ne répond plus : `Ctrl+C`, double-clic sur l'icône. Le classement est conservé ;
  seule la partie en cours est perdue, le joueur recommence (tu peux lui rendre ses minutes à l'oral).
- Si Ollama est planté : `sudo systemctl restart ollama`, puis relance l'icône.

## 7. Réglages utiles (fichier `.env`, relance le jeu après modification)

| Ligne | Effet |
|---|---|
| `MODEL=` | modèle du gardien |
| `MESSAGES_PER_LEVEL=6` | messages par niveau |
| `TIME_LIMIT=180` | secondes de jeu par équipe |
| `WRONG_GUESS_PENALTY=10` | secondes perdues par mot faux |
| `MAX_TOKENS=80` | longueur max des réponses ; plus petit = plus rapide |
| `ADMIN_TOKEN=` | jeton admin |

Ne mets pas de ligne `HISTORY_TURNS` (voir `README.md`).

## 8. Où sont les choses

| Chose | Emplacement |
|---|---|
| Classement | `~/crack-the-bot/data/leaderboard.json` |
| Copies de sécurité du classement | `~/crack-the-bot/data/leaderboard.backup-*.json` |
| Journal d'Ollama (seulement s'il a été démarré par l'icône) | `~/crack-the-bot/data/ollama.log` |
| Prompts et mots secrets | `app/levels.py` |
| QR d'inscription | `static/qr.png` |
