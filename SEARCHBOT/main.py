"""
SEARCHBOT — main.py
====================
Point d'entrée du bot.

Lancement :
    python main.py

Commandes disponibles :
    /addsite <url>      — Enregistre un site à surveiller
    /listsites          — Liste les sites enregistrés
    /removesite <domain>— Supprime un site
    /search <query>     — Cherche sur les sites enregistrés (résultats enrichis)
    /usearch <query>    — Recherche universelle via DuckDuckGo (pas limité aux sites enregistrés)
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN manquant dans .env — impossible de démarrer.")
        sys.exit(1)

    from bot.telegram_bot import run_bot
    run_bot(token)


if __name__ == "__main__":
    main()
