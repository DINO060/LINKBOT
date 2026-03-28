"""
bot/notifier.py
================
Envoie une carte de notification Telegram pour une nouveauté détectée.

Format du message :
  🖼️ [image de couverture]

  🎬 Titre de l'anime
  📺 Épisode 3  ·  24 min
  🌐 hentaihaven.xxx
  📝 Synopsis court...

  [▶ Regarder]   [🔗 Voir sur le site]

Usage :
    from bot.notifier import send_notification
    await send_notification(bot, chat_id, item)

`item` est un dict avec les clés :
    title, cover, synopsis, url, domain,
    episode_number, episode_count, episode_duration
"""

import logging
from urllib.parse import urlparse

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


def _esc(text: str) -> str:
    """Échappe les caractères HTML pour Telegram."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_caption(item: dict) -> str:
    """Construit le texte HTML de la notification."""
    # Préfixe watchlist éventuel
    prefix   = item.get("_watchlist_prefix", "")
    title    = item.get("title") or "Nouvelle sortie"
    domain   = item.get("domain") or urlparse(item.get("url", "")).netloc.lstrip("www.")
    synopsis = (item.get("synopsis") or "")[:300]

    # Ligne épisode
    ep_parts = []
    is_chapter = item.get("content_type") == "chapter"
    if item.get("episode_number"):
        label = "Chapitre" if is_chapter else "Épisode"
        ep_parts.append(f"{label} {item['episode_number']}")
    elif item.get("episode_count"):
        label = "chapitres" if is_chapter else "épisodes"
        ep_parts.append(f"{item['episode_count']} {label}")
    if item.get("episode_duration"):
        ep_parts.append(item["episode_duration"])
    ep_line = "  ·  ".join(ep_parts)

    lines = [f"🎬 <b>{_esc(title)}</b>"]
    if ep_line:
        ep_emoji = "📚" if is_chapter else "📺"
        lines.append(f"{ep_emoji} {_esc(ep_line)}")
    if domain:
        lines.append(f"🌐 {_esc(domain)}")
    if synopsis:
        short = synopsis + ("…" if len(synopsis) >= 300 else "")
        lines.append(f"📝 {_esc(short)}")

    return prefix + "\n".join(lines)


def _build_keyboard(item: dict) -> InlineKeyboardMarkup:
    """Crée les boutons inline de la carte."""
    url    = item.get("url", "")
    ep_num = item.get("episode_number")
    domain = item.get("domain", "")
    is_tg  = str(domain).startswith("t.me")

    if is_tg:
        label = f"\U0001f4e2 Voir le post {ep_num}" if ep_num else "\U0001f4e2 Voir le post"
    elif item.get("content_type") == "chapter":
        label = f"\U0001f4da Lire chapitre {ep_num}" if ep_num else "\U0001f4da Lire"
    else:
        label = f"\u25b6 Regarder \u00e9pisode {ep_num}" if ep_num else "\u25b6 Regarder"

    buttons = [InlineKeyboardButton(label, url=url)]
    return InlineKeyboardMarkup([buttons])


async def send_notification(bot: Bot, chat_id: int, item: dict) -> None:
    """
    Envoie une carte de notification pour un nouvel épisode/contenu.

    Stratégie :
      1. Si cover disponible → send_photo (image + caption + boutons)
      2. Sinon → send_message (texte + boutons)
    """
    caption  = _build_caption(item)
    keyboard = _build_keyboard(item)
    cover    = item.get("cover")

    try:
        if cover:
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=cover,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                return
            except Exception as e:
                logger.debug("Photo inaccessible (%s) — fallback texte", e)

        # Fallback : message texte seul
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=False,
        )

    except Exception as exc:
        logger.error(
            "Erreur envoi notification [%s] : %s",
            item.get("url", "?"),
            exc,
        )


async def send_check_summary(bot: Bot, chat_id: int, count: int) -> None:
    """Envoie un résumé après un check (/monitor now)."""
    if count == 0:
        text = "✅ Check terminé — Aucune nouveauté détectée."
    else:
        text = f"✅ Check terminé — <b>{count}</b> nouvelle(s) notification(s) envoyée(s) !"

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        logger.error("Erreur envoi résumé : %s", exc)
