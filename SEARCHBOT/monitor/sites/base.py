"""
monitor/sites/base.py
======================
Classe de base pour scraper les nouveaux contenus d'un site.

Chaque site peut implémenter sa propre sous-classe en overridant :
  - LATEST_PATH   : chemin de la page "dernières sorties"
  - fetch_latest(): logique de scraping spécifique

Le fallback générique tente plusieurs URLs communes (/latest, /newest, etc.)
et extrait les liens qui ressemblent à des épisodes/chapitres.

Usage :
    from monitor.sites.base import BaseSiteScraper, get_scraper_for
    scraper = get_scraper_for({"domain": "hentaihaven.xxx", "url": "https://hentaihaven.xxx"})
    items = scraper.fetch_latest()
    # items = [{"title": ..., "cover": ..., "synopsis": ..., "episode_number": ..., "url": ...}, ...]
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# User-agent partagé avec meta_scraper
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="133", "Google Chrome";v="133", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "DNT": "1",
    "Connection": "keep-alive",
}

# Chemins à tester pour trouver la page "nouveautés"
_GENERIC_LATEST_PATHS = [
    "/latest",
    "/newest",
    "/new",
    "/recent",
    "/updates",
    "/new-episodes",
    "/latest-episodes",
    "/new-release",
    "/",
]

# Patterns d'URL qui indiquent un lien de contenu (épisode, chapitre, etc.)
_CONTENT_URL_RE = re.compile(
    r"(/watch/|/episode/|/ep/|/read/|/chapter/|/video/|/stream/"
    r"|ep[-_]?\d+|episode[-_]\d+|chapter[-_]\d+)",
    re.IGNORECASE,
)


class BaseSiteScraper:
    """
    Scraper générique — fonctionne sur la plupart des sites statiques.
    À sous-classer pour les sites nécessitant une logique spécifique.
    """

    # Sous-classes peuvent override ces valeurs
    LATEST_PATH: str | None = None   # ex: "/latest"
    MAX_ITEMS: int = 15              # Nombre max de liens à analyser
    USE_PLAYWRIGHT: bool = False     # Utiliser Playwright (sites JS)

    def __init__(self, site_entry: dict):
        """
        site_entry : entrée du registre SiteRegistry
            {"domain": "hentaihaven.xxx", "url": "https://hentaihaven.xxx", ...}
        """
        self.domain: str = site_entry["domain"]
        self.base_url: str = site_entry["url"].rstrip("/")

    # ── API publique ──────────────────────────────────────────────────────────

    def fetch_latest(self) -> list[dict]:
        """
        Point d'entrée principal.
        Retourne une liste d'items récents, chacun sous la forme :
        {
            "title"           : str,
            "cover"           : str | None,
            "synopsis"        : str,
            "url"             : str,
            "domain"          : str,
            "episode_number"  : int | None,
            "episode_count"   : int | None,
            "episode_duration": str | None,
        }
        """
        html = self._get_latest_page()
        if not html:
            logger.warning("[%s] Impossible de récupérer la page latest", self.domain)
            return []

        links = self._extract_content_links(html)
        logger.info("[%s] %d liens de contenu trouvés", self.domain, len(links))

        if not links:
            return []

        # Enrichit chaque lien avec les métadonnées complètes
        from bot.meta_scraper import scrape_metadata
        results = []
        for url in links[: self.MAX_ITEMS]:
            try:
                meta = scrape_metadata(url, force_playwright=self.USE_PLAYWRIGHT)
                if meta.get("title"):
                    results.append(meta)
            except Exception as e:
                logger.debug("[%s] Erreur métadonnées %s : %s", self.domain, url, e)

        return results

    # ── Fetch ─────────────────────────────────────────────────────────────────

    def _get_latest_page(self) -> str | None:
        """Récupère le HTML de la page des nouveautés."""
        if self.LATEST_PATH:
            paths = [self.LATEST_PATH]
        else:
            paths = _GENERIC_LATEST_PATHS

        for path in paths:
            url = self.base_url + path
            html = self._fetch(url)
            if html and len(html) > 3000:
                logger.debug("[%s] Page latest : %s", self.domain, url)
                return html

        return None

    def _fetch(self, url: str, timeout: int = 15) -> str | None:
        """Fetch HTTP simple via HTTPX."""
        try:
            with httpx.Client(
                headers=_HEADERS,
                follow_redirects=True,
                timeout=timeout,
                http2=True,
            ) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    return resp.text
                logger.debug("[%s] HTTP %d pour %s", self.domain, resp.status_code, url)
        except Exception as e:
            logger.debug("[%s] Fetch échoué %s : %s", self.domain, url, e)
        return None

    def _fetch_playwright(self, url: str, timeout_ms: int = 20_000) -> str | None:
        """Fetch JS via Playwright (headless Chromium) avec Stealth anti-bot."""
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import Stealth
            _stealth = Stealth(navigator_platform_override="Win32")
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                    ],
                )
                page = browser.new_page(
                    user_agent=_UA,
                    viewport={"width": 1280, "height": 720},
                )
                _stealth.apply_stealth_sync(page)  # masque navigator.webdriver
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=6_000)
                    except Exception:
                        pass
                except Exception:
                    pass
                html = page.content()
                browser.close()
                return html
        except Exception as e:
            logger.debug("[%s] Playwright échoué %s : %s", self.domain, url, e)
            return None

    # ── Extraction des liens ──────────────────────────────────────────────────

    def _extract_content_links(self, html: str) -> list[str]:
        """
        Extrait les liens qui ressemblent à des pages de contenu
        (épisodes, chapitres, vidéos...) depuis le HTML.
        """
        soup = BeautifulSoup(html, "lxml")
        seen: set[str] = set()
        links: list[str] = []

        for a in soup.find_all("a", href=True):
            href: str = a.get("href", "").strip()
            if not href or href.startswith("#") or href.startswith("javascript:"):
                continue

            # Convertir en URL absolue
            if href.startswith("http"):
                url = href
            elif href.startswith("//"):
                url = "https:" + href
            elif href.startswith("/"):
                url = self.base_url + href
            else:
                url = urljoin(self.base_url + "/", href)

            # Garder seulement les URLs du même domaine
            parsed = urlparse(url)
            if self.domain not in parsed.netloc:
                continue

            # Vérifier si l'URL ressemble à du contenu
            if _CONTENT_URL_RE.search(url) and url not in seen:
                seen.add(url)
                links.append(url)

        return links


# ── Registry des scrapers spécifiques ────────────────────────────────────────

# Mapping domain → classe scraper
# Rempli automatiquement par les imports des modules spécifiques
_SCRAPERS: dict[str, type[BaseSiteScraper]] = {}


def register_scraper(domain: str, cls: type[BaseSiteScraper]) -> None:
    """Enregistre un scraper spécifique pour un domaine."""
    _SCRAPERS[domain] = cls


def get_scraper_for(site_entry: dict) -> BaseSiteScraper:
    """
    Retourne le scraper spécifique pour un site, ou le generic en fallback.

    Usage :
        scraper = get_scraper_for(registry_entry)
        items = scraper.fetch_latest()
    """
    domain = site_entry.get("domain", "")

    # Charger les scrapers spécifiques (import one-time)
    _load_specific_scrapers()

    # Canaux Telegram publics : domaine de type "t.me/nomcanal"
    if domain.startswith("t.me/"):
        from monitor.sites.telegram_channel import TelegramChannelScraper
        logger.debug("Scraper pour %s : TelegramChannelScraper", domain)
        return TelegramChannelScraper(site_entry)

    # Subreddits Reddit : domaine de type "reddit.com/r/anime"
    if domain.startswith("reddit.com/r/"):
        from monitor.sites.reddit import RedditScraper
        logger.debug("Scraper pour %s : RedditScraper", domain)
        return RedditScraper(site_entry)

    # Comptes Twitter/X : domaine de type "twitter.com/username"
    if domain.startswith("twitter.com/") or domain.startswith("x.com/"):
        from monitor.sites.twitter_nitter import TwitterNitterScraper
        logger.debug("Scraper pour %s : TwitterNitterScraper", domain)
        return TwitterNitterScraper(site_entry)

    cls = _SCRAPERS.get(domain, BaseSiteScraper)
    logger.debug("Scraper pour %s : %s", domain, cls.__name__)
    return cls(site_entry)


_scrapers_loaded = False


def _load_specific_scrapers() -> None:
    """Import lazy des scrapers spécifiques pour les enregistrer."""
    global _scrapers_loaded
    if _scrapers_loaded:
        return
    try:
        from monitor.sites import hentaihaven      # noqa: F401
        from monitor.sites import hanime           # noqa: F401
        from monitor.sites import animesama        # noqa: F401
        from monitor.sites import reddit           # noqa: F401
        from monitor.sites import twitter_nitter   # noqa: F401
    except ImportError as e:
        logger.warning("Erreur chargement scrapers spécifiques : %s", e)
    _scrapers_loaded = True
