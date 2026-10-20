# Crack the Bot

Jeu du département IA du Microsoft IssatSo Club pour le MicDay (samedi 24 octobre).
Un « gardien » IA protège un mot secret. Le joueur discute avec lui pour le lui faire dire, puis tape le mot
dans « Valider ». **C'est le code qui vérifie le mot, jamais l'IA.**

- 2 niveaux, avec un mot secret différent par niveau et par partie.
- 6 messages au gardien **par niveau** (compteur côté serveur, réglable : `MESSAGES_PER_LEVEL`). À 0, le bouton
  d'envoi est grisé mais le joueur peut encore valider un mot : **un mot faux met alors fin à la partie**, même s'il
  reste du temps. Tant qu'il reste des messages, un mot faux coûte 10 secondes.
- 3 minutes de temps de jeu par joueur. Le chrono démarre au premier message et **s'arrête pendant que le gardien répond**.
- Score = niveaux réussis x 1000 + secondes restantes au dernier niveau réussi. Égalité : le premier arrivé.
- À la fin, l'écran explique que le joueur vient de faire du **prompt engineering** (Session 2 de la roadmap).

**Pour installer, mesurer et choisir le modèle sur ton PC : suis `GUIDE_TESTS.md`**, étape par étape.

## Les 2 niveaux (fichier `app/levels.py`)

| Niveau | Défense | Ce qui marche (voulu, à confirmer avec un vrai modèle) |
|---|---|---|
| 1 | le prompt refuse un ordre direct, mais le gardien est naïf (exemple de chanson dans le prompt). Aucun filtre en code. | une chanson courte, un poème, des indices, le mot en caractères séparés |
| 2 | le code remplace chaque apparition du mot par `█████` (casse et accents ignorés). Si le joueur demande clairement le mot épelé et que le modèle ne l'épelle pas correctement, **le code répond lui-même** avec l'épellation (« P - L - A - G - E »). | demander le mot lettre par lettre, avec des tirets ou des espaces |

Au niveau 2 l'épellation est donc **garantie par le code**, pas par le modèle. La détection est une liste de
formulations (`asks_to_spell` dans `levels.py`) : « première lettre » ou « combien de lettres » ne comptent pas, mais
une formulation originale (« dis-le en plusieurs morceaux ») ne sera pas reconnue.

**Installer sur un autre PC (git, Ollama, modèle) : voir `INSTALLATION.md`.**

**Lancer avec une icône, utiliser l'admin, repartir propre, le jour J : voir `GUIDE_UTILISATION.md`.**

## Installation rapide (Ubuntu)

```bash
curl -fsSL https://ollama.com/install.sh | sh     # Ollama (une seule fois, demande internet)
ollama pull qwen2.5:3b                            # un modèle de départ (~2 Go, avec un bon wifi)
chmod +x run.sh && ./run.sh --install             # prépare l'environnement Python (.venv)
./run.sh                                          # lance le jeu
```

