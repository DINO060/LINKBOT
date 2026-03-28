"""
bot/searcher.py
================
Moteur de recherche pour les deux commandes :

  /search <query>
    → Recherche UNIQUEMENT sur les sites enregistrés dans le registre
    → Utilise DuckDuckGo avec l'opérateur "site:domain query"
    → Pour chaque résultat, scrape les métadonnées (cover, synopsis, épisodes)

  /usearch <query>
    → Recherche UNIVERSELLE sur DuckDuckGo (tout l'internet)
    → Pas limité aux sites enregistrés
    → Même enrichissement métadonnées pour chaque résultat

Usage :
    from bot.searcher import Searcher
    searcher = Searcher()

    # Recherche sur sites enregistrés
    results = searcher.search_registered("imaizumin", registry)

    # Recherche universelle
    results = searcher.search_universal("imaizumin hentai episode 3")
"""

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from urllib.parse import urlparse

from bot.meta_scraper import get_series_url, is_episode_url, scrape_series_page

logger = logging.getLogger(__name__)

# Nombre max de résultats DuckDuckGo par site (pour /search)
_MAX_PER_SITE = 5
# Nombre max de résultats pour /usearch
_MAX_UNIVERSAL = 10
# Nombre max de threads parallèles
_MAX_WORKERS = 6


def _slug_from_query(query: str) -> str:
    """Convertit une query en slug URL : minuscules, espaces → tirets, caractères spéciaux supprimés."""
    slug = query.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)   # retire ponctuation
    slug = re.sub(r"[\s_]+", "-", slug)    # espaces/underscores → tirets
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug


# Patterns d'URL à tenter par domaine quand DDG ne retourne rien.
# Clef : sous-chaîne du domaine.  Valeur : liste de templates avec {base} et {slug}.
_DOMAIN_URL_PATTERNS: dict[str, list[str]] = {
    "anime-sama":    ["{base}/catalogue/{slug}/"],
    "hentaihaven":   ["{base}/watch/{slug}/"],
    "hanime":        ["{base}/videos/hentai/{slug}"],
}

# Domaines commerciaux/non-médias à exclure de la recherche universelle.
# Ces domaines retournent des jouets, produits physiques ou pages commerciales
# au lieu de contenu multimédia (films, séries, anime, streaming).
_NON_MEDIA_DOMAINS: frozenset[str] = frozenset([
    "amazon.com", "amazon.fr", "amazon.co.uk", "amazon.de", "amazon.es",
    "amazon.co.jp", "amazon.ca", "amazon.com.br",
    "ebay.com", "ebay.fr", "ebay.co.uk", "ebay.de",
    "walmart.com", "target.com", "bestbuy.com",
    "aliexpress.com", "alibaba.com", "wish.com", "shein.com",
    "etsy.com", "redbubble.com", "teepublic.com",
    "fnac.com", "cdiscount.com", "darty.com", "boulanger.com",
    "rakuten.com", "pricespy.com", "idealo.com", "kelkoo.com",
    "shopping.google", "google.com/shopping",
    "play.google.com/store/apps",
    "apps.apple.com",
    "mercadolibre.com", "mercadolivre.com",
])

# Termes injectés dans la query universelle pour orienter DDG vers le contenu multimédia.
_MEDIA_BOOST_TERMS = (
    "film OR série OR anime OR streaming OR trailer "
    "OR épisode OR manga OR synopsis OR bande-annonce OR cinema"
)

# Sous-chaînes présentes dans les titres de pages d'erreur/404.
# Un résultat dont le titre contient l'une de ces chaînes est rejeté.
_ERROR_TITLE_FRAGMENTS: frozenset[str] = frozenset([
    "page not found", "page introuvable", "404", "not found",
    "oops", "error 404", "erreur 404", "cette page n'existe pas",
    "page doesn't exist", "page does not exist",
    "introuvable", "aucun résultat",
])


