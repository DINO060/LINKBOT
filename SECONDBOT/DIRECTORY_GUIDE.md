# 🌐 Guide d'utilisation du Directory Scraper

## Nouvelles fonctionnalités ajoutées!

Le bot peut maintenant **scraper n'importe quel site d'annuaire** pour trouver des sites selon tes critères!

## 🚀 Commandes disponibles:

### 1. Rechercher dans un annuaire
```
/directory <url_du_site> <mot-clé>
```

**Exemple:**
```
/directory https://sitecatalog.com gaming
```

**Ce que ça fait:**
- Visite le site d'annuaire
- Cherche tous les liens qui correspondent au mot-clé
- Te retourne une liste organisée avec:
  - Titre du site
  - URL
  - Description
- Sauvegarde tout en JSON

---

### 2. Extraire TOUS les sites d'un annuaire
```
/findsites <url_du_site>
```

**Exemple:**
```
/findsites https://sitecatalog.com
```

**Ce que ça fait:**
- Scrape tout le site d'annuaire
- Extrait tous les liens externes
- Organise par catégories automatiquement
- Te donne un fichier JSON avec tous les sites

---

## 💡 Cas d'usage:

### Scénario 1: Tu veux des sites de streaming
```
/directory https://example-directory.com streaming
```
➡️ Le bot va te trouver tous les sites de streaming listés sur cet annuaire

### Scénario 2: Tu veux voir tout ce qu'un annuaire propose
```
/findsites https://example-directory.com
```
➡️ Le bot extrait TOUS les sites et te donne un fichier JSON complet

### Scénario 3: Recherche spécifique
```
/directory https://tools-directory.com "video editing"
```
➡️ Trouve tous les outils d'édition vidéo

---

## 📊 Format des résultats:

Le bot te renvoie:

1. **Message Telegram** avec les meilleurs résultats
2. **Fichier JSON** avec toutes les infos détaillées:
```json
[
  {
    "title": "Nom du site",
    "url": "https://example.com",
    "description": "Description du site...",
    "category": "Catégorie"
  }
]
```

---

## 🎯 Comment ça marche?

1. **Tu donnes une URL d'annuaire** (un site qui liste d'autres sites)
2. **Tu donnes un mot-clé** (optionnel)
3. **Le bot:**
   - Visite le site
   - Parse tout le HTML
   - Trouve tous les liens
   - Filtre selon ton mot-clé
   - Extrait les descriptions
   - Organise par catégories
   - Te renvoie tout bien formaté!

---

## 🔥 Exemples de sites d'annuaires compatibles:

- Sites de catalogues/listes de ressources
- Annuaires de sites web
- Pages "awesome lists"
- Sites de répertoires
- Catalogues en ligne
- Tout site qui liste d'autres sites!

---

## ⚡ Tips:

1. **Sois spécifique dans ta recherche:**
   ```
   ❌ /directory https://site.com video
   ✅ /directory https://site.com "video streaming"
   ```

2. **Le bot filtre intelligemment:**
   - Ignore les liens internes
   - Évite les doublons
   - Classe par pertinence

3. **Utilise les fichiers JSON:**
   - Plus complet que le message
   - Peut être utilisé dans d'autres scripts
   - Facile à partager

---

## 🛠️ Code utilisable indépendamment:

Tu peux aussi utiliser le scraper directement dans Python:

```python
from directory_scraper import DirectoryScraper

scraper = DirectoryScraper()

# Recherche avec mot-clé
results = scraper.search_in_directory(
    "https://example.com", 
    "gaming", 
    max_results=20
)

# Extraire tout
all_sites = scraper.scrape_directory_site("https://example.com")

# Par catégories
categorized = scraper.scrape_with_categories("https://example.com")
```

---

## 🎊 C'est tout!

Maintenant tu peux scraper n'importe quel site d'annuaire et trouver exactement ce que tu cherches! 🚀
