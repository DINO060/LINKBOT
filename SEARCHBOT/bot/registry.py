"""
bot/registry.py
================
Registre des sites enregistrés via /addsite.

Stockage dans data/sites_registry.json :
{
  "hentaihaven.xxx": {
    "domain": "hentaihaven.xxx",
    "url": "https://hentaihaven.xxx",
    "category": "h",
    "added_at": "2026-03-07T01:00:00"
  },
  ...
}

Catégories disponibles :
  h       — hentai
  anime   — anime
  pwha    — pwha
  social  — réseaux sociaux (Telegram, Reddit, ...)

Usage :
    reg.add("https://hentaihaven.xxx", category="h")
    reg.get_by_category("anime")  → liste des sites anime
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Fichier de stockage
_REGISTRY_PATH = Path(__file__).parent.parent / "data" / "sites_registry.json"

# Catégories valides
VALID_CATEGORIES: dict[str, str] = {
    "h":      "Hentai 🔞",
    "anime":  "Anime 🎬",
    "pwha":   "Pwha 🔥",
    "social": "Social 📡",
    "comic":  "Comic 📚",
    "porn":   "Porn 🔥",
    "serie":  "Série 📺",
}
_ALIASES: dict[str, str] = {
    "hentai":    "h",
    "social":    "social",
    "telegram":  "social",
    "reddit":    "social",
    "twitter":   "social",
    "x":         "social",
    "comics":    "comic",
    "bd":        "comic",
    "manga":     "comic",
    "porno":     "porn",
    "xxx":       "porn",
    "series":    "serie",
    "tv":        "serie",
    "série":     "serie",
    "séries":    "serie",
}


_TG_RE      = re.compile(r"https?://(?:www\.)?t\.me/(?:s/)?(\w+)", re.IGNORECASE)
_REDDIT_RE  = re.compile(r"https?://(?:www\.)?reddit\.com/r/([\w]+)", re.IGNORECASE)
_TWITTER_RE = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/(@?[\w]+)", re.IGNORECASE)

def _make_key(url: str) -> str:
    """
    Clé unique pour un site.
    - Canal Telegram  : "t.me/NomCanal"           (distingue chaque canal)
    - Subreddit Reddit: "reddit.com/r/anime"      (distingue chaque subreddit)
    - Compte Twitter  : "twitter.com/username"    (normalisé, x.com → twitter.com)
    - Autres sites    : domaine sans www  (ex: "hentaihaven.xxx")
    """
    m = _TG_RE.match(url)
    if m:
        return f"t.me/{m.group(1).lower()}"
    m = _REDDIT_RE.match(url)
    if m:
        return f"reddit.com/r/{m.group(1).lower()}"
    m = _TWITTER_RE.match(url)
    if m:
        username = m.group(1).lstrip("@").lower()
        return f"twitter.com/{username}"
    return urlparse(url).netloc.lower().lstrip("www.")


class SiteRegistry:
    """Registre JSON des sites surveillés."""

    def __init__(self, path: Path = _REGISTRY_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, dict] = self._load()

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Impossible de lire le registre : %s", e)
        return {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── API publique ──────────────────────────────────────────────────────────

    def add(self, url: str, category: str = "") -> dict:
        """
        Enregistre un site avec sa catégorie.
        Retourne l'entrée créée (ou existante si déjà enregistré).
        """
        key = _make_key(url)
        if not key:
            raise ValueError(f"URL invalide : {url!r}")

        # Normaliser la catégorie
        cat = category.lower().strip()
        cat = _ALIASES.get(cat, cat)
        if cat and cat not in VALID_CATEGORIES:
            raise ValueError(
                f"Catégorie invalide : {category!r}.\n"
                f"Catégories valides : {', '.join(VALID_CATEGORIES)}"
            )

        # Auto-détection pour Telegram/Reddit/Twitter si pas de catégorie
        if not cat:
            if (
                key.startswith("t.me/")
                or key.startswith("reddit.com/r/")
                or key.startswith("twitter.com/")
            ):
                cat = "social"

        if key in self._data:
            # Mettre à jour la catégorie si précisée
            if cat:
                self._data[key]["category"] = cat
                self._save()
            return self._data[key]

        entry = {
            "domain":   key,
            "url":      url,
            "category": cat,
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._data[key] = entry
        self._save()
        logger.info("Site enregistré : %s (catégorie: %s)", key, cat or "aucune")
        return entry

    def remove(self, domain: str) -> bool:
        """Supprime un site. Retourne True si supprimé, False si introuvable."""
        # Accepte aussi une URL complète
        key = _make_key(domain) if domain.startswith("http") else domain.lower().lstrip("www.")
        if key in self._data:
            del self._data[key]
            self._save()
            logger.info("Site supprimé : %s", key)
            return True
        return False

    def all(self) -> list[dict]:
        """Retourne toutes les entrées."""
        return list(self._data.values())

    def get_by_category(self, category: str) -> list[dict]:
        """
        Retourne les sites d'une catégorie donnée.
        Si category est vide ou None, retourne tous les sites.
        """
        if not category:
            return self.all()
        cat = _ALIASES.get(category.lower(), category.lower())
        return [s for s in self._data.values() if s.get("category") == cat]

    def all_domains(self) -> list[str]:
        """Retourne la liste des domaines enregistrés."""
        return list(self._data.keys())

    def is_registered(self, domain_or_url: str) -> bool:
        """Vérifie si un domaine/URL est enregistré."""
        if domain_or_url.startswith("http"):
            key = _make_key(domain_or_url)
        else:
            key = domain_or_url.lower().lstrip("www.")
        return key in self._data

    def count(self) -> int:
        return len(self._data)