def _is_error_result(query: str, result: dict) -> bool:
    """
    Retourne True si le résultat est à rejeter :
      1. Titre contient un mot-clé de page 404/erreur
      2. Score de pertinence trop faible ET pas d'épisodes (page générique/bot-trap)
    """
    title = (result.get("title") or "").lower()

    # Règle 1 : titre d'erreur 404
    if any(frag in title for frag in _ERROR_TITLE_FRAGMENTS):
        logger.debug("Filtré (titre erreur) : %r", result.get("title"))
        return True

    # Règle 2 : pertinence trop faible ET pas de contenu utile
    score = _relevance_score(query, result.get("title", ""), result.get("url", ""))
    has_episodes = bool(result.get("episodes") or result.get("episode_count"))
    if score < 0.15 and not has_episodes:
        logger.debug("Filtré (pertinence %.2f, sans épisodes) : %r", score, result.get("title"))
        return True

    return False
_DEFAULT_URL_PATTERNS = [
    "{base}/catalogue/{slug}/",
    "{base}/watch/{slug}/",
    "{base}/{slug}/",
]


def _direct_url_candidates(base_url: str, domain: str, query: str) -> list[str]:
    """Retourne les URLs probables à tenter directement pour un domaine + query."""
    slug = _slug_from_query(query)
    base = base_url.rstrip("/")
    patterns = None
    for key, tmpl in _DOMAIN_URL_PATTERNS.items():
        if key in domain:
            patterns = tmpl
            break
    if patterns is None:
        patterns = _DEFAULT_URL_PATTERNS
    return [p.format(base=base, slug=slug) for p in patterns]


def _ddg_search(query: str, max_results: int = 5, safesearch: str = "off") -> list[dict]:
    """
    Lance une recherche DuckDuckGo et retourne les résultats bruts.
    Retourne [] en cas d'erreur.
    """
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.error("ddgs non installé — pip install ddgs")
            return []

    try:
        with DDGS() as ddgs:
            return list(ddgs.text(
                query,
                max_results=max_results,
                safesearch=safesearch,
            ))
    except Exception as exc:
        logger.warning("DuckDuckGo erreur pour %r : %s", query, exc)
        return []


def _normalize_slug(url: str) -> str:
    """
    Extrait et normalise le slug de série depuis une URL.
    Supprime le protocole, domaine, suffixes d'épisode/saison/langue et paramètres.
    Ex: anime-sama.to/catalogue/frieren/saison2/vostfr/ → catalogue/frieren
    """
    if "//" in url:
        path = url.split("//", 1)[-1].split("/", 1)[-1]
    else:
        path = url
    # Supprime query params d'abord
    path = path.split("?")[0].rstrip("/")
    # Supprime les suffixes épisode / saison / langue en boucle
    _SLUG_SEG_RE = re.compile(
        r"/(episode|ep|saison|season)[-_]?\d*(/|$)"
        r"|/(vostfr|vf(-vostfr)?|vo)(/|$)"
        r"|/\d+(/|$)",
        re.IGNORECASE,
    )
    prev = None
    while prev != path:
        prev = path
        path = _SLUG_SEG_RE.sub("/", path).rstrip("/")
    return path.lower()


def _relevance_score(query: str, title: str, url: str) -> float:
    """
    Score 0–1 mesurant la pertinence d'un résultat par rapport à la query.
    Combine similarité de titre (60 %) et couverture des mots-clés (40 %).
    """
    q = query.lower().replace("-", " ").replace("_", " ")
    t = (title or "").lower()
    u = url.lower()
    title_score = SequenceMatcher(None, q, t).ratio()
    words = [w for w in re.split(r"\s+", q) if len(w) >= 3]
    if words:
        in_title = sum(1 for w in words if w in t)
        in_url   = sum(1 for w in words if w in u)
        coverage = max(in_title, in_url) / len(words)
    else:
        coverage = 0.0
    return title_score * 0.6 + coverage * 0.4


