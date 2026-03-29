import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from anime_scraper import AnimeScraper
from directory_scraper import DirectoryScraper
import json

class AnimeBot:
    """Bot Telegram pour scraper et envoyer des infos d'animes"""
    
    def __init__(self, token: str):
        self.token = token
        self.scraper = AnimeScraper()
        self.directory_scraper = DirectoryScraper()
        self.app = Application.builder().token(token).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Configure les handlers du bot"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("search", self.search_command))
        self.app.add_handler(CommandHandler("user", self.user_command))
        self.app.add_handler(CommandHandler("directory", self.directory_command))
        self.app.add_handler(CommandHandler("findsites", self.findsites_command))
        self.app.add_handler(CommandHandler("details", self.details_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /start"""
        welcome_text = """
🎌 **Bienvenue sur AnimeBot!**

Je peux t'aider à récupérer des infos sur les animes depuis MyAnimeList!

**Commandes disponibles:**
/search <nom> - Rechercher un anime
/user <username> - Obtenir la liste d'un utilisateur MAL
/details <id> - Détails d'un anime spécifique
/directory <url> <keyword> - Chercher des sites dans un annuaire
/findsites <url> - Extraire tous les sites d'un annuaire
/help - Afficher l'aide

Envoie-moi juste le nom d'un anime pour commencer!
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /help"""
        help_text = """
📚 **Guide d'utilisation:**

**🔍 Rechercher un anime:**
/search Naruto
ou simplement: Naruto

**👤 Liste d'un utilisateur MAL:**
/user username

**📝 Détails d'un anime:**
/details 1535

**🌐 Chercher dans un annuaire de sites:**
/directory <url> <mot-clé>
Exemple: /directory https://example.com gaming

**📋 Extraire tous les sites d'un annuaire:**
/findsites <url>
Exemple: /findsites https://example.com

**Exemples:**
• /search One Piece
• /user Xinil
• /details 5114
• /directory https://example.com movies

Le bot va scraper les infos et te les envoyer!
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /search pour rechercher des animes"""
        if not context.args:
            await update.message.reply_text("❌ Utilise: /search <nom de l'anime>")
            return
        
        query = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Recherche de '{query}'...")
        
        try:
            results = self.scraper.search_anime(query, limit=10)
            
            if not results:
                await update.message.reply_text("❌ Aucun résultat trouvé!")
                return
            
            # Créer le message avec les résultats
            message = f"🎌 **Résultats pour '{query}':**\n\n"
            keyboard = []
            
            for i, anime in enumerate(results, 1):
                title = anime['title']
                score = anime['score'] or 'N/A'
                episodes = anime['episodes'] or 'N/A'
                anime_type = anime['type'] or 'N/A'
                
                message += f"**{i}. {title}**\n"
                message += f"   📊 Score: {score} | 📺 {episodes} eps | Type: {anime_type}\n"
                message += f"   🔗 {anime['url']}\n\n"
                
                # Ajouter bouton pour plus de détails
                if anime['mal_id']:
                    keyboard.append([
                        InlineKeyboardButton(f"{i}. Plus de détails", callback_data=f"details_{anime['mal_id']}")
                    ])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup, disable_web_page_preview=True)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /user pour récupérer la liste d'un utilisateur"""
        if not context.args:
            await update.message.reply_text("❌ Utilise: /user <username>")
            return
        
        username = context.args[0]
        await update.message.reply_text(f"👤 Récupération de la liste de {username}...")
        
        try:
            animes = self.scraper.scrape_myanimelist_user(username)
            
            if not animes:
                await update.message.reply_text(f"❌ Impossible de récupérer la liste de {username}")
                return
            
            # Sauvegarder en JSON
            filename = f"{username}_animelist.json"
            self.scraper.save_to_json(animes, filename)
            
            # Envoyer le fichier
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ Liste de {username}: {len(animes)} animes"
                )
            
            # Envoyer un résumé
            stats_text = self._get_user_stats(animes)
            await update.message.reply_text(stats_text, parse_mode='Markdown')
            
            # Supprimer le fichier temporaire
            os.remove(filename)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def details_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /details pour obtenir les détails d'un anime"""
        if not context.args:
            await update.message.reply_text("❌ Utilise: /details <mal_id>")
            return

        try:
            mal_id = int(context.args[0])
            await self._send_anime_details(update, mal_id)
        except ValueError:
            await update.message.reply_text("❌ L'ID doit être un nombre!")

    async def directory_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /directory pour chercher dans un site d'annuaire"""
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Utilise: /directory <url> <mot-clé>\n\n"
                "Exemple: /directory https://example.com gaming"
            )
            return
        
        directory_url = context.args[0]
        keyword = ' '.join(context.args[1:])
        
        await update.message.reply_text(f"🔍 Recherche de '{keyword}' dans l'annuaire...")
        
        try:
            results = self.directory_scraper.search_in_directory(directory_url, keyword, max_results=15)
            
            if not results:
                await update.message.reply_text("❌ Aucun site trouvé!")
                return
            
            # Créer le message avec les résultats
            message = f"🌐 **Sites trouvés pour '{keyword}':**\n\n"
            
            for i, site in enumerate(results, 1):
                title = site.get('title', 'Sans titre')
                url = site.get('url', '')
                description = site.get('description', '')
                
                message += f"**{i}. {title}**\n"
                message += f"🔗 {url}\n"
                
                if description:
                    desc_short = description[:150] + '...' if len(description) > 150 else description
                    message += f"📝 {desc_short}\n"
                
                message += "\n"
                
                # Split en plusieurs messages si trop long
                if len(message) > 3500:
                    await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
                    message = ""
            
            if message:
                await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
            # Sauvegarder en JSON et envoyer
            filename = f"sites_{keyword.replace(' ', '_')}.json"
            self.directory_scraper.save_results(results, filename)
            
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ {len(results)} sites trouvés"
                )
            
            os.remove(filename)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def findsites_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Commande /findsites pour extraire tous les sites d'un annuaire"""
        if not context.args:
            await update.message.reply_text(
                "❌ Utilise: /findsites <url>\n\n"
                "Exemple: /findsites https://example.com"
            )
            return
        
        directory_url = context.args[0]
        
        await update.message.reply_text(f"📋 Extraction de tous les sites de l'annuaire...")
        
        try:
            # Extraire tous les sites
            sites = self.directory_scraper.scrape_directory_site(directory_url)
            
            if not sites:
                await update.message.reply_text("❌ Aucun site trouvé!")
                return
            
            # Organiser par catégories si possible
            categorized = self.directory_scraper.scrape_with_categories(directory_url)
            
            if categorized:
                message = f"🗂️ **Sites par catégorie:**\n\n"
                
                for category, category_sites in list(categorized.items())[:5]:  # Limiter à 5 catégories
                    message += f"**📁 {category}** ({len(category_sites)} sites)\n"
                    
                    for site in category_sites[:3]:  # 3 premiers de chaque catégorie
                        message += f"  • [{site['title']}]({site['url']})\n"
                    
                    if len(category_sites) > 3:
                        message += f"  ... et {len(category_sites) - 3} autres\n"
                    
                    message += "\n"
                
                await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
            
            # Sauvegarder et envoyer le fichier complet
            filename = "all_sites.json"
            self.directory_scraper.save_results(sites, filename)
            
            with open(filename, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"✅ {len(sites)} sites extraits de l'annuaire"
                )
            
            os.remove(filename)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Erreur: {str(e)}")
    
    async def text_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler pour les messages texte (recherche automatique)"""
        query = update.message.text
        context.args = query.split()
        await self.search_command(update, context)
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler pour les boutons inline"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("details_"):
            mal_id = int(query.data.split("_")[1])
            await self._send_anime_details(query, mal_id)
    
    async def _send_anime_details(self, update_or_query, mal_id: int):
        """Envoie les détails complets d'un anime"""
        # Déterminer si c'est un message ou un callback
        if hasattr(update_or_query, 'callback_query'):
            send_message = update_or_query.callback_query.message.reply_text
        else:
            send_message = update_or_query.message.reply_text
        
        await send_message(f"📝 Récupération des détails...")
        
        try:
            details = self.scraper.scrape_anime_details(mal_id)
            
            if not details:
                await send_message("❌ Impossible de récupérer les détails!")
                return
            
            message = self._format_anime_details(details)
            await send_message(message, parse_mode='Markdown', disable_web_page_preview=True)
            
        except Exception as e:
            await send_message(f"❌ Erreur: {str(e)}")
    
    def _format_anime_details(self, details: dict) -> str:
        """Formate les détails d'un anime pour l'affichage"""
        title = details.get('title', 'N/A')
        title_en = details.get('title_english', 'N/A')
        score = details.get('score', 'N/A')
        ranked = details.get('ranked', 'N/A')
        popularity = details.get('popularity', 'N/A')
        anime_type = details.get('type', 'N/A')
        episodes = details.get('episodes', 'N/A')
        status = details.get('status', 'N/A')
        aired = details.get('aired', 'N/A')
        studios = details.get('studios', 'N/A')
        source = details.get('source', 'N/A')
        genres = ', '.join(details.get('genres', []))
        duration = details.get('duration', 'N/A')
        rating = details.get('rating', 'N/A')
        synopsis = details.get('synopsis', 'N/A')
        url = details.get('url', '')
        
        message = f"""
🎌 **{title}**
🌐 {title_en}

⭐ **Score:** {score}
📊 **Ranked:** {ranked}
👥 **Popularity:** {popularity}

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
{synopsis[:500]}{'...' if len(synopsis) > 500 else ''}

🔗 {url}
        """
        
        return message
    
    def _get_user_stats(self, animes: list) -> str:
        """Génère des statistiques sur la liste d'animes"""
        total = len(animes)
        completed = sum(1 for a in animes if a.get('status') == 'Completed')
        watching = sum(1 for a in animes if a.get('status') == 'Watching')
        
        scores = [a.get('score', 0) for a in animes if a.get('score', 0) > 0]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        stats = f"""
📊 **Statistiques:**

📚 Total: {total} animes
✅ Complétés: {completed}
▶️ En cours: {watching}
⭐ Score moyen: {avg_score:.2f}
        """
        
        return stats
    
    def run(self):
        """Démarre le bot"""
        print("🤖 Bot démarré!")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # REMPLACE PAR TON TOKEN TELEGRAM BOT
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
    
    if TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("❌ Configure ton token Telegram dans le fichier!")
        print("Va sur @BotFather sur Telegram pour créer un bot et obtenir un token")
    else:
        bot = AnimeBot(TOKEN)
        bot.run()
