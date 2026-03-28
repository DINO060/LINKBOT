# 🎌 Anime Scraper Bot

Bot pour scraper des informations d'animes depuis MyAnimeList et les envoyer via Telegram!

## 🚀 Fonctionnalités

- 🔍 **Recherche d'animes** par nom
- 👤 **Scraper la liste complète** d'un utilisateur MyAnimeList
- 📝 **Obtenir les détails** d'un anime spécifique (synopsis, score, genres, etc.)
- 💾 **Export en JSON** de toutes les données
- 🤖 **Bot Telegram** pour interagir facilement

## 📦 Installation

1. **Clone ou télécharge ce repo**

2. **Installe les dépendances:**
```bash
pip install -r requirements.txt
```

3. **Configure ton bot Telegram:**
   - Va sur Telegram et parle à [@BotFather](https://t.me/botfather)
   - Crée un nouveau bot avec `/newbot`
   - Copie le token que BotFather te donne
   - Colle-le dans `config.py` ou `telegram_bot.py`

## 🎮 Utilisation

### Option 1: Utiliser le scraper directement (Python)

```python
from anime_scraper import AnimeScraper

scraper = AnimeScraper()

# Rechercher un anime
results = scraper.search_anime("Naruto", limit=5)
print(results)

# Obtenir la liste d'un utilisateur
animes = scraper.scrape_myanimelist_user("username")
scraper.save_to_json(animes, "my_animelist.json")

# Détails d'un anime spécifique
details = scraper.scrape_anime_details(1535)  # Death Note
print(details)
```

### Option 2: Utiliser le bot Telegram

1. **Démarre le bot:**
```bash
python telegram_bot.py
```

2. **Sur Telegram, utilise ces commandes:**

- `/start` - Démarre le bot
- `/search Naruto` - Recherche un anime
- `/user username` - Obtient la liste d'un utilisateur MAL
- `/details 1535` - Détails d'un anime par son ID
- Ou envoie juste le nom d'un anime!

## 📋 Exemples de commandes

### Rechercher un anime
```
/search One Piece
```
ou simplement:
```
One Piece
```

### Obtenir la liste d'un utilisateur
```
/user Xinil
```

### Détails d'un anime spécifique
```
/details 5114
```

## 🛠️ Configuration

Édite `config.py` pour personnaliser:

- Token du bot Telegram
- Délai entre les requêtes (pour éviter le rate limiting)
- Nombre maximum de résultats
- Options d'export (JSON, CSV)

## 📚 Structure du projet

```
├── anime_scraper.py      # Classe principale de scraping
├── telegram_bot.py       # Bot Telegram
├── config.py            # Configuration
├── requirements.txt     # Dépendances Python
└── README.md           # Ce fichier
```

## ⚠️ Notes importantes

1. **Rate Limiting:** Le scraper inclut des délais entre les requêtes pour éviter d'être bloqué
2. **Utilisation responsable:** Respecte les règles de MyAnimeList et ne spam pas
3. **Données publiques uniquement:** Le bot ne peut accéder qu'aux listes publiques

## 🔧 Dépendances

- `requests` - Pour les requêtes HTTP
- `beautifulsoup4` - Pour parser le HTML
- `python-telegram-bot` - Pour le bot Telegram
- `lxml` - Parser HTML rapide

## 🤝 Contribution

N'hésite pas à améliorer le code, ajouter des fonctionnalités ou corriger des bugs!

## 📝 TODO

- [ ] Support pour AniList
- [ ] Support pour Discord bot
- [ ] Export en CSV
- [ ] Système de cache
- [ ] API REST
- [ ] Interface web

## ⚖️ Disclaimer

Ce bot est fait à des fins éducatives. Assure-toi de respecter les conditions d'utilisation des sites que tu scrapes.

## 🎉 Profite bien!

Si tu as des questions ou des problèmes, n'hésite pas!
