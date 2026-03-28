"""
API OMDb - Données IMDB officielles
http://www.omdbapi.com/
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

class OMDbAPI:
    def __init__(self, api_key=""):
        self.base_url = "http://www.omdbapi.com/"
        self.api_key = api_key or os.getenv("OMDB_API_KEY", "")
        self.last_request = 0
        self.rate_limit = 0.1
    
    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request = time.time()
    
    def _make_request(self, params):
        self._wait_for_rate_limit()
        params['apikey'] = self.api_key
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('Response') == 'False':
                print(f"OMDb Error: {data.get('Error')}")
                return None
            
            return data
        except requests.exceptions.RequestException as e:
            print(f"Erreur OMDb: {e}")
            return None
    
    def search(self, query, media_type="", year="", limit=10):
        """
        Recherche
        media_type: movie, series, episode (optionnel)
        """
        params = {'s': query, 'page': 1}
        
        if media_type:
            params['type'] = media_type
        if year:
            params['y'] = year
        
        data = self._make_request(params)
        if not data or 'Search' not in data:
            return []
        
        results = []
        for item in data['Search'][:limit]:
            result = {
                'imdb_id': item.get('imdbID'),
                'title': item.get('Title'),
                'year': item.get('Year'),
                'type': item.get('Type'),
                'poster': item.get('Poster')
            }
            results.append(result)
        
        return results
    
    def search_movies(self, query, limit=10):
        """Recherche films uniquement"""
        return self.search(query, media_type="movie", limit=limit)
    
    def search_series(self, query, limit=10):
        """Recherche séries uniquement"""
        return self.search(query, media_type="series", limit=limit)
    
    def get_details(self, imdb_id=None, title=None):
        """
        Détails complets d'un film/série
        Par IMDB ID ou titre
        """
        if not imdb_id and not title:
            return None
        
        params = {'plot': 'full'}
        
        if imdb_id:
            params['i'] = imdb_id
        else:
            params['t'] = title
        
        data = self._make_request(params)
        if not data:
            return None
        
        # Parser les données
        details = {
            'imdb_id': data.get('imdbID'),
            'title': data.get('Title'),
            'year': data.get('Year'),
            'rated': data.get('Rated'),
            'released': data.get('Released'),
            'runtime': data.get('Runtime'),
            'genre': data.get('Genre'),
            'director': data.get('Director'),
            'writer': data.get('Writer'),
            'actors': data.get('Actors'),
            'plot': data.get('Plot'),
            'language': data.get('Language'),
            'country': data.get('Country'),
            'awards': data.get('Awards'),
            'poster': data.get('Poster'),
            'type': data.get('Type'),
            
            # Ratings
            'imdb_rating': data.get('imdbRating'),
            'imdb_votes': data.get('imdbVotes'),
            'metascore': data.get('Metascore'),
            'ratings': data.get('Ratings', []),
            
            # Série uniquement
            'total_seasons': data.get('totalSeasons'),
            
            # Box office
            'box_office': data.get('BoxOffice'),
            
            'url': f"https://www.imdb.com/title/{data.get('imdbID')}/" if data.get('imdbID') else ""
        }
        
        return details


if __name__ == "__main__":
    print("\n🎬 Test API OMDb\n")
    
    api = OMDbAPI()
    
    if not api.api_key:
        print("⚠️ Pas de clé API OMDb!")
        print("Obtiens-en une sur: http://www.omdbapi.com/apikey.aspx")
        print("Puis ajoute OMDB_API_KEY dans .env")
    else:
        # Test recherche
        print("🔍 Recherche 'Inception':")
        results = api.search_movies("Inception", limit=3)
        for r in results:
            print(f"  - {r['title']} ({r['year']}) [{r['imdb_id']}]")
        
        # Test détails
        if results:
            print(f"\n📝 Détails de {results[0]['title']}:")
            details = api.get_details(imdb_id=results[0]['imdb_id'])
            if details:
                print(f"  Titre: {details['title']}")
                print(f"  Note IMDB: {details['imdb_rating']}/10 ({details['imdb_votes']} votes)")
                print(f"  Réalisateur: {details['director']}")
                print(f"  Genre: {details['genre']}")
                print(f"  Durée: {details['runtime']}")
    
    print("\n✅ Tests terminés!")
