# 🎯 GUIDE RAPIDE - SCRAPER DE CATALOGUE

## ⚡ OPTION 1: Script Simple (Sans bot)

### 📝 Utilise: `scraper_simple.py`

1. **Ouvre le fichier `scraper_simple.py`**

2. **Change cette ligne (ligne 8):**
```python
CATALOGUE_URL = "https://ton-site-catalogue.com"  # <-- METS TON LIEN ICI!
```

3. **Optionnel - Si tu veux chercher quelque chose de précis (ligne 11):**
```python
MOT_CLE = "gaming"  # Ou laisse vide pour tout
```

4. **Lance le script:**
```bash
python scraper_simple.py
```

5. **Résultat:**
   - `resultats_catalogue.json` (fichier JSON avec tous les sites)
   - `resultats_catalogue.txt` (fichier texte lisible)

---

## 🤖 OPTION 2: Bot Telegram

### 📝 Utilise: `bot_simple.py`

1. **Crée un bot Telegram:**
   - Va sur [@BotFather](https://t.me/botfather)
   - Tape `/newbot`
   - Suis les instructions
   - Copie le TOKEN

2. **Ouvre le fichier `bot_simple.py`**

3. **Change ces 2 lignes (lignes 8-9):**
```python
TELEGRAM_TOKEN = "123456:ABC-DEF..."  # <-- Token de BotFather
CATALOGUE_URL = "https://ton-site-catalogue.com"  # <-- Ton catalogue
```

4. **Lance le bot:**
```bash
python bot_simple.py
```

5. **Sur Telegram, utilise:**
```
/start
/search gaming
/all
```

---

## 📍 Où mettre ton lien?

### Dans `scraper_simple.py`:
```python
# LIGNE 8 - ICI! 👇
CATALOGUE_URL = "https://TON-LIEN-ICI.com"
```

### Dans `bot_simple.py`:
```python
# LIGNE 9 - ICI! 👇
CATALOGUE_URL = "https://TON-LIEN-ICI.com"
```

---

## 🚀 Exemple complet:

Si ton catalogue est: `https://example.com/sitelist`

### Fichier `scraper_simple.py`:
```python
CATALOGUE_URL = "https://example.com/sitelist"
MOT_CLE = ""  # Vide = tout extraire
MAX_RESULTATS = 50
```

### Fichier `bot_simple.py`:
```python
TELEGRAM_TOKEN = "1234567890:ABCdef..."
CATALOGUE_URL = "https://example.com/sitelist"
```

---

## 💡 C'est tout!

- **1 ligne à changer** dans chaque fichier
- **C'est marqué en gros en haut** avec des étoiles ⭐
- **Tu peux pas te tromper!** 😎

---

## ❓ Problèmes?

- **Erreur "Module not found"**: Lance `pip install requests beautifulsoup4 python-telegram-bot`
- **Bot ne répond pas**: Vérifie ton TOKEN Telegram
- **Aucun site trouvé**: Vérifie que ton URL de catalogue est correcte
