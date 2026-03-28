"""
monitor/sites/reddit.py
========================
Scraper monitor pour les subreddits Reddit publics.

Utilise l'API JSON publique Reddit (aucune auth requise) :
  GET https://www.reddit.com/r/<sub>/new.json?limit=25

Usage :
  /addsite https://reddit.com/r/anime
  → domain stocké : "reddit.com/r/anime"
  → surveille les nouveaux posts du subreddit

Items retournés au format standard BaseSiteScraper :
{
    "title"           : titre du post,
    "cover"           : image miniature ou preview (peut être None),
    "synopsis"        : texte du post (selftext) ou URL linkée,
    "url"             : lien vers le post (reddit.com/r/.../comments/...),
    "domain"          : "reddit.com/r/<subreddit>",
    "episode_number"  : score du post (upvotes),
    "episode_count"   : None,
    "episode_duration": None,
}
"""

import logging
import time

import httpx

from monitor.sites.base import BaseSiteScraper, register_scraper

logger = logging.getLogger(__name__)

_DOMAIN_BASE = "reddit.com"

_HEADERS = {
    "User-Agent": "SEARCHBOT/1.0 (monitor; +https://github.com/searchbot)",
    "Accept":     "application/json",
}


class RedditScraper(BaseSiteScraper):
    """Scraper pour un subreddit Reddit public via l'API JSON."""

    MAX_ITEMS = 20

    def __init__(self, site_entry: dict):
        super().__init__(site_entry)
        # domain = "reddit.com/r/anime" → extraire le subreddit
        parts = self.domain.split("/r/", 1)
        self.subreddit = parts[1].lower() if len(parts) == 2 else ""

    def fetch_latest(self) -> list[dict]:
        if not self.subreddit:
            logger.warning("[reddit] subreddit non détecté dans domain=%s", self.domain)
            return []

        logger.info("[reddit] Scraping /r/%s …", self.subreddit)
        items = self._fetch_json_api()
        logger.info("[reddit] /r/%s → %d post(s)", self.subreddit, len(items))
        return items

    def _fetch_json_api(self) -> list[dict]:
        """Récupère les derniers posts via l'API JSON Reddit."""
        api_url = f"https://www.reddit.com/r/{self.subreddit}/new.json?limit=25"
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=15, http2=True) as client:
                resp = client.get(api_url)

            if resp.status_code == 429:
                logger.warning("[reddit] Rate-limit (429) sur /r/%s", self.subreddit)
                return []
            if resp.status_code == 403:
                logger.warning("[reddit] Subreddit privé ou banni : /r/%s", self.subreddit)
                return []
            if resp.status_code != 200:
                logger.warning("[reddit] HTTP %d pour /r/%s", resp.status_code, self.subreddit)
                return []

            data = resp.json()
        except Exception as exc:
            logger.error("[reddit] Erreur API /r/%s : %s", self.subreddit, exc)
            return []

        posts = data.get("data", {}).get("children", [])
        items = []

        for child in posts:
            post = child.get("data", {})

            # Ignorer les posts supprimés/masqués
            if post.get("removed_by_category") or post.get("hidden"):
                continue

            title   = post.get("title", "").strip()
            post_id = post.get("id", "")
            url     = f"https://www.reddit.com{post.get('permalink', '')}"
            score   = post.get("score", 0)
            # Date de création (timestamp UNIX)
            created = int(post.get("created_utc", 0))
            pub_date = time.strftime("%Y-%m-%d", time.gmtime(created)) if created else ""

            # Cover : preview image > thumbnail
            cover = None
            preview = post.get("preview", {})
            if preview:
                images = preview.get("images", [])
                if images:
                    src = images[0].get("source", {})
                    cover_url = src.get("url", "").replace("&amp;", "&")
                    if cover_url.startswith("http"):
                        cover = cover_url
            if not cover:
                thumb = post.get("thumbnail", "")
                if thumb and thumb.startswith("http"):
                    cover = thumb

            # Synopsis : selftext ou URL externe
            selftext = post.get("selftext", "").strip()[:500]
            if selftext:
                synopsis = selftext
            else:
                ext_url = post.get("url", "")
                synopsis = ext_url if ext_url != url else ""

            if not title:
                continue

            items.append({
                "title":            title,
                "cover":            cover,
                "synopsis":         synopsis,
                "url":              url,
                "domain":           self.domain,
                "episode_number":   score,
                "episode_count":    None,
                "episode_duration": None,
                "date":             pub_date,
            })

            if len(items) >= self.MAX_ITEMS:
                break

        # Trier du plus récent au plus ancien (ordre naturel de /new)
        return items


# Pas de register_scraper() classique ici : la détection se fait via
# domain.startswith("reddit.com/r/") dans base.get_scraper_for()
