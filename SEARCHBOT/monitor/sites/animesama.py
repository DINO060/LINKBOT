"""
monitor/sites/animesama.py — lightweight scraper
Appelle Playwright UNE SEULE FOIS sur la homepage, parse les cards
directement via BeautifulSoup. Aucun appel à scrape_series_page().
"""
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from monitor.sites.base import BaseSiteScraper, register_scraper

logger = logging.getLogger(__name__)

_DOMAIN = "anime-sama.to"
_CATALOGUE_RE  = re.compile(r"/catalogue/([^/]+)/?", re.IGNORECASE)
_SAISON_NUM_RE = re.compile(r"saison[-_]?(\d+)", re.IGNORECASE)
_SKIP_SLUGS    = {"catalogue", "anime", "manga", "film", "hentai", "series"}


class AnimeSamaScraper(BaseSiteScraper):
    """Scraper léger pour anime-sama.to — parse les cards de la homepage."""

    LATEST_PATH = "/"
    MAX_ITEMS   = 12
    USE_PLAYWRIGHT = True

    def fetch_latest(self) -> list[dict]:
        logger.info("[anime-sama] Scraping homepage …")
        html = self._fetch_playwright(self.base_url + "/", timeout_ms=25_000)
        if not html or len(html) < 2000:
            logger.info("[anime-sama] Playwright vide, fallback HTTP …")
            html = self._fetch(self.base_url + "/")
        if not html:
            logger.warning("[anime-sama] Homepage inaccessible")
            return []
        items = self._parse_latest(html)
        logger.info("[anime-sama] %d item(s) extraits", len(items))
        return items

    # ── parsing ────────────────────────────────────────────────────────────

    def _parse_latest(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        results: list[dict] = []
        seen_slugs: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href:
                continue

            # Construire URL absolue
            if href.startswith("http"):
                url = href
            elif href.startswith("//"):
                url = "https:" + href
            elif href.startswith("/"):
                url = self.base_url + href
            else:
                url = urljoin(self.base_url + "/", href)

            if _DOMAIN not in urlparse(url).netloc:
                continue

            m = _CATALOGUE_RE.search(urlparse(url).path)
            if not m:
                continue
            slug = m.group(1)
            if len(slug) < 2 or slug in _SKIP_SLUGS or slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            series_url = f"{self.base_url}/catalogue/{slug}/"
            title  = self._extract_title(a) or slug.replace("-", " ").title()
            cover  = self._extract_cover(a)
            sm     = _SAISON_NUM_RE.search(href)
            saison = int(sm.group(1)) if sm else None

            results.append({
                "title":            title,
                "cover":            cover,
                "synopsis":         "",
                "url":              series_url,
                "domain":           _DOMAIN,
                "episode_number":   saison,
                "episode_count":    None,
                "episode_duration": None,
            })
            if len(results) >= self.MAX_ITEMS:
                break

        return results

    def _extract_title(self, a_tag) -> str:
        text = a_tag.get_text(strip=True)
        if text and 1 < len(text) < 100:
            return text
        for parent in a_tag.parents:
            if parent.name in ("article", "div", "li", "section"):
                for tag in ("h2", "h3", "h4", "h5"):
                    el = parent.find(tag)
                    if el:
                        t = el.get_text(strip=True)
                        if t and len(t) < 100:
                            return t
                break
        return ""

    def _extract_cover(self, a_tag) -> str | None:
        img = a_tag.find("img")
        if img:
            src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
            if src:
                return src if src.startswith("http") else self.base_url + src
        for parent in a_tag.parents:
            if parent.name in ("article", "div", "li"):
                img = parent.find("img")
                if img:
                    src = img.get("src") or img.get("data-src")
                    if src:
                        return src if src.startswith("http") else self.base_url + src
                break
        return None


# Enregistrement automatique
register_scraper(_DOMAIN, AnimeSamaScraper)
register_scraper("www.anime-sama.to", AnimeSamaScraper)
