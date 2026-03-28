"""
🌐 SCRAPER DE CATALOGUE - VERSION SIMPLE
==========================================

📍 METS TON LIEN ICI EN BAS 👇
"""

# ⭐⭐⭐ CONFIGURE TON SITE CATALOGUE ICI ⭐⭐⭐
CATALOGUE_URL = "https://ton-site-catalogue.com"  # <-- CHANGE CETTE LIGNE!
# ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐

# Tu peux aussi chercher un mot-clé spécifique (optionnel)
MOT_CLE = ""  # Laisse vide pour tout extraire, ou mets un mot comme "gaming"

# Nombre maximum de résultats
MAX_RESULTATS = 50

# ==========================================
# 🚀 LE CODE COMMENCE ICI (Ne touche pas!)
# ==========================================

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os

def scraper_catalogue(url, mot_cle=None, max_resultats=50):
    """
    Scrape le site catalogue et extrait tous les sites
    """
    print(f"\n🔍 Visite de: {url}")
    print(f"🎯 Recherche: {mot_cle if mot_cle else 'Tous les sites'}")
    print("⏳ Scraping en cours...\n")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        # Récupérer la page
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"❌ Erreur: Code {response.status_code}")
            return []
        
        print("✅ Page récupérée avec succès!")
        
        # Parser le HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extraire tous les liens
        tous_les_liens = soup.find_all('a', href=True)
        print(f"📊 {len(tous_les_liens)} liens trouvés au total")
        
        sites_trouves = []
        urls_vues = set()
        
        for lien in tous_les_liens:
            href = lien.get('href', '')
            texte = lien.get_text(strip=True)
            
            # Ignorer les liens vides, internes, ou en double
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
            
            # Convertir en URL complète
            if href.startswith('http'):
                url_complete = href
            elif href.startswith('//'):
                url_complete = 'https:' + href
            else:
                # Lien relatif, on ignore
                continue
            
            # Éviter les doublons
            if url_complete in urls_vues:
                continue
            
            urls_vues.add(url_complete)
            
            # Si mot-clé spécifié, filtrer
            if mot_cle:
                mot_cle_lower = mot_cle.lower()
                texte_lower = texte.lower()
                url_lower = url_complete.lower()
                
                # Chercher dans le texte, l'URL, et le contexte
                if mot_cle_lower not in texte_lower and mot_cle_lower not in url_lower:
                    # Chercher dans le parent aussi
                    parent = lien.parent
                    if parent:
                        contexte = parent.get_text(strip=True).lower()
                        if mot_cle_lower not in contexte:
                            continue
                    else:
                        continue
            
            # Extraire la description si disponible
            description = ""
            parent = lien.parent
            if parent:
                # Chercher une description dans les éléments proches
                for tag in parent.find_all(['p', 'span', 'div'], limit=3):
                    desc_text = tag.get_text(strip=True)
                    if desc_text and len(desc_text) > 20 and desc_text != texte:
                        description = desc_text[:300]
                        break
            
            # Trouver la catégorie si possible
            categorie = ""
            for header in soup.find_all(['h1', 'h2', 'h3', 'h4']):
                if lien in header.find_all('a') or any(lien in elem.find_all('a') for elem in header.find_all()):
                    categorie = header.get_text(strip=True)
                    break
            
            # Ajouter le site à la liste
            site_info = {
                'numero': len(sites_trouves) + 1,
                'titre': texte if texte else url_complete,
                'url': url_complete,
                'description': description,
                'categorie': categorie,
                'date_extraction': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            sites_trouves.append(site_info)
            
            # Limiter les résultats
            if len(sites_trouves) >= max_resultats:
                break
        
        return sites_trouves
        
    except Exception as e:
        print(f"❌ Erreur lors du scraping: {e}")
        return []


def afficher_resultats(sites):
    """
    Affiche les résultats dans la console
    """
    print(f"\n{'='*60}")
    print(f"🎉 RÉSULTATS: {len(sites)} sites trouvés!")
    print(f"{'='*60}\n")
    
    for site in sites:
        print(f"📌 {site['numero']}. {site['titre']}")
        print(f"   🔗 {site['url']}")
        
        if site['categorie']:
            print(f"   📁 Catégorie: {site['categorie']}")
        
        if site['description']:
            desc = site['description'][:150] + '...' if len(site['description']) > 150 else site['description']
            print(f"   📝 {desc}")
        
        print()


def sauvegarder_json(sites, nom_fichier="resultats_catalogue.json"):
    """
    Sauvegarde les résultats en JSON
    """
    with open(nom_fichier, 'w', encoding='utf-8') as f:
        json.dump(sites, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Résultats sauvegardés dans: {nom_fichier}")


def sauvegarder_txt(sites, nom_fichier="resultats_catalogue.txt"):
    """
    Sauvegarde les résultats en TXT simple
    """
    with open(nom_fichier, 'w', encoding='utf-8') as f:
        f.write(f"SITES EXTRAITS DU CATALOGUE\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total: {len(sites)} sites\n")
        f.write("="*60 + "\n\n")
        
        for site in sites:
            f.write(f"{site['numero']}. {site['titre']}\n")
            f.write(f"URL: {site['url']}\n")
            if site['categorie']:
                f.write(f"Catégorie: {site['categorie']}\n")
            if site['description']:
                f.write(f"Description: {site['description']}\n")
            f.write("\n" + "-"*60 + "\n\n")
    
    print(f"📄 Résultats sauvegardés dans: {nom_fichier}")


# ==========================================
# 🚀 EXÉCUTION DU SCRIPT
# ==========================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🌐 SCRAPER DE CATALOGUE DE SITES")
    print("="*60)
    
    # Vérifier que l'URL est configurée
    if CATALOGUE_URL == "https://ton-site-catalogue.com":
        print("\n⚠️  ATTENTION!")
        print("Tu dois configurer ton URL de catalogue!")
        print("Ouvre ce fichier et change la ligne CATALOGUE_URL en haut!")
        print("\nExemple:")
        print('CATALOGUE_URL = "https://example.com/sites"')
        input("\nAppuie sur Entrée pour quitter...")
        exit()
    
    # Lancer le scraping
    sites = scraper_catalogue(CATALOGUE_URL, MOT_CLE, MAX_RESULTATS)
    
    if sites:
        # Afficher les résultats
        afficher_resultats(sites)
        
        # Sauvegarder en JSON
        sauvegarder_json(sites)
        
        # Sauvegarder en TXT
        sauvegarder_txt(sites)
        
        print(f"\n✅ TERMINÉ! {len(sites)} sites extraits")
        print("\n📁 Fichiers créés:")
        print("   - resultats_catalogue.json")
        print("   - resultats_catalogue.txt")
    else:
        print("\n❌ Aucun site trouvé!")
    
    input("\n\nAppuie sur Entrée pour quitter...")