def _group_by_series(raw_results: list[dict]) -> dict[str, list[dict]]:
    """
    Groupe les résultats DuckDuckGo bruts par URL de série.
    Utilise _normalize_slug pour fusionner les variantes du même anime
    (épisodes différents, slugs légèrement différents).
    Retourne {series_url: [raw_result, ...]}
    """
    # Segments de chemin génériques qui ne correspondent pas à une série spécifique
    _GENERIC_PATHS = {
        "", "/", "catalogue", "watch", "anime", "manga", "hentai",
        "latest", "newest", "new", "recent", "updates", "search",
        "tags", "genres", "films", "movies", "archives",
    }

    slug_to_url: dict[str, str]       = {}  # slug normalisé → URL représentative
    groups: dict[str, list[dict]]     = {}  # URL représentative → résultats DDG
    for r in raw_results:
        url = r.get("href") or r.get("url", "")
        if not url:
            continue
        series_url = get_series_url(url) if is_episode_url(url) else url

        # Ignorer les URLs sans chemin ou avec un chemin générique (homepage, /catalogue/, etc.)
        path = urlparse(series_url).path.strip("/")
        # Le dernier segment du chemin doit exister et ne pas être générique
        last_seg = path.split("/")[-1] if path else ""
        if not last_seg or last_seg.lower() in _GENERIC_PATHS:
            logger.debug("URL ignorée (chemin générique) : %s", series_url)
            continue
        # Ignorer les URLs dont le path est purement numérique (ex: /2025/)
        if last_seg.isdigit():
            logger.debug("URL ignorée (segment numérique) : %s", series_url)
            continue

        slug = _normalize_slug(series_url)
        if slug not in slug_to_url:
            slug_to_url[slug] = series_url
            groups[series_url] = []
        repr_url = slug_to_url[slug]
        groups[repr_url].append(r)
    return groups


def _enrich_series(series_url: str, raw_samples: list[dict]) -> dict:
    """
    Scrape la page de la série (une seule fois) et retourne un dict enrichi.
    `raw_samples` sert de fallback si le scraping échoue.
    """
    fallback_title = raw_samples[0].get("title", "") if raw_samples else ""
    fallback_body  = raw_samples[0].get("body", "")  if raw_samples else ""

    meta = scrape_series_page(series_url)

    # Si la liste d'épisodes est vide mais que les URLs DDG étaient des épisodes,
    # on reconstruit une liste minimale à partir des URLs brutes
    episodes = meta.get("episodes") or []
    if not episodes:
        ep_re = re.compile(r"episode[-_]?(\d+)", re.IGNORECASE)
        seen: set[int] = set()
        for r in raw_samples:
            href = r.get("href") or r.get("url", "")
            m = ep_re.search(href)
            if m:
                num = int(m.group(1))
                if num not in seen:
                    seen.add(num)
                    episodes.append({"number": num, "url": href, "date": "", "thumb": None})
        episodes.sort(key=lambda e: e["number"], reverse=True)

    return {
        "title":            meta["title"] or fallback_title,
        "cover":            meta["cover"],
        "synopsis":         meta["synopsis"] or fallback_body[:400],
        "url":              series_url,
        "domain":           meta["domain"] or urlparse(series_url).netloc.lstrip("www."),
        "genres":           meta.get("genres", []),
        "authors":          meta.get("authors", []),
        "release_date":     meta.get("release_date", ""),
        "episodes":         episodes,
        "episode_count":    meta["episode_count"] or len(episodes) or None,
        "episode_number":   meta["episode_number"],
        "episode_duration": meta["episode_duration"],
    }


