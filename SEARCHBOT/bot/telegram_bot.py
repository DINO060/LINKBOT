"""
bot/telegram_bot.py
=====================
Bot Telegram principal — SEARCHBOT.

Commandes disponibles :
  /start              — Message de bienvenue
  /help               — Aide
  /addsite <url>      — Enregistre un site
  /listsites          — Liste les sites enregistrés
  /removesite <dom>   — Supprime un site
  /search <query>     — Recherche sur sites enregistrés (cartes riches)
  /usearch <query>    — Recherche universelle DuckDuckGo

Format des cartes de résultats :
  🎬 Titre du contenu
  📺 Épisode X  ·  24 min
  🌐 domaine.com
  📝 Synopsis court de la page...

  [▶ Télécharger]   [🔗 Voir sur le site]
"""

import asyncio
import hashlib
import io
import logging
import os
from urllib.parse import urlparse

import httpx
from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.registry import SiteRegistry
from bot.searcher import Searcher
from bot.notifier import send_check_summary
from bot.favorites import FavoritesStore
from bot.watchlist import WatchlistStore

logger = logging.getLogger(__name__)

# Instances globales — partagées entre tous les handlers
_registry = SiteRegistry()
_searcher = Searcher()
_favorites = FavoritesStore()
_watchlist_store = WatchlistStore()
_FAV_ITEMS: dict = {}      # stockage temporaire url_hash → item pour le bouton ⭐
_monitor_scheduler = None  # initialisé dans run_bot()
_admin_chat_ids: list[int] = []  # IDs admins, initialisé dans run_bot()


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def _build_card_text(result: dict) -> str:
    """Construit le texte d'une carte de résultat (titre, release, genres, auteurs, épisodes, synopsis)."""
    title        = result.get("title") or "Sans titre"
    synopsis     = result.get("synopsis", "")
    genres: list = result.get("genres") or []
    authors: list = result.get("authors") or []
    release_date = result.get("release_date", "")
    episodes: list = result.get("episodes") or []
    ep_count     = result.get("episode_count")
    is_tg        = result.get("domain") == "t.me"
    is_season    = result.get("is_season_based", False)
    score        = result.get("score")
    status       = result.get("status", "")

    emoji = "📢" if is_tg else "🎬"
    lines = [f"{emoji} <b>{_esc(title)}</b>"]
    lines.append("")

    # Score MAL
    if score:
        filled   = round(score / 2)          # 10 → 5 étoiles
        stars    = "⭐" * filled + "☆" * (5 - filled)
        lines.append(f"{stars} <b>{score}/10</b> <i>MAL</i>")

    # Date de sortie
    if release_date:
        lines.append(f"📅 Release : {_esc(str(release_date))}")

    # Status (Airing / Finished Airing / Not yet aired)
    if status and status not in ("Unknown", ""):
        status_emoji = {
            "Currently Airing": "🟢",
            "Finished Airing": "🔴",
            "Not yet aired": "🟡",
        }.get(status, "ℹ️")
        lines.append(f"{status_emoji} {_esc(status)}")

    # Genres
    if genres:
        lines.append(f"🎭 Genres : {_esc(', '.join(genres))}")

    # Type media (Movie, OVA, ONA…) — uniquement si non-TV
    media_type = result.get("media_type", "")
    if media_type and media_type not in ("TV", "anime", ""):
        type_emoji = {
            "Movie":   "🎬",
            "OVA":     "📾",
            "ONA":     "🌐",
            "Special": "⭐",
            "Music":   "🎵",
        }.get(media_type, "📱")
        lines.append(f"{type_emoji} {_esc(media_type)}")

    # Auteur(s) / Studio
    if authors:
        lines.append(f"✍️ Author : {_esc(', '.join(authors))}")

    # Nombre d'épisodes / posts
    count = len(episodes) if episodes else (
        ep_count if isinstance(ep_count, int) and 0 < ep_count < 50000 else None
    )
    if count:
        if is_tg:
            lines.append(f"📬 {count} post{'s' if count > 1 else ''} récent{'s' if count > 1 else ''}")
        elif is_season:
            lines.append(f"🗂 Saisons : {count}")
        elif result.get("content_type") == "chapter":
            lines.append(f"📚 Chapitres : {count}")
        else:
            lines.append(f"📺 Épisodes : {count}")

    # Ligne vide avant synopsis
    if score or release_date or genres or authors or count:
        lines.append("")

    # Synopsis (tronqué à 300 caractères pour rester lisible)
    if synopsis:
        syn = synopsis[:300] + "…" if len(synopsis) > 300 else synopsis
        lines.append("📝 <i>Synopsis :</i>")
        lines.append(_esc(syn))

    return "\n".join(lines)


def _esc(text: str) -> str:
    """Échappe les caractères HTML pour Telegram."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_keyboard(result: dict, fav_key: str | None = None) -> InlineKeyboardMarkup:
    """Crée les boutons inline d'une carte (lien série + boutons par épisode)."""
    series_url = result.get("url", "")
    episodes: list = result.get("episodes") or []
    is_tg      = result.get("domain") == "t.me"
    is_season  = result.get("is_season_based", False)

    rows: list = []

    # Boutons d'épisodes / posts — seulement les URLs valides http(s)
    ep_buttons: list = []
    for ep in sorted(episodes, key=lambda e: e["number"])[:20]:
        ep_url = ep.get("url", "")
        if not ep_url.startswith("http"):
            continue  # URL invalide → Telegram rejetterait tout le clavier
        if is_tg:
            label = f"📢 Post {ep['number']}"
        elif is_season or ep.get("is_season"):
            label = f"▶ Saison {ep['number']}"
        elif result.get("content_type") == "chapter":
            label = f"📖 Ch {ep['number']}"
        else:
            label = f"▶ Ép {ep['number']}"
        ep_buttons.append(InlineKeyboardButton(label, url=ep_url))

    # Regrouper par 2 par ligne
    for i in range(0, len(ep_buttons), 2):
        rows.append(ep_buttons[i:i+2])

    # Bouton principal + bouton favori
    bottom_row = []
    if series_url and series_url.startswith("http"):
        voir_label = "📢 Voir le canal" if is_tg else "🔗 Voir la série"
        bottom_row.append(InlineKeyboardButton(voir_label, url=series_url))
    if fav_key:
        bottom_row.append(InlineKeyboardButton("⭐ Favori", callback_data=f"fav:{fav_key}"))
    if bottom_row:
        rows.append(bottom_row)

    return InlineKeyboardMarkup(rows) if rows else InlineKeyboardMarkup([[]])


_IMG_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/133.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "sec-fetch-dest": "image",
    "sec-fetch-mode": "no-cors",
    "sec-fetch-site": "same-origin",
}
_MAX_IMG_SIZE = 5 * 1024 * 1024  # 5 MB — limite Telegram pour send_photo


