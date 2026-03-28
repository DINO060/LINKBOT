"""
monitor/sites/animesama.py — lightweight scraper
Appelle Playwright UNE SEULE FOIS sur la homepage, parse les cards
directement via BeautifulSoup. Enrichit les premiers items avec
synopsis/genres depuis leur page catalogue.
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

# Nombre d'items enrichis (synopsis/genres) par check
_ENRICH_COUNT = 5


class AnimeSamaScraper(BaseSiteScraper):
    """Scraper pour anime-sama.to — parse les cards de la homepage."""

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

        # Enrichir les premiers items avec synopsis/genres
        self._enrich_items(items, count=_ENRICH_COUNT)

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
            season = int(sm.group(1)) if sm else None

            results.append({
                "title":            title,
                "cover":            cover,
                "synopsis":         "",
                "genres":           [],
                "url":              series_url,
                "domain":           _DOMAIN,
                "season_number":    season,
                "episode_number":   None,
                "episode_count":    None,
                "episode_duration": None,
                "content_type":     "season" if season else "anime",
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

    # ── enrichissement ─────────────────────────────────────────────────────

    def _enrich_items(self, items: list[dict], count: int = 5) -> None:
        """Enrichit les N premiers items avec synopsis/genres depuis leur page catalogue."""
        for item in items[:count]:
            try:
                self._enrich_single(item)
            except Exception as exc:
                logger.debug("[anime-sama] Enrichissement échoué %s : %s",
                             item.get("url"), exc)

    def _enrich_single(self, item: dict) -> None:
        """Scrape la page catalogue d'un item pour extraire synopsis et genres."""
        url = item.get("url", "")
        if not url:
            return

        html = self._fetch(url, timeout=10)
        if not html or len(html) < 1000:
            return

        soup = BeautifulSoup(html, "lxml")

        # Synopsis — cherche les conteneurs courants
        if not item.get("synopsis"):
            for sel in (".synopsis", ".description", ".summary",
                        "[class*='synopsis']", "[class*='description']",
                        "p.desc", ".info p"):
                el = soup.select_one(sel)
                if el:
                    txt = el.get_text(separator=" ", strip=True)
                    if len(txt) > 40:
                        item["synopsis"] = txt[:1500]
                        break
            # Fallback: meta description
            if not item.get("synopsis"):
                meta = soup.find("meta", attrs={"name": "description"})
                if meta and meta.get("content"):
                    txt = meta["content"].strip()
                    if len(txt) > 40:
                        item["synopsis"] = txt[:1500]

        # Genres
        if not item.get("genres"):
            for sel in (".genres a", ".genre a", "[class*='genre'] a",
                        ".tags a", ".categories a"):
                tags = soup.select(sel)
                found = [t.get_text(strip=True) for t in tags
                         if t.get_text(strip=True) and len(t.get_text(strip=True)) < 30]
                if found:
                    item["genres"] = found[:10]
                    break

        # Cover fallback si la homepage n'en avait pas
        if not item.get("cover"):
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                item["cover"] = og_img["content"]

        logger.debug("[anime-sama] Enrichi %s → synopsis=%d genres=%d",
                     url, len(item.get("synopsis", "")), len(item.get("genres", [])))


# Enregistrement automatique
register_scraper(_DOMAIN, AnimeSamaScraper)
register_scraper("www.anime-sama.to", AnimeSamaScraper)
