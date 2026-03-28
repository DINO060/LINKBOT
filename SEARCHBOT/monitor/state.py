"""
monitor/state.py
=================
Gère la persistance des URLs déjà notifiées dans data/last_seen.json.
Évite d'envoyer deux fois la même notification.

Structure JSON :
{
  "hentaihaven.xxx": {
    "urls": ["https://...", "https://..."],
    "last_check": "2026-03-07T09:00:00+00:00"
  },
  ...
}

Usage :
    from monitor.state import LastSeenState
    state = LastSeenState()
    if state.is_new("hentaihaven.xxx", url):
        # envoyer la notif
        state.mark_seen("hentaihaven.xxx", url)
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_STATE_PATH = Path(__file__).parent.parent / "data" / "last_seen.json"

# Nombre max d'URLs gardées en mémoire par domaine (évite fichier infini)
_MAX_SEEN_PER_DOMAIN = 500


class LastSeenState:
    """Registre JSON des contenus déjà notifiés, par domaine."""

    def __init__(self, path: Path = _STATE_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

    # ── Persistance ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        bak = self._path.with_suffix(".json.bak")
        data = self._try_read(self._path)
        if data is not None:
            return data
        if bak.exists():
            logger.warning("last_seen.json illisible, chargement du backup…")
            data = self._try_read(bak)
            if data is not None:
                self._path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return data
        return {}

    @staticmethod
    def _try_read(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                return None
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning("Impossible de lire %s : %s", path, e)
        return None

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

    # ── API publique ──────────────────────────────────────────────────────────

    def is_new(self, domain: str, url: str) -> bool:
        """Retourne True si l'URL n'a jamais été notifiée pour ce domaine."""
        return url not in self._data.get(domain, {}).get("urls", [])

    def mark_seen(self, domain: str, url: str) -> None:
        """Marque une URL comme déjà notifiée."""
        if domain not in self._data:
            self._data[domain] = {"urls": [], "last_check": ""}

        seen: list = self._data[domain]["urls"]
        if url not in seen:
            seen.append(url)
            # Garder seulement les N dernières (FIFO)
            self._data[domain]["urls"] = seen[-_MAX_SEEN_PER_DOMAIN:]

        self._save()

    def update_check_time(self, domain: str) -> None:
        """Enregistre l'heure du dernier check pour un domaine."""
        if domain not in self._data:
            self._data[domain] = {"urls": [], "last_check": ""}
        self._data[domain]["last_check"] = datetime.now(timezone.utc).isoformat()
        self._save()

    def get_last_check(self, domain: str) -> str:
        """Retourne le timestamp ISO du dernier check, ou 'Jamais'."""
        ts = self._data.get(domain, {}).get("last_check", "")
        return ts if ts else "Jamais"

    def seen_count(self, domain: str) -> int:
        """Nombre d'URLs déjà vues pour un domaine."""
        return len(self._data.get(domain, {}).get("urls", []))


# ── Config monitor (enabled / check_hour) ────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent.parent / "data" / "monitor_config.json"

def _default_config() -> dict:
    """Valeurs par défaut — respecte les variables d'environnement si présentes."""
    import os
    return {
        "enabled":               False,
        "check_hour":            int(os.getenv("MONITOR_HOUR",   "9")),
        "check_minute":          int(os.getenv("MONITOR_MINUTE", "0")),
        "check_interval_hours":  0,   # 0 = mode quotidien (cron), >0 = mode intervalle
    }


class MonitorConfig:
    """Stocke la config du monitor (activé/désactivé, heure du check)."""

    def __init__(self, path: Path = _CONFIG_PATH):
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict = self._load()

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
                except Exception:
                    pass
        return _default_config()

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

    @property
    def enabled(self) -> bool:
        return bool(self._data.get("enabled", False))

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._data["enabled"] = value
        self._save()

    @property
    def check_hour(self) -> int:
        return int(self._data.get("check_hour", 9))

    @check_hour.setter
    def check_hour(self, value: int) -> None:
        self._data["check_hour"] = int(value)
        self._save()

    @property
    def check_minute(self) -> int:
        return int(self._data.get("check_minute", 0))

    @check_minute.setter
    def check_minute(self, value: int) -> None:
        self._data["check_minute"] = int(value)
        self._save()

    @property
    def check_interval_hours(self) -> int:
        """0 = mode quotidien (cron HH:MM), >0 = mode intervalle toutes les N heures."""
        return int(self._data.get("check_interval_hours", 0))

    @check_interval_hours.setter
    def check_interval_hours(self, value: int) -> None:
        self._data["check_interval_hours"] = int(value)
        self._save()

    @property
    def extra_chats(self) -> list[int]:
        """Chat IDs supplémentaires ajoutés via /monitor setchat."""
        return [int(x) for x in self._data.get("extra_chats", [])]

    @extra_chats.setter
    def extra_chats(self, value: list[int]) -> None:
        self._data["extra_chats"] = [int(x) for x in value]
        self._save()
