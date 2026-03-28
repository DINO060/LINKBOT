# Configuration pour le bot anime scraper

# Token du bot Telegram (obtiens-le depuis @BotFather)
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

# Configuration Discord (optionnel)
DISCORD_BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

# Paramètres de scraping
SCRAPING_CONFIG = {
    'delay_between_requests': 1,  # Secondes entre chaque requête
    'max_retries': 3,              # Nombre de tentatives en cas d'échec
    'timeout': 10,                 # Timeout des requêtes en secondes
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# Limites
MAX_SEARCH_RESULTS = 10
MAX_ANIME_PER_USER = 1000

# Fichiers de sortie
OUTPUT_DIR = "output"
JSON_OUTPUT = True
CSV_OUTPUT = False
