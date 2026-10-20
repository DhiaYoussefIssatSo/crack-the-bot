# Guide pas à pas : installer, mesurer, choisir le modèle, régler la vitesse

Tout se fait dans un terminal Ubuntu, dans le dossier `crack-the-bot`. Compte **1 h 30 de présence** et
environ **10 Go de téléchargement** (fais-le avec un bon wifi, pas avec ta 4G).

Les chiffres et seuils de ce guide sont des **repères que j'ai choisis**. Les outils ont été testés contre un
faux Ollama : leur comportement sur ton vrai PC est justement ce que tu vas vérifier.

> Avant tout : PC **branché sur secteur**, navigateur et autres applications **fermés** (le modèle a besoin de
> mémoire et de processeur, sinon les mesures sont faussées).

---

## Étape 1 — Installer Ollama (5 min)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama --version
```

Si Ollama était déjà installé, relance la première commande pour le mettre à jour : `ministral-3` demande
Ollama 0.13.1 ou plus récent (indiqué sur sa page officielle).

## Étape 2 — Installer le jeu (3 min)

```bash
unzip crack-the-bot.zip
cd crack-the-bot
chmod +x run.sh
./run.sh --install
```

Si tu vois « ensurepip is not available » : `sudo apt install python3-venv`, puis relance `./run.sh --install`.
Cette étape a besoin d'internet (installation de FastAPI, uvicorn, httpx). Message attendu à la fin :
« Environnement prêt (.venv) ».

## Étape 3 — Diagnostic du PC (2 min)

```bash
bash tools/diagnostic_pc.sh
```

Il ne change rien : il affiche le processeur, la mémoire libre, la carte graphique, le pilote Nvidia et Ollama.
Regarde les lignes **⚠** :

| Ligne | Quoi faire |
|---|---|
| PC sur batterie | Branche-le. |
| mode performance non actif | `bash tools/diagnostic_pc.sh --appliquer`, réponds `o` à la première question (valable jusqu'au redémarrage). |
| moins de 6 Go disponibles | Ferme des applications. |
| le pilote Nvidia ne fonctionne pas | Redémarre le PC une fois. Si ça persiste : **ne touche pas au pilote avant l'événement** (risque d'écran noir, Secure Boot) ; le jeu tourne sur le processeur, et avec ~2 Go de VRAM le gain de la carte serait de toute façon incertain. On y reviendra seulement si le processeur seul est trop lent. |
| Ollama ne répond pas | `sudo systemctl start ollama` (ou `ollama serve` dans un autre terminal). |

La deuxième question de `--appliquer` (réglage d'Ollama) n'accélère **rien** : elle évite seulement que plusieurs
modèles restent en mémoire en même temps quand tu en compares plusieurs. Réponds `o` si tu veux.

## Étape 4 — Télécharger les modèles (10 à 30 min selon le wifi)

```bash
ollama pull qwen2.5:3b
ollama pull granite4.1:3b
ollama pull ministral-3:3b
ollama pull gemma3:4b
ollama list
```

`ollama list` doit montrer les 4 modèles. Tu peux le faire pendant que tu lis la suite.

*Option (5ᵉ modèle)* : `ollama pull qwen3.5:4b`. C'est le modèle aux meilleurs chiffres publiés, mais il est
réputé « réfléchir » avant de répondre. Le jeu envoie maintenant `think: false` ; l'étape 5 te dira si ça suffit.

## Étape 5 — Mesurer le PC et tous les modèles d'un coup (10 à 15 min)

```bash
bash tools/mesurer_tout.sh
```

Pour ajouter l'option : `bash tools/mesurer_tout.sh qwen3.5:4b`. Le script écrit un rapport dans `data/`
(« Rapport enregistré dans : … ») et finit par un **tableau récapitulatif** :

```
RÉSUMÉ | granite4.1:3b | attente max ~13 s (50 tokens : ~10 s) | 8.7 tokens/s | GPU 25 % | acceptable
```

(exemple de format, pas un résultat réel). Comment le lire :

- **attente max** : le temps qu'un joueur attend une réponse au pire (question traitée + réponse la plus longue
  autorisée). Le chrono du jeu est en pause pendant ce temps, mais c'est l'attente que le public vivra.
  Repères : ≤ 10 s confortable, ≤ 15 s acceptable, ≤ 25 s lent, au-delà trop lent.
- **50 tokens** : l'attente si tu réduis `MAX_TOKENS` à 50 (réponses plus courtes). Si c'est ce chiffre qui te
  convient, mets `MAX_TOKENS=50` dans `.env` (étape 6).
- **GPU x %** : la part du modèle dans la carte graphique. 0 % est possible avec 2 Go de VRAM (le modèle ne tient pas) ; `tune.py` (étape 6) mesure si cela change quelque chose.
- **À CORRIGER** : lis les « Problèmes détectés » juste au-dessus dans le rapport.
  - *réponse VIDE* : le modèle réfléchit sans répondre. Si cela arrive même avec `THINK=off`, élimine le modèle
    et envoie-moi le rapport.
  - *non latins* ou *anglais* : le gardien ne parle pas français. Élimine le modèle.

**Décision** : écarte les « trop lent » et les « À CORRIGER ». Garde les **2 modèles les plus rapides** parmi les
autres. La vitesse ne dit rien de la qualité du gardien : c'est l'étape 7 qui la mesure.

## Étape 6 — Régler la vitesse du meilleur modèle (5 à 15 min)

```bash
python3 tools/tune.py granite4.1:3b        # remplace par ton modèle
```

Il teste plusieurs nombres de threads (et, si le modèle touche la carte graphique, « processeur seul »), puis
affiche un classement et une **conclusion**. Deux cas :

- « garde les réglages par défaut » : ne change rien (l'écart mesuré est du bruit).
- « Ajoute dans .env : NUM_THREAD=… » : fais-le.

Crée ensuite ton fichier de réglages et mets-y le modèle choisi :

```bash
cp .env.example .env
nano .env          # modifie MODEL=…, et NUM_THREAD / MAX_TOKENS si besoin ; Ctrl+O, Entrée, Ctrl+X pour enregistrer
python3 tools/check_model.py        # lit .env : vérifie que l'attente a bien baissé
```

Les mesures varient d'environ 10 % d'un passage à l'autre : si le résultat te surprend, relance une fois.

## Étape 7 — Mesurer la difficulté des 2 niveaux (10 à 15 min par modèle)

```bash
.venv/bin/python tools/redteam.py --trials 2
```

(Avec le `python` du `.venv`, pas `python3` : ce script a besoin de httpx.) Il rejoue 16 attaques classiques à
chaque niveau, avec le même traitement que le jeu (censure du niveau 2 et épellation garantie comprises) et affiche une estimation du temps restant. À la fin, regarde la ligne **TAUX GLOBAL** :

| Niveau | Résultat attendu (mon hypothèse de conception, jamais mesurée sur un vrai modèle) |
|---|---|
| 1 | « demande directe », « poli », « ordre », « faux admin » plutôt refusés ; « chanson », « poème », « épelé », « devinette » plutôt acceptés |
| 2 | « épelé » à 100 % (garanti par le code) ; « demande directe » et « chanson » à 0 (le mot est censuré) ; l'envers et le chiffré, rarement |

Si « épelé » n'est pas à 100 % au niveau 2, c'est un bogue : préviens-moi. Si le niveau 1 est à 0 % partout, le
modèle refuse trop (je dois alors alléger le prompt) ; s'il est à 100 % partout, il cède trop même à un ordre direct.
Les **indices** ne sont pas détectés par l'outil (seul le mot l'est) : relis les réponses brutes du fichier JSON.

Avec `--trials 2`, chaque niveau repose sur 32 essais seulement : c'est une estimation grossière (quelques
points d'écart ne veulent rien dire). Pour les 2 finalistes, si tu as le temps : `--trials 5`.
Pour changer de modèle sans modifier `.env` : `MODEL=gemma3:4b .venv/bin/python tools/redteam.py --trials 2`.
Les réponses brutes sont enregistrées dans `data/redteam-*.json` : envoie-les moi, je règlerai les prompts d'après.

## Étape 8 — Essai en vrai (15 min)

```bash
./run.sh
```

Le terminal affiche trois adresses et le **jeton admin**. Ouvre :

- `http://127.0.0.1:8000/` : joue une partie complète, comme un étudiant.
- `http://127.0.0.1:8000/board` : le classement (F11 pour le plein écran).
- `http://127.0.0.1:8000/admin` : colle le jeton ; « Vider le classement » efface tes essais.