async def _download_cover(cover_url: str) -> io.BytesIO | None:
    """
    Télécharge une image de couverture côté serveur.
    Ajoute un Referer basé sur l'origine de l'image pour contourner
    l'anti-hotlinking des sites adultes/streaming (xnxx, xvideos, etc.).
    Retourne un BytesIO prêt à passer à send_photo, ou None si échec.
    """
    if not cover_url or not cover_url.startswith("http"):
        return None
    from urllib.parse import urlparse as _up
    origin = f"{_up(cover_url).scheme}://{_up(cover_url).netloc}"
    headers = {**_IMG_HEADERS, "Referer": origin + "/"}
    try:
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=15,
        ) as client:
            resp = await client.get(cover_url)
        if resp.status_code != 200:
            logger.debug("Cover HTTP %d : %s", resp.status_code, cover_url)
            return None
        data = resp.content
        if len(data) > _MAX_IMG_SIZE:
            logger.debug("Cover trop grande (%d bytes) : %s", len(data), cover_url)
            return None
        ct = resp.headers.get("content-type", "")
        if not ct.startswith("image/"):
            logger.debug("Cover content-type inattendu '%s': %s", ct, cover_url)
            return None
        buf = io.BytesIO(data)
        buf.name = "cover.jpg"
        return buf
    except Exception as exc:
        logger.debug("Cover download échec (%s) : %s", cover_url, exc)
        return None


async def _send_result_card(
    update: Update,
    result: dict,
    reply: bool = False,
) -> None:
    """Envoie une carte de résultat (photo + texte + boutons) dans le chat."""
    chat_id = update.effective_chat.id
    bot: Bot = update.get_bot()

    text = _build_card_text(result)
    # Stocker l'item pour le bouton ⭐ (clé = 8 premiers chars du sha1 de l'URL)
    fav_key = None
    url = result.get("url", "")
    if url:
        fav_key = hashlib.sha1(url.encode()).hexdigest()[:8]
        _FAV_ITEMS[fav_key] = result
    keyboard = _build_keyboard(result, fav_key=fav_key)
    cover    = result.get("cover")

    try:
        if cover:
            # Telegram limit for photo captions: 1024 chars
            caption = text if len(text) <= 1024 else text[:1021] + "…"
            # Télécharger l'image côté serveur (contourne l'anti-hotlinking)
            img_bytes = await _download_cover(cover)
            photo_src = img_bytes if img_bytes is not None else cover
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_src,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
                # Si texte tronqué, envoyer la suite en message séparé
                if len(text) > 1024:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=text[1021:],
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                return
            except Exception as img_exc:
                logger.debug("send_photo échec (%s) → fallback texte", img_exc)

        # Pas d'image ou image inaccessible → message texte complet
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.error("Erreur envoi carte : %s", exc)


# ─── Handlers de commandes ────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🔍 <b>SEARCHBOT</b>\n"
        "Je cherche du contenu sur les sites que tu m'indiques "
        "et je te notifie automatiquement des nouveautés !\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "📂 <b>Gestion des sites</b>\n"
        "/addsite &lt;url1 url2 ...&gt; [cat] — Enregistrer un ou plusieurs sites d'un coup\n"
        "   <i>Catégories :</i> <code>h</code> · <code>anime</code> · <code>pwha</code> · <code>social</code> · <code>comic</code> · <code>porn</code> · <code>serie</code>\n"
        "/listsites — Sites enregistrés par catégorie\n"
        "/removesite &lt;domaine&gt; — Supprimer un site\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "🔎 <b>Recherche</b>\n"
        "/search [cat] &lt;titre&gt; — Sur tes sites enregistrés\n"
        "/usearch &lt;requête&gt; — Sur tout internet (DuckDuckGo)\n"
        "/ssearch &lt;url&gt; &lt;titre&gt; — Sur n'importe quel site précis\n"
        "/menu — 🎮 Menu interactif avec boutons de catégorie\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "🌟 <b>MyAnimeList — Jikan API</b>\n"
        "/seasonal — Anime de la saison actuelle\n"
        "/upcoming — Prochaine saison\n"
        "/top [genre] — Top anime MAL\n"
        "   <i>Ex :</i> <code>/top romance</code> · <code>/top action</code>\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "🔔 <b>Notifications &amp; Monitor</b>\n"
        "/monitor on — Activer les notifs auto\n"
        "/monitor off — Désactiver\n"
        "/monitor status — État + sites surveillés\n"
        "/monitor now — Check immédiat\n"
        "/monitor settime &lt;HH:MM&gt; — Heure du check quotidien (UTC)\n"
        "/monitor freq &lt;N&gt; — Check toutes les N heures\n"
        "/monitor setchat &lt;@canal&gt; — Envoyer dans un canal\n"
        "<i>💡 Ajoute le bot comme admin dans un groupe/canal :\n"
        "   les notifs s'y activent automatiquement !</i>\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "📋 <b>Watchlist &amp; Favoris</b>\n"
        "/watch &lt;titre&gt; — Surveiller un titre\n"
        "/unwatch &lt;titre&gt; — Retirer de la watchlist\n"
        "/watchlist — Voir ta watchlist\n"
        "/favlist — Voir tes favoris ⭐\n\n"

        "━━━━━━━━━━━━━━━━\n"
        "/help — Aide détaillée avec exemples",
        parse_mode=ParseMode.HTML,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📖 <b>Aide SEARCHBOT</b>\n\n"
        "<b>Catégories de sites</b>\n"
        "  <code>h</code>      → Hentai 🔞\n"
        "  <code>anime</code>  → Anime 🎬\n"
        "  <code>pwha</code>   → Pwha 🔥\n"
        "  <code>social</code> → Social 📡 (Telegram/Reddit/Twitter)\n"
        "  <code>comic</code>  → Comic 📚 (BD, manga...)\n"
        "  <code>porn</code>   → Porn 🔥\n"
        "  <code>serie</code>  → Série 📺\n\n"
        "<b>/addsite url1 url2 url3 [catégorie]</b>\n"
        "  Ajoute un ou plusieurs sites d'un seul coup !\n"
        "  Ex : <code>/addsite https://a.com https://b.com https://c.com anime</code>\n"
        "  Ex : <code>/addsite https://hentaihaven.xxx h</code>\n\n"
        "<b>/menu</b> — Menu interactif avec boutons de catégorie\n"
        "  Clique une catégorie → tape le titre → le bot cherche dans cette catégorie\n\n"
        "<b>/search [catégorie] titre</b>\n"
        "  Ex : <code>/search frieren</code> (tous les sites)\n"
        "  Ex : <code>/search anime frieren</code> (anime uniquement)\n\n"
        "<b>/usearch requête</b> — Recherche universelle DuckDuckGo\n"
        "<b>/ssearch url titre</b> — Chercher sur un site précis\n"
        "  Ex : <code>/ssearch anime-sama.fr frieren</code>\n\n"
        "────────────────\n"
        "🌟 <b>MyAnimeList (Jikan API — gratuit, sans clé)</b>\n\n"
        "<b>/seasonal</b> — Anime de la saison actuelle (triés par score MAL)\n"
        "<b>/upcoming</b> — Prochaine saison uniquement (séries + films)\n"
        "<b>/top</b> — Top anime MAL\n"
        "<b>/top romance</b> — Top anime d'un genre spécifique\n"
        "  Genres : action, romance, comedy, drama, fantasy, horror,\n"
        "  mystery, sci-fi, slice of life, sports, ecchi, harem, mecha…\n"
        "<b>/movies</b> — Films d'animation à venir cette année\n"
        "<b>/movies top</b> — Top films d'animation MAL\n\n"
        "────────────────\n"
        "<b>/monitor on/off/status/now</b> — Notifications auto\n"
        "<b>/monitor settime HH:MM</b> — Heure du check (UTC)\n"
        "<b>/monitor freq N</b> — Toutes les N heures\n"
        "<b>/monitor setchat @Canal</b> — Envoyer notifs dans un canal\n\n"
        "<b>/watch frieren</b> — Surveiller un titre (watchlist)\n"
        "<b>/unwatch frieren</b> — Retirer\n"
        "<b>/watchlist</b> — Voir ta watchlist\n"
        "<b>/favlist</b> — Tes favoris (⭐ sous chaque résultat)",
        parse_mode=ParseMode.HTML,
    )