Prérequis : Python 3.10 ou plus récent (je n'ai testé que sous Python 3.13) et `python3-venv`
(`sudo apt install python3-venv` s'il manque). Au lancement, le terminal affiche les adresses et le **jeton admin** :

| Page | Adresse | Rôle |
|---|---|---|
| Jeu | http://127.0.0.1:8000/ | l'écran du joueur |
| Classement | http://127.0.0.1:8000/board | à mettre en plein écran (F11) sur le projecteur |
| Admin | http://127.0.0.1:8000/admin | supprimer une entrée (ex. nom déplacé), vider le classement |

Pour essayer l'interface **sans modèle** : `BACKEND=mock ./run.sh` (faux gardien qui réagit à quelques mots-clés ;
il ne dit rien de la vraie difficulté).

## Outils de mesure (dossier `tools/`)

| Commande | Rôle | Durée |
|---|---|---|
| `bash tools/diagnostic_pc.sh` | État du PC (secteur, mode CPU, RAM, pilote Nvidia, Ollama). Lecture seule ; `--appliquer` propose 2 corrections. | 1 min |
| `bash tools/mesurer_tout.sh` | Diagnostic + mesure de chaque modèle candidat, rapport dans `data/`. | 10-15 min |
| `python3 tools/check_model.py MODELE` | Attente réelle d'un joueur, GPU, réponse vide, langue. | 1-3 min |
| `python3 tools/tune.py MODELE` | Meilleur nombre de threads / réglage GPU pour ce modèle sur ce PC. | 5-15 min |
| `.venv/bin/python tools/redteam.py --trials 2` | Difficulté de chaque niveau (16 attaques x 2 niveaux). | 10-15 min |

`check_model.py` et `tune.py` envoient au modèle de **vrais prompts du jeu** (dernier niveau, historique de 2 échanges,
mot secret différent à chaque essai) avec **les mêmes réglages que le jeu** (la requête est construite par le même
code, `app/ollama_payload.py`). Ils n'utilisent que la bibliothèque standard : le `python3` du système suffit.
`redteam.py` utilise le vrai code du jeu et a donc besoin du `.venv`.

## Réglages (fichier `.env`)

Copiez `.env.example` en `.env`. Le jeu (`run.sh`) et les trois outils le lisent. Les plus utiles :

| Réglage | Effet |
|---|---|
| `MODEL` | Le modèle Ollama du gardien. |
| `MAX_TOKENS` | Longueur max d'une réponse ; plus petit = attente plus courte (essayez 50). |
| `THINK` | `off` (défaut) envoie `think: false` : pas de mode « réflexion », qui peut épuiser le budget de `MAX_TOKENS` et laisser le joueur devant « … ». Si Ollama refuse ce champ pour un modèle sans réflexion (erreur 400), le jeu réessaie sans, automatiquement. |
| `NUM_THREAD`, `NUM_GPU` | Threads CPU et couches GPU ; `0` / `-1` = Ollama décide. À régler avec `tune.py`, pas au hasard. |
| `KEEP_ALIVE` | Durée de maintien du modèle en mémoire (défaut `24h`). |
| `MESSAGES_PER_LEVEL` | Messages autorisés par niveau (défaut 6). |
| `HISTORY_TURNS` | **Ne pas le mettre dans `.env`** : par défaut il vaut `MESSAGES_PER_LEVEL`, le gardien se souvient de tout le niveau et le début du prompt ne change jamais (le cache du modèle sert à chaque message). Une valeur plus petite fait glisser l'historique : mesuré sur gemma3:4b, le cache est alors perdu et certains messages prennent 15 s. Le jeu affiche un avertissement au démarrage dans ce cas. `0` = le gardien n'a aucune mémoire. |
| `TIME_LIMIT`, `WRONG_GUESS_PENALTY` | Règles du jeu. |

Volontairement **non réglés** : `OLLAMA_FLASH_ATTENTION` (automatique par défaut, doc officielle) et la
quantification du cache (`OLLAMA_KV_CACHE_TYPE`, qui exige Flash Attention) : avec un contexte de 1024 tokens le
cache est petit, le gain serait faible et je ne l'ai pas mesuré.

## Checklist du jour J

- [ ] Un fichier `static/qr.png` avec le QR d'inscription (sinon un cadre « QR code d'inscription » s'affiche).
- [ ] PC branché sur secteur, mode performance actif, autres applications fermées.
- [ ] `ollama ps` montre le modèle chargé après `./run.sh` (le jeu le précharge au démarrage ; le premier chargement peut prendre quelques secondes).
- [ ] Le classement de test est vidé (page `/admin` > « Vider le classement »).
- [ ] La page `/board` s'affiche bien sur le projecteur **dans la salle éclairée** (le fond est sombre : à vérifier).
- [ ] Une partie complète jouée en conditions réelles avec le vrai modèle.
- [ ] Sauvegarde : `data/leaderboard.json` contient le classement ; copiez-le de temps en temps.

Internet n'est pas nécessaire pendant l'événement : le modèle, les polices et les pages sont locaux.

### Ouvrir `/board` depuis un autre ordinateur

Par défaut le serveur n'écoute que sur ce PC (`HOST=127.0.0.1`). Si le projecteur est branché sur le laptop d'un
coéquipier, lancez avec `HOST=0.0.0.0 ./run.sh` et ouvrez `http://ADRESSE_IP_DU_PC:8000/board`. Attention : toute
personne connectée au même réseau pourra alors ouvrir le jeu ; la page admin reste protégée par le jeton.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

Les tests couvrent les règles (chrono simulé à la seconde près, pause pendant la réponse du modèle, pénalités,
plafond de messages, fin de partie, score, abandon, fin automatique), la censure et l'épellation, le classement (persistance, fichier corrompu), l'API, la connexion
à Ollama (contre un faux serveur qui suit sa documentation : réflexion, options, repli si `think` est refusé) et
les outils de mesure. Deux scripts testent l'interface dans un vrai navigateur (Playwright + Chromium, optionnel,
`pip install playwright`) : `tools/e2e_browser.py` et `tools/e2e_timeout.py`. Ils contiennent un chemin Chromium
propre à mon environnement : sur votre PC, donnez le vôtre avec la variable `CHROME_PATH` (ou lancez
`playwright install chromium`).

