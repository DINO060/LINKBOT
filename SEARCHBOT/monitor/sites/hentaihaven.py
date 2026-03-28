"""
monitor/sites/hentaihaven.py
=============================
Scraper spécifique pour HentaiHaven (hentaihaven.xxx).

Page latest : https://hentaihaven.xxx/latest/
Structure :
  - Cards avec classe .postCardContainer ou similaire
  - Chaque card contient : lien, image, titre, numéro d'épisode

Enregistré automatiquement via register_scraper().
"""

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from monitor.sites.base import BaseSiteScraper, register_scraper

logger = logging.getLogger(__name__)

_DOMAIN = "hentaihaven.xxx"


class HentaiHavenScraper(BaseSiteScraper):
    """Scraper optimisé pour hentaihaven.xxx."""

    LATEST_PATH = "/latest/"
    MAX_ITEMS = 12
    USE_PLAYWRIGHT = True  # Site React/JS — Playwright nécessaire

    def fetch_latest(self) -> list[dict]:
        """Scrape la page /latest/ et retourne les nouveaux épisodes."""
        logger.info("[hentaihaven] Scraping /latest/ …")
        html = self._fetch_playwright(self.base_url + self.LATEST_PATH)

        if not html or len(html) < 1000:
            # Fallback : essayer HTTPX
            html = self._fetch(self.base_url + self.LATEST_PATH)

        if not html:
            logger.warning("[hentaihaven] Impossible de récupérer la page latest")
            return []

        return self._parse_cards(html)

    def _parse_cards(self, html: str) -> list[dict]:
        """Parse les cartes d'épisodes sur la page latest."""
        soup = BeautifulSoup(html, "lxml")
        results = []
        seen: set[str] = set()

        # Sélecteurs potentiels (le site peut changer sa structure)
        card_selectors = [
            "article",
            ".postCard",
            ".post-card",
            ".episode-card",
            ".video-card",
            "[class*='card']",
            "[class*='episode']",
            "[class*='latest']",
        ]

        cards = []
        for sel in card_selectors:
            cards = soup.select(sel)
            if len(cards) >= 3:
                break

        if not cards:
            # Fallback : extraire tous les liens de contenu
            logger.debug("[hentaihaven] Fallback extraction générique")
            return super().fetch_latest()

        for card in cards[: self.MAX_ITEMS]:
            # Lien
            link = card.find("a", href=True)
            if not link:
                continue

            href = link.get("href", "")
            if href.startswith("/"):
                url = self.base_url + href
            elif href.startswith("http"):
                url = href
            else:
                continue

            if url in seen or self.domain not in url:
                continue
            seen.add(url)

            # Titre
            title = ""
            for tag in ["h2", "h3", "h4", ".title", "[class*='title']"]:
                el = card.select_one(tag)
                if el:
                    title = el.get_text(strip=True)
                    break
            if not title:
                title = link.get_text(strip=True)

            # Cover
            cover = None
            img = card.find("img")
            if img:
                cover = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
                if cover and cover.startswith("/"):
                    cover = self.base_url + cover

            # Numéro d'épisode (depuis le titre ou l'URL)
            ep_number = None
            m = re.search(r"(?:ep(?:isode)?\.?\s*|episode[-_\s])(\d+)", title + " " + url, re.IGNORECASE)
            if m:
                ep_number = int(m.group(1))

            results.append({
                "title": title,
                "cover": cover,
                "synopsis": "",       # Rempli par meta_scraper si nécessaire
                "url": url,
                "domain": self.domain,
                "episode_number": ep_number,
                "episode_count": None,
                "episode_duration": None,
            })

        # Enrichit le synopsis via meta_scraper si peu de résultats
        if results and not results[0].get("synopsis"):
            from bot.meta_scraper import scrape_metadata
            for item in results[:5]:  # Enrichit seulement les 5 premiers
                try:
                    meta = scrape_metadata(item["url"], force_playwright=True)
                    if meta.get("synopsis"):
                        item["synopsis"] = meta["synopsis"]
                    if meta.get("cover") and not item["cover"]:
                        item["cover"] = meta["cover"]
                except Exception:
                    pass

        logger.info("[hentaihaven] %d épisodes trouvés", len(results))
        return results


# Enregistrement automatique
register_scraper(_DOMAIN, HentaiHavenScraper)
register_scraper("www.hentaihaven.xxx", HentaiHavenScraper)