async def cmd_addsite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Enregistre un ou plusieurs sites en une seule commande.
    Usage : /addsite url1 [url2 url3 ...] [catégorie]
    Ex : /addsite https://a.com https://b.com anime
    """
    from bot.registry import VALID_CATEGORIES, _ALIASES

    if not context.args:
        cats = " · ".join(f"<code>{c}</code>" for c in VALID_CATEGORIES)
        await update.message.reply_text(
            "Usage : /addsite &lt;url1&gt; [url2 url3 ...] [catégorie]\n"
            f"Catégories : {cats}\n\n"
            "Exemple (un site)  : <code>/addsite https://anime-sama.fr anime</code>\n"
            "Exemple (plusieurs) : <code>/addsite https://a.com https://b.com https://c.com h</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_args = list(context.args)

    # Détecter si le dernier arg est une catégorie (pas une URL)
    cat = ""
    last = raw_args[-1].lower().strip()
    norm_last = _ALIASES.get(last, last)
    if norm_last in VALID_CATEGORIES and not raw_args[-1].startswith("http") and "." not in raw_args[-1]:
        cat = norm_last
        raw_args = raw_args[:-1]

    # Collecter tous les URLs valides
    urls: list[str] = []
    for arg in raw_args:
        a = arg.strip()
        if not a:
            continue
        if not a.startswith("http"):
            a = "https://" + a
        urls.append(a)

    if not urls:
        await update.message.reply_text("❌ Aucune URL valide trouvée.", parse_mode=ParseMode.HTML)
        return

    # ── Cas simple : un seul site ──────────────────────────────────────────
    if len(urls) == 1:
        msg = await update.message.reply_text(f"⏳ Analyse de {urls[0]} …")
        try:
            entry = await asyncio.to_thread(_registry.add, urls[0], cat)
            domain = entry["domain"]
            cat_label = VALID_CATEGORIES.get(entry.get("category", ""), "")
            cat_info = f" · catégorie <b>{_esc(cat_label)}</b>" if cat_label else ""
            await msg.edit_text(
                f"✅ <b>{_esc(domain)}</b> enregistré{cat_info} !\n"
                f"Utilise /search ou /menu pour chercher.",
                parse_mode=ParseMode.HTML,
            )
        except ValueError as e:
            cats = " · ".join(f"<code>{c}</code>" for c in VALID_CATEGORIES)
            await msg.edit_text(
                f"❌ {_esc(str(e))}\nCatégories valides : {cats}",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error("addsite erreur : %s", e)
            await msg.edit_text(f"❌ Impossible d'enregistrer ce site : {e}")
        return

    # ── Cas multiple : plusieurs sites d'un coup ───────────────────────────
    cat_label = VALID_CATEGORIES.get(cat, "") if cat else ""
    msg = await update.message.reply_text(
        f"⏳ Enregistrement de <b>{len(urls)}</b> site(s)" +
        (f" · {_esc(cat_label)}" if cat_label else "") + " …",
        parse_mode=ParseMode.HTML,
    )

    ok: list[str] = []
    errors: list[str] = []

    for url in urls:
        try:
            entry = await asyncio.to_thread(_registry.add, url, cat)
            ok.append(entry["domain"])
        except ValueError as e:
            errors.append(f"❌ <code>{_esc(url[:50])}</code> — {_esc(str(e))}")
        except Exception as e:
            logger.error("addsite bulk erreur %s : %s", url, e)
            errors.append(f"❌ <code>{_esc(url[:50])}</code> — {_esc(str(e))}")

    lines: list[str] = []
    if ok:
        header = f"✅ <b>{len(ok)} site(s) enregistré(s)"
        if cat_label:
            header += f" · {_esc(cat_label)}"
        header += "</b>"
        lines.append(header)
        for d in ok:
            lines.append(f"  🌐 {_esc(d)}")
    if errors:
        if ok:
            lines.append("")
        lines.append(f"⚠️ <b>{len(errors)} échec(s) :</b>")
        lines.extend(errors)

    await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_listsites(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sites = _registry.all()
    if not sites:
        await update.message.reply_text(
            "Aucun site enregistré.\nUtilise /addsite &lt;url&gt; [catégorie] pour en ajouter un.",
            parse_mode=ParseMode.HTML,
        )
        return

    from bot.registry import VALID_CATEGORIES
    # Grouper par catégorie
    groups: dict[str, list] = {cat: [] for cat in VALID_CATEGORIES}
    groups[""] = []  # sans catégorie
    for site in sites:
        cat = site.get("category", "")
        if cat in groups:
            groups[cat].append(site)
        else:
            groups[""].append(site)

    lines = [f"📋 <b>Sites enregistrés ({len(sites)})</b>\n"]
    for cat, label in VALID_CATEGORIES.items():
        cat_sites = groups.get(cat, [])
        if not cat_sites:
            continue
        lines.append(f"\n<b>{label}</b>")
        for site in cat_sites:
            lines.append(f"  🌐 <b>{_esc(site['domain'])}</b>")
    if groups[""]:
        lines.append("\n<b>Sans catégorie</b>")
        for site in groups[""]:
            lines.append(f"  🌐 <b>{_esc(site['domain'])}</b>")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def cmd_removesite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage : /removesite &lt;domaine&gt;\n"
            "Exemple : /removesite hentaihaven.xxx",
            parse_mode=ParseMode.HTML,
        )
        return

    domain = context.args[0].strip().lower().lstrip("www.")
    removed = await asyncio.to_thread(_registry.remove, domain)

    if removed:
        await update.message.reply_text(f"✅ <b>{_esc(domain)}</b> supprimé.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(
            f"❌ <b>{_esc(domain)}</b> n'est pas dans le registre.\n"
            "Vérifie avec /listsites.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recherche sur les sites enregistrés, avec filtre de catégorie optionnel."""
    if not context.args:
        await update.message.reply_text(
            "Usage : /search [catégorie] &lt;titre&gt;\n"
            "Catégories : <code>h</code> · <code>anime</code> · <code>pwha</code> · <code>social</code> · <code>comic</code> · <code>porn</code> · <code>serie</code>\n"
            "Ex : <code>/search frieren</code> (tous les sites)\n"
            "Ex : <code>/search anime frieren</code> (anime uniquement)\n\n"
            "💡 Utilise /menu pour chercher avec des boutons !",
            parse_mode=ParseMode.HTML,
        )
        return

    from bot.registry import VALID_CATEGORIES, _ALIASES
    first = context.args[0].lower()
    norm_first = _ALIASES.get(first, first)
    if norm_first in VALID_CATEGORIES:
        category = norm_first
        query = " ".join(context.args[1:])
        if not query:
            await update.message.reply_text(
                f"Précise le titre après la catégorie.\n"
                f"Ex : /search {category} frieren",
            )
            return
    else:
        category = ""
        query = " ".join(context.args)

    sites = _registry.get_by_category(category) if category else _registry.all()
    n_sites = len(sites)

    if not n_sites:
        no_sites_msg = (
            f"Aucun site dans la catégorie <b>{_esc(VALID_CATEGORIES.get(category, category))}</b>.\n"
            f"Ajoute-en un avec /addsite &lt;url&gt; {category}"
            if category else
            "Aucun site enregistré. Ajoute d'abord un site avec /addsite &lt;url&gt;"
        )
        await update.message.reply_text(no_sites_msg, parse_mode=ParseMode.HTML)
        return

    cat_label = VALID_CATEGORIES.get(category, "") if category else ""
    search_scope = f" · {cat_label}" if cat_label else f" · {n_sites} site(s)"
    msg = await update.message.reply_text(
        f"🔍 Recherche de <b>{_esc(query)}</b>{search_scope} …",
        parse_mode=ParseMode.HTML,
    )

    # Recherche en thread pour ne pas bloquer l'event loop Telegram
    results = await asyncio.to_thread(
        _searcher.search_registered, query, _registry, category=category
    )

    await msg.delete()

    if not results:
        await update.message.reply_text(
            f"😔 Aucun résultat pour <b>{_esc(query)}</b>" +
            (f" dans {_esc(cat_label)}" if cat_label else "") +
            ".\nEssaie /usearch pour une recherche universelle.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Enrichir avec score MAL en arrière-plan
    enrich_msg = await update.message.reply_text(
        f"⭐ Enrichissement MAL en cours…", parse_mode=ParseMode.HTML
    )
    results = await asyncio.to_thread(_enrich_with_mal, results)
    await enrich_msg.delete()

    header = f"✅ <b>{len(results)} résultat(s)</b> pour « {_esc(query)} »"
    if cat_label:
        header += f" · {_esc(cat_label)}"
    await update.message.reply_text(header + " :", parse_mode=ParseMode.HTML)

    for result in results:
        await _send_result_card(update, result)


# ─── Commandes Jikan (MyAnimeList) ────────────────────────────────────────────

def _enrich_with_mal(results: list[dict]) -> list[dict]:
    """Ajoute le score MAL aux résultats /search qui n'en ont pas encore."""
    import time
    from bot.jikan_api import search_anime
    for result in results:
        if result.get("score") or result.get("_source") == "jikan":
            continue
        title = result.get("title", "")
        if not title or len(title) < 3:
            continue
        try:
            mal = search_anime(title, limit=1)
            if mal and mal[0].get("score"):
                result["score"] = mal[0]["score"]
                if not result.get("mal_url"):
                    result["mal_url"] = mal[0].get("url")
        except Exception:
            pass
        time.sleep(0.4)  # respect 3 req/s
    return results


async def cmd_seasonal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Anime de la saison en cours (triés par score MAL)."""
    from bot.jikan_api import get_season_now
    msg = await update.message.reply_text(
        "⏳ Chargement des anime de la saison…", parse_mode=ParseMode.HTML
    )
    results = await asyncio.to_thread(get_season_now)
    await msg.delete()
    if not results:
        await update.message.reply_text("❌ Impossible de joindre Jikan API, réessaie plus tard.")
        return
    await update.message.reply_text(
        f"🌸 <b>Anime de la saison actuelle</b> · {len(results)} anime (triés par score MAL) :",
        parse_mode=ParseMode.HTML,
    )
    for r in results:
        await _send_result_card(update, r)


async def cmd_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Anime de la prochaine saison."""
    from bot.jikan_api import get_season_upcoming
    msg = await update.message.reply_text(
        "⏳ Chargement de la prochaine saison…", parse_mode=ParseMode.HTML
    )
    results = await asyncio.to_thread(get_season_upcoming)
    await msg.delete()
    if not results:
        await update.message.reply_text("❌ Impossible de joindre Jikan API, réessaie plus tard.")
        return
    from bot.jikan_api import _next_season
    nxt_year, nxt_season = _next_season()
    season_label = f"{nxt_season.capitalize()} {nxt_year}"
    tv    = [r for r in results if r.get("media_type") != "Movie"]
    films = [r for r in results if r.get("media_type") == "Movie"]
    await update.message.reply_text(
        f"🌠 <b>Prochaine saison — {_esc(season_label)}</b>\n"
        f"📺 {len(tv)} séries · 🎬 {len(films)} films · triés par score MAL",
        parse_mode=ParseMode.HTML,
    )
    for r in results:
        await _send_result_card(update, r)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Top anime MAL, filtrable par genre. Ex: /top romance"""
    from bot.jikan_api import get_top_anime, GENRE_IDS
    genre = " ".join(context.args).lower().strip() if context.args else ""
    # Vérifier que le genre est connu
    if genre and genre not in GENRE_IDS:
        genres_list = ", ".join(sorted(GENRE_IDS.keys()))
        await update.message.reply_text(
            f"❌ Genre <b>{_esc(genre)}</b> inconnu.\n"
            f"Genres disponibles :\n<code>{_esc(genres_list)}</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    genre_label = f" · {genre.title()}" if genre else ""
    msg = await update.message.reply_text(
        f"⏳ Chargement du top anime MAL{genre_label}…", parse_mode=ParseMode.HTML
    )
    results = await asyncio.to_thread(get_top_anime, genre, 8)
    await msg.delete()
    if not results:
        await update.message.reply_text("❌ Aucun résultat.")
        return
    await update.message.reply_text(
        f"🏆 <b>Top anime MAL{_esc(genre_label)}</b> ({len(results)}) :",
        parse_mode=ParseMode.HTML,
    )
    for r in results:
        await _send_result_card(update, r)


async def cmd_movies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /movies           — Films à venir cette année
    /movies top       — Top films d'animation MAL
    """
    from bot.jikan_api import get_upcoming_movies, get_top_movies
    sub = context.args[0].lower() if context.args else "upcoming"

    if sub == "top":
        msg = await update.message.reply_text(
            "⏳ Chargement du top films d'animation MAL…", parse_mode=ParseMode.HTML
        )
        results = await asyncio.to_thread(get_top_movies, 10)
        await msg.delete()
        if not results:
            await update.message.reply_text("❌ Aucun résultat.")
            return
        await update.message.reply_text(
            f"🏆 <b>Top Films d'animation MAL</b> ({len(results)}) :",
            parse_mode=ParseMode.HTML,
        )
    else:
        msg = await update.message.reply_text(
            "⏳ Chargement des films à venir…", parse_mode=ParseMode.HTML
        )
        results = await asyncio.to_thread(get_upcoming_movies)
        await msg.delete()
        if not results:
            await update.message.reply_text(
                "😔 Aucun film trouvé pour cette année.\n"
                "Essaie /movies top pour le top films MAL."
            )
            return
        await update.message.reply_text(
            f"🎬 <b>Films à venir</b> · {len(results)} film(s) cette année :",
            parse_mode=ParseMode.HTML,
        )
    for r in results:
        await _send_result_card(update, r)


# ─── /ssearch : recherche sur un site précis (sans enregistrement) ──────────────

async def cmd_ssearch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/ssearch <url_site> <titre> — Recherche directement sur n'importe quel site."""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "🔍 <b>Recherche sur site précis</b>\n"
            "Usage : /ssearch &lt;url_du_site&gt; &lt;titre&gt;\n\n"
            "Exemples :\n"
            "<code>/ssearch https://anime-sama.fr frieren</code>\n"
            "<code>/ssearch hentaihaven.xxx nurse</code>\n"
            "<code>/ssearch https://nyaa.si demon slayer</code>\n\n"
            "Le site n'a pas besoin d'être enregistré dans le bot.",
            parse_mode=ParseMode.HTML,
        )
        return
    site_url = context.args[0]
    query    = " ".join(context.args[1:])
    # Normaliser l'URL
    if not site_url.startswith(("http://", "https://")):
        site_url = "https://" + site_url
    parsed = urlparse(site_url)
    domain = parsed.netloc.lstrip("www.") or site_url
    msg = await update.message.reply_text(
        f"🔍 Recherche de <b>{_esc(query)}</b> sur « <code>{_esc(domain)}</code> »…",
        parse_mode=ParseMode.HTML,
    )
    results = await asyncio.to_thread(_searcher.search_site, site_url, query)
    await msg.delete()
    if not results:
        await update.message.reply_text(
            f"😔 Aucun résultat pour <b>{_esc(query)}</b> sur <code>{_esc(domain)}</code>.\n"
            f"Essaie /usearch {_esc(query)}",
            parse_mode=ParseMode.HTML,
        )
        return
    await update.message.reply_text(
        f"✅ <b>{len(results)} résultat(s)</b> sur <code>{_esc(domain)}</code> :",
        parse_mode=ParseMode.HTML,
    )
    for r in results:
        await _send_result_card(update, r)