## Ce qui n'a PAS été testé (et pourquoi)

- **Les prompts des 2 niveaux avec un vrai modèle** : le niveau 1 compte sur le modèle pour refuser un ordre direct
  mais céder à une chanson ; je n'ai aucune mesure que ça marche. Seuls la censure et l'épellation (du code) sont
  testées. Lance `tools/redteam.py`, puis joue toi-même.
- **Un vrai Ollama et un vrai modèle** : mon environnement n'y a pas accès. Tout ce qui touche Ollama a été vérifié
  contre un faux serveur écrit d'après la documentation, qui ne prouve pas que le vrai se comporte pareil. En
  particulier : l'effet réel de `think: false` sur chaque modèle, de `NUM_THREAD` et de `NUM_GPU`, et la façon dont
  Ollama réagit si un modèle sans réflexion reçoit `think: false`.
- **Les chiffres de vitesse** : ils dépendent de ton PC. Les repères de temps d'attente sont les miens.
- **`diagnostic_pc.sh --appliquer`** sur un vrai système (changement de mode CPU, service systemd d'Ollama) : la
  partie lecture est testée avec de faux outils ; les commandes `sudo` ne l'ont pas été.
- **Le français du modèle choisi** : les gardiens peuvent répondre dans une autre langue ou ignorer une consigne.
- **Le darija** : le jeu est prévu pour le français ; la censure et la détection d'épellation ne gèrent pas l'arabe.
- **Un projecteur réel et la lumière de l'amphi.**
- **Plusieurs joueurs en même temps** : le jeu est prévu pour un joueur (ou une équipe de deux) à la fois sur
  un PC. Techniquement, plusieurs parties peuvent coexister, mais un seul appel au modèle est traité à la fois :
  les autres attendent leur tour, ce qui ralentit les réponses (le chrono de chaque joueur reste en pause pendant
  l'attente).
- **Python 3.10 à 3.12** : je n'ai testé que 3.13.

## Contenu

```
GUIDE_TESTS.md   le guide pas à pas (à suivre dans l'ordre)
INSTALLATION.md  installer le projet sur un autre PC
GUIDE_UTILISATION.md  icône de lancement, admin, jour J
launcher/        crack-the-bot.sh (lanceur), installer_raccourci.sh, icon.svg
app/             config.py  levels.py (prompts, censure, épellation)  game.py (règles, chrono, score)  llm.py (Ollama)
                 ollama_payload.py (requête Ollama, partagée avec les outils)  leaderboard.py  main.py (API)  text.py
static/          index.html (joueur)  board.html (projecteur)  admin.html  *.js  style.css  fonts/
tools/           diagnostic_pc.sh  mesurer_tout.sh  check_model.py  tune.py  redteam.py  _probe.py (commun)
                 e2e_browser.py  e2e_timeout.py
tests/           tests automatiques (pytest)
data/            classement sauvegardé (leaderboard.json), rapports de mesure
```

Polices embarquées : Cormorant Garamond et Jost (licence SIL Open Font, fichiers de licence dans `static/fonts/`).
