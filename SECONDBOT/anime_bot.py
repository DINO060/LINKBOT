"""
🤖 BOT TELEGRAM ANIME - AVEC JIKAN API
======================================
Plus simple et plus puissant que le scraping!

📍 CONFIGURE TON TOKEN ICI 👇
"""

# ⭐⭐⭐ METS TON TOKEN TELEGRAM ICI ⭐⭐⭐
TELEGRAM_TOKEN = "TON_TOKEN_ICI"  # <-- Token de @BotFather
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

# ==========================================
# 🚀 LE CODE DU BOT (Ne touche pas!)
# ==========================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from anime_api import JikanAnimeAPI
import os
import json

class AnimeBot:
    """Bot Telegram utilisant Jikan API"""
    
    def __init__(self, token: str):
        self.token = token
        self.api = JikanAnimeAPI()
        self.app = Application.builder().token(token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Configure les handlers du bot"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("search", self.search_command))
        self.app.add_handler(CommandHandler("anime", self.anime_command))
        self.app.add_handler(CommandHandler("top", self.top_command))
        self.app.add_handler(CommandHandler("user", self.user_command))
        self.app.add_handler(CommandHandler("season", self.season_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /start"""
        welcome = """
🎌 **Bienvenue sur AnimeBot avec Jikan API!**

Je peux te donner des infos sur n'importe quel anime!

**📚 Commandes disponibles:**

🔍 **Recherche:**
/search <nom> - Chercher un anime
/anime <id> - Détails par ID

📊 **Top & Tendances:**
/top - Top animes
/season <année> <saison> - Animes de la saison

👤 **Utilisateurs:**
/user <username> - Liste MAL d'un user

**Ou tape juste le nom d'un anime!**

Propulsé par Jikan API 🚀
        """
        await update.message.reply_text(welcome, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /help"""
        help_text = """
📖 **Guide d'utilisation:**

**🔍 Rechercher:**
/search Naruto
ou simplement: Naruto

**📝 Détails d'un anime:**
/anime 1535

**🏆 Top animes:**
/top
/top 10

**👤 Liste d'un utilisateur:**
/user Xinil

**📅 Animes de la saison:**
/season 2024 winter
/season 2023 summer

**Saisons disponibles:**
winter, spring, summer, fall

**Exemples:**
• /search One Piece
• /anime 5114
• /top 20
• /user Xinil
• /season 2024 winter
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Recherche d'animes"""
        if not context.args:
            await update.message.reply_text("❌ Utilise: /search <nom>\n\nExemple: /search Naruto")
            return
        
        query = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Recherche de '{query}'...")
        
        try:
            results = self.api.search_anime(query, limit=10)
            
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
                message += f"   ⭐ {score} | 📺 {episodes} eps | {anime_type}\n"
                message += f"   🔗 [MyAnimeList]({anime['url']})\n\n"
                
                # Bouton pour détails
                keyboard.append([
                    InlineKeyboardButton(f"{i}. Détails complets", callback_data=f"details_{anime['mal_id']}")
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                message, 
                parse_mode='Markdown', 
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
            # Sauvegarder JSON
            filename = f"search_{query.replace(' ', '_')}.json"
            self.api.save_to_json(results, filename)
            
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ {len(results)} résultats"
                )
            
            os.remove(filename)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def anime_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Détails d'un anime par ID"""
        if not context.args:
            await update.message.reply_text("❌ Utilise: /anime <id>\n\nExemple: /anime 1535")
            return
        
        try:
            anime_id = int(context.args[0])
            await self._send_anime_details(update, anime_id)
        except ValueError:
            await update.message.reply_text("❌ L'ID doit être un nombre!")
    
    async def top_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Top animes"""
        limit = 10
        if context.args and context.args[0].isdigit():
            limit = min(int(context.args[0]), 25)
        
        await update.message.reply_text(f"🏆 Récupération du top {limit} animes...")
        
        try:
            top_animes = self.api.get_top_anime(limit=limit)
            
            if not top_animes:
                await update.message.reply_text("❌ Impossible de récupérer le top!")
                return
            
            message = f"🏆 **Top {limit} Animes:**\n\n"
            
            for anime in top_animes:
                rank = anime['rank']
                title = anime['title']
                score = anime['score']
                episodes = anime['episodes'] or 'N/A'
                
                message += f"**#{rank}. {title}**\n"
                message += f"   ⭐ {score} | 📺 {episodes} eps\n"
                message += f"   🔗 [Voir sur MAL]({anime['url']})\n\n"
            
            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Liste d'un utilisateur MAL"""
        if not context.args:
            await update.message.reply_text("❌ Utilise: /user <username>\n\nExemple: /user Xinil")
            return
        
        username = context.args[0]
        await update.message.reply_text(f"👤 Récupération de la liste de {username}...")
        
        try:
            animelist = self.api.get_user_animelist(username)
            
            if not animelist:
                await update.message.reply_text(f"❌ Utilisateur '{username}' non trouvé ou liste privée!")
                return
            
            # Statistiques
            total = len(animelist)
            watching = sum(1 for a in animelist if a['watching_status'] == 'watching')
            completed = sum(1 for a in animelist if a['watching_status'] == 'completed')
            
            scores = [a['score'] for a in animelist if a['score'] and a['score'] > 0]
            avg_score = sum(scores) / len(scores) if scores else 0
            
            stats = f"""
📊 **Stats de {username}:**

📚 Total: {total} animes
▶️ En cours: {watching}
✅ Complétés: {completed}
⭐ Score moyen: {avg_score:.2f}
            """
            
            await update.message.reply_text(stats, parse_mode='Markdown')
            
            # Sauvegarder et envoyer JSON
            filename = f"{username}_animelist.json"
            self.api.save_to_json(animelist, filename)
            
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ Liste de {username}: {total} animes"
                )
            
            os.remove(filename)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def season_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Animes de la saison"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Utilise: /season <année> <saison>\n\n"
                "Exemple: /season 2024 winter\n"
                "Saisons: winter, spring, summer, fall"
            )
            return
        
        try:
            year = int(context.args[0])
            season = context.args[1].lower()
            
            if season not in ['winter', 'spring', 'summer', 'fall']:
                await update.message.reply_text("❌ Saison invalide! Utilise: winter, spring, summer, fall")
                return
            
            await update.message.reply_text(f"📅 Animes de {season} {year}...")
            
            animes = self.api.get_seasonal_anime(year, season)
            
            if not animes:
                await update.message.reply_text("❌ Aucun anime trouvé pour cette saison!")
                return
            
            message = f"📅 **{season.title()} {year}** ({len(animes)} animes):\n\n"
            
            for i, anime in enumerate(animes[:15], 1):
                title = anime['title']
                score = anime['score'] or 'N/A'
                anime_type = anime['type']
                
                message += f"**{i}. {title}**\n"
                message += f"   ⭐ {score} | {anime_type}\n\n"
                
                if len(message) > 3500:
                    await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
                    message = ""
            
            if message:
                await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except ValueError:
            await update.message.reply_text("❌ Année invalide!")
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler pour texte simple"""
        query = update.message.text
        context.args = query.split()
        await self.search_command(update, context)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler pour boutons"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("details_"):
            anime_id = int(query.data.split("_")[1])
            await self._send_anime_details(query, anime_id)
    
    async def _send_anime_details(self, update_or_query, anime_id: int):
        """Envoie les détails d'un anime"""
        if hasattr(update_or_query, 'callback_query'):
            send_message = update_or_query.callback_query.message.reply_text
        else:
            send_message = update_or_query.message.reply_text
        
        await send_message(f"📝 Récupération des détails de l'anime {anime_id}...")
        
        try:
            details = self.api.get_anime_details(anime_id)
            
            if not details:
                await send_message("❌ Anime non trouvé!")
                return
            
            # Formater le message
            title = details['title']
            title_en = f"\n🌐 {details['title_english']}" if details['title_english'] else ""
            title_jp = f"\n🇯🇵 {details['title_japanese']}" if details['title_japanese'] else ""
            
            score = details['score'] or 'N/A'
            rank = details['rank'] or 'N/A'
            popularity = details['popularity'] or 'N/A'
            members = details['members'] or 'N/A'
            
            anime_type = details['type'] or 'N/A'
            episodes = details['episodes'] or 'N/A'
            status = details['status'] or 'N/A'
            aired = details['aired'] or 'N/A'
            duration = details['duration'] or 'N/A'
            
            studios = ', '.join(details['studios']) if details['studios'] else 'N/A'
            genres = ', '.join(details['genres']) if details['genres'] else 'N/A'
            source = details['source'] or 'N/A'
            rating = details['rating'] or 'N/A'
            
            synopsis = details['synopsis'][:400] + '...' if details['synopsis'] and len(details['synopsis']) > 400 else details['synopsis'] or 'N/A'
            
            message = f"""
🎌 **{title}**{title_en}{title_jp}

⭐ **Score:** {score}
📊 **Ranked:** #{rank}
👥 **Popularity:** #{popularity}
👤 **Members:** {members:,}

📺 **Type:** {anime_type}
🎬 **Episodes:** {episodes}
📡 **Status:** {status}
📅 **Aired:** {aired}
⏱️ **Duration:** {duration}

🎨 **Studios:** {studios}
📖 **Source:** {source}
🏷️ **Genres:** {genres}
🔞 **Rating:** {rating}

📝 **Synopsis:**
{synopsis}

🔗 [Voir sur MyAnimeList]({details['url']})
            """
            
            await send_message(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except Exception as e:
            await send_message(f"❌ Erreur: {str(e)}")
    
    def run(self):
        """Démarre le bot"""
        print("🤖 Bot démarré avec Jikan API!")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


# ==========================================
# 🚀 DÉMARRAGE DU BOT
# ==========================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🤖 BOT TELEGRAM ANIME - JIKAN API")
    print("="*60)
    
    if TELEGRAM_TOKEN == "TON_TOKEN_ICI":
        print("\n⚠️  ERREUR!")
        print("Configure ton token Telegram!")
        print("\n1. Va sur @BotFather sur Telegram")
        print("2. Crée un bot avec /newbot")
        print("3. Copie le token")
        print("4. Ouvre ce fichier et change TELEGRAM_TOKEN")
        print("\nExemple:")
        print('TELEGRAM_TOKEN = "1234567890:ABCdef..."')
        input("\nAppuie sur Entrée pour quitter...")
        exit()
    
    print(f"\n✅ Token configuré!")
    print(f"🚀 Démarrage du bot...\n")
    
    bot = AnimeBot(TELEGRAM_TOKEN)
    bot.run()
