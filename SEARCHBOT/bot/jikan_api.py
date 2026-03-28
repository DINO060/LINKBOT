"""
bot/jikan_api.py
=================
Wrapper pour l'API Jikan v4 (MyAnimeList non-officiel, gratuit, sans clé).

Endpoints utilisés :
  GET https://api.jikan.moe/v4/seasons/now          → anime saison actuelle
  GET https://api.jikan.moe/v4/seasons/upcoming      → prochaine saison
  GET https://api.jikan.moe/v4/top/anime             → top anime MAL
  GET https://api.jikan.moe/v4/top/anime?type=movie  → top films MAL
  GET https://api.jikan.moe/v4/anime?q=<query>       → recherche

Limites Jikan : 3 req/s, 60 req/min — on respecte ça avec sleep.
"""

import datetime
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.jikan.moe/v4"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate, br",
}

# Genres MAL (id → nom)
GENRE_IDS: dict[str, int] = {
    "action": 1, "adventure": 2, "comedy": 4, "drama": 8,
    "fantasy": 10, "horror": 14, "mystery": 7, "romance": 22,
    "sci-fi": 24, "slice of life": 36, "sports": 30,
    "supernatural": 37, "thriller": 41, "harem": 35,
    "ecchi": 9, "mecha": 18, "music": 19, "school": 23,
}


def _get(endpoint: str, params: dict | None = None, retries: int = 3) -> dict | None:
    """Effectue une requête GET sur l'API Jikan avec retry automatique."""
    url = f"{_BASE}{endpoint}"
    for attempt in range(retries):
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True,
                              timeout=12, http2=True) as client:
                resp = client.get(url, params=params or {})
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.debug("Jikan rate limit → attente %ds", wait)
                time.sleep(wait)
                continue
            logger.debug("Jikan HTTP %d pour %s", resp.status_code, url)
            return None
        except Exception as exc:
            logger.debug("Jikan erreur %s : %s", url, exc)
            if attempt < retries - 1:
                time.sleep(1)
    return None


def _format_anime(a: dict) -> dict:
    """Convertit un objet anime Jikan en dict standard du bot."""
    genres = [g["name"] for g in (a.get("genres") or [])
              + (a.get("explicit_genres") or [])
              + (a.get("themes") or [])]
    studios = [s["name"] for s in (a.get("studios") or [])]
    score = a.get("score")
    ep_count = a.get("episodes")
    aired = (a.get("aired") or {}).get("prop", {})
    year = aired.get("from", {}).get("year") or a.get("year") or ""
    media_type = a.get("type") or "TV"   # TV, Movie, OVA, ONA, Special, Music
    raw_season = a.get("season") or ""   # winter/spring/summer/fall
    raw_year   = a.get("year") or year

    return {
        "title":         a.get("title_english") or a.get("title") or "",
        "title_jp":      a.get("title") or "",
        "cover":         (a.get("images") or {}).get("jpg", {}).get("large_image_url")
                         or (a.get("images") or {}).get("jpg", {}).get("image_url"),
        "synopsis":      (a.get("synopsis") or "").replace("[Written by MAL Rewrite]", "").strip(),
        "score":         score,
        "genres":        genres[:8],
        "authors":       studios,
        "release_date":  str(year) if year else "",
        "episode_count": ep_count,
        "episodes":      [],
        "episode_number": None,
        "episode_duration": f"{a['duration']}" if a.get("duration") else None,
        "status":        a.get("status") or "",
        "season":        raw_season,
        "_raw_year":     raw_year,
        "media_type":    media_type,
        "content_type":  "movie" if media_type == "Movie" else "anime",
        "url":           a.get("url") or f"https://myanimelist.net/anime/{a.get('mal_id')}",
        "domain":        "myanimelist.net",
        "mal_id":        a.get("mal_id"),
        "_source":       "jikan",
    }


# ─── API publique ──────────────────────────────────────────────────────────────