class Searcher:
    """
    Moteur de recherche principal du bot.
    Toutes les méthodes sont synchrones (à appeler via asyncio.to_thread).
    """

    # ── /search : sur les sites enregistrés ───────────────────────────────────

    def search_registered(
        self,
        query: str,
        registry,
        max_per_site: int = _MAX_PER_SITE,
        category: str = "",
    ) -> list[dict]:
        """
        Cherche `query` sur les sites enregistrés dans `registry`.
        Si `category` est fourni (h, anime, pwha, social), n'interroge que
        les sites de cette catégorie.

        1. DuckDuckGo "site:domain query" → URLs d'épisodes ou de séries
        2. Groupe par série (déduplique les épisodes du même anime)
        3. Scrape la page de série une seule fois par groupe
        4. Retourne TOUS les résultats trouvés (pas de limite)
        """
        sites = registry.get_by_category(category) if category else registry.all()
        domains = [s["domain"] for s in sites]
        if not domains:
            return []

        # Étape 1 : Récupérer les URLs DuckDuckGo pour chaque site en parallèle
        raw_results: list[dict] = []

        def _search_one_site(domain: str) -> list[dict]:
            site_query = f'site:{domain} {query}'
            raws = _ddg_search(site_query, max_results=max_per_site)
            logger.info("DDG site:%s → %d résultats", domain, len(raws))
            return raws

        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(domains))) as pool:
            futures = {pool.submit(_search_one_site, d): d for d in domains}
            for fut in as_completed(futures):
                try:
                    raw_results.extend(fut.result())
                except Exception as e:
                    logger.warning("Erreur site %s : %s", futures[fut], e)

        if not raw_results:
            pass  # continuer vers le fallback même si DDG vide

        # Étape 2 : Grouper par série + scraper une fois par série (parallèle)
        groups = _group_by_series(raw_results)
        logger.info("Groupés en %d série(s) depuis %d résultats DDG", len(groups), len(raw_results))

        # ── Fallback direct ────────────────────────────────────────────────
        # Pour chaque domaine enregistré qui n'a AUCUNE entrée dans groups,
        # on construit l'URL probabble directement depuis la query et on scrape.
        domains_in_groups = {
            urlparse(u).netloc.lstrip("www.") for u in groups
        }
        for site in sites:
            domain = site["domain"]
            if domain.startswith("t.me/") or domain.startswith("reddit.com/r/"):
                continue  # canaux Telegram / subreddits : pas de fallback URL
            if domain in domains_in_groups:
                continue  # déjà couvert par DDG
            base_url = site.get("url", f"https://{domain}")
            candidates = _direct_url_candidates(base_url, domain, query)
            logger.info("[fallback] %s → candidates %s", domain, candidates)
            for candidate_url in candidates:
                if candidate_url not in groups:
                    groups[candidate_url] = [{"href": candidate_url, "title": query, "body": ""}]
                    break  # un seul candidat par domaine

        enriched: list[dict] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures_map = {
                pool.submit(_enrich_series, series_url, samples): series_url
                for series_url, samples in groups.items()
            }
            for fut in as_completed(futures_map):
                try:
                    enriched.append(fut.result())
                except Exception as e:
                    logger.warning("Erreur enrichissement série %s : %s", futures_map[fut], e)

        # Trier par pertinence (query vs titre / URL) et retourner max 3
        # Filtrer les résultats vides (fallback échoué : titre = query, pas de synopsis)
        enriched = [
            r for r in enriched
            if (r.get("synopsis") or r.get("cover") or (
                r.get("title", "").lower() != query.lower()
                and r.get("title", "").lower() != _slug_from_query(query)
            ))
            and not _is_error_result(query, r)
        ]
        enriched.sort(
            key=lambda r: _relevance_score(query, r.get("title", ""), r.get("url", "")),
            reverse=True,
        )
        logger.info("Résultats : %d pour catégorie=%r", len(enriched), category or "toutes")
        return enriched  # tous les résultats, sans limite

    # ── /usearch : recherche universelle ─────────────────────────────────────

    def search_universal(
        self,
        query: str,
        max_results: int = _MAX_UNIVERSAL,
    ) -> list[dict]:
        """
        Recherche universelle sur DuckDuckGo (tout l'internet).
        Injecte des termes média pour orienter DDG vers films/séries/anime.
        Filtre les domaines commerciaux (Amazon, eBay, boutiques…).
        Groupe également les résultats par série pour éviter les doublons.
        """
        # Injecter les termes média uniquement si la query n'en contient pas déjà
        _media_keywords = {"film", "serie", "série", "anime", "streaming",
                           "trailer", "episode", "épisode", "manga", "cinema"}
        query_lower = query.lower()
        needs_boost = not any(kw in query_lower for kw in _media_keywords)
        ddg_query = f"{query} {_MEDIA_BOOST_TERMS}" if needs_boost else query

        # Demander plus de résultats pour compenser le filtrage des domaines commerciaux
        raw_results = _ddg_search(ddg_query, max_results=max_results + 8)
        logger.info("DDG universel %r → %d résultats bruts", ddg_query, len(raw_results))

        # Filtrer les domaines commerciaux / non-médias
        def _is_commercial(r: dict) -> bool:
            href = (r.get("href") or r.get("url") or "").lower()
            return any(d in href for d in _NON_MEDIA_DOMAINS)

        raw_results = [r for r in raw_results if not _is_commercial(r)]
        raw_results = raw_results[:max_results]
        logger.info("DDG universel après filtrage commercial → %d résultats", len(raw_results))

        if not raw_results:
            return []

        # Grouper par série + enrichir
        groups = _group_by_series(raw_results)
        logger.info("Groupés en %d série(s)", len(groups))

        enriched: list[dict] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures_map = {
                pool.submit(_enrich_series, series_url, samples): series_url
                for series_url, samples in groups.items()
            }
            for fut in as_completed(futures_map):
                try:
                    enriched.append(fut.result())
                except Exception as e:
                    logger.warning("Erreur enrichissement série : %s", e)

        # Trier par pertinence et retourner max 3
        enriched = [r for r in enriched if not _is_error_result(query, r)]
        enriched.sort(
            key=lambda r: _relevance_score(query, r.get("title", ""), r.get("url", "")),
            reverse=True,
        )
        return enriched[:3]
    # ── /ssearch : recherche sur un site précis (pas besoin d'être enregistré) ──

    def search_site(
        self,
        site_url: str,
        query: str,
        max_results: int = _MAX_PER_SITE,
    ) -> list[dict]:
        """
        Cherche `query` sur un site précis donné par son URL.
        Le site n'a pas besoin d'être enregistré dans le registre.

        1. DuckDuckGo "site:domain query" → URLs candidates
        2. Fallback URLs directes si DDG vide
        3. Groupe + enrichit (cover, synopsis, épisodes)
        4. Retourne tous les résultats triés par pertinence
        """
        parsed = urlparse(site_url)
        domain = parsed.netloc.lstrip("www.") or site_url.lstrip("www.")
        base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else site_url.rstrip("/")

        # Étape 1 : DuckDuckGo site:domain query
        site_query = f"site:{domain} {query}"
        raw_results = _ddg_search(site_query, max_results=max_results)
        logger.info("DDG site:%s %r → %d résultats", domain, query, len(raw_results))

        # Étape 2 : Fallback URL directe si DDG vide
        if not raw_results:
            candidates = _direct_url_candidates(base_url, domain, query)
            logger.info("[fallback ssearch] %s → %s", domain, candidates)
            for c in candidates:
                raw_results.append({"href": c, "title": query, "body": ""})

        if not raw_results:
            return []

        # Étape 3 : Grouper + enrichir
        groups = _group_by_series(raw_results)
        logger.info("ssearch groupés en %d série(s)", len(groups))

        enriched: list[dict] = []
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures_map = {
                pool.submit(_enrich_series, series_url, samples): series_url
                for series_url, samples in groups.items()
            }
            for fut in as_completed(futures_map):
                try:
                    enriched.append(fut.result())
                except Exception as e:
                    logger.warning("Erreur enrichissement ssearch %s : %s", futures_map[fut], e)

        enriched = [r for r in enriched if not _is_error_result(query, r)]
        enriched.sort(
            key=lambda r: _relevance_score(query, r.get("title", ""), r.get("url", "")),
            reverse=True,
        )
        logger.info("ssearch résultats : %d pour %r sur %s", len(enriched), query, domain)
        return enriched