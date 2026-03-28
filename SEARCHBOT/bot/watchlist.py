"""
bot/watchlist.py
=================
Watchlist par utilisateur — stockée dans data/watchlist.json.

Structure :
{
  "123456789": ["frieren", "one piece", "jujutsu kaisen"]
}

Fonctionnement :
  - L'utilisateur ajoute des mots-clés avec /watch <titre>
  - Le monitor, quand il détecte un nouvel item, compare le titre
    avec tous les mots-clés de tous les utilisateurs
  - Si match → notification directe à l'utilisateur
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_WATCH_PATH = Path(__file__).parent.parent / "data" / "watchlist.json"

MAX_KEYWORDS_PER_USER = 30


class WatchlistStore:
    """Registre persistant des mots-clés de surveillance par utilisateur."""

    def __init__(self, path: Path = _WATCH_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, list[str]] = self._load()

    def _load(self) -> dict:
        if self._path.exists():
            try:
                return json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("watchlist: impossible de lire %s : %s", self._path, e)
        return {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, user_id: int, keyword: str) -> bool:
        """
        Ajoute un mot-clé à surveiller.
        Retourne False si déjà présent ou quota atteint.
        """
        key = str(user_id)
        kw  = keyword.lower().strip()
        if not kw:
            return False

        if key not in self._data:
            self._data[key] = []

        if kw in self._data[key]:
            return False

        if len(self._data[key]) >= MAX_KEYWORDS_PER_USER:
            return False

        self._data[key].append(kw)
        self._save()
        logger.debug("watchlist: user %s → ajout «%s»", user_id, kw)
        return True

    def remove(self, user_id: int, keyword: str) -> bool:
        """Supprime un mot-clé. Retourne True si supprimé."""
        key = str(user_id)
        kw  = keyword.lower().strip()
        if key in self._data and kw in self._data[key]:
            self._data[key].remove(kw)
            self._save()
            logger.debug("watchlist: user %s → suppression «%s»", user_id, kw)
            return True
        return False

    def all_keywords(self, user_id: int) -> list[str]:
        """Retourne les mots-clés d'un utilisateur."""
        return list(self._data.get(str(user_id), []))

    def all_watchers(self) -> dict[str, list[str]]:
        """Retourne le dict complet {user_id_str: [keywords]}."""
        return dict(self._data)

    def matches_for_title(self, title: str) -> dict[str, list[str]]:
        """
        Retourne {user_id_str: [matched_keywords]} pour les utilisateurs
        dont au moins un mot-clé correspond au titre donné.
        """
        t = title.lower()
        result = {}
        for uid_str, keywords in self._data.items():
            matched = [kw for kw in keywords if kw in t]
            if matched:
                result[uid_str] = matched
        return result