def get_season_now(page: int = 1) -> list[dict]:
    """Anime de la saison en cours — toutes les pages, triés par score MAL."""
    all_items: list[dict] = []
    current = page
    while True:
        data = _get("/seasons/now", {"page": current, "limit": 25})
        if not data:
            break
        all_items.extend(data.get("data") or [])
        pagination = data.get("pagination") or {}
        if not pagination.get("has_next_page", False):
            break
        current += 1
    formatted = [_format_anime(a) for a in all_items]
    formatted.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return formatted


def get_season_upcoming() -> list[dict]:
    """
    Anime de la PROCHAINE saison uniquement (filtre strict).
    Exclut tout ce qui est au-delà de la prochaine saison.
    Tri : score MAL décroissant, puis titre.
    """
    nxt_year, nxt_season = _next_season()
    all_items: list[dict] = []
    page = 1
    while True:
        data = _get("/seasons/upcoming", {"page": page, "limit": 25})
        if not data:
            break
        for a in (data.get("data") or []):
            a_season = (a.get("season") or "").lower()
            a_year   = a.get("year") or 0
            # Inclure si saison+année correspondent à la prochaine saison
            if a_season == nxt_season and a_year == nxt_year:
                all_items.append(a)
            # Inclure si saison inconnue mais année correspond
            elif not a_season and a_year == nxt_year:
                all_items.append(a)
        pagination = data.get("pagination") or {}
        if not pagination.get("has_next_page", False):
            break
        page += 1
    formatted = [_format_anime(a) for a in all_items]
    formatted.sort(key=lambda x: (-(x.get("score") or 0), x.get("title", "")))
    return formatted


def get_upcoming_movies() -> list[dict]:
    """
    Films à venir cette année ou l'année prochaine.
    Filtre type=Movie depuis /seasons/upcoming.
    """
    cur_year, _ = _current_season()
    all_items: list[dict] = []
    page = 1
    while True:
        data = _get("/seasons/upcoming", {"page": page, "limit": 25})
        if not data:
            break
        for a in (data.get("data") or []):
            if a.get("type") != "Movie":
                continue
            a_year = a.get("year") or cur_year
            if a_year > cur_year + 1:
                continue
            all_items.append(a)
        pagination = data.get("pagination") or {}
        if not pagination.get("has_next_page", False):
            break
        page += 1
    formatted = [_format_anime(a) for a in all_items]
    formatted.sort(key=lambda x: (-(x.get("score") or 0), x.get("title", "")))
    return formatted


def get_top_movies(limit: int = 10) -> list[dict]:
    """Top films d'animation MAL par popularité."""
    data = _get("/top/anime", {"limit": min(limit, 25), "type": "movie",
                               "filter": "bypopularity"})
    if not data:
        return []
    return [_format_anime(a) for a in (data.get("data") or [])]


def get_top_anime(genre: str = "", limit: int = 10, page: int = 1) -> list[dict]:
    """Top anime MAL, filtrable par genre."""
    params: dict = {"limit": min(limit, 25), "page": page, "filter": "bypopularity"}
    if genre:
        genre_id = GENRE_IDS.get(genre.lower())
        if genre_id:
            params["genres"] = genre_id
        else:
            # Tentative par nom exact
            params["genres"] = genre
    data = _get("/top/anime", params)
    if not data:
        return []
    return [_format_anime(a) for a in (data.get("data") or [])]


def search_anime(query: str, limit: int = 5) -> list[dict]:
    """Recherche un anime sur MAL et retourne les meilleurs résultats."""
    data = _get("/anime", {"q": query, "limit": limit, "order_by": "score",
                           "sort": "desc", "sfw": False})
    if not data:
        return []
    return [_format_anime(a) for a in (data.get("data") or [])]


def get_mal_score(title: str) -> Optional[float]:
    """
    Retourne le score MAL pour un titre donné (meilleure correspondance).
    Utilisé pour enrichir les résultats /search.
    """
    results = search_anime(title, limit=1)
    if results and results[0].get("score"):
        return results[0]["score"]
    return None
