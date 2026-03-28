"""
bot/meta_scraper.py
====================
Extrait les métadonnées riches d'une page web :
  - Titre, image de couverture, synopsis
  - Auteur(s), genres, date de sortie
  - Liste des épisodes (numéro, lien, date, miniature)
  - Nombre d'épisodes / numéro d'épisode courant

Stratégie fetch :
  1. HTTPX (rapide, statique)
  2. Playwright si échec ou HTML vide (sites JS)

Usage :
    from bot.meta_scraper import scrape_metadata, scrape_series_page
    meta = scrape_metadata("https://hentaihaven.xxx/watch/some-anime/")
    series = scrape_series_page("https://hentaihaven.xxx/watch/some-anime/")
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

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

# Pattern URL épisode/saison/chapitre (dernier segment de chemin)
# Couvre : episode-3, ep3, chapter-23, ch5, saison2, season2, vostfr, vf, vo …
_EPISODE_SEG_RE = re.compile(
    r"(episode|ep|chapter|ch|saison|season)[-_]?\d*"
    r"|vostfr|vf(-vostfr)?$|\bvo\b",
    re.IGNORECASE,
)


# ─── Détection canal Telegram ───────────────────────────────────────────────────────────────

_TG_RE = re.compile(
    r"https?://(?:www\.)?t\.me/(?:s/)?(\w+)", re.IGNORECASE
)

def is_telegram_channel(url: str) -> bool:
    """Retourne True si l'URL est un canal Telegram public."""
    m = _TG_RE.match(url)
    if not m:
        return False
    slug = m.group(1).lower()
    # Exclure les URL spéciales de Telegram
    return slug not in ("joinchat", "share", "addstickers", "addtheme", "boost")


def _tg_channel_name(url: str) -> str | None:
    """Extrait le nom du canal depuis une URL t.me/..."""
    m = _TG_RE.match(url)
    return m.group(1) if m else None


# ─── Scraper canal Telegram public ───────────────────────────────────────────

def _scrape_telegram_channel(url: str) -> dict:
    """
    Scrape un canal Telegram public via :
      1. t.me/s/<channel>  (HTML avec BeautifulSoup)
      2. RSSHub            (fallback RSS)
    Retourne un dict compatible avec le format meta standard.
    """
    channel = _tg_channel_name(url)
    empty = {
        "title": channel or "", "cover": None, "synopsis": "",
        "genres": [], "authors": [], "release_date": "",
        "episodes": [], "episode_count": None,
        "episode_number": None, "episode_duration": None,
        "url": url, "domain": "t.me",
    }
    if not channel:
        return empty

    posts: list[dict] = []
    title    = ""
    synopsis = ""
    cover    = None

    # ── 1. Scraping HTML t.me/s/<channel> ────────────────────────────────────
    preview_url = f"https://t.me/s/{channel}"
    html = _fetch_httpx(preview_url, timeout=10)
    if html:
        soup = BeautifulSoup(html, "lxml")

        # Infos du canal
        title_el = soup.select_one(".tgme_channel_info_header_title")
        if title_el:
            title = title_el.get_text(strip=True)

        desc_el = soup.select_one(".tgme_channel_info_description")
        if desc_el:
            synopsis = desc_el.get_text(strip=True)

        img_el = soup.select_one(".tgme_page_photo_image img, .tgme_channel_info_header_photo img")
        if img_el:
            cover = img_el.get("src") or img_el.get("data-src")

        # Posts récents
        for wrap in soup.select(".tgme_widget_message_wrap"):
            # URL du post
            date_link = wrap.select_one(".tgme_widget_message_date")
            post_url  = date_link["href"] if date_link and date_link.get("href") else ""
            if not post_url:
                continue

            # Date
            time_el  = wrap.select_one("time[datetime]")
            pub_date = time_el["datetime"][:10] if time_el else ""

            # Texte du post (titre/résumé)
            text_el   = wrap.select_one(".tgme_widget_message_text")
            post_text = text_el.get_text(" ", strip=True)[:200] if text_el else ""

            # Image du post
            thumb = None
            ph = wrap.select_one(".tgme_widget_message_photo_wrap")
            if ph:
                style = ph.get("style", "")
                m = re.search(r"url\('?([^')]+)'?\)", style)
                if m:
                    thumb = m.group(1)

            # Numéro de post (depuis l'URL : t.me/canal/123)
            num_m = re.search(r"/(\d+)$", post_url)
            num   = int(num_m.group(1)) if num_m else 0

            posts.append({
                "number": num,
                "url":    post_url,
                "date":   pub_date,
                "thumb":  thumb,
                "title":  post_text,
            })

        logger.info("Telegram HTML ✓ @%s → %d posts", channel, len(posts))

    # ── 2. Fallback RSSHub si HTML vide ──────────────────────────────────────
    if not posts:
        rsshub_url = f"https://rsshub.app/telegram/channel/{channel}"
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=10, http2=True) as client:
                resp = client.get(rsshub_url)
            if resp.status_code == 200 and "<rss" in resp.text[:500]:
                root    = ET.fromstring(resp.text)
                ch_el   = root.find("channel")
                if ch_el is not None:
                    if not title:
                        title    = (ch_el.findtext("title") or "").strip()
                    if not synopsis:
                        synopsis = (ch_el.findtext("description") or "").strip()
                    for i, item in enumerate(ch_el.findall("item"), start=1):
                        link  = (item.findtext("link") or "").strip()
                        desc  = (item.findtext("description") or "").strip()[:200]
                        pdate = (item.findtext("pubDate") or "")[:10]
                        num_m = re.search(r"/(\d+)[/?]?", link)
                        num   = int(num_m.group(1)) if num_m else i
                        posts.append({"number": num, "url": link, "date": pdate, "thumb": None, "title": desc})
                    logger.info("RSSHub ✓ @%s → %d posts", channel, len(posts))
        except Exception as exc:
            logger.debug("RSSHub @%s échec : %s", channel, exc)

    posts.sort(key=lambda p: p["number"])

    return {
        "title":         title or f"@{channel}",
        "cover":         cover,
        "synopsis":      synopsis,
        "genres":        [],
        "authors":       [f"@{channel}"],
        "release_date":  "",
        "episodes":      posts,
        "episode_count": len(posts) or None,
        "episode_number":  None,
        "episode_duration": None,
        "url":    url,
        "domain": "t.me",
    }


