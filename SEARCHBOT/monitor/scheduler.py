"""
monitor/scheduler.py
=====================
APScheduler — vérifie les nouveautés sur tous les sites enregistrés.

Fonctionnement :
  - Check automatique 1x/jour à l'heure configurée (MONITOR_HOUR dans .env)
  - Peut être déclenché manuellement via /monitor now
  - Pour chaque site enregistré dans SiteRegistry :
      1. Récupère les derniers contenus via le scraper du site
      2. Compare avec last_seen.json (LastSeenState)
      3. Pour chaque nouveauté → envoie une notification Telegram (notifier.py)

Usage (intégration dans run_bot) :
    from monitor.scheduler import MonitorScheduler
    scheduler = MonitorScheduler(bot=app.bot, chat_id=ADMIN_CHAT_ID, registry=_registry)
    scheduler.start()
    # ...
    scheduler.stop()

    # Check immédiat :
    await scheduler.check_now()
"""

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.registry import SiteRegistry
from monitor.sites.base import get_scraper_for
from monitor.state import LastSeenState, MonitorConfig

logger = logging.getLogger(__name__)


class MonitorScheduler:
    """
    Orchestrateur du monitoring.
    Utilise APScheduler (AsyncIOScheduler) pour automatiser les checks.
    """

    def __init__(self, bot, registry: SiteRegistry, chat_ids: list[int] = None, chat_id: int = None):
        """
        bot       : instance telegram.Bot
        chat_ids  : liste d'IDs Telegram (admins) où envoyer les notifications
        registry  : SiteRegistry partagé avec le bot
        """
        self.bot = bot
        # Support ancien paramètre chat_id (int) et nouveau chat_ids (list)
        if chat_ids:
            self._admin_chat_ids: list[int] = chat_ids
        elif chat_id:
            self._admin_chat_ids = [int(chat_id)]
        else:
            self._admin_chat_ids = []
        self.registry = registry
        self.state = LastSeenState()
        self.config = MonitorConfig()

        # Watchlist — pour notifier les utilisateurs qui suivent des mots-clés
        from bot.watchlist import WatchlistStore
        self._watchlist = WatchlistStore()

        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._job = None

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Démarre le scheduler APScheduler."""
        self._schedule_daily_job()
        self._scheduler.start()
        logger.info(
            "Monitor démarré — check quotidien à %02d:%02d UTC (activé: %s)",
            self.config.check_hour,
            self.config.check_minute,
            self.config.enabled,
        )

    @property
    def chat_ids(self) -> list[int]:
        """Fusion des IDs admins + chats supplémentaires persistés."""
        extra = self.config.extra_chats
        combined = list(self._admin_chat_ids)
        for cid in extra:
            if cid not in combined:
                combined.append(cid)
        return combined

    def add_notification_chat(self, chat_id: int) -> bool:
        """Ajoute un chat aux destinataires des notifications. Retourne False si déjà présent."""
        extra = self.config.extra_chats
        if chat_id in extra or chat_id in self._admin_chat_ids:
            return False
        extra.append(chat_id)
        self.config.extra_chats = extra
        logger.info("Monitor : chat %d ajouté aux destinataires", chat_id)
        return True

    def remove_notification_chat(self, chat_id: int) -> bool:
        """Supprime un chat ajouté via setchat. Retourne False si introuvable."""
        extra = self.config.extra_chats
        if chat_id not in extra:
            return False
        extra.remove(chat_id)
        self.config.extra_chats = extra
        logger.info("Monitor : chat %d retiré des destinataires", chat_id)
        return True

    def stop(self) -> None:
        """Arrête proprement le scheduler."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Monitor arrêté.")

    def _schedule_daily_job(self) -> None:
        """Planifie (ou replanifie) le job selon le mode actuel (cron ou intervalle)."""
        if self._job:
            try:
                self._job.remove()
            except Exception:
                pass

        interval_h = self.config.check_interval_hours
        if interval_h and interval_h > 0:
            # Mode intervalle : toutes les N heures
            self._job = self._scheduler.add_job(
                self._daily_check_wrapper,
                trigger="interval",
                hours=interval_h,
                id="daily_monitor",
                replace_existing=True,
            )
            logger.debug("Job planifié : toutes les %dh", interval_h)
        else:
            # Mode cron : quotidien à HH:MM UTC
            self._job = self._scheduler.add_job(
                self._daily_check_wrapper,
                trigger="cron",
                hour=self.config.check_hour,
                minute=self.config.check_minute,
                id="daily_monitor",
                replace_existing=True,
            )
            logger.debug(
                "Job quotidien planifié : %02d:%02d UTC",
                self.config.check_hour,
                self.config.check_minute,
            )

    def set_schedule(self, hour: int, minute: int) -> None:
        """Change l'heure du check quotidien (désactive le mode intervalle)."""
        self.config.check_hour = hour
        self.config.check_minute = minute
        self.config.check_interval_hours = 0  # retour au mode cron
        self._schedule_daily_job()
        logger.info("Monitor : check quotidien replanifié à %02d:%02d UTC", hour, minute)

    def set_interval(self, hours: int) -> None:
        """Active le mode intervalle : check toutes les N heures."""
        self.config.check_interval_hours = hours
        self._schedule_daily_job()
        logger.info("Monitor : intervalle réglé toutes les %dh", hours)

    def next_run_info(self) -> str:
        """Retourne une chaîne lisible indiquant le prochain run planifié."""
        if self._job is None:
            return "Non planifié"
        next_run = self._job.next_run_time
        if next_run is None:
            return "Non planifié"
        return next_run.strftime("%Y-%m-%d %H:%M UTC")

    # ── Check ─────────────────────────────────────────────────────────────────

    async def _daily_check_wrapper(self) -> None:
        """Wrapper APScheduler → lance le check uniquement si activé."""
        if not self.config.enabled:
            logger.debug("Monitor désactivé — check ignoré.")
            return
        await self.check_now()

    async def check_now(self) -> int:
        """
        Lance un check immédiat sur tous les sites enregistrés.
        Retourne le nombre total de nouvelles notifications envoyées.
        """
        sites = self.registry.all()
        if not sites:
            logger.info("Monitor : aucun site enregistré.")
            return 0

        logger.info("Monitor : check de %d site(s) …", len(sites))
        total_new = 0

        # Scrape chaque site en thread (bloquant → thread pool)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(self._scrape_site, site): site
                for site in sites
            }
            for future in as_completed(futures):
                site = futures[future]
                try:
                    items = future.result()
                except Exception as e:
                    logger.error("Erreur scraping %s : %s", site["domain"], e)
                    items = []

                # Notifie les nouveautés (async)
                new_count = await self._notify_new_items(site["domain"], items)
                self.state.update_check_time(site["domain"])
                total_new += new_count
                logger.info("[%s] %d nouveauté(s)", site["domain"], new_count)

        logger.info("Monitor : check terminé — %d notification(s) envoyée(s)", total_new)
        return total_new

    def _scrape_site(self, site_entry: dict) -> list[dict]:
        """Scrape synchrone d'un site (exécuté dans un thread). 2 retries en cas d'échec."""
        import time as _time
        domain = site_entry["domain"]
        url    = site_entry.get("url", domain)
        logger.info("[MONITOR] ▶ Scraping %s (%s) …", domain, url)
        last_exc: Exception | None = None
        for attempt in range(1, 4):  # 3 tentatives max
            try:
                scraper = get_scraper_for(site_entry)
                items   = scraper.fetch_latest()
                logger.info("[MONITOR] ✔ %s → %d item(s) récupéré(s)", domain, len(items))
                for i, it in enumerate(items[:5], 1):
                    logger.debug(
                        "[MONITOR]   item %d : ep=%s url=%s",
                        i, it.get("episode_number"), it.get("url", "")
                    )
                return items
            except Exception as e:
                last_exc = e
                logger.warning(
                    "[MONITOR] ⚠ %s tentative %d/3 échouée : %s",
                    domain, attempt, e,
                )
                if attempt < 3:
                    _time.sleep(3 * attempt)  # backoff 3s puis 6s
        logger.error("[MONITOR] ❌ Erreur scraper %s (toutes tentatives épuisées) : %s", domain, last_exc, exc_info=True)
        return []

    async def _notify_new_items(self, domain: str, items: list[dict]) -> int:
        """
        Envoie uniquement les items NOUVEAUX (pas encore vus dans last_seen.json).
        Trie par numéro d'épisode/post décroissant, limite à 3 par check.
        Retourne le nombre de notifications envoyées.
        """
        from bot.notifier import send_notification

        if not items:
            logger.info("[MONITOR] %s : aucun item, rien à notifier.", domain)
            return 0

        # Trier du plus récent au plus ancien
        sorted_items = sorted(
            [i for i in items if i.get("url")],
            key=lambda i: i.get("episode_number") or 0,
            reverse=True,
        )

        # Filtrer : garder uniquement les items jamais notifiés
        new_items = [i for i in sorted_items if self.state.is_new(domain, i["url"])]

        if not new_items:
            logger.info("[MONITOR] %s : aucune nouveauté (tous déjà vus).", domain)
            return 0

        # Limiter à 3 notifications par check pour éviter le spam
        to_send = new_items[:3]

        logger.info(
            "[MONITOR] %s : %d item(s) disponibles, %d nouveau(x) → envoi de %d",
            domain, len(items), len(new_items), len(to_send),
        )

        count = 0
        for item in to_send:
            url   = item.get("url", "")
            ep    = item.get("episode_number", "?")
            title = item.get("title", "")
            try:
                logger.info("[MONITOR] %s → Notification ep=%s %s", domain, ep, url)
                # Envoi aux admins / chats configurés
                for cid in self.chat_ids:
                    await send_notification(self.bot, cid, item)
                    await asyncio.sleep(0.5)
                # Envoi watchlist — utilisateurs qui suivent ce titre
                await self._notify_watchlist(item, exclude_ids=set(self.chat_ids))
                self.state.mark_seen(domain, url)
                count += 1
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.error("[MONITOR] Erreur notification ep=%s %s : %s", ep, url, e, exc_info=True)

        logger.info("[MONITOR] %s : %d notification(s) envoyée(s)", domain, count)
        return count

    async def _notify_watchlist(self, item: dict, exclude_ids: set) -> None:
        """Notifie les utilisateurs dont un mot-clé watchlist correspond au titre de l'item."""
        from bot.notifier import send_notification
        title = item.get("title", "")
        if not title:
            return
        matches = self._watchlist.matches_for_title(title)
        for uid_str, keywords in matches.items():
            uid = int(uid_str)
            if uid in exclude_ids:
                continue  # déjà notifié via canal admin
            try:
                kw_list = ", ".join(f"<b>{kw}</b>" for kw in keywords)
                # Ajouter un préfixe watchlist à l'item
                notif_item = dict(item)
                notif_item["_watchlist_prefix"] = f"👁 Watchlist : {kw_list}\n\n"
                await send_notification(self.bot, uid, notif_item)
                logger.info("[WATCHLIST] Notifié user %s pour «%s» (kw: %s)", uid_str, title, keywords)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.debug("[WATCHLIST] Erreur envoi user %s : %s", uid_str, e)

    # ── Contrôle externe (pour les commandes /monitor) ────────────────────────

    def enable(self) -> None:
        """Active le monitoring automatique."""
        self.config.enabled = True
        logger.info("Monitor ACTIVÉ")

    def disable(self) -> None:
        """Désactive le monitoring automatique."""
        self.config.enabled = False
        logger.info("Monitor DÉSACTIVÉ")

    def is_enabled(self) -> bool:
        return self.config.enabled

    def status_lines(self) -> list[str]:
        """Retourne les lignes de statut pour /monitor status."""
        sites = self.registry.all()
        extra = self.config.extra_chats
        interval_h = self.config.check_interval_hours

        if interval_h and interval_h > 0:
            schedule_str = f"Toutes les {interval_h}h"
        else:
            schedule_str = f"{self.config.check_hour:02d}:{self.config.check_minute:02d} UTC (quotidien)"

        lines = [
            f"{'🟢 Activé' if self.config.enabled else '🔴 Désactivé'}",
            f"⏰ Fréquence : {schedule_str}",
            f"⏭ Prochain run : {self.next_run_info()}",
            f"👤 Admins : {len(self._admin_chat_ids)} · 📡 Canaux extra : {len(extra)}",
            f"📋 Sites surveillés : {len(sites)}",
            "",
        ]
        for site in sites:
            domain = site["domain"]
            last = self.state.get_last_check(domain)
            seen = self.state.seen_count(domain)
            lines.append(f"🌐 <b>{domain}</b>")
            lines.append(f"   └ Dernier check : {last}")
            lines.append(f"   └ URLs vues : {seen}")
        return lines
