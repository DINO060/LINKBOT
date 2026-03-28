"""
API Simkl.com - Films, Séries, Anime
"""

import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

class SimklAPI:
    def __init__(self, client_id=""):
        self.base_url = "https://api.simkl.com"
        self.client_id = client_id or os.getenv("SIMKL_CLIENT_ID", "your_client_id_here")
        self.headers = {
            "Content-Type": "application/json",
            "simkl-api-key": self.client_id,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.last_request = 0
        self.rate_limit = 0.25
    
    def _wait_for_rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request = time.time()
    
    def _make_request(self, endpoint, params=None):
        self._wait_for_rate_limit()
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Erreur API Simkl: {e}")
            return None
    
    def search(self, query, media_type="movie", limit=10):
        """
        Recherche multi-type
        media_type: movie, show, anime (pas "all")
        """
        endpoint = f"/search/{media_type}"
        params = {"q": query, "limit": limit}
        
        data = self._make_request(endpoint, params)
        if not data:
            return []
        
        results = []
        for item in data[:limit]:
            ids = item.get("ids", {})
            ratings = item.get("ratings", {}).get("simkl", {})
            
            result = {
                "id": ids.get("simkl_id"),
                "imdb_id": ids.get("imdb"),
                "title": item.get("title"),
                "year": item.get("year"),
                "type": item.get("endpoint_type", "").rstrip('s'),  # movies -> movie
                "poster": item.get("poster"),
                "rating": ratings.get("rating"),
                "votes": ratings.get("votes"),
                "overview": item.get("overview", "")[:200]
            }
            results.append(result)
        
        return results
    
    def search_anime(self, query, limit=10):
        """Recherche anime uniquement"""
        return self.search(query, media_type="anime", limit=limit)
    
    def search_movies(self, query, limit=10):
        """Recherche films uniquement"""
        return self.search(query, media_type="movie", limit=limit)
    
    def search_shows(self, query, limit=10):
        """Recherche séries uniquement"""
        return self.search(query, media_type="show", limit=limit)
    
    def get_details(self, simkl_id, media_type="show"):
        """
        Détails d'un média
        media_type: movie, show, anime
        """
        # Corriger l'endpoint: movie -> movies, show -> tv, anime -> anime
        endpoint_map = {"movie": "movies", "show": "tv", "anime": "anime"}
        endpoint_type = endpoint_map.get(media_type, "tv")
        endpoint = f"/{endpoint_type}/{simkl_id}"
        params = {"extended": "full"}
        
        data = self._make_request(endpoint, params)
        if not data:
            return None
        
        # Extraire les ratings
        ratings = data.get("ratings", {})
        simkl_rating = ratings.get("simkl", {})
        imdb_rating = ratings.get("imdb", {})
        
        # Infos de diffusion
        first_aired = data.get("first_aired", "")
        last_aired = data.get("last_aired") or "Now"
        aired_episodes = data.get("aired_episodes", 0)
        total_episodes = data.get("total_episodes", 0)
        total_seasons = data.get("seasons_count", 0)
        
        # Infos de schedule (jour/heure de diffusion)
        schedule = data.get("schedule", {})
        schedule_time = schedule.get("time", "")
        schedule_days = schedule.get("days", [])
        schedule_str = ""
        if schedule_days and schedule_time:
            days_str = ", ".join(schedule_days)
            schedule_str = f"{days_str} {schedule_time}"
        
        # Calculer durée totale
        runtime_str = data.get("runtime", "")
        runtime_minutes = 0
        if runtime_str:
            # Convertir en string si c'est un nombre
            runtime_str = str(runtime_str)
            
            # Parser "45m" ou "1h 30m" ou "118"
            if 'h' in runtime_str and 'm' in runtime_str:
                hours = int(runtime_str.split('h')[0].strip())
                minutes = int(runtime_str.split('h')[1].replace('m', '').strip())
                runtime_minutes = hours * 60 + minutes
            elif 'h' in runtime_str:
                hours = int(runtime_str.replace('h', '').strip())
                runtime_minutes = hours * 60
            elif 'm' in runtime_str:
                runtime_minutes = int(runtime_str.replace('m', '').strip())
            else:
                # Si c'est juste un nombre, c'est des minutes
                try:
                    runtime_minutes = int(runtime_str)
                except:
                    runtime_minutes = 0
        
        total_runtime_minutes = runtime_minutes * aired_episodes if runtime_minutes and aired_episodes else 0
        
        details = {
            "id": simkl_id,
            "title": data.get("title"),
            "year": data.get("year"),
            "type": media_type,
            "overview": data.get("overview"),
            "poster": data.get("poster"),
            "fanart": data.get("fanart"),
            
            # Ratings
            "rating": simkl_rating.get("rating"),
            "votes": simkl_rating.get("votes"),
            "imdb_rating": imdb_rating.get("rating"),
            "imdb_votes": imdb_rating.get("votes"),
            
            # Infos détaillées
            "genres": data.get("genres", []),
            "status": data.get("status"),
            "first_aired": first_aired,
            "last_aired": last_aired,
            "aired_episodes": aired_episodes,
            "total_episodes": total_episodes,
            "total_seasons": total_seasons,
            "schedule": schedule_str,
            "episode_run_time": runtime_minutes,
            "total_runtime": total_runtime_minutes,
            "country": data.get("country"),
            "network": data.get("network"),
            "runtime": runtime_str,
            
            # Stats
            "rank": data.get("rank"),
            "drop_rate": data.get("drop_rate"),
            
            # Infos supplémentaires
            "trailers": data.get("trailers", []),
            "cast": data.get("cast", [])[:5],  # Top 5 acteurs
            "url": f"https://simkl.com/{endpoint_type}/{simkl_id}"
        }
        
        return details
    
    def get_trending(self, media_type="movies", limit=10):
        """
        Tendances
        media_type: movies, anime (shows n'existe pas)
        """
        endpoint = f"/{media_type}/trending"
        
        params = {"limit": limit, "extended": "full"}
        data = self._make_request(endpoint, params)
        if not data:
            return []
        
        results = []
        for item in data[:limit]:
            ids = item.get("ids", {})
            ratings = item.get("ratings", {}).get("simkl", {})
            
            result = {
                "id": ids.get("simkl"),
                "title": item.get("title"),
                "year": item.get("year"),
                "type": item.get("type"),
                "poster": item.get("poster"),
                "rating": ratings.get("rating"),
                "overview": item.get("overview", "")[:150]
            }
            results.append(result)
        
        return results
    
    def get_best(self, media_type="movies", period="this-year", limit=10):
        """
        Meilleurs contenus
        media_type: movies, shows, anime
        period: this-week, this-month, this-year, all-time
        """
        endpoint = f"/{media_type}/best/{period}"
        
        data = self._make_request(endpoint, {"limit": limit})
        if not data:
            return []
        
        results = []
        for item in data[:limit]:
            result = {
                "id": item.get("ids", {}).get("simkl"),
                "title": item.get("title"),
                "year": item.get("year"),
                "type": item.get("type"),
                "rating": item.get("ratings", {}).get("simkl", {}).get("rating"),
                "rank": item.get("rank")
            }
            results.append(result)
        
        return results


if __name__ == "__main__":
    print("\n🎬 Test API Simkl\n")
    
    # Pas besoin de client_id pour les recherches publiques
    api = SimklAPI()
    
    # Test recherche
    print("🔍 Recherche 'Breaking Bad':")
    results = api.search("Breaking Bad", limit=3)
    for r in results:
        print(f"  - {r['title']} ({r['year']}) [{r['type']}] ⭐ {r['rating']}")
    
    # Test anime
    print("\n🎌 Recherche anime 'Naruto':")
    anime = api.search_anime("Naruto", limit=3)
    for a in anime:
        print(f"  - {a['title']} ({a['year']}) ⭐ {a['rating']}")
    
    # Test trending
    print("\n🔥 Trending movies:")
    trending = api.get_trending("movies", limit=5)
    for t in trending:
        print(f"  - {t['title']} ({t['year']}) ⭐ {t['rating']}")
    
    print("\n✅ Tests terminés!")
