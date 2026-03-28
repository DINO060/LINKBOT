"""
monitor/sites/twitter_nitter.py
================================
Scraper monitor pour les comptes Twitter/X via Nitter RSS.

Nitter est un front-end open-source pour Twitter/X qui expose des flux RSS
publics sans nécessiter de compte ni d'API payante.

Flux RSS d'un compte : https://{instance}/{username}/rss

Usage :
  /addsite https://twitter.com/AnimeNewsNetwork
  → domain stocké : "twitter.com/animenewsnetwork"
  → surveille les tweets du compte @AnimeNewsNetwork

  /addsite https://x.com/AniNewsNetwork
  → domain stocké : "twitter.com/aninewsnetwork"  (normalisé twitter.com)

Items retournés au format standard BaseSiteScraper :
{
    "title"           : texte du tweet (tronqué à 200 chars),
    "cover"           : première image du tweet (si présente),
    "synopsis"        : texte complet du tweet,
    "url"             : lien vers le tweet,
    "domain"          : "twitter.com/<username>",
    "episode_number"  : None,
    "episode_count"   : None,
    "episode_duration": None,
    "date"            : date de publication (YYYY-MM-DD),
}
"""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from monitor.sites.base import BaseSiteScraper

logger = logging.getLogger(__name__)

# Instances Nitter publiques alternatives (testées dans l'ordre)
# Si une instance est down, on passe à la suivante automatiquement
_NITTER_INSTANCES = [
    "nitter.poast.org",
    "nitter.privacydev.net",
    "nitter.net",
    "nitter.1d4.us",
    "nitter.kavin.rocks",
    "nitter.unixfox.eu",
    "nitter.42l.fr",
]

_HEADERS = {
    "User-Agent": "SEARCHBOT/1.0 (monitor; RSS feed reader)",
    "Accept":     "application/rss+xml, application/xml, text/xml, */*",
}

# Namespace Atom pour les items RSS enrichis
_MEDIA_NS = "http://search.yahoo.com/mrss/"
_ATOM_NS  = "http://www.w3.org/2005/Atom"

# Regex pour extraire les URLs d'images dans le contenu HTML
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


