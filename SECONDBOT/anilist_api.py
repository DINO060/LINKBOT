"""
📚 ANILIST API - Pour Anime, Manga, Manhwa, Manhua
===================================================
API GraphQL gratuite et complète!
Couvre TOUT: Anime, Manga (JP), Manhwa (KR), Manhua (CN)
"""

import requests
import json
import time
from typing import List, Dict, Optional

class AniListAPI:
    """Interface pour AniList GraphQL API"""
    
    def __init__(self):
        self.base_url = "https://graphql.anilist.co"
        self.session = requests.Session()
        self.rate_limit_delay = 1
    
    def _make_request(self, query: str, variables: dict = None) -> Optional[Dict]:
        """
        Fait une requête GraphQL à AniList
        
        Args:
            query: Query GraphQL
            variables: Variables pour la query
            
        Returns:
            Données JSON ou None
        """
        try:
            response = self.session.post(
                self.base_url,
                json={'query': query, 'variables': variables or {}},
                timeout=10
            )
            
            time.sleep(self.rate_limit_delay)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('data')
            else:
                print(f"❌ Erreur {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return None
    
    def search_media(self, query: str, media_type: str = None, limit: int = 10) -> List[Dict]:
        """
        Recherche anime, manga, manhwa, manhua
        
        Args:
            query: Terme de recherche
            media_type: ANIME ou MANGA (None = les deux)
            limit: Nombre de résultats
            
        Returns:
            Liste de médias
        """
        graphql_query = """
        query ($search: String, $type: MediaType, $perPage: Int) {
            Page(perPage: $perPage) {
                media(search: $search, type: $type, sort: POPULARITY_DESC) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    type
                    format
                    status
                    description
                    startDate {
                        year
                        month
                        day
                    }
                    endDate {
                        year
                        month
                        day
                    }
                    episodes
                    chapters
                    volumes
                    countryOfOrigin
                    averageScore
                    popularity
                    favourites
                    genres
                    coverImage {
                        large
                    }
                    siteUrl
                }
            }
        }
        """
        
        variables = {
            'search': query,
            'type': media_type,
            'perPage': limit
        }
        
        data = self._make_request(graphql_query, variables)
        
        if not data or 'Page' not in data:
            return []
        
        results = []
        for media in data['Page']['media']:
            results.append({
                'id': media.get('id'),
                'title': media.get('title', {}).get('romaji'),
                'title_english': media.get('title', {}).get('english'),
                'title_native': media.get('title', {}).get('native'),
                'type': media.get('type'),  # ANIME ou MANGA
                'format': media.get('format'),  # TV, MOVIE, MANGA, NOVEL, ONE_SHOT, MANHWA
                'status': media.get('status'),
                'description': media.get('description'),
                'start_year': media.get('startDate', {}).get('year'),
                'episodes': media.get('episodes'),
                'chapters': media.get('chapters'),
                'volumes': media.get('volumes'),
                'country': media.get('countryOfOrigin'),  # JP, KR, CN
                'score': media.get('averageScore'),
                'popularity': media.get('popularity'),
                'favourites': media.get('favourites'),
                'genres': media.get('genres', []),
                'cover_image': media.get('coverImage', {}).get('large'),
                'url': media.get('siteUrl')
            })
        
        return results
    
    def search_manhwa(self, query: str, limit: int = 10) -> List[Dict]:
        """
        Recherche spécifique de manhwa (coréens)
        
        Args:
            query: Terme de recherche
            limit: Nombre de résultats
            
        Returns:
            Liste de manhwa
        """
        graphql_query = """
        query ($search: String, $perPage: Int) {
            Page(perPage: $perPage) {
                media(search: $search, type: MANGA, countryOfOrigin: "KR", sort: POPULARITY_DESC) {
                    id
                    title {
                        romaji
                        english
                        native
                    }
                    format
                    status
                    description
                    chapters
                    volumes
                    averageScore
                    popularity
                    genres
                    coverImage {
                        large
                    }
                    siteUrl
                }
            }
        }
        """
        
        variables = {
            'search': query,
            'perPage': limit
        }
        
        data = self._make_request(graphql_query, variables)
        
        if not data or 'Page' not in data:
            return []
        
        results = []
        for media in data['Page']['media']:
            results.append({
                'id': media.get('id'),
                'title': media.get('title', {}).get('romaji'),
                'title_english': media.get('title', {}).get('english'),
                'title_native': media.get('title', {}).get('native'),
                'format': media.get('format'),
                'status': media.get('status'),
                'description': media.get('description'),
                'chapters': media.get('chapters'),
                'volumes': media.get('volumes'),
                'score': media.get('averageScore'),
                'popularity': media.get('popularity'),
                'genres': media.get('genres', []),
                'cover_image': media.get('coverImage', {}).get('large'),
                'url': media.get('siteUrl'),
                'country': 'KR'  # Manhwa coréen
            })
        
        return results
    
    def get_media_details(self, media_id: int) -> Optional[Dict]:
        """
        Obtient les détails complets d'un anime/manga/manhwa
        
        Args:
            media_id: ID AniList
            
        Returns:
            Détails complets
        """
        graphql_query = """
        query ($id: Int) {
            Media(id: $id) {
                id
                title {
                    romaji
                    english
                    native
                }
                type
                format
                status
                description
                startDate {
                    year
                    month
                    day
                }
                endDate {
                    year
                    month
                    day
                }
                season
                seasonYear
                episodes
                duration
                chapters
                volumes
                countryOfOrigin
                isLicensed
                source
                hashtag
                averageScore
                meanScore
                popularity
                favourites
                genres
                tags {
                    name
                    rank
                }
                studios {
                    nodes {
                        name
                    }
                }
                coverImage {
                    large
                    extraLarge
                }
                bannerImage
                siteUrl
            }
        }
        """
        
        variables = {'id': media_id}
        data = self._make_request(graphql_query, variables)
        
        if not data or 'Media' not in data:
            return None
        
        media = data['Media']
        
        return {
            'id': media.get('id'),
            'title': media.get('title', {}).get('romaji'),
            'title_english': media.get('title', {}).get('english'),
            'title_native': media.get('title', {}).get('native'),
            'type': media.get('type'),
            'format': media.get('format'),
            'status': media.get('status'),
            'description': media.get('description'),
            'start_date': f"{media.get('startDate', {}).get('year', '')}-{media.get('startDate', {}).get('month', '')}-{media.get('startDate', {}).get('day', '')}",
            'season': media.get('season'),
            'season_year': media.get('seasonYear'),
            'episodes': media.get('episodes'),
            'duration': media.get('duration'),
            'chapters': media.get('chapters'),
            'volumes': media.get('volumes'),
            'country': media.get('countryOfOrigin'),
            'source': media.get('source'),
            'score': media.get('averageScore'),
            'mean_score': media.get('meanScore'),
            'popularity': media.get('popularity'),
            'favourites': media.get('favourites'),
            'genres': media.get('genres', []),
            'tags': [tag['name'] for tag in media.get('tags', [])[:10]],
            'studios': [studio['name'] for studio in media.get('studios', {}).get('nodes', [])],
            'cover_image': media.get('coverImage', {}).get('extraLarge'),
            'banner': media.get('bannerImage'),
            'url': media.get('siteUrl')
        }
    
    def get_trending(self, media_type: str = None, limit: int = 10) -> List[Dict]:
        """
        Obtient les tendances (trending)
        
        Args:
            media_type: ANIME ou MANGA
            limit: Nombre de résultats
            
        Returns:
            Liste des tendances
        """
        graphql_query = """
        query ($type: MediaType, $perPage: Int) {
            Page(perPage: $perPage) {
                media(type: $type, sort: TRENDING_DESC) {
                    id
                    title {
                        romaji
                        english
                    }
                    type
                    format
                    averageScore
                    popularity
                    episodes
                    chapters
                    countryOfOrigin
                    coverImage {
                        large
                    }
                    siteUrl
                }
            }
        }
        """
        
        variables = {
            'type': media_type,
            'perPage': limit
        }
        
        data = self._make_request(graphql_query, variables)
        
        if not data or 'Page' not in data:
            return []
        
        results = []
        for media in data['Page']['media']:
            results.append({
                'id': media.get('id'),
                'title': media.get('title', {}).get('romaji'),
                'title_english': media.get('title', {}).get('english'),
                'type': media.get('type'),
                'format': media.get('format'),
                'score': media.get('averageScore'),
                'popularity': media.get('popularity'),
                'episodes': media.get('episodes'),
                'chapters': media.get('chapters'),
                'country': media.get('countryOfOrigin'),
                'cover_image': media.get('coverImage', {}).get('large'),
                'url': media.get('siteUrl')
            })
        
        return results
    
    def get_user_list(self, username: str) -> List[Dict]:
        """
        Récupère la liste d'un utilisateur
        
        Args:
            username: Nom d'utilisateur AniList
            
        Returns:
            Liste des médias de l'utilisateur
        """
        graphql_query = """
        query ($username: String) {
            MediaListCollection(userName: $username, type: ANIME) {
                lists {
                    name
                    entries {
                        media {
                            id
                            title {
                                romaji
                                english
                            }
                            type
                            format
                            averageScore
                            episodes
                            siteUrl
                        }
                        status
                        score
                        progress
                    }
                }
            }
        }
        """
        
        variables = {'username': username}
        data = self._make_request(graphql_query, variables)
        
        if not data or 'MediaListCollection' not in data:
            return []
        
        results = []
        for list_data in data['MediaListCollection']['lists']:
            for entry in list_data['entries']:
                media = entry['media']
                results.append({
                    'id': media.get('id'),
                    'title': media.get('title', {}).get('romaji'),
                    'title_english': media.get('title', {}).get('english'),
                    'type': media.get('type'),
                    'format': media.get('format'),
                    'score': media.get('averageScore'),
                    'episodes': media.get('episodes'),
                    'url': media.get('siteUrl'),
                    'user_status': entry.get('status'),
                    'user_score': entry.get('score'),
                    'user_progress': entry.get('progress')
                })
        
        return results
    
    def save_to_json(self, data: any, filename: str):
        """Sauvegarde en JSON"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Sauvegardé: {filename}")


# ==========================================
# 🧪 EXEMPLES
# ==========================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("📚 ANILIST API - TEST")
    print("="*60 + "\n")
    
    api = AniListAPI()
    
    # 1. Recherche d'anime
    print("1️⃣ Recherche d'anime: Naruto")
    results = api.search_media("Naruto", media_type="ANIME", limit=3)
    for r in results:
        print(f"   📺 {r['title']} - Score: {r['score']}")
    
    print()
    
    # 2. Recherche de manhwa (coréen)
    print("2️⃣ Recherche de manhwa: Solo Leveling")
    manhwa = api.search_manhwa("Solo Leveling", limit=3)
    for m in manhwa:
        print(f"   📖 {m['title']} (KR) - Score: {m['score']}")
    
    print()
    
    # 3. Trending animes
    print("3️⃣ Top 5 trending animes:")
    trending = api.get_trending(media_type="ANIME", limit=5)
    for i, t in enumerate(trending, 1):
        print(f"   {i}. {t['title']} - Score: {t['score']}")
    
    print()
    
    # 4. Détails d'un média
    print("4️⃣ Détails de Solo Leveling:")
    details = api.get_media_details(105398)  # ID de Solo Leveling
    if details:
        print(f"   📚 {details['title']}")
        print(f"   🇰🇷 Pays: {details['country']}")
        print(f"   ⭐ Score: {details['score']}")
        print(f"   📖 Chapitres: {details['chapters']}")
    
    print("\n✅ Test terminé!\n")
