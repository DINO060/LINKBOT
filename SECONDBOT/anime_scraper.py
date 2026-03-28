import requests
from bs4 import BeautifulSoup
import json
import time
from typing import List, Dict

class AnimeScraper:
    """Scraper pour récupérer des infos d'animes depuis différents sites"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.session = requests.Session()
    
    def scrape_myanimelist_user(self, username: str) -> List[Dict]:
        """
        Scrape la liste d'animes d'un utilisateur MyAnimeList
        
        Args:
            username: Nom d'utilisateur MyAnimeList
            
        Returns:
            Liste de dictionnaires contenant les infos des animes
        """
        animes = []
        page = 0
        
        while True:
            url = f"https://myanimelist.net/animelist/{username}/load.json?offset={page}&status=7"
            
            try:
                response = self.session.get(url, headers=self.headers, timeout=10)
                
                if response.status_code != 200:
                    print(f"Erreur: Status code {response.status_code}")
                    break
                
                data = response.json()
                
                if not data:
                    break
                
                for item in data:
                    anime_info = {
                        'title': item.get('anime_title'),
                        'mal_id': item.get('anime_id'),
                        'score': item.get('score'),
                        'status': self._get_watch_status(item.get('status')),
                        'episodes_watched': item.get('num_watched_episodes'),
                        'total_episodes': item.get('anime_num_episodes'),
                        'url': f"https://myanimelist.net/anime/{item.get('anime_id')}",
                        'image_url': item.get('anime_image_path'),
                        'type': item.get('anime_media_type_string'),
                        'rating': item.get('anime_mpaa_rating_string'),
                        'start_date': item.get('anime_start_date_string'),
                        'end_date': item.get('anime_end_date_string')
                    }
                    animes.append(anime_info)
                
                page += 300
                time.sleep(1)  # Pause pour éviter le rate limiting
                
            except Exception as e:
                print(f"Erreur lors du scraping: {e}")
                break
        
        return animes
    
    def scrape_anime_details(self, mal_id: int) -> Dict:
        """
        Scrape les détails d'un anime spécifique depuis MyAnimeList
        
        Args:
            mal_id: ID MyAnimeList de l'anime
            
        Returns:
            Dictionnaire avec les détails de l'anime
        """
        url = f"https://myanimelist.net/anime/{mal_id}"
        
        try:
            response = self.session.get(url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            details = {
                'mal_id': mal_id,
                'url': url,
                'title': self._get_text(soup.select_one('h1.title-name')),
                'title_english': self._get_text(soup.select_one('p.title-english')),
                'synopsis': self._get_text(soup.select_one('p[itemprop="description"]')),
                'score': self._get_text(soup.select_one('div.score-label')),
                'ranked': self._get_info_value(soup, 'Ranked:'),
                'popularity': self._get_info_value(soup, 'Popularity:'),
                'members': self._get_info_value(soup, 'Members:'),
                'type': self._get_info_value(soup, 'Type:'),
                'episodes': self._get_info_value(soup, 'Episodes:'),
                'status': self._get_info_value(soup, 'Status:'),
                'aired': self._get_info_value(soup, 'Aired:'),
                'studios': self._get_info_value(soup, 'Studios:'),
                'source': self._get_info_value(soup, 'Source:'),
                'genres': self._get_genres(soup),
                'duration': self._get_info_value(soup, 'Duration:'),
                'rating': self._get_info_value(soup, 'Rating:')
            }
            
            return details
            
        except Exception as e:
            print(f"Erreur lors du scraping des détails: {e}")
            return {}
    
    def search_anime(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Recherche des animes par nom
        
        Args:
            query: Terme de recherche
            limit: Nombre maximum de résultats
            
        Returns:
            Liste de dictionnaires avec les résultats
        """
        url = "https://myanimelist.net/anime.php"
        params = {
            'q': query,
            'cat': 'anime'
        }
        
        try:
            response = self.session.get(url, params=params, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            results = []
            items = soup.select('div.js-categories-seasonal tr')[:limit]
            
            for item in items:
                link = item.select_one('a.hoverinfo_trigger')
                if link:
                    anime_id = link.get('href', '').split('/')[4] if '/anime/' in link.get('href', '') else None
                    
                    result = {
                        'title': link.get_text(strip=True),
                        'mal_id': anime_id,
                        'url': f"https://myanimelist.net{link.get('href')}",
                        'type': self._get_text(item.select('td')[2]),
                        'episodes': self._get_text(item.select('td')[3]),
                        'score': self._get_text(item.select('td')[4])
                    }
                    results.append(result)
            
            return results
            
        except Exception as e:
            print(f"Erreur lors de la recherche: {e}")
            return []
    
    def _get_watch_status(self, status_code: int) -> str:
        """Convertit le code de statut en texte"""
        statuses = {
            1: "Watching",
            2: "Completed",
            3: "On Hold",
            4: "Dropped",
            6: "Plan to Watch"
        }
        return statuses.get(status_code, "Unknown")
    
    def _get_text(self, element) -> str:
        """Récupère le texte d'un élément ou retourne une chaîne vide"""
        return element.get_text(strip=True) if element else ""
    
    def _get_info_value(self, soup, label: str) -> str:
        """Récupère une valeur d'info spécifique"""
        for span in soup.find_all('span', class_='dark_text'):
            if label in span.get_text():
                parent = span.parent
                return parent.get_text().replace(label, '').strip()
        return ""
    
    def _get_genres(self, soup) -> List[str]:
        """Récupère la liste des genres"""
        genres = []
        genre_spans = soup.find_all('span', itemprop='genre')
        for genre in genre_spans:
            genres.append(genre.get_text(strip=True))
        return genres
    
    def save_to_json(self, data: List[Dict], filename: str):
        """Sauvegarde les données dans un fichier JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Données sauvegardées dans {filename}")


if __name__ == "__main__":
    # Exemple d'utilisation
    scraper = AnimeScraper()
    
    # Rechercher un anime
    print("Recherche d'animes...")
    results = scraper.search_anime("Naruto", limit=5)
    for anime in results:
        print(f"- {anime['title']} (Score: {anime['score']})")
    
    # Scraper la liste d'un utilisateur (remplace 'username' par un vrai nom)
    # animes = scraper.scrape_myanimelist_user("username")
    # scraper.save_to_json(animes, "user_animelist.json")
    
    # Obtenir les détails d'un anime spécifique
    # details = scraper.scrape_anime_details(1535)  # Death Note
    # print(json.dumps(details, indent=2, ensure_ascii=False))
