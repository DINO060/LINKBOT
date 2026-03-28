import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import time
import re

class DirectoryScraper:
    """Scraper pour sites d'annuaires/catalogues de sites web"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        self.session = requests.Session()
    
    def scrape_directory_site(self, base_url: str, search_query: str = None) -> List[Dict]:
        """
        Scrape un site d'annuaire pour extraire les sites listés
        
        Args:
            base_url: URL du site d'annuaire
            search_query: Terme de recherche optionnel
            
        Returns:
            Liste de dictionnaires avec les sites trouvés
        """
        sites = []
        
        try:
            # Construire l'URL avec la recherche si fournie
            if search_query:
                # Essayer différents formats de recherche
                possible_urls = [
                    f"{base_url}/search?q={search_query}",
                    f"{base_url}?s={search_query}",
                    f"{base_url}?search={search_query}",
                    base_url
                ]
            else:
                possible_urls = [base_url]
            
            response = None
            for url in possible_urls:
                try:
                    response = self.session.get(url, headers=self.headers, timeout=15)
                    if response.status_code == 200:
                        break
                except:
                    continue
            
            if not response or response.status_code != 200:
                print(f"Erreur: Impossible d'accéder au site")
                return sites
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extraire tous les liens du site
            links = soup.find_all('a', href=True)
            
            seen_urls = set()
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Filtrer les liens internes et invalides
                if not href or href.startswith('#') or href.startswith('javascript:'):
                    continue
                
                # Normaliser l'URL
                if href.startswith('http'):
                    url = href
                elif href.startswith('//'):
                    url = 'https:' + href
                else:
                    continue
                
                # Éviter les doublons
                if url in seen_urls:
                    continue
                
                # Filtrer si recherche spécifique
                if search_query:
                    search_lower = search_query.lower()
                    if search_lower not in text.lower() and search_lower not in url.lower():
                        # Chercher aussi dans le contexte autour du lien
                        parent = link.parent
                        if parent:
                            parent_text = parent.get_text(strip=True).lower()
                            if search_lower not in parent_text:
                                continue
                
                seen_urls.add(url)
                
                # Extraire plus d'infos sur le lien
                description = ""
                category = ""
                
                # Chercher une description à proximité
                parent = link.parent
                if parent:
                    # Essayer de trouver une description dans le parent
                    desc_candidates = parent.find_all(['p', 'span', 'div'], limit=3)
                    for candidate in desc_candidates:
                        candidate_text = candidate.get_text(strip=True)
                        if candidate_text and len(candidate_text) > 20 and candidate_text != text:
                            description = candidate_text[:200]
                            break
                
                # Essayer de détecter la catégorie
                headers = soup.find_all(['h1', 'h2', 'h3', 'h4'])
                for header in headers:
                    if link in header.find_all('a'):
                        category = header.get_text(strip=True)
                        break
                
                site_info = {
                    'title': text if text else url,
                    'url': url,
                    'description': description,
                    'category': category
                }
                
                sites.append(site_info)
            
            return sites
            
        except Exception as e:
            print(f"Erreur lors du scraping: {e}")
            return sites
    
    def scrape_with_categories(self, base_url: str) -> Dict[str, List[Dict]]:
        """
        Scrape un site d'annuaire en organisant par catégories
        
        Args:
            base_url: URL du site d'annuaire
            
        Returns:
            Dictionnaire avec catégories et leurs sites
        """
        categorized_sites = {}
        
        try:
            response = self.session.get(base_url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Chercher des sections/catégories
            sections = soup.find_all(['section', 'div'], class_=re.compile(r'categor|section|group'))
            
            if not sections:
                # Si pas de sections claires, chercher des headers
                sections = soup.find_all(['article', 'div'])
            
            for section in sections:
                # Trouver le titre de la catégorie
                category_header = section.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                category_name = category_header.get_text(strip=True) if category_header else "Général"
                
                # Trouver tous les liens dans cette section
                links = section.find_all('a', href=True)
                
                sites_in_category = []
                seen = set()
                
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    
                    if not href or href.startswith('#') or href in seen:
                        continue
                    
                    if href.startswith('http'):
                        url = href
                    elif href.startswith('//'):
                        url = 'https:' + href
                    else:
                        continue
                    
                    seen.add(href)
                    
                    # Description
                    description = ""
                    parent = link.parent
                    if parent:
                        desc = parent.find(['p', 'span'])
                        if desc:
                            description = desc.get_text(strip=True)[:200]
                    
                    sites_in_category.append({
                        'title': text if text else url,
                        'url': url,
                        'description': description
                    })
                
                if sites_in_category:
                    categorized_sites[category_name] = sites_in_category
            
            return categorized_sites
            
        except Exception as e:
            print(f"Erreur: {e}")
            return categorized_sites
    
    def search_in_directory(self, base_url: str, keyword: str, max_results: int = 20) -> List[Dict]:
        """
        Recherche dans un site d'annuaire avec un mot-clé
        
        Args:
            base_url: URL du site d'annuaire
            keyword: Mot-clé à rechercher
            max_results: Nombre maximum de résultats
            
        Returns:
            Liste des sites correspondants
        """
        sites = self.scrape_directory_site(base_url, keyword)
        
        # Filtrer et trier par pertinence
        keyword_lower = keyword.lower()
        
        def relevance_score(site):
            score = 0
            title = site.get('title', '').lower()
            desc = site.get('description', '').lower()
            url = site.get('url', '').lower()
            
            # Plus de points si le mot-clé est dans le titre
            if keyword_lower in title:
                score += 10
            
            # Points si dans la description
            if keyword_lower in desc:
                score += 5
            
            # Points si dans l'URL
            if keyword_lower in url:
                score += 3
            
            return score
        
        # Trier par score de pertinence
        sites_with_scores = [(site, relevance_score(site)) for site in sites]
        sites_with_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Garder seulement ceux avec un score > 0
        filtered = [site for site, score in sites_with_scores if score > 0]
        
        return filtered[:max_results]
    
    def get_all_external_links(self, url: str) -> List[str]:
        """
        Récupère tous les liens externes d'une page
        
        Args:
            url: URL de la page
            
        Returns:
            Liste d'URLs externes
        """
        try:
            response = self.session.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            external_links = set()
            base_domain = self._get_domain(url)
            
            for link in soup.find_all('a', href=True):
                href = link.get('href')
                
                if href.startswith('http'):
                    link_domain = self._get_domain(href)
                    if link_domain != base_domain:
                        external_links.add(href)
            
            return list(external_links)
            
        except Exception as e:
            print(f"Erreur: {e}")
            return []
    
    def _get_domain(self, url: str) -> str:
        """Extrait le domaine d'une URL"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except:
            return ""
    
    def save_results(self, sites: List[Dict], filename: str):
        """Sauvegarde les résultats en JSON"""
        import json
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(sites, f, ensure_ascii=False, indent=2)
        print(f"Résultats sauvegardés dans {filename}")


if __name__ == "__main__":
    # Exemple d'utilisation
    scraper = DirectoryScraper()
    
    # Exemple avec un site d'annuaire générique
    print("Test du scraper d'annuaire...")
    
    # Tu peux tester avec différents sites d'annuaires
    # Remplace par l'URL de ton choix
    directory_url = "https://example.com"  # Remplace par un vrai site
    
    # Recherche avec mot-clé
    results = scraper.search_in_directory(directory_url, "gaming", max_results=10)
    
    print(f"\nTrouvé {len(results)} résultats:")
    for i, site in enumerate(results, 1):
        print(f"\n{i}. {site['title']}")
        print(f"   URL: {site['url']}")
        if site['description']:
            print(f"   Description: {site['description'][:100]}...")
    
    # Sauvegarder
    if results:
        scraper.save_results(results, "directory_results.json")