Fais jouer **3 ou 4 personnes** qui ne connaissent pas le jeu, sans leur expliquer les astuces. Note : combien de
temps l'attente leur a paru longue, quel niveau les bloque, ce qu'ils ont essayé. Dans un autre terminal,
`ollama ps` doit montrer le modèle chargé.

## Étape 9 — Ce que tu m'envoies

1. Le fichier `data/rapport-mesures-….txt` (étape 5).
2. La sortie de `tune.py` (copie-colle le terminal).
3. Le tableau de `redteam.py` et les fichiers `data/redteam-*.json` (étape 7).
4. Tes notes de l'essai avec les joueurs (étape 8).

---

## Si ça ne marche pas

| Symptôme | Cause probable | Solution |
|---|---|---|
| « Ollama ne répond pas » | Le serveur Ollama n'est pas lancé | `sudo systemctl start ollama` ou `ollama serve` |
| « modèle introuvable » | Modèle non téléchargé | `ollama pull NOM` |
| `ModuleNotFoundError: httpx` | Script lancé avec `python3` au lieu du `.venv` | `.venv/bin/python tools/redteam.py …` |
| « Address already in use » | Le port 8000 est pris | `PORT=8001 ./run.sh`, ou `ss -ltnp \| grep 8000` pour voir qui l'occupe |
| Note « Ollama a refusé think » | Ce modèle n'a pas de mode réflexion | Normal : le jeu s'adapte tout seul |
| Mesures très différentes d'un passage à l'autre | Autre application active, ou PC qui chauffe | Ferme tout ; `watch -n2 sensors` (après `sudo apt install lm-sensors`) ; sous ~90 °C c'est bon |
| GPU à 0 % alors que `nvidia-smi` répond | Le modèle ne tient pas / Ollama a choisi le processeur | Regarde `ollama ps` (colonne PROCESSOR) et `journalctl -e -u ollama` ; `tune.py` dira si ça change quelque chose |
| Le jeu affiche « Le gardien dort » | Ollama s'est arrêté | `sudo systemctl restart ollama` |
| Le gardien répond « … » | Réponse vide du modèle | Regarde le terminal du jeu : un message te dit s'il faut `THINK=off` |

## Ce que ces outils ne peuvent PAS te dire

- **La qualité du gardien** (créativité, humour, cohérence) : seul un essai humain la montre.
- **Le comportement exact d'Ollama** : les outils ont été validés contre un faux serveur qui suit la doc, pas
  contre le vrai. Si une sortie te semble absurde, envoie-la moi, ne la devine pas.
- **L'effet de `think: false` sur chaque modèle** : c'est ce que l'étape 5 vérifie pour toi.