class TwitterNitterScraper(BaseSiteScraper):
    """Scraper pour comptes Twitter/X via Nitter RSS (sans API, sans compte)."""

    MAX_ITEMS = 20

    def __init__(self, site_entry: dict):
        super().__init__(site_entry)
        # domain = "twitter.com/username" → extraire le username
        # Nettoyer le @ si présent
        parts = self.domain.split("/", 1)
        raw_user = parts[1].lstrip("@") if len(parts) == 2 else ""
        self.username = raw_user.lower()

    def fetch_latest(self) -> list[dict]:
        if not self.username:
            logger.warning("[twitter_nitter] username non détecté dans domain=%s", self.domain)
            return []

        logger.info("[twitter_nitter] Scraping @%s via Nitter RSS …", self.username)
        items = self._try_nitter_instances()
        logger.info("[twitter_nitter] @%s → %d tweet(s)", self.username, len(items))
        return items

    def _try_nitter_instances(self) -> list[dict]:
        """Essaie chaque instance Nitter jusqu'à obtenir une réponse valide."""
        for instance in _NITTER_INSTANCES:
            rss_url = f"https://{instance}/{self.username}/rss"
            try:
                items = self._fetch_rss(rss_url)
                if items is not None:
                    return items
            except Exception as exc:
                logger.debug("[twitter_nitter] %s indisponible : %s", instance, exc)
                continue

        logger.warning(
            "[twitter_nitter] Toutes les instances Nitter ont échoué pour @%s",
            self.username,
        )
        return []

    def _fetch_rss(self, rss_url: str) -> list[dict] | None:
        """
        Récupère et parse le flux RSS d'une instance Nitter.
        Retourne None si l'instance est down ou le flux invalide.
        Retourne [] si le compte est privé ou inexistant.
        """
        try:
            with httpx.Client(
                headers=_HEADERS,
                follow_redirects=True,
                timeout=10,
                verify=False,  # Quelques instances ont des certs expirés
            ) as client:
                resp = client.get(rss_url)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError):
            return None  # Instance down → passer à la suivante

        if resp.status_code in (404, 302):
            # 404 = compte inexistant ; 302 sans RSS = compte protégé
            logger.warning(
                "[twitter_nitter] Compte @%s introuvable ou protégé (HTTP %d)",
                self.username, resp.status_code,
            )
            return []

        if resp.status_code != 200:
            logger.debug("[twitter_nitter] HTTP %d sur %s", resp.status_code, rss_url)
            return None  # Instance problématique → passer à la suivante

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type and "xml" not in content_type:
            # Redirigé vers une page d'erreur HTML → instance down
            return None

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as exc:
            logger.debug("[twitter_nitter] XML invalide sur %s : %s", rss_url, exc)
            return None

        # Chercher les <item> (RSS 2.0) ou <entry> (Atom)
        channel = root.find("channel")
        if channel is None:
            # Essai Atom
            entries = root.findall(f"{{{_ATOM_NS}}}entry")
            if entries:
                return self._parse_atom_entries(entries)
            return None

        items_xml = channel.findall("item")
        if not items_xml:
            return []

        return self._parse_rss_items(items_xml)

    def _parse_rss_items(self, items_xml) -> list[dict]:
        """Parse les <item> d'un flux RSS 2.0 Nitter."""
        results = []

        for item in items_xml:
            title    = (item.findtext("title") or "").strip()
            url      = (item.findtext("link")  or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc     = (item.findtext("description") or "").strip()

            if not title or not url:
                continue

            # Filtrer les retweets si souhaité (titre commence par "RT by")
            # On les garde pour l'instant

            date_str = _parse_date(pub_date)
            cover    = _extract_image(desc)
            synopsis = _html_to_text(desc) if desc else ""

            # Titre souvent dupliqué dans desc → utiliser desc comme synopsis
            # et le titre comme titre court
            display_title = title[:200] + ("…" if len(title) > 200 else "")

            results.append({
                "title":            display_title,
                "cover":            cover,
                "synopsis":         synopsis[:500] if synopsis else title,
                "url":              url,
                "domain":           self.domain,
                "episode_number":   None,
                "episode_count":    None,
                "episode_duration": None,
                "date":             date_str,
            })

            if len(results) >= self.MAX_ITEMS:
                break

        return results

    def _parse_atom_entries(self, entries) -> list[dict]:
        """Parse les <entry> d'un flux Atom (fallback)."""
        results = []
        ns = _ATOM_NS

        for entry in entries:
            title   = (entry.findtext(f"{{{ns}}}title") or "").strip()
            url_el  = entry.find(f"{{{ns}}}link")
            url     = url_el.get("href", "") if url_el is not None else ""
            updated = (entry.findtext(f"{{{ns}}}updated") or "").strip()
            content = (entry.findtext(f"{{{ns}}}content") or "").strip()
            summary = (entry.findtext(f"{{{ns}}}summary") or "").strip()

            if not title or not url:
                continue

            date_str = updated[:10] if updated else ""
            desc     = content or summary
            cover    = _extract_image(desc)
            synopsis = _html_to_text(desc)

            results.append({
                "title":            title[:200],
                "cover":            cover,
                "synopsis":         synopsis[:500] if synopsis else title,
                "url":              url,
                "domain":           self.domain,
                "episode_number":   None,
                "episode_count":    None,
                "episode_duration": None,
                "date":             date_str,
            })

            if len(results) >= self.MAX_ITEMS:
                break

        return results


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(pub_date: str) -> str:
    """Convertit une date RFC 2822 (RSS) en YYYY-MM-DD."""
    if not pub_date:
        return ""
    try:
        dt = parsedate_to_datetime(pub_date)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return pub_date[:10]


def _extract_image(html: str) -> str | None:
    """Extrait la première URL d'image d'un fragment HTML."""
    if not html:
        return None
    m = _IMG_RE.search(html)
    if m:
        src = m.group(1)
        if src.startswith("http"):
            return src
    return None


def _html_to_text(html: str) -> str:
    """Retire les balises HTML basiques pour obtenir du texte brut."""
    if not html:
        return ""
    # Retirer les balises <br> / <p> → espace/newline
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    # Retirer toutes les autres balises
    text = re.sub(r"<[^>]+>", "", text)
    # Décoder les entités HTML basiques
    text = (
        text.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&nbsp;", " ")
    )
    return " ".join(text.split()).strip()
