"""
🤖 BOT TELEGRAM UNIFIÉ - SITES + ANIMES + MANHWA + SIMKL
============================================================
4 modes en 1 bot:
1. 🌐 Chercher des sites
2. 🎌 Anime/Manga (MyAnimeList)
3. 📚 Manhwa/Manhua (AniList)
4. 🎬 Films/Séries (Simkl)
"""

import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from anime_api import JikanAnimeAPI
from anilist_api import AniListAPI
from simkl_api import SimklAPI
from omdb_api import OMDbAPI
from directory_scraper import DirectoryScraper

load_dotenv()

class UnifiedBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.catalogue_url = os.getenv('CATALOGUE_URL', '')
        self.anime_catalogue_url = os.getenv('ANIME_CATALOGUE_URL', '')
        
        if not self.token or self.token == 'TON_TOKEN_TELEGRAM_ICI':
            raise ValueError("❌ Configure TELEGRAM_BOT_TOKEN dans .env!")
        
        self.anime_api = JikanAnimeAPI()
        self.anilist_api = AniListAPI()
        self.simkl_api = SimklAPI()
        self.omdb_api = OMDbAPI()
        self.directory_scraper = DirectoryScraper()
        self.user_modes = {}
        
        self.app = Application.builder().token(self.token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("menu", self.menu_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))
    
    def _get_main_menu_keyboard(self):
        keyboard = [
            [
                InlineKeyboardButton("🔞 Sites", callback_data="mode_sites"),
                InlineKeyboardButton("📺 Anime Sites", callback_data="mode_anime_sites")
            ],
            [
                InlineKeyboardButton("🎌 Anime/Manga", callback_data="mode_anime"),
                InlineKeyboardButton("📚 Manhwa", callback_data="mode_manhwa")
            ],
            [
                InlineKeyboardButton("🎬 Simkl", callback_data="mode_simkl"),
                InlineKeyboardButton("🎭 IMDB/OMDb", callback_data="mode_omdb")
            ],
            [InlineKeyboardButton("❓ Aide", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome = """🤖 Bot Unifié

🔞 Sites - Catalogue adult
📺 Anime Sites - Sites streaming/reader
🎌 Anime/Manga - MyAnimeList  
📚 Manhwa - AniList (KR/CN)
🎬 Films/Séries - Simkl
🎭 IMDB - Données OMDb

Choisis un mode:"""
        await update.message.reply_text(welcome, reply_markup=self._get_main_menu_keyboard())
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        self.user_modes.pop(user_id, None)
        await update.message.reply_text("🏠 Menu Principal", reply_markup=self._get_main_menu_keyboard())
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """📖 Aide:

MODE SITES:
Tape un mot-clé: gaming, movies...

MODE ANIME:
- Tape un nom d'anime
- top / top 10
- user username
- season 2024 winter

MODE MANHWA:
- Tape un nom
- trending
- manhwa Solo Leveling

MODE SIMKL (Films/Séries):
- Tape un titre
- movies Inception
- shows Breaking Bad
- trending

MODE OMDB (IMDB):
- Tape un titre
- movies Inception
- series Breaking Bad

/menu - Retour au menu"""
        await update.message.reply_text(help_text)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        if data == "mode_sites":
            self.user_modes[user_id] = "sites"
            cat_info = f"\n📍 {self.catalogue_url}" if self.catalogue_url else "\n⚠️ Configure CATALOGUE_URL"
            await query.message.reply_text(f"🔞 Mode Sites{cat_info}\n\nTape un mot-clé")
        
        elif data == "mode_anime_sites":
            self.user_modes[user_id] = "anime_sites"
            cat_info = f"\n📍 {self.anime_catalogue_url}" if self.anime_catalogue_url else "\n⚠️ Configure ANIME_CATALOGUE_URL"
            await query.message.reply_text(f"📺 Mode Anime Sites{cat_info}\n\nTape: anime, manga, manhwa...")
        
        elif data == "mode_anime":
            self.user_modes[user_id] = "anime"
            await query.message.reply_text("🎌 Mode Anime (MAL)\n\nTape un nom ou: top, user, season")
        
        elif data == "mode_manhwa":
            self.user_modes[user_id] = "manhwa"
            await query.message.reply_text("📚 Mode Manhwa (AniList)\n\nTape un nom ou: trending, manhwa")
        
        elif data == "mode_simkl":
            self.user_modes[user_id] = "simkl"
            await query.message.reply_text("🎬 Mode Simkl (Films/Séries/Anime)\n\nTape un titre ou: trending, movies, shows")
        
        elif data == "mode_omdb":
            self.user_modes[user_id] = "omdb"
            if not self.omdb_api.api_key:
                await query.message.reply_text("⚠️ Clé API OMDb manquante!\n\nObtiens-la sur:\nhttp://www.omdbapi.com/apikey.aspx\n\nPuis ajoute OMDB_API_KEY dans .env")
            else:
                await query.message.reply_text("🎭 Mode IMDB/OMDb (Données officielles)\n\nTape un titre ou: movies Inception, series Breaking Bad")
        
        elif data == "help":
            await self.help_command(query, context)
        
        elif data.startswith("details_"):
            anime_id = int(data.split("_")[1])
            await self._send_mal_details(query, anime_id)
        
        elif data.startswith("anilist_"):
            media_id = int(data.split("_")[1])
            await self._send_anilist_details(query, media_id)
        
        elif data.startswith("simkl_"):
            simkl_id = int(data.split("_")[1])
            media_type = data.split("_")[2] if len(data.split("_")) > 2 else "show"
            await self._send_simkl_details(query, simkl_id, media_type)
        
        elif data.startswith("omdb_"):
            imdb_id = data.split("_")[1]
            await self._send_omdb_details(query, imdb_id)
    
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text.strip()
        mode = self.user_modes.get(user_id)
        
        if not mode:
            await update.message.reply_text("Choisis un mode: /start", reply_markup=self._get_main_menu_keyboard())
            return
        
        if mode == "sites":
            await self._handle_sites(update, text)
        elif mode == "anime_sites":
            await self._handle_anime_sites(update, text)
        elif mode == "anime":
            await self._handle_anime(update, text)
        elif mode == "manhwa":
            await self._handle_manhwa(update, text)
        elif mode == "simkl":
            await self._handle_simkl(update, text)
        elif mode == "omdb":
            await self._handle_omdb(update, text)
    
    async def _handle_sites(self, update: Update, keyword: str):
        if not self.catalogue_url or self.catalogue_url == 'https://ton-site-catalogue.com':
            await update.message.reply_text("⚠️ Configure CATALOGUE_URL dans .env")
            return
        
        await update.message.reply_text(f"🔍 Recherche '{keyword}'...")
        
        try:
            results = self.directory_scraper.search_in_directory(self.catalogue_url, keyword, max_results=15)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun site pour '{keyword}'")
                return
            
            message = f"🎯 {len(results)} sites trouvés:\n\n"
            
            for i, site in enumerate(results[:10], 1):
                title = site.get('title', 'Sans titre')[:60]
                url = site.get('url', '')
                desc = site.get('description', '')
                
                # Nettoyer la description
                if desc:
                    desc = desc.replace('*', '').replace('_', '').replace('[', '').replace(']', '')
                    desc = desc[:80] + '...' if len(desc) > 80 else desc
                
                message += f"🔞 {i}. {title}\n{url}\n"
                if desc:
                    message += f"{desc}\n"
                message += "\n"
                
                if len(message) > 3500:
                    await update.message.reply_text(message, disable_web_page_preview=True)
                    message = ""
            
            if message:
                await update.message.reply_text(message, disable_web_page_preview=True)
            
            if len(results) > 10:
                await update.message.reply_text(f"... et {len(results)-10} autres")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _handle_anime_sites(self, update: Update, keyword: str):
        """Handler pour le catalogue anime/manga/manhwa sites"""
        if not self.anime_catalogue_url:
            await update.message.reply_text("⚠️ Configure ANIME_CATALOGUE_URL dans .env")
            return
        
        keyword_lower = keyword.lower()
        
        # Déterminer la catégorie et URL
        if any(word in keyword_lower for word in ['anime', 'streaming', 'watch']):
            category = "🎬 Anime Streaming"
            url = "https://fmhy.net/video#anime-streaming"
            desc = "Sites de streaming anime gratuits"
        elif any(word in keyword_lower for word in ['manga', 'manhwa', 'manhua', 'read', 'reader']):
            category = "📖 Manga/Manhwa Readers"
            url = "https://fmhy.net/reading#manga"
            desc = "Sites pour lire manga/manhwa/manhua"
        elif 'torrent' in keyword_lower:
            category = "💾 Torrents Anime"
            url = "https://fmhy.net/torrenting#anime-torrenting"
            desc = "Sites torrent pour anime"
        elif 'download' in keyword_lower:
            category = "⬇️ Téléchargement"
            url = "https://fmhy.net/downloading"
            desc = "Sites de téléchargement direct"
        else:
            # Par défaut, montrer toutes les catégories
            message = """📺 *Anime Sites - Catégories disponibles:*

🎬 *Anime Streaming*
Tape: `anime` ou `streaming`
🔗 https://fmhy.net/video#anime-streaming

📖 *Manga/Manhwa Readers*
Tape: `manga` ou `manhwa`
🔗 https://fmhy.net/reading#manga

💾 *Torrents Anime*
Tape: `torrent`
🔗 https://fmhy.net/torrenting#anime-torrenting

⬇️ *Téléchargement*
Tape: `download`
🔗 https://fmhy.net/downloading

💡 *Astuce:* FMHY est un catalogue géant, clique sur les liens pour voir tous les sites!"""
            
            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            return
        
        # Envoyer la catégorie trouvée
        message = f"""📺 *{category}*

{desc}

🔗 {url}

💡 Clique sur le lien pour voir la liste complète des meilleurs sites!"""
        
        await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=False)
    
    async def _handle_anime(self, update: Update, text: str):
        parts = text.lower().split()
        
        if parts[0] == "top":
            limit = min(int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 10, 25)
            await self._show_top_anime(update, limit)
        elif parts[0] == "user" and len(parts) > 1:
            await self._show_user_list(update, parts[1])
        elif parts[0] == "season" and len(parts) >= 3:
            try:
                await self._show_season(update, int(parts[1]), parts[2])
            except:
                await update.message.reply_text("Format: season 2024 winter")
        else:
            await self._search_anime(update, text)
    
    async def _search_anime(self, update: Update, query: str):
        await update.message.reply_text(f"🔍 Recherche '{query}'...")
        
        try:
            results = self.anime_api.search_anime(query, limit=8)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun résultat")
                return
            
            message = f"🎯 Résultats:\n\n"
            keyboard = []
            
            for i, anime in enumerate(results, 1):
                title = anime['title']
                score = anime['score'] or '?'
                eps = anime['episodes'] or '?'
                
                message += f"{i}. {title}\n⭐ {score} | 📺 {eps} eps\n\n"
                keyboard.append([InlineKeyboardButton(f"{i}. Détails", callback_data=f"details_{anime['mal_id']}")])
            
            await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _show_top_anime(self, update: Update, limit: int):
        await update.message.reply_text(f"🏆 Top {limit}...")
        
        try:
            top = self.anime_api.get_top_anime(limit=limit)
            message = f"🏆 Top {limit}:\n\n"
            
            for anime in top:
                message += f"#{anime['rank']}. {anime['title']}\n⭐ {anime['score']}\n\n"
            
            await update.message.reply_text(message, disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _show_user_list(self, update: Update, username: str):
        await update.message.reply_text(f"👤 Liste de {username}...")
        
        try:
            animelist = self.anime_api.get_user_animelist(username)
            
            if not animelist:
                await update.message.reply_text(f"❌ Utilisateur non trouvé")
                return
            
            total = len(animelist)
            watching = sum(1 for a in animelist if a['watching_status'] == 'watching')
            completed = sum(1 for a in animelist if a['watching_status'] == 'completed')
            
            message = f"📊 {username}:\n\n📚 Total: {total}\n▶️ En cours: {watching}\n✅ Complétés: {completed}\n\nTop 5:\n"
            
            for i, anime in enumerate(animelist[:5], 1):
                message += f"{i}. {anime['title'][:30]}\n"
            
            await update.message.reply_text(message)
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _show_season(self, update: Update, year: int, season: str):
        if season not in ['winter', 'spring', 'summer', 'fall']:
            await update.message.reply_text("Saisons: winter, spring, summer, fall")
            return
        
        await update.message.reply_text(f"📅 {season} {year}...")
        
        try:
            animes = self.anime_api.get_seasonal_anime(year, season)
            message = f"📅 {season.title()} {year}:\n\n"
            
            for i, anime in enumerate(animes[:10], 1):
                message += f"{i}. {anime['title'][:40]}\n⭐ {anime['score'] or '?'}\n\n"
            
            await update.message.reply_text(message, disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _handle_manhwa(self, update: Update, text: str):
        parts = text.lower().split()
        
        if parts[0] == "trending":
            await self._show_trending(update)
        elif parts[0] == "manhwa" and len(parts) > 1:
            query = ' '.join(parts[1:])
            await self._search_manhwa(update, query)
        else:
            await self._search_anilist(update, text)
    
    async def _search_anilist(self, update: Update, query: str):
        await update.message.reply_text(f"🔍 Recherche '{query}'...")
        
        try:
            results = self.anilist_api.search_media(query, limit=8)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun résultat")
                return
            
            message = f"🎯 Résultats:\n\n"
            keyboard = []
            
            for i, media in enumerate(results, 1):
                title = media['title']
                score = media['score'] or '?'
                country = {"JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳"}.get(media['country'], "🌐")
                
                message += f"{i}. {title}\n{country} ⭐ {score}\n\n"
                keyboard.append([InlineKeyboardButton(f"{i}. Détails", callback_data=f"anilist_{media['id']}")])
            
            await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _search_manhwa(self, update: Update, query: str):
        await update.message.reply_text(f"🇰🇷 Recherche manhwa '{query}'...")
        
        try:
            results = self.anilist_api.search_manhwa(query, limit=8)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun manhwa")
                return
            
            message = f"🇰🇷 Manhwa:\n\n"
            keyboard = []
            
            for i, manhwa in enumerate(results, 1):
                title = manhwa['title']
                score = manhwa['score'] or '?'
                
                message += f"{i}. {title}\n⭐ {score}\n\n"
                keyboard.append([InlineKeyboardButton(f"{i}. Détails", callback_data=f"anilist_{manhwa['id']}")])
            
            await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _show_trending(self, update: Update):
        await update.message.reply_text("🔥 Tendances...")
        
        try:
            trending = self.anilist_api.get_trending(limit=10)
            message = "🔥 Trending:\n\n"
            
            for i, media in enumerate(trending, 1):
                title = media['title']
                score = media['score'] or '?'
                country = {"JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳"}.get(media['country'], "🌐")
                
                message += f"{i}. {title}\n{country} ⭐ {score}\n\n"
            
            await update.message.reply_text(message, disable_web_page_preview=True)
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _send_mal_details(self, query, anime_id: int):
        await query.message.reply_text("📝 Détails...")
        
        try:
            details = self.anime_api.get_anime_details(anime_id)
            if not details:
                await query.message.reply_text("❌ Non trouvé")
                return
            
            message = f"""🎌 {details['title']}

⭐ Score: {details['score'] or '?'}
📊 Rank: #{details['rank'] or '?'}
📺 Episodes: {details['episodes'] or '?'}
🎨 Studios: {', '.join(details['studios'][:2]) if details['studios'] else '?'}

{details['synopsis'][:250] if details['synopsis'] else ''}...

{details['url']}"""
            
            await query.message.reply_text(message, disable_web_page_preview=True)
        except Exception as e:
            await query.message.reply_text(f"❌ {str(e)}")
    
    async def _send_anilist_details(self, query, media_id: int):
        await query.message.reply_text("📝 Détails...")
        
        try:
            details = self.anilist_api.get_media_details(media_id)
            if not details:
                await query.message.reply_text("❌ Non trouvé")
                return
            
            country = {"JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳"}.get(details['country'], "🌐")
            desc = details['description'] or ''
            desc = desc.replace('<br>', '\n').replace('<i>', '').replace('</i>', '')
            desc = desc[:250] if len(desc) > 250 else desc
            
            message = f"""📚 {details['title']}

{country} ⭐ {details['score'] or '?'}
📊 Popularity: #{details['popularity'] or '?'}
🏷️ {', '.join(details['genres'][:3]) if details['genres'] else '?'}

{desc}...

{details['url']}"""
            
            await query.message.reply_text(message, disable_web_page_preview=True)
        except Exception as e:
            await query.message.reply_text(f"❌ {str(e)}")
    
    async def _handle_simkl(self, update: Update, text: str):
        parts = text.lower().split()
        
        if parts[0] == "trending":
            await self._show_simkl_trending(update)
        elif parts[0] == "movies" and len(parts) > 1:
            query = ' '.join(parts[1:])
            await self._search_simkl_movies(update, query)
        elif parts[0] == "shows" and len(parts) > 1:
            query = ' '.join(parts[1:])
            await self._search_simkl_shows(update, query)
        else:
            await self._search_simkl(update, text)
    
    async def _search_simkl(self, update: Update, query: str):
        await update.message.reply_text(f"🔍 Recherche '{query}'...")
        
        try:
            # Chercher dans shows d'abord (priorité), puis movies
            shows = self.simkl_api.search_shows(query, limit=6)
            movies = self.simkl_api.search_movies(query, limit=4)
            
            # Trier par année décroissante (plus récents d'abord)
            shows_sorted = sorted(shows, key=lambda x: x.get('year') or 0, reverse=True)
            movies_sorted = sorted(movies, key=lambda x: x.get('year') or 0, reverse=True)
            
            # Combiner: shows en premier, puis movies
            results = shows_sorted + movies_sorted
            
            if not results:
                await update.message.reply_text(f"❌ Aucun résultat")
                return
            
            message = f"🎯 Résultats:\n\n"
            keyboard = []
            
            for i, media in enumerate(results[:8], 1):
                title = media['title']
                year = media['year'] or '?'
                rating = media['rating'] or '?'
                media_type = media['type']
                type_emoji = {"movie": "🎬", "show": "📺", "anime": "🎌"}.get(media_type, "🎥")
                
                message += f"{i}. {title} ({year})\n{type_emoji} ⭐ {rating}\n\n"
                
                callback_type = "movie" if media_type == "movie" else "show"
                keyboard.append([InlineKeyboardButton(f"{i}. Détails", callback_data=f"simkl_{media['id']}_{callback_type}")])
            
            await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _search_simkl_movies(self, update: Update, query: str):
        await update.message.reply_text(f"🎬 Films '{query}'...")
        
        try:
            results = self.simkl_api.search_movies(query, limit=8)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun film")
                return
            
            message = f"🎬 Films:\n\n"
            keyboard = []
            
            for i, movie in enumerate(results, 1):
                title = movie['title']
                year = movie['year'] or '?'
                rating = movie['rating'] or '?'
                
                message += f"{i}. {title} ({year})\n⭐ {rating}\n\n"
                keyboard.append([InlineKeyboardButton(f"{i}. Détails", callback_data=f"simkl_{movie['id']}_movie")])
            
            await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _search_simkl_shows(self, update: Update, query: str):
        await update.message.reply_text(f"📺 Séries '{query}'...")
        
        try:
            results = self.simkl_api.search_shows(query, limit=8)
            
            if not results:
                await update.message.reply_text(f"❌ Aucune série")
                return
            
            message = f"📺 Séries:\n\n"
            keyboard = []
            
            for i, show in enumerate(results, 1):
                title = show['title']
                year = show['year'] or '?'
                rating = show['rating'] or '?'
                
                message += f"{i}. {title} ({year})\n⭐ {rating}\n\n"
                keyboard.append([InlineKeyboardButton(f"{i}. Détails", callback_data=f"simkl_{show['id']}_show")])
            
            await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _show_simkl_trending(self, update: Update):
        # L'API Simkl trending ne retourne pas les titres
        # On affiche plutôt des suggestions populaires
        message = """🔥 Suggestions Simkl:

Recherche des titres populaires:
- Avengers Endgame
- Breaking Bad
- The Last of Us
- Dune
- Stranger Things

Ou tape:
• movies [titre] - Films
• shows [titre] - Séries
• [titre] - Recherche générale"""
        
        await update.message.reply_text(message)
    
    async def _send_simkl_details(self, query, simkl_id: int, media_type: str):
        await query.message.reply_text("📝 Chargement...")
        
        try:
            details = self.simkl_api.get_details(simkl_id, media_type)
            if not details:
                await query.message.reply_text("❌ Non trouvé")
                return
            
            type_emoji = {"movie": "🎬", "show": "📺", "anime": "🎌"}.get(media_type, "🎥")
            
            # Titre et année
            title = details['title']
            year = details['year'] or '?'
            first_aired = details.get('first_aired', '')[:4] if details.get('first_aired') else year
            last_aired = details.get('last_aired', 'Now')
            
            # Ratings
            rating_simkl = details['rating'] or '?'
            votes_simkl = details['votes'] or 0
            rating_imdb = details.get('imdb_rating') or '?'
            votes_imdb = details.get('imdb_votes') or 0
            
            # Infos détaillées
            genres = ', '.join(details['genres']) if details['genres'] else '?'
            status = details['status'] or '?'
            country = (details['country'] or '?').upper()
            network = details.get('network') or '?'
            
            # Episodes et durée
            aired_eps = details.get('aired_episodes', 0)
            total_eps = details.get('total_episodes', 0)
            total_seasons = details.get('total_seasons', 0)
            runtime_per_ep = details.get('episode_run_time', 0)
            total_runtime = details.get('total_runtime', 0)
            schedule = details.get('schedule', '')
            
            # Stats
            rank = details.get('rank')
            drop_rate = details.get('drop_rate')
            
            # Cast
            cast = details.get('cast', [])
            cast_names = ', '.join([actor.get('name', '') for actor in cast[:3]]) if cast else 'N/A'
            
            # Synopsis
            overview = details['overview'] or 'Pas de description disponible.'
            if len(overview) > 400:
                overview = overview[:400] + '...'
            
            # Poster
            poster = details.get('poster', '')
            poster_url = f"https://wsrv.nl/?url=simkl.in/posters/{poster}_m.jpg" if poster else None
            
            # Construire le message
            caption = f"""*{title}*

📅 {first_aired} - {last_aired}"""
            
            # Type de média
            if media_type == "movie":
                caption += f"\n🎬 Film"
            
            # Schedule (jour/heure de diffusion) ou Network/Pays
            if schedule:
                caption += f"\n📡 {schedule} on {network}"
            elif network and network != '?':
                caption += f"\n📡 {network}"
            
            if country != '?':
                caption += f" • {country}"
            
            # Durée pour films (runtime simple)
            if media_type == "movie" and runtime_per_ep > 0:
                hours = runtime_per_ep // 60
                minutes = runtime_per_ep % 60
                if hours > 0:
                    caption += f"\n⏱️ {hours}h {minutes}min"
                else:
                    caption += f"\n⏱️ {minutes}min"
            # Durée totale pour séries
            elif total_runtime > 0:
                hours = total_runtime // 60
                minutes = total_runtime % 60
                if hours > 0:
                    caption += f"\n⏱️ {hours}h {minutes}m total"
                else:
                    caption += f"\n⏱️ {minutes}min total"
            
            # Saisons et épisodes
            if total_seasons > 0:
                caption += f"\n📺 {total_seasons} season{'s' if total_seasons > 1 else ''}"
                if aired_eps > 0:
                    caption += f" • {aired_eps} episode{'s' if aired_eps > 1 else ''}"
                elif total_eps > 0:
                    caption += f" • {total_eps} episode{'s' if total_eps > 1 else ''}"
            elif total_eps > 0:
                caption += f"\n📺 {total_eps} episode{'s' if total_eps > 1 else ''}"
                if aired_eps > 0 and aired_eps != total_eps:
                    caption += f" ({aired_eps} diffusés)"
            elif aired_eps > 0:
                caption += f"\n📺 {aired_eps} episode{'s' if aired_eps > 1 else ''}"
            
            # Durée par épisode
            if runtime_per_ep > 0:
                caption += f"\n⏱️ {runtime_per_ep}min par épisode"
            
            caption += f"\n\n⭐ Simkl: {rating_simkl}/10 ({votes_simkl} votes)"
            caption += f"\n🎭 IMDB: {rating_imdb}/10 ({votes_imdb} votes)"
            
            if rank:
                caption += f"\n📊 Classement: #{rank}"
            if drop_rate:
                caption += f"\n📉 Drop rate: {drop_rate}"
            
            caption += f"\n\n🏷️ {genres}"
            caption += f"\n📊 Status: {status}"
            
            if cast_names != 'N/A':
                caption += f"\n🎭 Cast: {cast_names}"
            
            caption += f"\n\n📖 {overview}"
            caption += f"\n\n🔗 {details['url']}"
            
            # Envoyer avec photo
            if poster_url:
                try:
                    await query.message.reply_photo(
                        photo=poster_url,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                except:
                    # Si l'image échoue, envoyer le texte
                    await query.message.reply_text(caption, parse_mode='Markdown', disable_web_page_preview=True)
            else:
                await query.message.reply_text(caption, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception as e:
            await query.message.reply_text(f"❌ {str(e)}")
    
    async def _handle_omdb(self, update: Update, text: str):
        """Handler pour le mode OMDb (IMDB)"""
        if not self.omdb_api.api_key:
            await update.message.reply_text("⚠️ Clé API OMDb manquante!\nVoir: http://www.omdbapi.com/apikey.aspx")
            return
        
        await update.message.reply_text(f"🔍 Recherche OMDb '{text}'...")
        
        try:
            # Déterminer le type
            media_type = ""
            query = text
            
            if text.lower().startswith("movies "):
                media_type = "movie"
                query = text[7:].strip()
            elif text.lower().startswith("series "):
                media_type = "series"
                query = text[7:].strip()
            
            results = self.omdb_api.search(query, media_type=media_type, limit=10)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun résultat pour '{text}'")
                return
            
            await self._search_omdb(update, results, query)
        except Exception as e:
            await update.message.reply_text(f"❌ {str(e)}")
    
    async def _search_omdb(self, update: Update, results, query: str):
        """Afficher résultats recherche OMDb avec boutons"""
        keyboard = []
        message = f"🎭 Résultats OMDb pour '{query}':\n\n"
        
        for i, item in enumerate(results[:10], 1):
            title = item.get('title', 'N/A')
            year = item.get('year', 'N/A')
            media_type = item.get('type', 'N/A')
            imdb_id = item.get('imdb_id', '')
            
            # Emoji selon type
            if media_type == 'movie':
                emoji = "🎬"
            elif media_type == 'series':
                emoji = "📺"
            else:
                emoji = "🎭"
            
            message += f"{i}. {emoji} {title} ({year})\n"
            
            if imdb_id:
                button = InlineKeyboardButton(
                    f"{i}. {title[:30]}",
                    callback_data=f"omdb_{imdb_id}"
                )
                keyboard.append([button])
        
        if keyboard:
            await update.message.reply_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True
            )
        else:
            await update.message.reply_text(message, disable_web_page_preview=True)
    
    async def _send_omdb_details(self, query, imdb_id: str):
        """Envoyer détails complets OMDb + Simkl combinés"""
        try:
            await query.message.reply_text(f"🔍 Chargement détails IMDB + Simkl...")
            
            # 1. Récupérer détails OMDb
            details = self.omdb_api.get_details(imdb_id=imdb_id)
            if not details:
                await query.message.reply_text("❌ Impossible de charger les détails")
                return
            
            # 2. Chercher sur Simkl pour les infos streaming
            title = details.get('title', '')
            year = details.get('year', '').split('–')[0].strip()  # Gérer "2022–" pour séries
            media_type = details.get('type', 'movie')
            
            simkl_data = None
            if title:
                # Rechercher sur Simkl
                if media_type == 'series':
                    results = self.simkl_api.search_shows(f"{title} {year}", limit=5)
                else:
                    results = self.simkl_api.search_movies(f"{title} {year}", limit=5)
                
                # Trouver la meilleure correspondance
                for result in results:
                    result_title = result.get('title', '').lower()
                    result_year = str(result.get('year', ''))
                    if title.lower() in result_title and year in result_year:
                        # Récupérer les détails Simkl
                        simkl_id = result.get('ids', {}).get('simkl_id')
                        endpoint_type = result.get('type', 'show')
                        if simkl_id:
                            simkl_data = self.simkl_api.get_details(simkl_id, endpoint_type)
                            break
            
            # 3. Construire caption combiné
            title_display = details.get('title', 'N/A').replace('_', '\\_').replace('*', '\\*').replace('[', '\\[')
            rated = details.get('rated', 'N/A')
            
            # Emoji selon type
            if media_type == 'movie':
                emoji = "🎬"
            elif media_type == 'series':
                emoji = "📺"
            else:
                emoji = "🎭"
            
            caption = f"*{emoji} {title_display}*\n"
            caption += f"📅 {year}"
            
            if rated and rated != 'N/A':
                caption += f" • {rated}"
            
            # STREAMING (Simkl)
            if simkl_data:
                network = simkl_data.get('network', '')
                country = simkl_data.get('country', '')
                if network:
                    caption += f"\n📡 {network}"
                    if country:
                        caption += f" ({country})"
            
            # DURÉE (Priorité Simkl > OMDb)
            runtime_displayed = False
            if simkl_data:
                # Runtime total
                total_runtime = simkl_data.get('total_runtime', 0)
                runtime_per_ep = simkl_data.get('runtime', 0)
                
                if media_type == 'movie' and runtime_per_ep > 0:
                    hours = runtime_per_ep // 60
                    minutes = runtime_per_ep % 60
                    if hours > 0:
                        caption += f"\n⏱️ {hours}h {minutes}min"
                    else:
                        caption += f"\n⏱️ {minutes}min"
                    runtime_displayed = True
                elif total_runtime > 0:
                    hours = total_runtime // 60
                    minutes = total_runtime % 60
                    if hours > 0:
                        caption += f"\n⏱️ {hours}h {minutes}m total"
                    else:
                        caption += f"\n⏱️ {minutes}min total"
                    runtime_displayed = True
            
            # Fallback OMDb runtime si Simkl n'a rien
            if not runtime_displayed:
                runtime = details.get('runtime', 'N/A')
                if runtime and runtime != 'N/A':
                    caption += f"\n⏱️ {runtime}"
            
            # SAISONS/ÉPISODES (Simkl > OMDb)
            if simkl_data:
                total_seasons = simkl_data.get('total_seasons', 0)
                total_eps = simkl_data.get('total_episodes', 0)
                aired_eps = simkl_data.get('aired_episodes', 0)
                runtime_per_ep = simkl_data.get('runtime', 0)
                
                if total_seasons > 0:
                    caption += f"\n📺 {total_seasons} season{'s' if total_seasons > 1 else ''}"
                    if aired_eps > 0:
                        caption += f" • {aired_eps} épisodes"
                    elif total_eps > 0:
                        caption += f" • {total_eps} épisodes"
                elif total_eps > 0:
                    caption += f"\n📺 {total_eps} épisode{'s' if total_eps > 1 else ''}"
                
                if runtime_per_ep > 0 and media_type == 'series':
                    caption += f"\n⏱️ {runtime_per_ep}min par épisode"
            else:
                # Fallback OMDb
                total_seasons = details.get('total_seasons', '')
                if total_seasons:
                    caption += f"\n📺 {total_seasons} saison{'s' if int(total_seasons) > 1 else ''}"
            
            # RATINGS (Combiner tous)
            caption += "\n\n*📊 Ratings:*"
            
            # IMDB (OMDb)
            imdb_rating = details.get('imdb_rating', 'N/A')
            imdb_votes = details.get('imdb_votes', 'N/A')
            if imdb_rating and imdb_rating != 'N/A':
                caption += f"\n⭐ IMDB: {imdb_rating}/10"
                if imdb_votes and imdb_votes != 'N/A':
                    caption += f" ({imdb_votes} votes)"
            
            # Simkl rating
            if simkl_data:
                rating_simkl = simkl_data.get('rating', 'N/A')
                if rating_simkl != 'N/A':
                    caption += f"\n⭐ Simkl: {rating_simkl}/10"
            
            # Metascore (OMDb)
            metascore = details.get('metascore', '')
            if metascore and metascore != 'N/A':
                caption += f"\n📊 Metascore: {metascore}/100"
            
            # Rotten Tomatoes + autres (OMDb)
            ratings = details.get('ratings', [])
            for rating in ratings:
                source = rating.get('Source', '').replace('_', '\\_')
                value = rating.get('Value', '')
                if 'Rotten' in source or 'Metacritic' in source:
                    caption += f"\n🍅 {source}: {value}"
            
            # CLASSEMENT (Simkl)
            if simkl_data:
                rank = simkl_data.get('rank', '')
                if rank:
                    caption += f"\n📊 Classement: #{rank}"
            
            # GENRE
            genre = details.get('genre', 'N/A')
            if genre and genre != 'N/A':
                caption += f"\n\n🏷️ {genre}"
            
            # STATUS (Simkl)
            if simkl_data:
                status = simkl_data.get('status', '')
                if status:
                    caption += f"\n📊 Status: {status}"
            
            # RÉALISATEUR (OMDb)
            director = details.get('director', 'N/A')
            if director and director != 'N/A' and director != 'N/A' and len(director) < 100:
                caption += f"\n\n🎬 *Réalisateur:* {director.replace('_', '\\_')}"
            
            # CAST (Combiner)
            cast_list = []
            if simkl_data:
                cast_data = simkl_data.get('people', [])
                cast_list = [p.get('name', '') for p in cast_data[:5] if p.get('name')]
            
            if not cast_list:
                actors = details.get('actors', '')
                if actors and actors != 'N/A':
                    cast_list = [a.strip() for a in actors.split(',')[:5]]
            
            if cast_list:
                caption += f"\n🎭 *Cast:* {', '.join(cast_list).replace('_', '\\_')}"
            
            # AWARDS (OMDb)
            awards = details.get('awards', 'N/A')
            if awards and awards != 'N/A' and awards != 'N/A' and len(awards) < 200:
                caption += f"\n\n🏆 {awards.replace('_', '\\_')}"
            
            # BOX OFFICE (OMDb - films uniquement)
            if media_type == 'movie':
                box_office = details.get('box_office', '')
                if box_office and box_office != 'N/A':
                    caption += f"\n💰 Box Office: {box_office}"
            
            # SYNOPSIS (Priorité Simkl > OMDb)
            plot = ''
            if simkl_data:
                plot = simkl_data.get('overview', '')
            if not plot:
                plot = details.get('plot', '')
            
            if plot and plot != 'N/A' and len(plot) < 600:
                caption += f"\n\n📖 {plot.replace('_', '\\_')}"
            
            # URLS
            caption += f"\n\n🔗 IMDB: {details.get('url', '')}"
            if simkl_data and simkl_data.get('url'):
                caption += f"\n🔗 Simkl: {simkl_data['url']}"
            
            # IMAGE (Priorité Simkl > OMDb)
            poster_url = None
            
            if simkl_data:
                poster = simkl_data.get('poster', '')
                if poster and 'http' in poster:
                    poster_url = f"https://wsrv.nl/?url={poster}"
            
            if not poster_url:
                poster = details.get('poster', '')
                if poster and poster != 'N/A' and 'http' in poster:
                    poster_url = poster
            
            # Envoyer avec photo
            if poster_url:
                try:
                    await query.message.reply_photo(
                        photo=poster_url,
                        caption=caption,
                        parse_mode='Markdown'
                    )
                except:
                    # Si échec image, envoyer texte seul
                    await query.message.reply_text(caption, parse_mode='Markdown', disable_web_page_preview=True)
            else:
                await query.message.reply_text(caption, parse_mode='Markdown', disable_web_page_preview=True)
        except Exception as e:
            await query.message.reply_text(f"❌ {str(e)}")
    
    def run(self):
        print("🤖 Bot unifié démarré!")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🤖 BOT TELEGRAM UNIFIÉ")
    print("="*60)
    
    try:
        bot = UnifiedBot()
        print("\n✅ Configuration OK!")
        print("🚀 Démarrage...\n")
        bot.run()
    except ValueError as e:
        print(f"\n{e}")
        print("\nConfigure .env avec ton token!")
        input("\nEntrée pour quitter...")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        input("\nEntrée pour quitter...")
