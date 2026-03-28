"""
🤖 BOT TELEGRAM - SCRAPER DE CATALOGUE
=======================================

📍 CONFIGURE TON BOT ICI 👇
"""

# ⭐⭐⭐ CONFIGURATION - CHANGE CES 2 LIGNES ⭐⭐⭐
TELEGRAM_TOKEN = "TON_TOKEN_ICI"  # <-- Token de @BotFather
CATALOGUE_URL = "https://ton-site-catalogue.com"  # <-- URL de ton catalogue
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

# ==========================================
# 🚀 LE CODE DU BOT (Ne touche pas!)
# ==========================================

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import json
import os

def scraper_catalogue(url, mot_cle=None, max_resultats=30):
    """Scrape le catalogue"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        tous_les_liens = soup.find_all('a', href=True)
        
        sites_trouves = []
        urls_vues = set()
        
        for lien in tous_les_liens:
            href = lien.get('href', '')
            texte = lien.get_text(strip=True)
            
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            
            if href.startswith('http'):
                url_complete = href
            elif href.startswith('//'):
                url_complete = 'https:' + href
            else:
                continue
            
            if url_complete in urls_vues:
                continue
            
            urls_vues.add(url_complete)
            
            # Filtrer par mot-clé
            if mot_cle:
                mot_cle_lower = mot_cle.lower()
                if mot_cle_lower not in texte.lower() and mot_cle_lower not in url_complete.lower():
                    parent = lien.parent
                    if parent:
                        if mot_cle_lower not in parent.get_text(strip=True).lower():
                            continue
                    else:
                        continue
            
            # Description
            description = ""
            parent = lien.parent
            if parent:
                for tag in parent.find_all(['p', 'span', 'div'], limit=3):
                    desc_text = tag.get_text(strip=True)
                    if desc_text and len(desc_text) > 20 and desc_text != texte:
                        description = desc_text[:200]
                        break
            
            sites_trouves.append({
                'titre': texte if texte else url_complete,
                'url': url_complete,
                'description': description
            })
            
            if len(sites_trouves) >= max_resultats:
                break
        
        return sites_trouves
        
    except Exception as e:
        print(f"Erreur: {e}")
        return []


# Commandes du bot
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    message = f"""
🌐 **Bot Scraper de Catalogue**

Je peux extraire des sites depuis le catalogue!

**Commandes:**
/search <mot-clé> - Chercher des sites
/all - Voir tous les sites du catalogue
/help - Aide

**Exemples:**
/search gaming
/search streaming
/all

Le catalogue configuré:
🔗 {CATALOGUE_URL}
    """
    await update.message.reply_text(message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help"""
    message = """
📚 **Aide:**

**Rechercher des sites spécifiques:**
/search gaming
/search movies
/search streaming

**Voir tous les sites:**
/all

**Ou envoie juste un mot-clé:**
gaming
movies
    """
    await update.message.reply_text(message, parse_mode='Markdown')


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /search pour chercher"""
    if not context.args:
        await update.message.reply_text("❌ Utilise: /search <mot-clé>\n\nExemple: /search gaming")
        return
    
    mot_cle = ' '.join(context.args)
    await update.message.reply_text(f"🔍 Recherche de '{mot_cle}' dans le catalogue...")
    
    try:
        sites = scraper_catalogue(CATALOGUE_URL, mot_cle, max_resultats=20)
        
        if not sites:
            await update.message.reply_text(f"❌ Aucun site trouvé pour '{mot_cle}'")
            return
        
        # Créer le message
        message = f"🎯 **Résultats pour '{mot_cle}':**\n\n"
        
        for i, site in enumerate(sites[:15], 1):  # Max 15 dans le message
            titre = site['titre'][:50] + '...' if len(site['titre']) > 50 else site['titre']
            message += f"**{i}. {titre}**\n"
            message += f"🔗 {site['url']}\n"
            if site['description']:
                desc = site['description'][:100] + '...' if len(site['description']) > 100 else site['description']
                message += f"📝 {desc}\n"
            message += "\n"
            
            # Split si trop long
            if len(message) > 3500:
                await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
                message = ""
        
        if message:
            await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
        
        # Sauvegarder et envoyer le JSON
        filename = f"sites_{mot_cle.replace(' ', '_')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(sites, f, ensure_ascii=False, indent=2)
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"✅ {len(sites)} sites trouvés"
            )
        
        os.remove(filename)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")


async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /all pour tout extraire"""
    await update.message.reply_text("📋 Extraction de tous les sites du catalogue...")
    
    try:
        sites = scraper_catalogue(CATALOGUE_URL, None, max_resultats=100)
        
        if not sites:
            await update.message.reply_text("❌ Aucun site trouvé!")
            return
        
        # Message résumé
        message = f"📊 **Catalogue complet:**\n\n"
        message += f"✅ {len(sites)} sites extraits\n\n"
        
        # Montrer les 10 premiers
        message += "**Aperçu (10 premiers):**\n\n"
        for i, site in enumerate(sites[:10], 1):
            titre = site['titre'][:40] + '...' if len(site['titre']) > 40 else site['titre']
            message += f"{i}. {titre}\n   🔗 {site['url']}\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
        
        # Envoyer le fichier complet
        filename = "tous_les_sites.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(sites, f, ensure_ascii=False, indent=2)
        
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📦 Catalogue complet: {len(sites)} sites"
            )
        
        os.remove(filename)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur: {str(e)}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pour texte simple (recherche auto)"""
    mot_cle = update.message.text
    context.args = mot_cle.split()
    await search_command(update, context)


# ==========================================
# 🚀 DÉMARRAGE DU BOT
# ==========================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🤖 BOT TELEGRAM - SCRAPER DE CATALOGUE")
    print("="*60)
    
    # Vérifier la configuration
    if TELEGRAM_TOKEN == "TON_TOKEN_ICI":
        print("\n⚠️  ERREUR DE CONFIGURATION!")
        print("\n1. Ouvre ce fichier (bot_simple.py)")
        print("2. Change TELEGRAM_TOKEN avec ton token de @BotFather")
        print("3. Change CATALOGUE_URL avec ton site catalogue")
        print("\nExemple:")
        print('TELEGRAM_TOKEN = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"')
        print('CATALOGUE_URL = "https://example.com/sites"')
        input("\nAppuie sur Entrée pour quitter...")
        exit()
    
    if CATALOGUE_URL == "https://ton-site-catalogue.com":
        print("\n⚠️  ATTENTION!")
        print("Tu dois configurer l'URL de ton catalogue!")
        print('Change CATALOGUE_URL = "https://ton-site-catalogue.com"')
        input("\nAppuie sur Entrée pour quitter...")
        exit()
    
    # Créer et lancer le bot
    print(f"\n✅ Configuration OK!")
    print(f"📱 Token: {TELEGRAM_TOKEN[:20]}...")
    print(f"🌐 Catalogue: {CATALOGUE_URL}")
    print("\n🚀 Démarrage du bot...")
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Ajouter les handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("all", all_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    print("✅ Bot prêt! Attente de messages...")
    print("\nVa sur Telegram et parle à ton bot!")
    print("Utilise /start pour commencer\n")
    
    # Lancer le bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)
