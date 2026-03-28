"""
bot/favorites.py
=================
Favoris par utilisateur — stockés dans data/favorites.json.

Structure :
{
  "123456789": [
    {"title": "Frieren", "url": "https://...", "domain": "...", "cover": "...", "added_at": "..."},
    ...
  ]
}
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_FAV_PATH = Path(__file__).parent.parent / "data" / "favorites.json"

MAX_FAV_PER_USER = 50


class FavoritesStore:
    """Registre persistant des favoris par utilisateur."""

    def __init__(self, path: Path = _FAV_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, list] = self._load()

    def _load(self) -> dict:
        bak = self._path.with_suffix(".json.bak")
        for p in (self._path, bak):
            if p.exists():
                try:
                    text = p.read_text(encoding="utf-8").strip()
                    if text:
                        data = json.loads(text)
                        if isinstance(data, dict):
                            return data
                except Exception as e:
                    logger.warning("favorites: impossible de lire %s : %s", p, e)
        return {}

    def _save(self) -> None:
        if self._path.exists():
            try:
                self._path.with_suffix(".json.bak").write_text(
                    self._path.read_text(encoding="utf-8"), encoding="utf-8",
                )
            except Exception:
                pass
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def add(self, user_id: int, item: dict) -> bool:
        """
        Ajoute un item aux favoris.
        Retourne False si déjà présent ou quota atteint.
        """
        key = str(user_id)
        if key not in self._data:
            self._data[key] = []

        url = item.get("url", "")
        if not url:
            return False

        # Déjà en favori ?
        if any(f["url"] == url for f in self._data[key]):
            return False

        # Quota
        if len(self._data[key]) >= MAX_FAV_PER_USER:
            return False

        self._data[key].append({
            "title":    item.get("title") or "Sans titre",
            "url":      url,
            "domain":   item.get("domain", ""),
            "cover":    item.get("cover"),
            "added_at": datetime.now(timezone.utc).isoformat(),
        })
        self._save()
        logger.debug("favorites: user %s → ajout %s", user_id, url[:60])
        return True

    def remove(self, user_id: int, index: int) -> bool:
        """Supprime le favori à l'index donné (0-based). Retourne True si supprimé."""
        key = str(user_id)
        favs = self._data.get(key, [])
        if 0 <= index < len(favs):
            removed = favs.pop(index)
            self._save()
            logger.debug("favorites: user %s → suppression index %d (%s)", user_id, index, removed.get("title"))
            return True
        return False

    def all(self, user_id: int) -> list[dict]:
        """Retourne la liste des favoris d'un utilisateur."""
        return list(self._data.get(str(user_id), []))

    def count(self, user_id: int) -> int:
        return len(self._data.get(str(user_id), []))