# ─── Utilitaire URL série ──────────────────────────────────────────────────────────────────

def get_series_url(episode_url: str) -> str:
    """
    Déduit l'URL de la page série depuis une URL d'épisode ou de saison.
    Ex: /catalogue/frieren/saison2/vostfr/ → /catalogue/frieren/
        /watch/my-anime/episode-3/         → /watch/my-anime/
    Boucle jusqu'à ce qu'aucun segment «épisode/saison/langue» ne soit trouvé.
    """
    parsed = urlparse(episode_url)
    parts = [p for p in parsed.path.split("/") if p]
    # Retirer les segments terminaux tant qu'ils ressemblent à un épisode/saison/langue
    # fullmatch : le segment ENTIER doit correspondre (pas juste un préfixe)
    while parts and _EPISODE_SEG_RE.fullmatch(parts[-1]):
        parts = parts[:-1]
    series_path = "/" + "/".join(parts) + "/" if parts else "/"
    return f"{parsed.scheme}://{parsed.netloc}{series_path}"


def is_episode_url(url: str) -> bool:
    """Retourne True si l'URL contient un segment épisode/saison/langue."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    # fullmatch : le segment ENTIER doit correspondre pour éviter les faux positifs
    # ex: 'epic' ne doit pas matcher 'ep', 'saisons-speciales' ne doit pas matcher 'saison'
    return any(_EPISODE_SEG_RE.fullmatch(p) for p in parts)


# ─── Extraction depuis le HTML ──────────────────────────────────────────────────────────────────

def _parse_meta(html: str, base_url: str) -> dict:
    """Extrait les métadonnées complètes depuis le HTML brut."""
    soup = BeautifulSoup(html, "lxml")

    def og(prop: str) -> str:
        tag = soup.find("meta", property=f"og:{prop}") or soup.find("meta", attrs={"name": prop})
        return (tag.get("content") or "").strip() if tag else ""

    # ── Données Schema.org (JSON-LD) – source la plus fiable ──────────────────────
    jsonld = _extract_jsonld(soup)

    # ── Titre ───────────────────────────────────────────────────────────────────────────────
    title = (
        jsonld.get("name") or
        og("title") or
        (soup.title.get_text(strip=True) if soup.title else "") or
        (soup.find("h1").get_text(strip=True) if soup.find("h1") else "")
    )
    # Nettoyer le titre (retirer le nom du site s'il est collé)
    for sep in [" | ", " - ", " – ", " — "]:
        if sep in title:
            title = title.split(sep)[0].strip()
            break

    # ── Image de couverture ───────────────────────────────────────────────────────────────
    cover = jsonld.get("image") or og("image")
    if not cover:
        for img in soup.find_all("img", src=True):
            src = img.get("src", "")
            if any(kw in src.lower() for kw in ("cover", "poster", "thumb", "banner")):
                cover = src
                break
    if not cover:
        img = soup.find("img", src=True)
        cover = img.get("src", "") if img else ""
    if cover and not cover.startswith("http"):
        cover = urljoin(base_url, cover)

    # ── Synopsis ──────────────────────────────────────────────────────────────────────────────
    synopsis = (
        jsonld.get("description") or
        og("description") or
        (soup.find("meta", attrs={"name": "description"}) or {}).get("content", "")
    )
    if not synopsis:
        for selector in [
            ".synopsis", ".summary", ".description", ".plot",
            "#synopsis", "#summary", "#description",
            ".entry-content", ".post-content", ".content-desc",
            ".series-synopsis", ".anime-synopsis", ".video-desc",
            "[class*='synopsis']", "[class*='summary']", "[class*='description']",
            "p.desc", ".desc", ".info p", ".series-info p",
        ]:
            el = soup.select_one(selector)
            if el:
                txt = el.get_text(separator=" ", strip=True)
                if len(txt) > 40:  # Évite les faux positifs trop courts
                    synopsis = txt
                    break
    synopsis = (synopsis or "")[:1500].strip()

    # ── Genres ────────────────────────────────────────────────────────────────────────────────
    genres: list[str] = jsonld.get("genre", []) if isinstance(jsonld.get("genre"), list) else []
    if not genres and isinstance(jsonld.get("genre"), str):
        genres = [g.strip() for g in jsonld["genre"].split(",") if g.strip()]
    if not genres:
        for sel in [
            ".genres a", ".genre a", "[class*='genre'] a",
            ".tags a", "[class*='tag'] a", ".categories a",
            ".genre-list a", ".anime-genre a",
            # Spans/divs contenant du texte de genre
            ".genres span", ".genre span", "[class*='genre'] span",
            "[class*='genre']",  # élément lui-même
        ]:
            tags = soup.select(sel)
            found = [t.get_text(strip=True) for t in tags if t.get_text(strip=True)]
            if found:
                genres = found[:10]
                break
    if not genres:
        # Keywords meta
        kw_tag = soup.find("meta", attrs={"name": "keywords"})
        if kw_tag and kw_tag.get("content"):
            genres = [k.strip() for k in kw_tag["content"].split(",") if k.strip()][:8]

    # ── Auteurs / Studio ───────────────────────────────────────────────────────────────────
    authors: list[str] = []
    raw_authors = jsonld.get("author") or jsonld.get("creator") or jsonld.get("director")
    if isinstance(raw_authors, list):
        authors = [a.get("name", a) if isinstance(a, dict) else str(a) for a in raw_authors]
    elif isinstance(raw_authors, str):
        authors = [raw_authors]
    if not authors:
        for sel in [".author a", ".studio a", ".producer a",
                    "[class*='author']", "[class*='studio']",
                    ".series-info .value"]:
            els = soup.select(sel)
            if els:
                authors = [e.get_text(strip=True) for e in els][:3]
                break

    # ── Date de sortie ────────────────────────────────────────────────────────────────────
    release_date: str = (
        jsonld.get("datePublished") or
        jsonld.get("startDate") or
        og("release_date") or
        ""
    )
    if not release_date:
        for sel in [".release-date", ".date", "[class*='release']", "[class*='date']",
                    "time[datetime]"]:
            el = soup.select_one(sel)
            if el:
                release_date = el.get("datetime") or el.get_text(strip=True)
                break
    # Garder seulement l'année ou date courte
    if release_date and len(release_date) > 20:
        release_date = release_date[:10]

    # ── Liste des épisodes ───────────────────────────────────────────────────────────────────
    episodes = _extract_episode_list(soup, base_url)

    # ── Infos épisode courant (si URL d'épisode) ─────────────────────────────────────────
    ep_info = _extract_episode_info(soup, title, episodes)

    return {
        "title":          title,
        "cover":          cover or None,
        "synopsis":       synopsis,
        "url":            base_url,
        "domain":         urlparse(base_url).netloc.lstrip("www."),
        "genres":         genres,
        "authors":        authors,
        "release_date":   release_date,
        "episodes":       episodes,       # liste de {number, url, date, thumb}
        **ep_info,
    }


def _extract_jsonld(soup: BeautifulSoup) -> dict:
    """Extrait les données Schema.org JSON-LD de la page."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "{}")
            if isinstance(data, list):
                data = data[0] if data else {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _extract_episode_list(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Extrait la liste complète des épisodes depuis la page série.
    Retourne une liste de dicts : {number, url, date, thumb}
    triée par numéro décroissant (plus récent en premier).
    """
    seen_urls: set[str] = set()
    seen_nums: set[int] = set()
    episodes: list[dict] = []
    parsed_base = urlparse(base_url)
    domain = parsed_base.netloc

    # Couvre : episode-3, chapter-23, ep3, ch5, …
    ep_link_re = re.compile(r"(?:episode|chapter|ep|ch)[-_]?(\d+)", re.IGNORECASE)

    def _add_link(a_tag) -> bool:
        """Tente d'extraire un épisode depuis un tag <a>. Retourne True si ajouté."""
        href = a_tag.get("href", "")
        if not href:
            return False

        # Cherche le numéro d'épisode dans l'URL ou le texte du lien
        m = ep_link_re.search(href) or ep_link_re.search(a_tag.get_text())
        if not m:
            return False

        ep_num = int(m.group(1))
        url = href if href.startswith("http") else urljoin(base_url, href)

        # Filtrer : même domaine, pas déjà vu
        if domain not in url:
            return False
        if url in seen_urls or ep_num in seen_nums:
            return False

        seen_urls.add(url)
        seen_nums.add(ep_num)

        # Miniature
        img = a_tag.find("img")
        thumb = None
        if img:
            thumb = (img.get("src") or img.get("data-src")
                     or img.get("data-lazy-src") or img.get("data-original"))
            if thumb and not thumb.startswith("http"):
                thumb = urljoin(base_url, thumb)

        # Date
        date_str = ""
        for date_tag in a_tag.find_all(["time", "span", "small", "p"]):
            txt = date_tag.get("datetime") or date_tag.get_text(strip=True)
            if txt and re.search(r"\d{4}", txt):
                date_str = txt[:20]
                break

        episodes.append({"number": ep_num, "url": url, "date": date_str, "thumb": thumb})
        return True

    # ── Passe 1 : cherche dans les conteneurs sémantiques ────────────────────
    CONTAINER_SELS = [
        ".episodes", "#episodes", ".episode-list", ".episodelist",
        "[class*='episode-list']", "[class*='episodes']",
        ".chapters", "#chapters", ".chapter-list", ".chapterlist",
        "[class*='chapter-list']", "[class*='chapters']",
        ".video-list", ".watch-list", ".ep-list",
        ".listing", ".items", ".series-ep",
        "ul", "ol",
    ]
    for sel in CONTAINER_SELS:
        for container in soup.select(sel):
            for a in container.find_all("a", href=True):
                _add_link(a)
        if episodes:
            break  # On a trouvé au moins un épisode dans ce sélecteur

    # ── Passe 2 (fallback) : scanner TOUS les liens de la page ───────────────
    # Utile quand le site est rendu en JS et que les conteneurs sont génériques
    if len(episodes) < 2:
        for a in soup.find_all("a", href=True):
            _add_link(a)

    # _add_link déduplique déjà via seen_nums/seen_urls → episodes est propre
    episodes.sort(key=lambda e: e["number"], reverse=True)
    return episodes


def _extract_episode_info(soup: BeautifulSoup, title: str, episodes: list[dict]) -> dict:
    """Extrait le numéro d'épisode courant et la durée."""
    ep_count    = len(episodes) if episodes else None
    ep_number   = None
    ep_duration = None

    page_text = soup.get_text(" ")

    # Durée
    m = re.search(r"(\d{1,3})\s*min", page_text, re.IGNORECASE)
    if m:
        ep_duration = f"{m.group(1)} min"

    # Numéro d'épisode courant (depuis titre ou URL)
    m = re.search(r"ep(?:isode)?[-_.\s#]*(\d+)", title, re.IGNORECASE)
    if m:
        ep_number = int(m.group(1))

    # Nombre total depuis la liste réelle uniquement
    # (pas de recherche textuelle — trop de faux positifs avec les années)

    return {
        "episode_count":    ep_count,
        "episode_number":   ep_number,
        "episode_duration": ep_duration,
    }


# ─── Fetch HTTP statique ──────────────────────────────────────────────────────────────────

def _fetch_httpx(url: str, timeout: int = 10) -> Optional[str]:
    """Récupère le HTML via HTTPX."""
    try:
        with httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=timeout,
            http2=True,
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.debug("HTTPX échec pour %s : %s", url, exc)
        return None


# ─── Fetch RSS ───────────────────────────────────────────────────────────────

def _try_rss(series_url: str) -> dict | None:
    """
    Tente de trouver et parser le flux RSS d'une page série.
    Retourne un dict {title, cover, synopsis, episodes, episode_count} ou None.
    Beaucoup plus rapide que Playwright pour récupérer la liste des épisodes.
    """
    parsed     = urlparse(series_url)
    base       = f"{parsed.scheme}://{parsed.netloc}"
    path_parts = [p for p in parsed.path.split("/") if p]
    # Slug de la série = dernier segment non-épisode
    slug = path_parts[-1] if path_parts else ""

    # ── 1. Découverte: <link rel="alternate" type="application/rss+xml"> ───────
    candidates: list[str] = []
    html = _fetch_httpx(series_url, timeout=8)
    if html:
        soup   = BeautifulSoup(html, "lxml")
        rss_tag = soup.find("link", attrs={"type": "application/rss+xml"})
        if rss_tag and rss_tag.get("href"):
            candidates.append(urljoin(series_url, rss_tag["href"]))

    # ── 2. Candidats RSS génériques ───────────────────────────────────────────
    candidates += [
        f"{base}/feed/",
        f"{base}/feed",
        f"{base}/?feed=rss2",
        f"{base}/rss/",
        f"{base}/rss",
    ]

    # Couvre episode-N, chapter-N, ep-N, ch-N
    ep_re = re.compile(r"(?:episode|chapter|ep|ch)[-_]?(\d+)", re.IGNORECASE)

    for feed_url in candidates:
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=8, http2=True) as client:
                resp = client.get(feed_url)
            if resp.status_code != 200:
                continue
            ct   = resp.headers.get("content-type", "")
            body = resp.text.strip()
            # Vérifier que c'est bien du XML/RSS
            if not body.startswith("<"):
                continue
            if "xml" not in ct and "rss" not in ct and "<rss" not in body[:300]:
                continue

            root    = ET.fromstring(body)
            channel = root.find("channel")
            if channel is None:
                continue

            # Métadonnées du channel
            ch_title    = (channel.findtext("title") or "").strip()
            ch_synopsis = (channel.findtext("description") or "").strip()
            ch_cover    = None
            img_el      = channel.find("image/url")
            if img_el is not None and img_el.text:
                ch_cover = img_el.text.strip()

            # Items → épisodes
            episodes: list[dict] = []
            for item in channel.findall("item"):
                link = (item.findtext("link") or "").strip()
                if not link:
                    guid = item.find("guid")
                    link = (guid.text or "").strip() if guid is not None else ""
                if not link.startswith("http"):
                    continue
                # Filtrer : appartient à cette série
                if slug and slug not in link:
                    continue

                item_title = (item.findtext("title") or "").strip()
                pub_date   = (item.findtext("pubDate") or "").strip()

                m = ep_re.search(link) or ep_re.search(item_title)
                if m is None:
                    continue
                num = int(m.group(1))

                # Miniature (media:thumbnail ou enclosure image)
                thumb = None
                mt = item.find("{http://search.yahoo.com/mrss/}thumbnail")
                if mt is not None:
                    thumb = mt.get("url")
                if not thumb:
                    enc = item.find("enclosure")
                    if enc is not None and "image" in enc.get("type", ""):
                        thumb = enc.get("url")

                episodes.append({
                    "number": num,
                    "url":    link,
                    "date":   pub_date[:30] if pub_date else "",
                    "thumb":  thumb,
                })

            if not episodes:
                continue

            episodes.sort(key=lambda e: e["number"])
            logger.info("RSS ✓ %s → %d épisodes (feed: %s)", series_url, len(episodes), feed_url)
            return {
                "title":         ch_title,
                "cover":         ch_cover,
                "synopsis":      ch_synopsis,
                "episodes":      episodes,
                "episode_count": len(episodes),
                "_rss_feed":     feed_url,
            }

        except Exception as exc:
            logger.debug("RSS échec %s : %s", feed_url, exc)

    return None


# ─── Playwright : extraction directe via JS ─────────────────────────────────

def _scrape_playwright_direct(url: str, timeout_ms: int = 30_000,
                              rss_episodes: list | None = None) -> dict:
    """
    Lance Chromium headless, attend le rendu JS complet (networkidle),
    puis extrait toutes les données directement via eval_on_selector_all.
    C'est la méthode principale pour les sites JS-heavy (hentaihaven, etc.)
    """
    empty = {
        "title": "", "cover": None, "synopsis": "",
        "genres": [], "authors": [], "release_date": "",
        "episodes": [], "episode_count": None,
        "episode_number": None, "episode_duration": None,
        "content_type": "episode",
        "url": url, "domain": urlparse(url).netloc.lstrip("www."),
    }
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        from playwright_stealth import Stealth

        _stealth = Stealth(
            navigator_user_agent_override=_UA,
            navigator_platform_override="Win32",
        )

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
                viewport={"width": 1280, "height": 900},
            )
            _stealth.apply_stealth_sync(page)  # masque navigator.webdriver + fingerprints

            # ── 1. Charger la page et attendre le JS complet ──────────────────
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PWTimeout:
                logger.warning("networkidle timeout pour %s, on continue", url)
            except Exception as exc:
                logger.warning("goto échec %s : %s", url, exc)

            # ── 2. Attendre que les liens d'épisodes apparaissent ─────────────
            # Si on a déjà les épisodes via RSS, inutile d'attendre
            if rss_episodes is None:
                for sel in [
                    "a[href*='episode']", "a[href*='chapter']",
                    ".episodes a", ".episode-list a",
                    ".chapters a", ".chapter-list a",
                    "[class*='episode'] a", "[class*='chapter'] a",
                    "li a[href*='ep']", "li a[href*='ch']",
                ]:
                    try:
                        page.wait_for_selector(sel, timeout=8_000)
                        logger.debug("Sélecteur épisodes trouvé : %s", sel)
                        break
                    except Exception:
                        pass

            domain = urlparse(url).netloc

            # ── 3. Extraction complète via JavaScript dans le navigateur ──────
            result: dict = page.evaluate("""
                (domain) => {
                    const og = (prop) => {
                        const m = document.querySelector(
                            `meta[property="og:${prop}"], meta[name="${prop}"]`
                        );
                        return m ? (m.getAttribute("content") || "").trim() : "";
                    };

                    // ── Titre ─────────────────────────────────────────────────
                    // Priorité h1 (titre réel) > og:title (souvent le titre SEO du site)
                    const h1El = document.querySelector("h1");
                    const h1Text = h1El ? h1El.innerText.trim() : "";
                    let ogTitle = og("title");
                    // Rejette og:title s'il ressemble à un slogan de site (trop court ou mots SEO)
                    const SEO_TITLE_RE = /free|stream|watch|hentai haven|hentaihaven|sensual tease|ecchi anime/i;
                    if (SEO_TITLE_RE.test(ogTitle) && h1Text) ogTitle = "";
                    let title = h1Text || ogTitle || document.title || "";
                    for (const sep of [" | ", " - ", " – ", " — "]) {
                        if (title.includes(sep)) {
                            title = title.split(sep)[0].trim(); break;
                        }
                    }

                    // ── Couverture ────────────────────────────────────────────
                    let cover = og("image") || "";
                    if (!cover) {
                        for (const img of document.querySelectorAll("img")) {
                            const src = img.getAttribute("src") || img.getAttribute("data-src") || "";
                            if (/cover|poster|thumb|banner/i.test(src) && src.startsWith("http")) {
                                cover = src; break;
                            }
                        }
                    }

                    // ── Synopsis ──────────────────────────────────────────────
                    // Filtre anti-SEO : rejette les meta descriptions publicitaires
                    const SEO_RE = /watch free|stream online|full hd|english sub|watch .* hentai|all episodes in|hentai stream|watch and download/i;
                    function cleanSynopsis(text) {
                        if (!text) return "";
                        text = text.trim();
                        if (SEO_RE.test(text)) return "";
                        if (text.length < 30) return "";
                        return text;
                    }
                    // Priorité 1 : sélecteurs DOM (vrai synopsis de la page)
                    // Filtre épisodes : rejette les conteneurs qui listent des épisodes
                    const EP_LIST_RE = /episode\\s*\\d|\\bep\\.?\\s*\\d/gi;
                    function isEpisodeList(text) {
                        const matches = text.match(EP_LIST_RE);
                        return matches && matches.length >= 2;
                    }
                    let synopsis = "";

                    // Stratégie 0 : cherche un heading "SUMMARY" et prend le contenu suivant
                    // (pattern utilisé par hentaihaven et plusieurs sites similaires)
                    const allEls = document.querySelectorAll("h1,h2,h3,h4,h5,p,div,section");
                    for (const el of allEls) {
                        const t = el.innerText?.trim() || "";
                        if (/^(summary|synopsis|description|about|plot|story)$/i.test(t)) {
                            // Essaie le sibling direct d'abord, puis le parent
                            let target = el.nextElementSibling;
                            if (!target || target.tagName === "A") {
                                target = el.parentElement?.nextElementSibling;
                            }
                            if (target) {
                                const txt = cleanSynopsis(target.innerText);
                                if (txt && !isEpisodeList(txt)) { synopsis = txt; break; }
                            }
                        }
                    }

                    // Stratégie 1 : sélecteurs CSS spécifiques
                    if (!synopsis) {
                        const synSels = [
                            ".synopsis", ".synopsis-content", "#synopsis",
                            ".story-text", ".description-content", ".anime-synopsis",
                            ".series-summary > p", ".summary > p",
                            "[class*='synopsis']",
                            ".info-desc", ".series-desc", ".content-desc",
                            ".anime-info .desc", ".detail > p", "p.desc",
                            ".entry-content > p", ".info > p",
                            ".summary", "[class*='summary']",
                        ];
                        for (const s of synSels) {
                            const el = document.querySelector(s);
                            if (el) {
                                const txt = cleanSynopsis(el.innerText);
                                if (txt && !isEpisodeList(txt)) { synopsis = txt; break; }
                            }
                        }
                    }
                    // Priorité 2 : og:description (avec filtre SEO)
                    if (!synopsis) synopsis = cleanSynopsis(og("description"));
                    // Priorité 3 : meta name="description" (dernier recours)
                    if (!synopsis) {
                        const metaD = (document.querySelector('meta[name="description"]')?.getAttribute("content") || "").trim();
                        synopsis = cleanSynopsis(metaD);
                    }

                    // ── Date de sortie ────────────────────────────────────────
                    let releaseDate = "";
                    const relSels = [
                        ".release", ".released", ".year", "[class*='release']",
                        "[class*='year']", ".date", "time[datetime]",
                    ];
                    for (const s of relSels) {
                        const el = document.querySelector(s);
                        if (el) {
                            const txt = (el.getAttribute("datetime") || el.innerText || "").trim();
                            const ym = txt.match(/\\b(19|20)\\d{2}\\b/);
                            if (ym) { releaseDate = ym[0]; break; }
                        }
                    }
                    // Fallback : cherche "Release: YYYY" dans le texte de la page
                    if (!releaseDate) {
                        const bodyText = document.body?.innerText || "";
                        const rm = bodyText.match(/Release[:\\s]+((?:\\d{4}[,\\s]*)+)/i);
                        if (rm) releaseDate = rm[1].trim();
                    }

                    // ── Genres ────────────────────────────────────────────────
                    // Filtre par href : accepte seulement les liens /genre/, /tag/, /category/
                    // Cela élimine les titres d'autres séries et les liens de navigation
                    const GENRE_HREF_RE = /\\/(genre|tag|categor|label|theme)s?\\//i;
                    const JUNK_RE = /^(home|all|watch|stream|download|hentai haven|hentaihaven|episode|ep\\s*\\d|\\d+|january|february|march|april|may|june|july|august|september|october|november|december|login|log in|sign up|signup|register|logout|account|profile|search|contact|about|menu|navigation|more|less|next|prev|previous|back|submit|cancel|close|open)$/i;
                    const genreContainerSels = [
                        ".genres", ".genre", "#genres", "#genre",
                        "[class*='genre']", ".tags", ".tag",
                        ".categories", ".category", "[class*='tag']", "[class*='categor']",
                    ];
                    let genres = [];
                    for (const s of genreContainerSels) {
                        const container = document.querySelector(s);
                        if (!container) continue;
                        const links = Array.from(container.querySelectorAll("a"));
                        if (links.length === 0) continue;
                        let found = links
                            .filter(a => {
                                const href = (a.getAttribute("href") || "").toLowerCase();
                                // Exclut les liens vers /watch/ (ce sont des séries, pas des genres)
                                if (href.includes("/watch/")) return false;
                                // Accepte liens vers /genre/, /tag/, etc. OU sans href
                                return !href || GENRE_HREF_RE.test(href);
                            })
                            .map(a => a.innerText.trim())
                            .filter(t =>
                                t.length >= 2 && t.length <= 35 &&
                                !JUNK_RE.test(t) &&
                                !/\\d{4}/.test(t) &&
                                !/^episode\\s/i.test(t) &&
                                !/^\\d+$/.test(t)
                            );
                        if (found.length > 0) {
                            const seenLc = new Set();
                            genres = found.filter(t => {
                                const lc = t.toLowerCase();
                                if (seenLc.has(lc)) return false;
                                seenLc.add(lc); return true;
                            }).slice(0, 10);
                            break;
                        }
                    }

                    // ── Auteurs ───────────────────────────────────────────────
                    // Stratégie 1 : liens vers /author/ ou /studio/ (précis)
                    const AUTHOR_HREF_RE = /\\/(author|studio|artist|producer|label)s?\\//i;
                    let authors = [];
                    const allLinks = document.querySelectorAll("a[href]");
                    const authorLinks = Array.from(allLinks).filter(a =>
                        AUTHOR_HREF_RE.test(a.getAttribute("href") || "")
                    );
                    if (authorLinks.length > 0) {
                        const seen = new Set();
                        authors = authorLinks
                            .map(a => a.innerText.trim())
                            .filter(t => t.length > 1 && t.length <= 60 && !seen.has(t) && seen.add(t))
                            .slice(0, 5);
                    }
                    // Stratégie 2 : cherche label "Author" et prend les liens de son conteneur
                    if (authors.length === 0) {
                        const labelEls = document.querySelectorAll("b, strong, th, dt, td, span, label");
                        for (const lbl of labelEls) {
                            if (/^author|^studio|^artist|^producer/i.test(lbl.innerText?.trim() || "")) {
                                const parent = lbl.closest("tr, li, div, p") || lbl.parentElement;
                                if (parent) {
                                    const as = Array.from(parent.querySelectorAll("a"));
                                    if (as.length > 0) {
                                        const seen2 = new Set();
                                        authors = as.map(a => a.innerText.trim())
                                            .filter(t => t.length > 1 && t.length <= 60 && !seen2.has(t) && seen2.add(t))
                                            .slice(0, 5);
                                        break;
                                    }
                                }
                            }
                        }
                    }
                    // Stratégie 3 : classe author/studio (fallback)
                    if (authors.length === 0) {
                        const authorSels = [".author a", ".studio a", "[class*='author'] a", "[class*='studio'] a"];
                        for (const s of authorSels) {
                            const els = document.querySelectorAll(s);
                            if (els.length > 0) {
                                const seen3 = new Set();
                                const found = Array.from(els)
                                    .map(e => e.innerText.trim())
                                    .filter(t => t.length > 1 && t.length <= 60 && !/^\\d+$/.test(t) && !seen3.has(t) && seen3.add(t));
                                if (found.length > 0) { authors = found.slice(0, 5); break; }
                            }
                        }
                    }

                    // ── Épisodes ─────────────────────────────────────────────
                    // Extrait le slug de la série depuis l'URL courante
                    // Filtre les segments génériques pour trouver l'identifiant réel de la série
                    const SKIP_SEGS = new Set(['watch', 'catalogue', 'anime', 'manga', 'hentai', 'series', 'show', 'film', 'movie']);
                    const pathParts = window.location.pathname.split('/').filter(p => p && !SKIP_SEGS.has(p.toLowerCase()));
                    const seriesSlug = pathParts[0] || "";

                    const epLinks = document.querySelectorAll("a[href*='episode'], a[href*='chapter']");
                    const epMap = {};
                    let contentType = "episode"; // sera mis à "chapter" si des chapitres trouvés

                    for (const a of epLinks) {
                        const href = a.href || "";
                        if (!href.includes(domain)) continue;
                        // Filtre strict : le lien doit contenir le slug de la série courante
                        if (seriesSlug && !href.includes(seriesSlug)) continue;

                        const mHref = href.match(/(?:episode|chapter|ep|ch)[-_]?(\\d+)/i);
                        if (mHref && /chapter|ch[-_]/i.test(href)) contentType = "chapter";
                        const mText = a.innerText.match(/(\\d+)/);
                        const num = mHref
                            ? parseInt(mHref[1])
                            : (mText ? parseInt(mText[1]) : null);
                        if (num === null || num < 1 || num > 9999) continue;

                        if (!epMap[num]) {
                            const img = a.querySelector("img");
                            let thumb = null;
                            if (img) {
                                thumb = img.getAttribute("src")
                                     || img.getAttribute("data-src")
                                     || img.getAttribute("data-lazy-src")
                                     || null;
                            }
                            let date = "";
                            const dateEl = a.querySelector("time, [class*='date'], small, span");
                            if (dateEl) {
                                date = dateEl.getAttribute("datetime")
                                    || dateEl.innerText.trim();
                                if (date.length > 30) date = date.substring(0, 30);
                            }
                            epMap[num] = { number: num, url: href, date: date, thumb: thumb };
                        }
                    }

                    const episodes = Object.values(epMap)
                        .sort((a, b) => a.number - b.number);

                    // ── Saisons (anime-sama et sites similaires) ──────────────
                    const saisonLinks = document.querySelectorAll("a[href*='/saison'], a[href*='/season']");
                    const saisonMap = {};
                    for (const a of saisonLinks) {
                        const href = a.href || "";
                        if (!href.includes(domain)) continue;
                        if (seriesSlug && !href.includes(seriesSlug)) continue;
                        const m = href.match(/\\/(saison|season)[-_]?(\\d+)/i);
                        const num = m ? parseInt(m[2]) : null;
                        if (num === null || num < 1 || num > 50) continue;
                        if (!saisonMap[num]) {
                            const img = a.querySelector("img");
                            let thumb = null;
                            if (img) thumb = img.getAttribute("src") || img.getAttribute("data-src") || null;
                            saisonMap[num] = { number: num, url: href, date: "", thumb: thumb, is_season: true };
                        }
                    }
                    const saisons = Object.values(saisonMap).sort((a, b) => a.number - b.number);

                    // Utiliser les saisons si aucun épisode direct trouvé
                    const finalEpisodes = episodes.length > 0 ? episodes : saisons;
                    const isSeasonBased = episodes.length === 0 && saisons.length > 0;

                    return {
                        title, cover, synopsis, genres, authors,
                        release_date: releaseDate,
                        episodes: finalEpisodes,
                        episode_count: finalEpisodes.length > 0 ? finalEpisodes.length : null,
                        is_season_based: isSeasonBased,
                        content_type: isSeasonBased ? "season" : (finalEpisodes.length > 0 && contentType === "chapter" ? "chapter" : "episode"),
                    };
                }
            """, domain)

            browser.close()

            if not result:
                return empty

            result.setdefault("release_date", "")
            result.setdefault("episode_number", None)
            result.setdefault("episode_duration", None)
            result["url"]    = url
            result["domain"] = urlparse(url).netloc.lstrip("www.")

            # ── Injecter les épisodes RSS si Playwright n'en a pas trouvé ────
            if rss_episodes and not result.get("episodes"):
                result["episodes"]      = rss_episodes
                result["episode_count"] = len(rss_episodes)

            logger.info(
                "Playwright direct %s → titre=%r genres=%s épisodes=%d",
                url, result.get("title"), result.get("genres"),
                len(result.get("episodes", [])),
            )
            return result

    except Exception as exc:
        logger.error("_scrape_playwright_direct %s : %s", url, exc, exc_info=True)
        return empty


