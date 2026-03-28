"""
🎌 ANIME API - Utilise Jikan API (MyAnimeList)
==============================================
Plus simple, plus rapide, plus fiable que le scraping!
"""

import requests
import json
import time
from typing import List, Dict, Optional

class JikanAnimeAPI:
    """Interface simple pour Jikan API v4"""
    
    def __init__(self):
        self.base_url = "https://api.jikan.moe/v4"
        self.session = requests.Session()
        self.rate_limit_delay = 1  # Jikan demande 1 sec entre requêtes
    
    def _make_request(self, endpoint: str) -> Optional[Dict]:
        """
        Fait une requête à l'API avec gestion d'erreurs
        
        Args:
            endpoint: Point d'accès de l'API (ex: "/anime/1535")
            
        Returns:
            Données JSON ou None si erreur
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = self.session.get(url, timeout=10)
            
            # Rate limiting (respecter les règles de Jikan)
            time.sleep(self.rate_limit_delay)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                print("⚠️ Rate limit atteint, attente de 5 secondes...")
                time.sleep(5)
                return self._make_request(endpoint)
            else:
                print(f"❌ Erreur {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return None
    
    def search_anime(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Recherche des animes par nom
        
        Args:
            query: Terme de recherche
            limit: Nombre de résultats (max 25)
            
        Returns:
            Liste d'animes
        """
        endpoint = f"/anime?q={query}&limit={limit}"
        data = self._make_request(endpoint)
        
        if not data or 'data' not in data:
            return []
        
        results = []
        for anime in data['data']:
            results.append({
                'mal_id': anime.get('mal_id'),
                'title': anime.get('title'),
                'title_english': anime.get('title_english'),
                'title_japanese': anime.get('title_japanese'),
                'type': anime.get('type'),
                'episodes': anime.get('episodes'),
                'status': anime.get('status'),
                'score': anime.get('score'),
                'scored_by': anime.get('scored_by'),
                'rank': anime.get('rank'),
                'popularity': anime.get('popularity'),
                'members': anime.get('members'),
                'favorites': anime.get('favorites'),
                'synopsis': anime.get('synopsis'),
                'year': anime.get('year'),
                'season': anime.get('season'),
                'url': anime.get('url'),
                'image_url': anime.get('images', {}).get('jpg', {}).get('large_image_url')
            })
        
        return results
    
    def get_anime_details(self, anime_id: int) -> Optional[Dict]:
        """
        Obtient les détails complets d'un anime
        
        Args:
            anime_id: ID MyAnimeList de l'anime
            
        Returns:
            Détails complets de l'anime
        """
        endpoint = f"/anime/{anime_id}/full"
        data = self._make_request(endpoint)
        
        if not data or 'data' not in data:
            return None
        
        anime = data['data']
        
        return {
            'mal_id': anime.get('mal_id'),
            'url': anime.get('url'),
            'title': anime.get('title'),
            'title_english': anime.get('title_english'),
            'title_japanese': anime.get('title_japanese'),
            'title_synonyms': anime.get('title_synonyms', []),
            'type': anime.get('type'),
            'source': anime.get('source'),
            'episodes': anime.get('episodes'),
            'status': anime.get('status'),
            'airing': anime.get('airing'),
            'aired': anime.get('aired', {}).get('string'),
            'duration': anime.get('duration'),
            'rating': anime.get('rating'),
            'score': anime.get('score'),
            'scored_by': anime.get('scored_by'),
            'rank': anime.get('rank'),
            'popularity': anime.get('popularity'),
            'members': anime.get('members'),
            'favorites': anime.get('favorites'),
            'synopsis': anime.get('synopsis'),
            'background': anime.get('background'),
            'season': anime.get('season'),
            'year': anime.get('year'),
            'studios': [s['name'] for s in anime.get('studios', [])],
            'genres': [g['name'] for g in anime.get('genres', [])],
            'themes': [t['name'] for t in anime.get('themes', [])],
            'demographics': [d['name'] for d in anime.get('demographics', [])],
            'producers': [p['name'] for p in anime.get('producers', [])],
            'licensors': [l['name'] for l in anime.get('licensors', [])],
            'image_url': anime.get('images', {}).get('jpg', {}).get('large_image_url'),
            'trailer_url': anime.get('trailer', {}).get('url')
        }
    
    def get_user_animelist(self, username: str) -> List[Dict]:
        """
        Récupère la liste d'animes d'un utilisateur
        
        Args:
            username: Nom d'utilisateur MyAnimeList
            
        Returns:
            Liste des animes de l'utilisateur
        """
        all_animes = []
        page = 1
        
        while True:
            endpoint = f"/users/{username}/animelist?page={page}"
            data = self._make_request(endpoint)
            
            if not data or 'data' not in data or not data['data']:
                break
            
            for entry in data['data']:
                anime = entry.get('anime', {})
                all_animes.append({
                    'mal_id': anime.get('mal_id'),
                    'title': anime.get('title'),
                    'url': anime.get('url'),
                    'image_url': anime.get('images', {}).get('jpg', {}).get('image_url'),
                    'watching_status': entry.get('watching_status'),
                    'score': entry.get('score'),
                    'episodes_watched': entry.get('episodes_watched'),
                    'total_episodes': anime.get('episodes'),
                    'is_rewatching': entry.get('is_rewatching'),
                    'start_date': entry.get('start_date'),
                    'finish_date': entry.get('finish_date')
                })
            
            # Vérifier s'il y a plus de pages
            pagination = data.get('pagination', {})
            if not pagination.get('has_next_page'):
                break
            
            page += 1
        
        return all_animes
    
    def get_top_anime(self, limit: int = 25, filter_type: str = None) -> List[Dict]:
        """
        Obtient le top des animes
        
        Args:
            limit: Nombre de résultats (max 25)
            filter_type: Type de filtre (tv, movie, ova, special, ona, music)
            
        Returns:
            Top animes
        """
        endpoint = f"/top/anime?limit={limit}"
        if filter_type:
            endpoint += f"&filter={filter_type}"
        
        data = self._make_request(endpoint)
        
        if not data or 'data' not in data:
            return []
        
        results = []
        for anime in data['data']:
            results.append({
                'rank': anime.get('rank'),
                'mal_id': anime.get('mal_id'),
                'title': anime.get('title'),
                'title_english': anime.get('title_english'),
                'type': anime.get('type'),
                'episodes': anime.get('episodes'),
                'score': anime.get('score'),
                'scored_by': anime.get('scored_by'),
                'url': anime.get('url'),
                'image_url': anime.get('images', {}).get('jpg', {}).get('large_image_url')
            })
        
        return results
    
    def get_seasonal_anime(self, year: int, season: str) -> List[Dict]:
        """
        Obtient les animes d'une saison
        
        Args:
            year: Année (ex: 2024)
            season: Saison (winter, spring, summer, fall)
            
        Returns:
            Animes de la saison
        """
        endpoint = f"/seasons/{year}/{season}"
        data = self._make_request(endpoint)
        
        if not data or 'data' not in data:
            return []
        
        results = []
        for anime in data['data']:
            results.append({
                'mal_id': anime.get('mal_id'),
                'title': anime.get('title'),
                'title_english': anime.get('title_english'),
                'type': anime.get('type'),
                'episodes': anime.get('episodes'),
                'score': anime.get('score'),
                'synopsis': anime.get('synopsis'),
                'url': anime.get('url'),
                'image_url': anime.get('images', {}).get('jpg', {}).get('large_image_url')
            })
        
        return results
    
    def get_anime_recommendations(self, anime_id: int) -> List[Dict]:
        """
        Obtient les recommandations pour un anime
        
        Args:
            anime_id: ID de l'anime
            
        Returns:
            Liste d'animes recommandés
        """
        endpoint = f"/anime/{anime_id}/recommendations"
        data = self._make_request(endpoint)
        
        if not data or 'data' not in data:
            return []
        
        results = []
        for rec in data['data']:
            entry = rec.get('entry', {})
            results.append({
                'mal_id': entry.get('mal_id'),
                'title': entry.get('title'),
                'url': entry.get('url'),
                'image_url': entry.get('images', {}).get('jpg', {}).get('large_image_url'),
                'votes': rec.get('votes')
            })
        
        return results
    
    def save_to_json(self, data: any, filename: str):
        """Sauvegarde les données en JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Données sauvegardées: {filename}")


# ==========================================
# 🧪 EXEMPLES D'UTILISATION
# ==========================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🎌 JIKAN API - EXEMPLES")
    print("="*60 + "\n")
    
    api = JikanAnimeAPI()
    
    # 1. Rechercher un anime
    print("1️⃣ Recherche de 'Naruto'...")
    results = api.search_anime("Naruto", limit=5)
    if results:
        for anime in results:
            print(f"   📌 {anime['title']} - Score: {anime['score']} - Episodes: {anime['episodes']}")
    
    print()
    
    # 2. Détails d'un anime spécifique
    print("2️⃣ Détails de Death Note (ID: 1535)...")
    details = api.get_anime_details(1535)
    if details:
        print(f"   📺 Titre: {details['title']}")
        print(f"   ⭐ Score: {details['score']}")
        print(f"   🎬 Episodes: {details['episodes']}")
        print(f"   🎨 Studios: {', '.join(details['studios'])}")
        print(f"   🏷️ Genres: {', '.join(details['genres'])}")
    
    print()
    
    # 3. Top animes
    print("3️⃣ Top 5 animes de tous les temps...")
    top = api.get_top_anime(limit=5)
    if top:
        for anime in top:
            print(f"   #{anime['rank']} {anime['title']} - Score: {anime['score']}")
    
    print()
    
    # 4. Liste d'un utilisateur (exemple commenté pour éviter erreur)
    # print("4️⃣ Liste d'un utilisateur...")
    # user_list = api.get_user_animelist("Xinil")
    # print(f"   Trouvé: {len(user_list)} animes")
    
    print("\n✅ Test terminé!\n")
