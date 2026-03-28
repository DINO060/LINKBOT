# 🔐 GUIDE - UTILISATION DU FICHIER .ENV

## 📁 Fichiers créés:

1. **[.env](.env)** - Tes tokens SECRETS (ne partage JAMAIS ce fichier!)
2. **[.env.example](.env.example)** - Template d'exemple
3. **[.gitignore](.gitignore)** - Empêche de commit les secrets
4. **[anime_bot_env.py](anime_bot_env.py)** - Bot qui utilise .env

---

## 🚀 ÉTAPES POUR LANCER LE BOT:

### 1️⃣ Crée ton bot Telegram

Sur Telegram:
1. Cherche **@BotFather**
2. Tape `/newbot`
3. Donne un nom (ex: "My Anime Bot")
4. Donne un username (ex: "myanime_bot")
5. **Copie le TOKEN** qu'il te donne

### 2️⃣ Configure le fichier .env

Ouvre le fichier **[.env](.env)** et change cette ligne:

```env
TELEGRAM_BOT_TOKEN=TON_TOKEN_TELEGRAM_ICI
```

Remplace par ton vrai token:
```env
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 3️⃣ Installe python-dotenv

```bash
pip install python-dotenv
```

Ou installe tout:
```bash
pip install -r requirements.txt
```

### 4️⃣ Lance le bot!

```bash
python anime_bot_env.py
```

---

## 🔒 POURQUOI UTILISER .ENV?

### ❌ AVANT (Token dans le code):
```python
TELEGRAM_TOKEN = "1234567890:ABCdef..."  # Visible dans le code!
```

**Problèmes:**
- Si tu partages le code → tout le monde voit ton token
- Si tu commit sur GitHub → token exposé publiquement
- Difficile de changer le token

### ✅ MAINTENANT (Token dans .env):
```python
from dotenv import load_dotenv
token = os.getenv('TELEGRAM_BOT_TOKEN')  # Lu depuis .env
```

**Avantages:**
- ✅ Token séparé du code
- ✅ Pas dans Git (grâce à .gitignore)
- ✅ Facile à changer
- ✅ Plus sécurisé!

---

## 📝 EXEMPLE DE FICHIER .env:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Catalogue URL (optionnel)
CATALOGUE_URL=https://mon-site.com/catalogue

# Paramètres
MAX_SEARCH_RESULTS=20
RATE_LIMIT_DELAY=1
```

---

## ⚠️ IMPORTANT:

1. **NE PARTAGE JAMAIS** le fichier `.env`
2. Le `.gitignore` empêche de le commit sur Git
3. Partage plutôt `.env.example` (sans les vrais tokens)
4. Chaque personne doit créer son propre `.env`

---

## 🎯 UTILISATION:

### Bot Anime (avec .env):
```bash
python anime_bot_env.py
```

### Bot Simple (catalogue):
Tu peux aussi mettre ton URL de catalogue dans `.env`:
```env
CATALOGUE_URL=https://ton-site.com
```

---

## 🛠️ COMMANDES RAPIDES:

```bash
# Installer les dépendances
pip install -r requirements.txt

# Lancer le bot anime
python anime_bot_env.py

# Tester l'API
python anime_api.py
```

---

## ✅ CHECKLIST:

- [ ] Créer un bot sur @BotFather
- [ ] Copier le token
- [ ] Ouvrir le fichier .env
- [ ] Coller le token dans .env
- [ ] Sauvegarder .env
- [ ] Lancer: `pip install python-dotenv`
- [ ] Lancer: `python anime_bot_env.py`
- [ ] Aller sur Telegram et taper /start

---

C'est tout! Ton bot est maintenant sécurisé! 🔐
