"""
🤖 BOT TELEGRAM UNIFIÉ - SITES + ANIMES
========================================
Un bot avec 2 fonctionnalités:
1. 🌐 Chercher des sites dans un catalogue
2. 🎌 Infos sur les animes/manga

Configure tes tokens dans le fichier .env
"""

import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from anime_api import JikanAnimeAPI
from anilist_api import AniListAPI
from directory_scraper import DirectoryScraper

# Charger les variables d'environnement
load_dotenv()

class UnifiedBot:
    """Bot unifié avec menu de sélection"""
    
    def __init__(self):
        # Tokens
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.catalogue_url = os.getenv('CATALOGUE_URL', '')
        
        if not self.token or self.token == 'TON_TOKEN_TELEGRAM_ICI':
            raise ValueError(
                "❌ Token Telegram non configuré!\n"
                "Ouvre le fichier .env et configure TELEGRAM_BOT_TOKEN"
            )
        
        # Initialiser les APIs
        self.anime_api = JikanAnimeAPI()
        self.anilist_api = AniListAPI()
        self.directory_scraper = DirectoryScraper()
        
        # Mode de l'utilisateur (pour savoir quel scraper utiliser)
        self.user_modes = {}
        
        self.app = Application.builder().token(self.token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Configure les handlers du bot"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("menu", self.menu_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))
    
    def _get_main_menu_keyboard(self):
        """Crée le clavier du menu principal"""
        keyboard = [
            [InlineKeyboardButton("🌐 Chercher des Sites", callback_data="mode_sites")],
            [
                InlineKeyboardButton("🎌 Anime/Manga (MAL)", callback_data="mode_anime"),
                InlineKeyboardButton("📚 Manhwa/Manhua", callback_data="mode_manhwa")
            ],
            [InlineKeyboardButton("❓ Aide", callback_data="help")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /start avec menu"""
        welcome = """
🤖 **Bienvenue sur le Bot Unifié!**

Choisis ce que tu veux faire:

🌐 **Chercher des Sites**
Trouve des sites dans un catalogue/annuaire
Anime/Manga (MAL)**
Base MyAnimeList - Animes et Mangas japonais

📚 **Manhwa/Manhua**
Base AniList - Manhwa (KR 🇰🇷), Manhua (CN 🇨🇳), + tout le reste!
Recherche d'animes, top animes, listes utilisateurs

**Clique sur un bouton pour commencer!**
        """
        await update.message.reply_text(
            welcome,
            parse_mode='Markdown',
            reply_markup=self._get_main_menu_keyboard()
        )
    
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /menu pour revenir au menu"""
        user_id = update.effective_user.id
        self.user_modes.pop(user_id, None)
        
        await update.message.reply_text(
            "🏠 **Menu Principal**\n\nQue veux-tu faire?",
            parse_mode='Markdown',
            reply_markup=self._get_main_menu_keyboard()
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /help"""
        help_text = """
📖 **Guide d'utilisation:**

**🌐 MODE SITES:**
Active ce mode puis tape un mot-clé pour chercher des sites.
Exemple: "gaming", "movies", "streaming"

**🎌 MODE ANIME:**
Active ce mode puis:
• Tape le nom d'un anime pour le chercher
• Commandes spéciales:
  - `top` ou `top 10` - Top animes
  - `user username` - Liste d'un utilisateur MAL
  - `season 2024 winter` - Animes de la saison

**📍 Commandes:**
/start - Menu principal
/menu - Retour au menu
/help - Cette aide

**Navigation:**
Utilise les boutons pour changer de mode!
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler pour les boutons"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        data = query.data
        
        # Menu principal
        if data == "mode_sites":
            self.user_modes[user_id] = "sites"
            catalogue_info = f"\n📍 Catalogue: {self.catalogue_url}" if self.catalogue_url else "\n⚠️ Configure CATALOGUE_URL dans .env"
            await query.message.reply_text(
                f"🌐 **Mode Sites activé!**{catalogue_info}\n\n"
                "Tape un mot-clé pour chercher des sites.\n"
                "Exemple: gaming, movies, streaming\n\n"
                "💡 /menu pour revenir au menu"
            )
        elif data == "mode_anime":
            self.user_modes[user_id] = "anime"
            await query.message.reply_text(
                f"🎌 **Mode Anime/Manga (MAL) activé!**\n\n"
                "Base: MyAnimeList\n\n"
                "Tape le nom d'un anime/manga pour le chercher.\n"
                "Ou utilise:\n"
                "• `top` - Top animes\n"
                "• `top 10` - Top 10\n"
                "• `user username` - Liste MAL\n"
                "• `season 2024 winter` - Saison\n\n"
                "💡 /menu pour revenir au menu"
            )
        
        elif data == "mode_manhwa":
            self.user_modes[user_id] = "manhwa"
            await query.message.reply_text(
                "📚 **Mode Manhwa/Manhua (AniList) activé!**\n\n"
                "Base: AniList - Tu peux chercher:\n"
                "• Manhwa coréen 🇰🇷 (Solo Leveling, Tower of God...)\n"
                "• Manhua chinois 🇨🇳\n"
                "• Anime et Manga aussi!\n\n"
                "Commandes:\n"
                "• `trending` - Tendances actuelles\n"
                "• `manhwa <nom>` - Cherche spécifiquement un manhwa KR\n"
                "• Ou tape juste un nom!\n\n"
                "💡 /menu pour revenir au menu",
                parse_mode='Markdown'
            )

        elif data == "help":
            await self.help_command(query, context)

        # Détails d'un anime (MAL)
        elif data.startswith("details_"):
            anime_id = int(data.split("_")[1])
            await self._send_anime_details(query, anime_id)

        # Détails d'un média (AniList)
        elif data.startswith("anilist_"):
            media_id = int(data.split("_")[1])
            await self._send_anilist_details(query, media_id)
        
        # Retour au menu
        elif data == "back_menu":
            self.user_modes.pop(user_id, None)
            await query.message.reply_text(
                "🏠 **Menu Principal**",
                reply_markup=self._get_main_menu_keyboard()
            )
    
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler pour les messages texte"""
        user_id = update.effective_user.id
        text = update.message.text.strip()

        # Vérifier le mode de l'utilisateur
        mode = self.user_modes.get(user_id)

        if not mode:
            await update.message.reply_text(
                "👋 Choisis d'abord un mode!\n\n"
                "Utilise /start pour voir le menu",
                reply_markup=self._get_main_menu_keyboard()
            )
            return

        # Mode Sites
        if mode == "sites":
            await self._handle_sites_search(update, text)

        # Mode Anime
        elif mode == "anime":
            await self._handle_anime_search(update, text)

        # Mode Manhwa/AniList
        elif mode == "manhwa":
            await self._handle_manhwa_search(update, text)
    
    async def _handle_sites_search(self, update: Update, keyword: str):
        """Recherche de sites dans le catalogue"""
        if not self.catalogue_url or self.catalogue_url == 'https://ton-site-catalogue.com':
            await update.message.reply_text(
                "⚠️ **Catalogue non configuré!**\n\n"
                "Ouvre le fichier .env et configure:\n"
                "CATALOGUE_URL=https://ton-site.com"
            )
            return
        
        await update.message.reply_text(f"🔍 Recherche de '{keyword}' dans le catalogue...")
        
        try:
            results = self.directory_scraper.search_in_directory(
                self.catalogue_url, 
                keyword, 
                max_results=15
            )
            
            if not results:
                await update.message.reply_text(
                    f"❌ Aucun site trouvé pour '{keyword}'\n\n"
                    "💡 Essaye un autre mot-clé"
                )
                return
            
            # Créer le message sans Markdown pour éviter les erreurs de parsing
            message = f"🎯 {len(results)} sites trouvés pour '{keyword}':\n\n"
            
            for i, site in enumerate(results[:10], 1):
                title = site.get('title', 'Sans titre')[:60]
                url = site.get('url', '')
                description = site.get('description', '')
                
                message += f"{i}. {title}\n"
                message += f"🔗 {url}\n"
                
                if description:
                    # Nettoyer la description des caractères problématiques
                    desc_clean = description.replace('*', '').replace('_', '').replace('[', '').replace(']', '')
                    desc_short = desc_clean[:100] + '...' if len(desc_clean) > 100 else desc_clean
                    message += f"📝 {desc_short}\n"
                
                message += "\n"
                
                # Split si trop long
                if len(message) > 3800:
                    await update.message.reply_text(message, disable_web_page_preview=True)
                    message = ""
            
            if message:
                await update.message.reply_text(message, disable_web_page_preview=True)
            
            if len(results) > 10:
                await update.message.reply_text(f"... et {len(results) - 10} autres sites trouvés!")
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _handle_anime_search(self, update: Update, text: str):
        """Recherche d'anime ou commandes spéciales"""
        parts = text.lower().split()
        
        # Commande top
        if parts[0] == "top":
            limit = 10
            if len(parts) > 1 and parts[1].isdigit():
                limit = min(int(parts[1]), 25)
            await self._show_top_anime(update, limit)
        
        # Commande user
        elif parts[0] == "user" and len(parts) > 1:
            username = parts[1]
            await self._show_user_list(update, username)
        
        # Commande season
        elif parts[0] == "season" and len(parts) >= 3:
            try:
                year = int(parts[1])
                season = parts[2]
                await self._show_seasonal_anime(update, year, season)
            except:
                await update.message.reply_text("❌ Format: season 2024 winter")
        
        # Recherche d'anime
        else:
            await self._search_anime(update, text)
    
    async def _search_anime(self, update: Update, query: str):
        """Recherche d'anime"""
        await update.message.reply_text(f"🔍 Recherche de '{query}'...")
        
        try:
            results = self.anime_api.search_anime(query, limit=10)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun anime trouvé pour '{query}'")
                return
            
            message = f"🎯 **Résultats pour '{query}':**\n\n"
            keyboard = []
            
            for i, anime in enumerate(results, 1):
                title = anime['title']
                title_en = f" ({anime['title_english']})" if anime['title_english'] else ""
                score = anime['score'] or 'N/A'
                episodes = anime['episodes'] or 'N/A'
                anime_type = anime['type'] or 'N/A'
                
                message += f"**{i}. {title}**{title_en}\n"
                message += f"   ⭐ {score} | 📺 {episodes} eps | {anime_type}\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"{i}. Plus de détails", callback_data=f"details_{anime['mal_id']}")
                ])
            
            # Limiter à 8 boutons
            keyboard = keyboard[:8]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message, 
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _show_top_anime(self, update: Update, limit: int):
        """Affiche le top anime"""
        await update.message.reply_text(f"🏆 Top {limit} animes...")
        
        try:
            top_animes = self.anime_api.get_top_anime(limit=limit)
            
            if not top_animes:
                await update.message.reply_text("❌ Impossible de récupérer le top!")
                return
            
            message = f"🏆 **Top {limit} Animes:**\n\n"
            
            for anime in top_animes:
                rank = anime['rank']
                title = anime['title']
                score = anime['score']
                
                message += f"**#{rank}. {title}**\n"
                message += f"   ⭐ {score}\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _show_user_list(self, update: Update, username: str):
        """Affiche la liste d'un utilisateur"""
        await update.message.reply_text(f"👤 Liste de {username}...")
        
        try:
            animelist = self.anime_api.get_user_animelist(username)
            
            if not animelist:
                await update.message.reply_text(f"❌ Utilisateur '{username}' non trouvé!")
                return
            
            total = len(animelist)
            watching = sum(1 for a in animelist if a['watching_status'] == 'watching')
            completed = sum(1 for a in animelist if a['watching_status'] == 'completed')
            
            scores = [a['score'] for a in animelist if a['score'] and a['score'] > 0]
            avg_score = sum(scores) / len(scores) if scores else 0
            
            message = f"""
📊 **Stats de {username}:**

📚 Total: {total} animes
▶️ En cours: {watching}
✅ Complétés: {completed}
⭐ Score moyen: {avg_score:.2f}

**Derniers ajouts:**
"""
            
            # Montrer les 5 derniers
            for i, anime in enumerate(animelist[:5], 1):
                title = anime['title'][:40]
                status = anime['watching_status']
                message += f"{i}. {title} ({status})\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _show_seasonal_anime(self, update: Update, year: int, season: str):
        """Affiche les animes de la saison"""
        if season not in ['winter', 'spring', 'summer', 'fall']:
            await update.message.reply_text("❌ Saison invalide! Utilise: winter, spring, summer, fall")
            return
        
        await update.message.reply_text(f"📅 {season.title()} {year}...")
        
        try:
            animes = self.anime_api.get_seasonal_anime(year, season)

            if not animes:
                await update.message.reply_text("❌ Aucun anime trouvé!")
                return

            message = f"📅 **{season.title()} {year}** ({len(animes)} animes):\n\n"

            for i, anime in enumerate(animes[:15], 1):
                title = anime['title'][:50]
                score = anime['score'] or 'N/A'
                message += f"**{i}. {title}**\n"
                message += f"   ⭐ {score}\n\n"
                if len(message) > 3800:
                    await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
                    message = ""

            if message:
                await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)

        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")

    async def _handle_manhwa_search(self, update: Update, text: str):
        """Recherche de manhwa/manga sur AniList"""
        parts = text.lower().split()

        if parts[0] == "trending":
            await self._show_anilist_trending(update)
        elif parts[0] == "manhwa" and len(parts) > 1:
            query = ' '.join(parts[1:])
            await self._search_anilist_manhwa(update, query)
        else:
            await self._search_anilist(update, text)
    
    async def _search_anilist(self, update: Update, query: str):
        """Recherche générale sur AniList"""
        await update.message.reply_text(f"🔍 Recherche de '{query}' sur AniList...")
        
        try:
            results = self.anilist_api.search_media(query, limit=10)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun résultat pour '{query}'")
                return
            
            message = f"🎯 **Résultats pour '{query}':**\n\n"
            keyboard = []
            
            for i, media in enumerate(results[:8], 1):
                title = media['title']
                title_en = f" ({media['title_english']})" if media['title_english'] else ""
                score = media['score'] or 'N/A'
                media_type = media['type']  # ANIME ou MANGA
                format_type = media['format']  # TV, MANGA, MANHWA, etc.
                country = media['country']  # JP, KR, CN
                
                country_flag = {"JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳"}.get(country, "🌐")
                
                message += f"**{i}. {title}**{title_en}\n"
                message += f"   ⭐ {score} | {country_flag} {format_type}"
                
                if media_type == "ANIME":
                    eps = media['episodes'] or '?'
                    message += f" | 📺 {eps} eps"
                else:
                    chaps = media['chapters'] or '?'
                    message += f" | 📖 {chaps} ch"
                
                message += "\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"{i}. Détails", callback_data=f"anilist_{media['id']}")
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _search_anilist_manhwa(self, update: Update, query: str):
        """Recherche spécifique de manhwa coréens"""
        await update.message.reply_text(f"🇰🇷 Recherche de manhwa: '{query}'...")
        
        try:
            results = self.anilist_api.search_manhwa(query, limit=10)
            
            if not results:
                await update.message.reply_text(f"❌ Aucun manhwa trouvé pour '{query}'")
                return
            
            message = f"🇰🇷 **Manhwa trouvés pour '{query}':**\n\n"
            keyboard = []
            
            for i, manhwa in enumerate(results[:8], 1):
                title = manhwa['title']
                title_en = f" ({manhwa['title_english']})" if manhwa['title_english'] else ""
                score = manhwa['score'] or 'N/A'
                chapters = manhwa['chapters'] or '?'
                
                message += f"**{i}. {title}**{title_en}\n"
                message += f"   ⭐ {score} | 📖 {chapters} chapitres\n\n"
                
                keyboard.append([
                    InlineKeyboardButton(f"{i}. Détails", callback_data=f"anilist_{manhwa['id']}")
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _show_anilist_trending(self, update: Update):
        """Affiche les tendances AniList"""
        await update.message.reply_text("🔥 Tendances actuelles...")
        
        try:
            trending = self.anilist_api.get_trending(limit=10)
            
            if not trending:
                await update.message.reply_text("❌ Impossible de récupérer les tendances!")
                return
            
            message = "🔥 **Top Trending:**\n\n"
            
            for i, media in enumerate(trending, 1):
                title = media['title']
                score = media['score'] or 'N/A'
                media_type = media['type']
                country = media['country']
                
                country_flag = {"JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳"}.get(country, "🌐")
                
                message += f"**{i}. {title}**\n"
                message += f"   ⭐ {score} | {country_flag} {media_type}\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _send_anilist_details(self, query, media_id: int):
        """Envoie les détails d'un média AniList"""
        await query.message.reply_text(f"📝 Détails du média {media_id}...")
        
        try:
            details = self.anilist_api.get_media_details(media_id)
            
            if not details:
                await query.message.reply_text("❌ Média non trouvé!")
                return
            
            title = details['title']
            title_en = f"\n🌐 {details['title_english']}" if details['title_english'] else ""
            title_native = f"\n📝 {details['title_native']}" if details['title_native'] else ""
            
            score = details['score'] or 'N/A'
            popularity = details['popularity'] or 'N/A'
            favourites = details['favourites'] or 'N/A'
            
            media_type = details['type']
            format_type = details['format']
            status = details['status'] or 'N/A'
            country = details['country'] or '?'
            
            country_flag = {"JP": "🇯🇵", "KR": "🇰🇷", "CN": "🇨🇳"}.get(country, "🌐")
            
            genres = ', '.join(details['genres'][:5]) if details['genres'] else 'N/A'
            studios = ', '.join(details['studios'][:3]) if details['studios'] else 'N/A'
            
            description = details['description']
            if description:
                # Nettoyer le HTML
                description = description.replace('<br>', '\n').replace('<i>', '').replace('</i>', '')
                description = description[:350] + '...' if len(description) > 350 else description
            else:
                description = 'N/A'
            
            message = f"""
📚 **{title}**{title_en}{title_native}

⭐ Score: {score} | {country_flag} {country}
👥 Popularity: {popularity:,} | ❤️ {favourites:,}

📺 Type: {media_type} - {format_type}
📡 Status: {status}
"""
            
            if media_type == "ANIME":
                eps = details['episodes'] or '?'
                duration = details['duration'] or '?'
                message += f"🎬 Episodes: {eps} | ⏱️ {duration} min\n"
            else:
                chaps = details['chapters'] or '?'
                vols = details['volumes'] or '?'
                message += f"📖 Chapitres: {chaps} | 📚 Volumes: {vols}\n"
            
            message += f"""
🎨 Studios: {studios}
🏷️ Genres: {genres}

📝 {description}

🔗 [Voir sur AniList]({details['url']})
            """
            
            await query.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except Exception as e:
            await query.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def _send_anime_details(self, query, anime_id: int):
        """Envoie les détails d'un anime"""
        await query.message.reply_text(f"📝 Détails de l'anime {anime_id}...")
        
        try:
            details = self.anime_api.get_anime_details(anime_id)
            
            if not details:
                await query.message.reply_text("❌ Anime non trouvé!")
                return
            
            title = details['title']
            title_en = f"\n🌐 {details['title_english']}" if details['title_english'] else ""
            
            score = details['score'] or 'N/A'
            rank = details['rank'] or 'N/A'
            popularity = details['popularity'] or 'N/A'
            
            anime_type = details['type'] or 'N/A'
            episodes = details['episodes'] or 'N/A'
            status = details['status'] or 'N/A'
            
            studios = ', '.join(details['studios'][:3]) if details['studios'] else 'N/A'
            genres = ', '.join(details['genres'][:5]) if details['genres'] else 'N/A'
            
            synopsis = details['synopsis'][:300] + '...' if details['synopsis'] and len(details['synopsis']) > 300 else details['synopsis'] or 'N/A'
            
            message = f"""
🎌 **{title}**{title_en}

⭐ Score: {score} | 📊 Ranked: #{rank}
👥 Popularity: #{popularity}

📺 {anime_type} | 🎬 {episodes} eps
📡 Status: {status}

🎨 Studios: {studios}
🏷️ Genres: {genres}

📝 {synopsis}

🔗 [Voir sur MyAnimeList]({details['url']})
            """
            
            await query.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except Exception as e:
            await query.message.reply_text(f"❌ Erreur: {str(e)}")
    
    def run(self):
        """Démarre le bot"""
        print("🤖 Bot unifié démarré!")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


# ==========================================
# 🚀 DÉMARRAGE
# ==========================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🤖 BOT TELEGRAM UNIFIÉ - SITES + ANIMES")
    print("="*60)
    
    try:
        bot = UnifiedBot()
        print(f"\n✅ Configuration chargée!")
        print(f"🚀 Démarrage du bot...\n")
        bot.run()
    except ValueError as e:
        print(f"\n{e}")
        print("\n📝 Configure le fichier .env avec ton token!")
        input("\nAppuie sur Entrée pour quitter...")
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        input("\nAppuie sur Entrée pour quitter...")