# ─── API publique ────────────────────────────────────────────────────────────────────────────

_EMPTY_META = {
    "title":          "",
    "cover":          None,
    "synopsis":       "",
    "genres":         [],
    "authors":        [],
    "release_date":   "",
    "episodes":       [],
    "episode_count":  None,
    "episode_number": None,
    "episode_duration": None,
    "content_type":   "episode",
}


def scrape_metadata(url: str, force_playwright: bool = False) -> dict:
    """
    Extrait les métadonnées complètes d'une page.
    Stratégie :
      0. Canal Telegram public → scraper dédié (t.me/s/ + RSSHub)
      1. RSS  → épisodes + méta de base (rapide, sans navigateur)
      2. Playwright → genres / cover / synopsis (JS rendu)
      3. Fusion des deux sources
    """
    # ── 0. Canal Telegram public ──────────────────────────────────────────────
    if is_telegram_channel(url):
        return _scrape_telegram_channel(url)

    # ── 1. Tentative RSS ──────────────────────────────────────────────────────
    rss = _try_rss(url)
    rss_episodes = rss["episodes"] if rss else None

    # ── 2. Playwright (passe les épisodes RSS pour éviter l'attente inutile) ──
    result = _scrape_playwright_direct(url, rss_episodes=rss_episodes)

    # ── 3. Fusion : RSS comble les trous laissés par Playwright ──────────────
    if rss:
        if not result.get("title")   and rss.get("title"):    result["title"]    = rss["title"]
        if not result.get("cover")   and rss.get("cover"):    result["cover"]    = rss["cover"]
        if not result.get("synopsis") and rss.get("synopsis"): result["synopsis"] = rss["synopsis"]
        # Épisodes RSS prioritaires si plus complets
        if rss_episodes and len(rss_episodes) > len(result.get("episodes") or []):
            result["episodes"]      = rss_episodes
            result["episode_count"] = len(rss_episodes)
            # Détecter si les épisodes RSS sont des chapitres
            _ch_re2 = re.compile(r"(?:chapter|ch)[-_]\d+", re.IGNORECASE)
            if any(_ch_re2.search(ep.get("url", "")) for ep in rss_episodes):
                result["content_type"] = "chapter"

    return result


def scrape_series_page(series_url: str, force_playwright: bool = False) -> dict:
    """
    Scrape la page de la série pour obtenir les métadonnées + liste d'épisodes.
    """
    return scrape_metadata(series_url)
