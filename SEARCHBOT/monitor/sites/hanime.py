"""
monitor/sites/hanime.py
========================
Scraper spécifique pour Hanime.tv.

Page latest : https://hanime.tv/videos?sort=created_at_unix&order=desc
Structure JSON via API :
  GET https://hanime.tv/api/v8/search?...
  → JSON avec champ `hentai_videos`

Enregistré automatiquement via register_scraper().
"""

import logging
import re

import httpx

from monitor.sites.base import BaseSiteScraper, register_scraper

logger = logging.getLogger(__name__)

_DOMAIN = "hanime.tv"

# Endpoint API Hanime (plus fiable que le scraping HTML)
_API_ENDPOINT = "https://hanime.tv/api/v8/search"
_API_PARAMS = {
    "ordering": "created_at_unix",
    "page": "0",
    "tags_mode": "AND",
}

_HEADERS_API = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://hanime.tv/",
    "sec-ch-ua": '"Chromium";v="133", "Google Chrome";v="133", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
    "DNT": "1",
}


class HanimeScraper(BaseSiteScraper):
    """Scraper optimisé pour hanime.tv (via API JSON)."""

    LATEST_PATH = "/videos?sort=created_at_unix&order=desc"
    MAX_ITEMS = 12
    USE_PLAYWRIGHT = True

    def fetch_latest(self) -> list[dict]:
        """Tente d'abord l'API JSON, fallback sur Playwright si échec."""
        logger.info("[hanime] Tentative via API JSON …")

        results = self._fetch_via_api()
        if results:
            return results

        logger.info("[hanime] API échouée — fallback Playwright …")
        return self._fetch_via_playwright()

    # ── Méthode 1 : API JSON ─────────────────────────────────────────────────

    def _fetch_via_api(self) -> list[dict]:
        """Récupère les derniers épisodes via l'API JSON de Hanime."""
        try:
            with httpx.Client(
                headers=_HEADERS_API,
                follow_redirects=True,
                timeout=15,
                http2=True,
            ) as client:
                resp = client.get(_API_ENDPOINT, params=_API_PARAMS)
                if resp.status_code != 200:
                    logger.debug("[hanime] API HTTP %d", resp.status_code)
                    return []

                data = resp.json()
        except Exception as e:
            logger.debug("[hanime] Erreur API : %s", e)
            return []

        videos = data.get("hentai_videos", [])
        if not videos:
            return []

        results = []
        for v in videos[: self.MAX_ITEMS]:
            slug = v.get("slug", "")
            url = f"https://hanime.tv/videos/hentai/{slug}" if slug else ""
            if not url:
                continue

            # Cover
            cover = (
                v.get("cover_url")
                or v.get("poster_url")
                or v.get("thumbnail_url")
            )

            # Épisode
            ep_number = v.get("episode")
            if ep_number is None:
                m = re.search(r"[-_ ](\d+)$", slug)
                if m:
                    ep_number = int(m.group(1))

            results.append({
                "title":            v.get("name", slug),
                "cover":            cover,
                "synopsis":         (v.get("description") or "")[:400],
                "url":              url,
                "domain":           _DOMAIN,
                "episode_number":   ep_number,
                "episode_count":    None,
                "episode_duration": f"{v.get('duration_in_ms', 0) // 60000} min"
                                    if v.get("duration_in_ms") else None,
            })

        logger.info("[hanime] %d épisodes via API", len(results))
        return results

    # ── Méthode 2 : Playwright fallback ─────────────────────────────────────

    def _fetch_via_playwright(self) -> list[dict]:
        """Scrape la page /videos via Playwright."""
        url = self.base_url + self.LATEST_PATH
        html = self._fetch_playwright(url, timeout_ms=25_000)

        if not html or len(html) < 1000:
            logger.warning("[hanime] Playwright n'a rien retourné")
            return []

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        results = []
        seen: set[str] = set()

        # Cartes Hanime : généralement des <a> avec href /videos/hentai/slug
        for a in soup.find_all("a", href=re.compile(r"/videos/hentai/")):
            href = a.get("href", "")
            video_url = "https://hanime.tv" + href if href.startswith("/") else href

            if video_url in seen:
                continue
            seen.add(video_url)

            title = a.get_text(strip=True) or href.split("/")[-1].replace("-", " ").title()
            img = a.find("img")
            cover = None
            if img:
                cover = img.get("src") or img.get("data-src") or img.get("data-lazy-src")

            ep_number = None
            m = re.search(r"[-_ ](\d+)$", href.split("/")[-1])
            if m:
                ep_number = int(m.group(1))

            results.append({
                "title":            title,
                "cover":            cover,
                "synopsis":         "",
                "url":              video_url,
                "domain":           _DOMAIN,
                "episode_number":   ep_number,
                "episode_count":    None,
                "episode_duration": None,
            })

            if len(results) >= self.MAX_ITEMS:
                break

        logger.info("[hanime] %d épisodes via Playwright", len(results))
        return results


# Enregistrement automatique
register_scraper(_DOMAIN, HanimeScraper)
register_scraper("www.hanime.tv", HanimeScraper)