# ─── Auto-enregistrement groupe/canal quand le bot devient admin ──────────────

async def on_bot_member_update(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Déclenché automatiquement quand le statut du bot change dans un groupe ou canal.
    - Bot devient admin  → ajoute le chat aux destinataires des notifs monitor
    - Bot perd ses droits → retire le chat
    """
    result = update.my_chat_member
    if not result or not _monitor_scheduler:
        return
    chat     = result.chat
    chat_id  = chat.id
    name     = chat.title or chat.username or str(chat_id)
    new_status = result.new_chat_member.status

    if new_status in ("administrator", "creator"):
        added = _monitor_scheduler.add_notification_chat(chat_id)
        if added:
            for aid in _admin_chat_ids:
                try:
                    await context.bot.send_message(
                        aid,
                        f"📡 Bot ajouté comme admin dans <b>{_esc(name)}</b>\n"
                        f"ID : <code>{chat_id}</code>\n"
                        f"Les notifications monitor seront envoyées ici automatiquement.",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass
    elif new_status in ("left", "kicked", "member", "restricted"):
        removed = _monitor_scheduler.remove_notification_chat(chat_id)
        if removed:
            for aid in _admin_chat_ids:
                try:
                    await context.bot.send_message(
                        aid,
                        f"📴 Bot retiré de <b>{_esc(name)}</b> (<code>{chat_id}</code>).\n"
                        f"Notifications monitor désactivées pour ce chat.",
                        parse_mode=ParseMode.HTML,
                    )
                except Exception:
                    pass


async def cmd_usearch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Recherche universelle DuckDuckGo (tout internet)."""
    if not context.args:
        await update.message.reply_text(
            "Usage : /usearch &lt;requête&gt;\n"
            "Exemple : /usearch anime harem 2024 episode 1",
            parse_mode=ParseMode.HTML,
        )
        return

    query = " ".join(context.args)
    max_results = int(os.getenv("USEARCH_MAX_RESULTS", "8"))

    msg = await update.message.reply_text(
        f"🌐 Recherche universelle : <b>{_esc(query)}</b> …",
        parse_mode=ParseMode.HTML,
    )

    results = await asyncio.to_thread(
        _searcher.search_universal, query, max_results
    )

    await msg.delete()

    if not results:
        await update.message.reply_text(
            f"😔 Aucun résultat pour <b>{_esc(query)}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        f"✅ <b>{len(results)} résultat(s)</b> pour « {_esc(query)} » :",
        parse_mode=ParseMode.HTML,
    )

    for result in results:
        await _send_result_card(update, result)


# ─── Favoris ─────────────────────────────────────────────────────────────────

async def cmd_favlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche les favoris de l'utilisateur."""
    user_id = update.effective_user.id
    favs = _favorites.all(user_id)

    if not favs:
        await update.message.reply_text(
            "⭐ Tu n'as pas encore de favoris.\n"
            "Appuie sur le bouton <b>⭐ Favori</b> sous n'importe quel résultat pour en ajouter.",
            parse_mode=ParseMode.HTML,
        )
        return

    lines = [f"⭐ <b>Tes favoris ({len(favs)})</b>\n"]
    keyboard_rows = []
    for i, fav in enumerate(favs):
        domain = fav.get("domain", "")
        lines.append(f"{i + 1}. <b>{_esc(fav['title'])}</b>  —  <i>{_esc(domain)}</i>")
        keyboard_rows.append([
            InlineKeyboardButton(f"🔗 {fav['title'][:28]}", url=fav["url"]),
            InlineKeyboardButton("🗑 Supprimer", callback_data=f"unfav:{i}"),
        ])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


async def callback_fav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les boutons ⭐ Favori et 🗑 Supprimer des favoris."""
    q = update.callback_query
    await q.answer()
    data    = q.data or ""
    user_id = q.from_user.id

    if data.startswith("fav:"):
        key  = data[4:]
        item = _FAV_ITEMS.get(key)
        if not item:
            await q.answer("❌ Session expirée — relance /search pour réessayer.", show_alert=True)
            return
        added = _favorites.add(user_id, item)
        if added:
            await q.answer("⭐ Ajouté aux favoris !", show_alert=False)
        else:
            await q.answer("Déjà dans tes favoris.", show_alert=False)

    elif data.startswith("unfav:"):
        try:
            idx = int(data[6:])
        except ValueError:
            return
        removed = _favorites.remove(user_id, idx)
        if removed:
            await q.answer("🗑 Supprimé.", show_alert=False)
            # Rafraîchir la liste
            favs = _favorites.all(user_id)
            if not favs:
                await q.edit_message_text("⭐ Ta liste de favoris est maintenant vide.", parse_mode=ParseMode.HTML)
            else:
                lines = [f"⭐ <b>Tes favoris ({len(favs)})</b>\n"]
                keyboard_rows = []
                for i, fav in enumerate(favs):
                    lines.append(f"{i + 1}. <b>{_esc(fav['title'])}</b>  —  <i>{_esc(fav.get('domain', ''))}</i>")
                    keyboard_rows.append([
                        InlineKeyboardButton(f"🔗 {fav['title'][:28]}", url=fav["url"]),
                        InlineKeyboardButton("🗑 Supprimer", callback_data=f"unfav:{i}"),
                    ])
                await q.edit_message_text(
                    "\n".join(lines),
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(keyboard_rows),
                )
        else:
            await q.answer("❌ Favori introuvable.", show_alert=False)


# ─── Watchlist ────────────────────────────────────────────────────────────────

# ─── Menu interactif ─────────────────────────────────────────────────────────

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le menu principal avec boutons inline de catégorie et utilitaires."""
    from bot.registry import VALID_CATEGORIES

    keyboard = InlineKeyboardMarkup([
        # Ligne 1 — catégories recherche
        [
            InlineKeyboardButton("🎬 Anime",   callback_data="menu:cat:anime"),
            InlineKeyboardButton("🔞 Hentai",  callback_data="menu:cat:h"),
            InlineKeyboardButton("🔥 Pwha",    callback_data="menu:cat:pwha"),
        ],
        [
            InlineKeyboardButton("📚 Comic",   callback_data="menu:cat:comic"),
            InlineKeyboardButton("🔞 Porn",    callback_data="menu:cat:porn"),
            InlineKeyboardButton("📺 Série",   callback_data="menu:cat:serie"),
        ],
        [
            InlineKeyboardButton("📡 Social",  callback_data="menu:cat:social"),
            InlineKeyboardButton("🔍 Tous",    callback_data="menu:cat:"),
        ],
        # Ligne 2 — utilitaires
        [
            InlineKeyboardButton("📋 Mes sites",  callback_data="menu:listsites"),
            InlineKeyboardButton("🔔 Monitor",    callback_data="menu:monitor"),
        ],
        [
            InlineKeyboardButton("⭐ Favoris",    callback_data="menu:favlist"),
            InlineKeyboardButton("📌 Watchlist",  callback_data="menu:watchlist"),
        ],
        [
            InlineKeyboardButton("🌐 Recherche libre (DDG)", callback_data="menu:usearch"),
        ],
    ])

    await update.message.reply_text(
        "🎛 <b>Menu SEARCHBOT</b>\n\n"
        "📂 <b>Recherche par catégorie</b> — Clique une catégorie, puis tape le titre\n"
        "🛠 <b>Utilitaires</b> — Accès rapide à tes sites, monitor et listes",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def callback_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gère les clics sur les boutons du menu principal."""
    from bot.registry import VALID_CATEGORIES
    q       = update.callback_query
    await q.answer()
    data    = q.data or ""
    user_id = q.from_user.id

    # ── Boutons de catégorie → lance une recherche filtrée ──
    if data.startswith("menu:cat:"):
        cat = data[9:]  # "" = tous les sites
        cat_label = VALID_CATEGORIES.get(cat, "Tous les sites") if cat else "Tous les sites"
        context.user_data["pending_cat"] = cat if cat != "" else "__all__"
        await q.message.reply_text(
            f"🔍 <b>{_esc(cat_label)}</b>\nTape le titre à chercher :",
            parse_mode=ParseMode.HTML,
        )
        return

    # ── Bouton Mes sites ──
    if data == "menu:listsites":
        sites = _registry.all()
        if not sites:
            await q.message.reply_text(
                "Aucun site enregistré.\nUtilise /addsite &lt;url&gt; pour en ajouter.",
                parse_mode=ParseMode.HTML,
            )
            return
        groups: dict[str, list] = {c: [] for c in VALID_CATEGORIES}
        groups[""] = []
        for site in sites:
            c = site.get("category", "")
            groups.get(c, groups[""]).append(site)
        lines = [f"📋 <b>Sites enregistrés ({len(sites)})</b>\n"]
        for c, label in VALID_CATEGORIES.items():
            if groups.get(c):
                lines.append(f"\n<b>{label}</b>")
                for s in groups[c]:
                    lines.append(f"  🌐 {_esc(s['domain'])}")
        if groups[""]:
            lines.append("\n<b>Sans catégorie</b>")
            for s in groups[""]:
                lines.append(f"  🌐 {_esc(s['domain'])}")
        await q.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    # ── Bouton Monitor ──
    if data == "menu:monitor":
        if _monitor_scheduler:
            lines = _monitor_scheduler.status_lines()
            await q.message.reply_text(
                "📊 <b>Statut du Monitor</b>\n\n" + "\n".join(lines),
                parse_mode=ParseMode.HTML,
            )
        else:
            await q.message.reply_text("❌ Monitor non initialisé.", parse_mode=ParseMode.HTML)
        return

    # ── Bouton Favoris ──
    if data == "menu:favlist":
        favs = _favorites.all(user_id)
        if not favs:
            await q.message.reply_text(
                "⭐ Aucun favori pour l'instant.\nClique ⭐ sous un résultat de recherche.",
                parse_mode=ParseMode.HTML,
            )
            return
        keyboard_rows = []
        lines = [f"⭐ <b>Tes favoris ({len(favs)})</b>\n"]
        for i, fav in enumerate(favs):
            lines.append(f"{i + 1}. <b>{_esc(fav['title'])}</b>  —  <i>{_esc(fav.get('domain', ''))}</i>")
            keyboard_rows.append([
                InlineKeyboardButton(f"🔗 {fav['title'][:28]}", url=fav["url"]),
                InlineKeyboardButton("🗑 Supprimer", callback_data=f"unfav:{i}"),
            ])
        await q.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard_rows),
        )
        return

    # ── Bouton Watchlist ──
    if data == "menu:watchlist":
        items = _watchlist_store.all_keywords(user_id)
        if not items:
            await q.message.reply_text(
                "📌 Ta watchlist est vide.\nUtilise /watch &lt;titre&gt;.",
                parse_mode=ParseMode.HTML,
            )
            return
        lines = [f"📋 <b>Watchlist ({len(items)} titre(s))</b>\n"]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {_esc(item)}")
        await q.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    # ── Bouton Recherche universelle ──
    if data == "menu:usearch":
        context.user_data["pending_cat"] = "__usearch__"
        await q.message.reply_text(
            "🌐 <b>Recherche universelle (DuckDuckGo)</b>\nTape ta requête :",
            parse_mode=ParseMode.HTML,
        )
        return


async def handle_text_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    MessageHandler — déclenché après qu'un utilisateur a cliqué un bouton
    de catégorie dans /menu et tape ensuite son titre.
    """
    from bot.registry import VALID_CATEGORIES

    pending = context.user_data.pop("pending_cat", None)
    if pending is None:
        return  # Rien en attente → on ignore le message

    query = (update.message.text or "").strip()
    if not query:
        return

    # ── Recherche universelle ──────────────────────────────────────────────
    if pending == "__usearch__":
        msg = await update.message.reply_text(
            f"🌐 Recherche universelle pour <b>{_esc(query)}</b> …",
            parse_mode=ParseMode.HTML,
        )
        results = await asyncio.to_thread(_searcher.search_universal, query)
        await msg.delete()
        if not results:
            await update.message.reply_text(
                f"😔 Aucun résultat pour <b>{_esc(query)}</b>.", parse_mode=ParseMode.HTML
            )
            return
        await update.message.reply_text(
            f"✅ <b>{len(results)} résultat(s)</b> :", parse_mode=ParseMode.HTML
        )
        for r in results:
            await _send_result_card(update, r)
        return

    # ── Recherche par catégorie (ou tous) ──────────────────────────────────
    cat = "" if pending == "__all__" else pending
    cat_label = VALID_CATEGORIES.get(cat, "") if cat else ""
    sites = _registry.get_by_category(cat) if cat else _registry.all()
    n_sites = len(sites)

    if not n_sites:
        scope = f"dans <b>{_esc(cat_label)}</b>" if cat_label else "dans le registre"
        await update.message.reply_text(
            f"❌ Aucun site {scope}.\n"
            f"Ajoute-en un avec /addsite &lt;url&gt;{(' ' + cat) if cat else ''}",
            parse_mode=ParseMode.HTML,
        )
        return

    scope_label = f" · {cat_label}" if cat_label else f" · {n_sites} site(s)"
    msg = await update.message.reply_text(
        f"🔍 Recherche de <b>{_esc(query)}</b>{scope_label} …",
        parse_mode=ParseMode.HTML,
    )
    results = await asyncio.to_thread(
        _searcher.search_registered, query, _registry, category=cat
    )
    await msg.delete()

    if not results:
        await update.message.reply_text(
            f"😔 Aucun résultat pour <b>{_esc(query)}</b>" +
            (f" dans {_esc(cat_label)}" if cat_label else "") + ".\n"
            "Essaie /usearch pour une recherche universelle.",
            parse_mode=ParseMode.HTML,
        )
        return

    enrich_msg = await update.message.reply_text("⭐ Enrichissement MAL en cours…")
    results = await asyncio.to_thread(_enrich_with_mal, results)
    await enrich_msg.delete()

    await update.message.reply_text(
        f"✅ <b>{len(results)} résultat(s)</b> pour « {_esc(query)} »" +
        (f" · {_esc(cat_label)}" if cat_label else "") + " :",
        parse_mode=ParseMode.HTML,
    )
    for result in results:
        await _send_result_card(update, result)


# ─── Watchlist (commandes) ───────────────────────────────────────────────────

async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/watch <titre> — ajoute un terme à surveiller."""
    if not context.args:
        await update.message.reply_text(
            "Usage : /watch &lt;titre à surveiller&gt;\n"
            "Exemple : /watch frieren",
            parse_mode=ParseMode.HTML,
        )
        return
    keyword = " ".join(context.args).strip()
    user_id = update.effective_user.id
    added   = _watchlist_store.add(user_id, keyword)
    if added:
        await update.message.reply_text(
            f"👁 <b>{_esc(keyword)}</b> ajouté à ta watchlist !\n"
            "Tu seras notifié dès qu'un contenu correspondant est détecté par le monitor.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"<b>{_esc(keyword)}</b> est déjà dans ta watchlist.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/unwatch <titre> — retire un terme de la watchlist."""
    if not context.args:
        await update.message.reply_text(
            "Usage : /unwatch &lt;titre&gt;\n"
            "Exemple : /unwatch frieren",
            parse_mode=ParseMode.HTML,
        )
        return
    keyword = " ".join(context.args).strip()
    user_id = update.effective_user.id
    removed = _watchlist_store.remove(user_id, keyword)
    if removed:
        await update.message.reply_text(
            f"✅ <b>{_esc(keyword)}</b> retiré de ta watchlist.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"❌ <b>{_esc(keyword)}</b> n'est pas dans ta watchlist.",
            parse_mode=ParseMode.HTML,
        )


async def cmd_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche la watchlist de l'utilisateur."""
    user_id  = update.effective_user.id
    keywords = _watchlist_store.all_keywords(user_id)
    if not keywords:
        await update.message.reply_text(
            "👁 Ta watchlist est vide.\n"
            "Utilise /watch &lt;titre&gt; pour surveiller un contenu.",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = [f"👁 <b>Ta watchlist ({len(keywords)} terme(s))</b>\n"]
    for i, kw in enumerate(keywords, 1):
        lines.append(f"{i}. {_esc(kw)}")
    lines.append("\n<i>Utilise /unwatch &lt;terme&gt; pour supprimer.</i>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ─── Commandes /monitor ──────────────────────────────────────────────────────

async def cmd_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /monitor on      — active les notifications automatiques
    /monitor off     — désactive
    /monitor status  — affiche l'état + les sites surveillés
    /monitor now     — force un check immédiat
    """
    sub = (context.args[0].lower() if context.args else "status")

    if _monitor_scheduler is None:
        await update.message.reply_text(
            "❌ Le scheduler n'est pas initialisé. Redémarre le bot.",
            parse_mode=ParseMode.HTML,
        )
        return

    if sub == "on":
        _monitor_scheduler.enable()
        await update.message.reply_text(
            "🟢 <b>Monitor activé !</b>\n"
            f"Check quotidien à <b>{_monitor_scheduler.config.check_hour:02d}:{_monitor_scheduler.config.check_minute:02d} UTC</b>\n"
            "Utilise /monitor now pour tester immédiatement.",
            parse_mode=ParseMode.HTML,
        )

    elif sub == "off":
        _monitor_scheduler.disable()
        await update.message.reply_text(
            "🔴 <b>Monitor désactivé.</b>\n"
            "Les notifications automatiques sont suspendues.\n"
            "Tu peux toujours lancer /monitor now manuellement.",
            parse_mode=ParseMode.HTML,
        )

    elif sub == "status":
        lines = _monitor_scheduler.status_lines()
        await update.message.reply_text(
            "📊 <b>Statut du Monitor</b>\n\n" + "\n".join(lines),
            parse_mode=ParseMode.HTML,
        )

    elif sub == "now":
        sites = _registry.all()
        if not sites:
            await update.message.reply_text(
                "❌ Aucun site enregistré.\nAjoute d'abord un site avec /addsite &lt;url&gt;",
                parse_mode=ParseMode.HTML,
            )
            return

        msg = await update.message.reply_text(
            f"⏳ Check en cours sur <b>{len(sites)}</b> site(s)…\n"
            "(Cela peut prendre 1-2 minutes selon les sites)",
            parse_mode=ParseMode.HTML,
        )

        try:
            count = await _monitor_scheduler.check_now()
            await msg.edit_text(
                f"✅ Check terminé !\n"
                f"📬 <b>{count}</b> nouvelle(s) notification(s) envoyée(s).",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.error("Monitor check_now erreur : %s", e)
            await msg.edit_text(f"❌ Erreur pendant le check : {e}")

    elif sub == "setchat":
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage : /monitor setchat &lt;@canal ou chat_id&gt;\n\n"
                "Exemples :\n"
                "  /monitor setchat @MonCanal\n"
                "  /monitor setchat -1001234567890\n\n"
                "Le bot doit être admin du canal.\n"
                "Retire avec /monitor removechat &lt;chat_id&gt;",
                parse_mode=ParseMode.HTML,
            )
            return
        target = context.args[1]
        try:
            chat = await context.bot.get_chat(target)
            cid  = chat.id
            name = chat.title or chat.username or str(cid)
            added = _monitor_scheduler.add_notification_chat(cid)
            if added:
                await update.message.reply_text(
                    f"✅ Notifications activées vers <b>{_esc(name)}</b> (ID : <code>{cid}</code>)",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.message.reply_text(
                    f"Ce chat est déjà dans les destinataires.",
                    parse_mode=ParseMode.HTML,
                )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Impossible d'accéder au chat : {_esc(str(e))}\n"
                "Vérifie que le bot est admin du canal.",
                parse_mode=ParseMode.HTML,
            )

    elif sub == "removechat":
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage : /monitor removechat &lt;chat_id&gt;\n"
                "L'ID est affiché dans /monitor status.",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            cid     = int(context.args[1])
            removed = _monitor_scheduler.remove_notification_chat(cid)
            if removed:
                await update.message.reply_text(
                    f"✅ Canal <code>{cid}</code> retiré des destinataires.",
                    parse_mode=ParseMode.HTML,
                )
            else:
                await update.message.reply_text(
                    f"❌ <code>{cid}</code> non trouvé parmi les canaux ajoutés.\n"
                    "Les IDs admins (.env) ne peuvent pas être retirés ici.",
                    parse_mode=ParseMode.HTML,
                )
        except ValueError:
            await update.message.reply_text(
                "❌ ID invalide — utilise un ID numérique (ex: -1001234567890).",
                parse_mode=ParseMode.HTML,
            )

    elif sub == "settime":
        # /monitor settime HH:MM  — change l'heure du check quotidien
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage : /monitor settime &lt;HH:MM&gt;\n"
                "Exemple : /monitor settime 08:30\n"
                "L'heure est en UTC. Désactive le mode intervalle.",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            hh, mm = context.args[1].split(":")
            hour, minute = int(hh), int(mm)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            _monitor_scheduler.set_schedule(hour, minute)
            await update.message.reply_text(
                f"✅ Check quotidien reprogrammé à <b>{hour:02d}:{minute:02d} UTC</b>\n"
                f"⏭ Prochain run : {_monitor_scheduler.next_run_info()}",
                parse_mode=ParseMode.HTML,
            )
        except (ValueError, AttributeError):
            await update.message.reply_text(
                "❌ Format invalide. Utilise HH:MM (ex: 08:30).",
                parse_mode=ParseMode.HTML,
            )

    elif sub == "freq":
        # /monitor freq <N>  — check toutes les N heures (0 = retour au mode quotidien)
        if len(context.args) < 2:
            await update.message.reply_text(
                "Usage : /monitor freq &lt;heures&gt;\n"
                "Exemples :\n"
                "  /monitor freq 2   → check toutes les 2h\n"
                "  /monitor freq 6   → check toutes les 6h\n"
                "  /monitor freq 0   → revenir au mode quotidien (settime)\n",
                parse_mode=ParseMode.HTML,
            )
            return
        try:
            hours = int(context.args[1])
            if hours < 0:
                raise ValueError
            if hours == 0:
                # Retour au mode cron
                _monitor_scheduler.set_interval(0)
                _monitor_scheduler._schedule_daily_job()
                await update.message.reply_text(
                    f"✅ Retour au mode quotidien : "
                    f"<b>{_monitor_scheduler.config.check_hour:02d}:{_monitor_scheduler.config.check_minute:02d} UTC</b>\n"
                    f"⏭ Prochain run : {_monitor_scheduler.next_run_info()}",
                    parse_mode=ParseMode.HTML,
                )
            else:
                _monitor_scheduler.set_interval(hours)
                await update.message.reply_text(
                    f"✅ Monitor : check toutes les <b>{hours}h</b>\n"
                    f"⏭ Prochain run : {_monitor_scheduler.next_run_info()}",
                    parse_mode=ParseMode.HTML,
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Nombre d'heures invalide (entier positif ou 0).",
                parse_mode=ParseMode.HTML,
            )

    else:
        await update.message.reply_text(
            "📖 <b>Commandes /monitor :</b>\n\n"
            "/monitor on          — Active les notifications automatiques\n"
            "/monitor off         — Désactive\n"
            "/monitor status      — Voir l'état + les sites surveillés\n"
            "/monitor now         — Lancer un check immédiat\n"
            "/monitor settime &lt;HH:MM&gt; — Changer l'heure du check quotidien (UTC)\n"
            "/monitor freq &lt;N&gt;       — Check toutes les N heures (0 = mode quotidien)\n"
            "/monitor setchat &lt;@canal&gt; — Envoyer les notifs dans un canal\n"
            "/monitor removechat &lt;id&gt;  — Retirer un canal\n\n"
            "<i>Exemples :</i>\n"
            "  /monitor settime 08:30  → check chaque jour à 8h30 UTC\n"
            "  /monitor freq 3         → check toutes les 3h\n"
            "  /monitor freq 0         → retour au check quotidien",
            parse_mode=ParseMode.HTML,
        )


# ─── Lancement du bot ─────────────────────────────────────────────────────────

def run_bot(token: str) -> None:
    """Lance le bot en mode polling avec le scheduler de monitoring."""
    global _monitor_scheduler, _admin_chat_ids

    admin_chat_id_raw = os.getenv("ADMIN_CHAT_ID", "").strip()
    # Support plusieurs IDs séparés par une virgule
    admin_chat_ids = [
        int(x.strip()) for x in admin_chat_id_raw.split(",") if x.strip().lstrip("-").isdigit()
    ]
    _admin_chat_ids = admin_chat_ids  # rendre accessible globalement

    async def _post_init(app: Application) -> None:
        """Démarre le scheduler après l'initialisation de l'app."""
        global _monitor_scheduler
        if not admin_chat_ids:
            logger.warning(
                "ADMIN_CHAT_ID non configuré — le monitor ne peut pas envoyer de notifications.\n"
                "Ajoute ADMIN_CHAT_ID dans .env (obtiens ton ID via @userinfobot)"
            )
            return
        from monitor.scheduler import MonitorScheduler
        _monitor_scheduler = MonitorScheduler(
            bot=app.bot,
            chat_ids=admin_chat_ids,
            registry=_registry,
        )
        _monitor_scheduler.start()
        logger.info("MonitorScheduler démarré (ADMIN_CHAT_IDS=%s)", admin_chat_ids)

    async def _post_stop(app: Application) -> None:
        """Arrête le scheduler proprement."""
        if _monitor_scheduler:
            _monitor_scheduler.stop()

    app = (
        Application.builder()
        .token(token)
        .post_init(_post_init)
        .post_stop(_post_stop)
        .build()
    )

    # Enregistrement des handlers
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
    app.add_handler(CommandHandler("menu",       cmd_menu))
    app.add_handler(CommandHandler("addsite",    cmd_addsite))
    app.add_handler(CommandHandler("listsites",  cmd_listsites))
    app.add_handler(CommandHandler("removesite", cmd_removesite))
    app.add_handler(CommandHandler("search",     cmd_search))
    app.add_handler(CommandHandler("usearch",    cmd_usearch))
    app.add_handler(CommandHandler("ssearch",    cmd_ssearch))
    app.add_handler(CommandHandler("seasonal",   cmd_seasonal))
    app.add_handler(CommandHandler("upcoming",   cmd_upcoming))
    app.add_handler(CommandHandler("top",        cmd_top))
    app.add_handler(CommandHandler("movies",     cmd_movies))
    app.add_handler(CommandHandler("monitor",    cmd_monitor))
    app.add_handler(ChatMemberHandler(on_bot_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(CommandHandler("favlist",    cmd_favlist))
    app.add_handler(CommandHandler("watch",      cmd_watch))
    app.add_handler(CommandHandler("unwatch",    cmd_unwatch))
    app.add_handler(CommandHandler("watchlist",  cmd_watchlist))
    app.add_handler(CallbackQueryHandler(callback_fav,  pattern=r"^(fav:|unfav:)"))
    app.add_handler(CallbackQueryHandler(callback_menu, pattern=r"^menu:"))
    # MessageHandler pour les recherches déclenchées via boutons du /menu
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_search))

    logger.info("SEARCHBOT démarré — en attente de messages…")
    app.run_polling(drop_pending_updates=True)
