"""
monitor/sites/telegram_channel.py
===================================
Scraper monitor pour les canaux Telegram publics.

Récupère les derniers posts de t.me/s/<channel> (HTML)
avec fallback RSSHub si Telegram bloque.

Items retournés au format standard BaseSiteScraper :
{
    "title"          : texte du post (tronqué),
    "cover"          : image du post ou None,
    "synopsis"       : texte complet du post,
    "url"            : lien direct vers le post (t.me/canal/123),
    "domain"         : "t.me/nomcanal",
    "episode_number" : numéro du post,
    "episode_count"  : None,
    "episode_duration": None,
}
"""

import logging
import re
import xml.etree.ElementTree as ET

import httpx
from bs4 import BeautifulSoup

from monitor.sites.base import BaseSiteScraper, register_scraper

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "sec-ch-ua": '"Chromium";v="133", "Google Chrome";v="133", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "DNT": "1",
}


class TelegramChannelScraper(BaseSiteScraper):
    """
    Scraper pour un canal Telegram public.
    Détecte les nouveaux posts et les envoie via le monitor.
    """

    MAX_ITEMS = 20  # Nombre de posts max à récupérer par check

    def __init__(self, site_entry: dict):
        super().__init__(site_entry)
        # domain = "t.me/nomcanal"  → extraire le nom du canal
        self.channel = self.domain.split("/")[-1]  # "nomcanal"

    def fetch_latest(self) -> list[dict]:
        """
        Récupère les derniers posts du canal.
        Essaie d'abord t.me/s/<channel>, puis RSSHub en fallback.
        """
        items = self._fetch_from_html()
        if not items:
            items = self._fetch_from_rsshub()

        logger.info("[%s] %d post(s) récupérés", self.domain, len(items))
        return items

    # ── Scraping HTML t.me/s/<channel> ────────────────────────────────────────

    def _fetch_from_html(self) -> list[dict]:
        preview_url = f"https://t.me/s/{self.channel}"
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=10, http2=True) as client:
                resp = client.get(preview_url)
            if resp.status_code != 200:
                return []
            html = resp.text
        except Exception as exc:
            logger.debug("[%s] HTML fetch échoué : %s", self.domain, exc)
            return []

        soup  = BeautifulSoup(html, "lxml")
        items = []

        for wrap in soup.select(".tgme_widget_message_wrap"):
            # URL du post
            date_link = wrap.select_one(".tgme_widget_message_date")
            post_url  = date_link["href"] if date_link and date_link.get("href") else ""
            if not post_url or not post_url.startswith("http"):
                continue

            # Numéro du post (dernier segment de l'URL)
            num_m = re.search(r"/(\d+)$", post_url)
            num   = int(num_m.group(1)) if num_m else 0

            # Date de publication
            time_el  = wrap.select_one("time[datetime]")
            pub_date = time_el["datetime"][:10] if time_el else ""

            # Texte du post
            text_el   = wrap.select_one(".tgme_widget_message_text")
            post_text = text_el.get_text(" ", strip=True) if text_el else ""

            # Image du post
            cover = None
            ph = wrap.select_one(".tgme_widget_message_photo_wrap")
            if ph:
                style = ph.get("style", "")
                m = re.search(r"url\('?([^')]+)'?\)", style)
                if m:
                    cover = m.group(1)

            # Vidéo thumbnail
            if not cover:
                vid = wrap.select_one(".tgme_widget_message_video_thumb")
                if vid:
                    style = vid.get("style", "")
                    m = re.search(r"url\('?([^')]+)'?\)", style)
                    if m:
                        cover = m.group(1)

            title = post_text[:80] + ("…" if len(post_text) > 80 else "")

            items.append({
                "title":            title or f"Post {num}",
                "cover":            cover,
                "synopsis":         post_text[:500],
                "url":              post_url,
                "domain":           self.domain,
                "episode_number":   num,
                "episode_count":    None,
                "episode_duration": None,
                "date":             pub_date,
            })

        items.sort(key=lambda i: i["episode_number"])
        return items[: self.MAX_ITEMS]

    # ── Fallback RSSHub ────────────────────────────────────────────────────────

    def _fetch_from_rsshub(self) -> list[dict]:
        rsshub_url = f"https://rsshub.app/telegram/channel/{self.channel}"
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=10, http2=True) as client:
                resp = client.get(rsshub_url)
            if resp.status_code != 200 or "<rss" not in resp.text[:500]:
                return []

            root    = ET.fromstring(resp.text)
            channel = root.find("channel")
            if channel is None:
                return []

            items = []
            for i, item in enumerate(channel.findall("item"), start=1):
                link  = (item.findtext("link") or "").strip()
                if not link.startswith("http"):
                    continue
                title = (item.findtext("title") or "").strip()
                desc  = (item.findtext("description") or "").strip()[:500]
                pdate = (item.findtext("pubDate") or "")[:10]

                num_m = re.search(r"/(\d+)[/?]?$", link)
                num   = int(num_m.group(1)) if num_m else i

                # Image media:content ou media:thumbnail
                thumb = None
                for ns in [
                    "{http://search.yahoo.com/mrss/}thumbnail",
                    "{http://search.yahoo.com/mrss/}content",
                ]:
                    el = item.find(ns)
                    if el is not None:
                        thumb = el.get("url")
                        break

                items.append({
                    "title":            title[:80] or f"Post {num}",
                    "cover":            thumb,
                    "synopsis":         desc,
                    "url":              link,
                    "domain":           self.domain,
                    "episode_number":   num,
                    "episode_count":    None,
                    "episode_duration": None,
                    "date":             pdate,
                })

            items.sort(key=lambda i: i["episode_number"])
            return items[: self.MAX_ITEMS]

        except Exception as exc:
            logger.debug("[%s] RSSHub échoué : %s", self.domain, exc)
            return []
