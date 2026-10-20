# Crack the Bot : installer le projet sur un autre PC

À suivre dans l'ordre, **avec une bonne connexion (wifi)** : les modèles pèsent plusieurs Go. Tout ce qui nécessite
internet doit être fait **avant** l'événement ; le jour J, le jeu fonctionne sans connexion.

## Ce qu'il faut

- Ubuntu 22.04 ou 24.04 (c'est ce qui a été utilisé et testé). Windows et macOS : **non testés**, les scripts sont en bash.
- 16 Go de RAM conseillés, quelques Go de disque libre par modèle (`ollama list` donne les tailles réelles).
- Un processeur récent suffit : **le jeu marche sans carte graphique Nvidia**. Ne touche pas aux pilotes pour ça.
- Un compte GitHub avec accès au dépôt (il est privé : Dhia doit t'ajouter comme collaborateur).

## Installation

```bash
# 1. Outils de base
sudo apt update && sudo apt install -y git curl python3 python3-venv

# 2. Ollama (le moteur qui fait tourner le modèle)
curl -fsSL https://ollama.com/install.sh | sh

# 3. Le modèle du gardien (long : plusieurs Go). Demande à Dhia lequel est choisi ; exemple :
ollama pull gemma3:4b

# 4. Le projet (dépôt privé : Dhia doit t'avoir ajouté comme collaborateur ; accepte l'invitation reçue par e-mail)
sudo apt install -y gh
gh auth login          # choisis GitHub.com, puis HTTPS, puis connexion par le navigateur
gh repo clone DhiaYoussefIssatSo/crack_the_bot crack-the-bot
cd crack-the-bot

# 5. Réglages de ce PC
cp .env.example .env
sed -i 's/^MODEL=[^ ]*/MODEL=gemma3:4b/' .env       # le même modèle que le pull ci-dessus

# 6. Environnement Python (télécharge les bibliothèques, une seule fois)
./run.sh --install
```

## Vérifier que tout marche

```bash
BACKEND=mock ./run.sh        # faux gardien : vérifie l'interface sans modèle. Ouvre http://127.0.0.1:8000/ puis Ctrl+C
python3 tools/check_model.py # vrai modèle : temps d'attente réel sur CE PC (voir GUIDE_TESTS.md)
```

Tests automatiques (facultatif, ils n'ont pas besoin du modèle) :

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

## Lancer en vrai

```bash
bash launcher/installer_raccourci.sh    # crée l'icône ; puis double-clic dessus
```

Utilisation, admin, classement, jour J : `GUIDE_UTILISATION.md`.

## Avant l'événement : le test « sans internet »

Coupe le wifi, lance l'icône, joue une partie complète. Si ça marche, rien ne dépend d'internet.
Si une erreur parle de modèle ou de bibliothèque manquants, refais l'étape correspondante en ligne.

## Travailler à plusieurs sans se marcher dessus

- `.env` et `data/` ne sont **jamais** envoyés dans git (ils sont dans `.gitignore`) : chacun a les siens.
- Une seule personne modifie `app/levels.py` (prompts) à la fois ; toute modification de prompt se re-mesure avec
  `tools/redteam.py` sur le PC du jour J, avec le modèle du jour J.
- Avant de modifier : `git pull`. Après : `.venv/bin/python -m pytest -q`, puis `git add`, `git commit`, `git push`.
- La version qui sera jouée le jour J est marquée par une étiquette (`git tag`, ex. `v1.0`) : ne la déplace pas.
- Les mots secrets possibles sont écrits dans `app/levels.py` : garde le dépôt **privé**, sinon un joueur peut les lire.

## Si ça ne marche pas

| Symptôme | Solution |
|---|---|
| `python3 -m venv` échoue | `sudo apt install python3-venv` |
| `Ollama ne répond pas` | `sudo systemctl start ollama` |
| « modèle introuvable » | `ollama pull NOM` (le même nom que `MODEL=` dans `.env`) |
| `./run.sh: Permission denied` | `chmod +x run.sh launcher/*.sh tools/*.sh` |
| Autre problème | `GUIDE_TESTS.md`, section « Si ça ne marche pas » |
