# 🏠 Analyseur de Pièces Immobilières

Ce système utilise l'API Gemini de Google pour analyser automatiquement les types de pièces dans les annonces immobilières d'Otodom. Il récupère les images des annonces et les classifie selon des catégories prédéfinies.

## 📋 Fonctionnalités

- **Scraping automatique** des images d'annonces Otodom
- **Classification IA** des pièces avec Gemini 2.5 Flash
- **Détection des doublons** - Identifie les images montrant la même pièce
- **27 types de pièces** prédéfinis (voir `room_type_classes.json`)
- **Distinction habitables/non-habitables** pour le calcul des surfaces
- **Comptage précis** des pièces uniques (sans doublons)
- **Sauvegarde des résultats** en format JSON
- **Interface en français**

## 🚀 Installation

### 1. Prérequis

```bash
# Python 3.8 ou plus récent
python --version

# Pip pour installer les dépendances
pip --version
```

### 2. Installation des dépendances

```bash
cd back_end
pip install -r requirements.txt
```

### 3. Configuration de l'API Gemini

1. Obtenez une clé API Gemini depuis [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Définissez la variable d'environnement :

```bash
# Linux/macOS
export GEMINI_API_KEY='votre_clé_api_ici'

# Windows (Command Prompt)
set GEMINI_API_KEY=votre_clé_api_ici

# Windows (PowerShell)
$env:GEMINI_API_KEY="votre_clé_api_ici"
```

## 📖 Utilisation

### Configuration des limites API

**Important :** Avant la première utilisation, configurez les paramètres selon vos quotas API :

```bash
python config_analyzer.py
```

Ce script vous aidera à :
- Tester vos limites API
- Déterminer le délai optimal entre les appels
- Configurer la détection des doublons selon votre usage

### Utilisation simple avec l'exemple

```bash
python example_usage.py
```

Ce script vous montrera :
- Les types de pièces disponibles
- Un exemple d'analyse d'une annonce Otodom

### Utilisation programmatique

```python
from analyze_the_rooms import RoomAnalyzer
import os

# Initialiser l'analyseur
api_key = os.getenv('GEMINI_API_KEY')
analyzer = RoomAnalyzer(api_key)

# Analyser une annonce
url = "https://www.otodom.pl/pl/oferta/votre-annonce-ID"
results = analyzer.analyze_listing_rooms(url)

# Afficher les résultats
if 'error' not in results:
    print(f"Pièces habitables trouvées: {results['habitable_rooms_count']}")
    print(f"Types de pièces: {results['room_summary']}")
```

### Test du scraper uniquement

```bash
python scraper_otodom.py
```

## 📊 Types de Pièces Supportés

Le système reconnaît 27 types de pièces, organisés en catégories :

### 🛏️ Pièces Habitables
- Oturma Odası (Salon)
- Yemek Odası (Salle à manger)
- Yatak Odası (Chambre)
- Ebeveyn Yatak Odası (Chambre parentale)
- Mutfak (Cuisine)
- Çalışma Odası (Bureau)
- Çatı Katı (Grenier aménagé)
- Oyun Odası (Salle de jeux)
- Ev Sineması (Home cinéma)
- Spor Odası (Salle de sport)

### 🚿 Pièces Non-Habitables
- Banyo (Salle de bain)
- Tuvalet (WC)
- Balkon (Balcon)
- Teras (Terrasse)
- Bahçe (Jardin)
- Çamaşır Odası (Buanderie)
- Depo/Kiler (Débarras)
- Antre/Koridor (Couloir)
- Garaj (Garage)
- Bodrum Katı (Cave)
- Giyinme Odası (Dressing)
- Teknik Oda (Local technique)

## 📁 Structure des Fichiers

```
back_end/
├── analyze_the_rooms.py      # Module principal d'analyse
├── scraper_otodom.py         # Scraper pour Otodom
├── room_type_classes.json    # Définitions des types de pièces
├── example_usage.py          # Script d'exemple
├── requirements.txt          # Dépendances Python
└── README.md                # Ce fichier
```

## 🔧 API de la Classe RoomAnalyzer

### Constructeur
```python
RoomAnalyzer(gemini_api_key: str)
```

### Méthodes principales

#### `analyze_listing_rooms(listing_url: str) -> Dict`
Analyse toutes les pièces d'une annonce Otodom.

**Retourne :**
```python
{
    'listing_url': str,
    'listing_details': dict,           # Détails de l'annonce
    'total_images': int,               # Nombre total d'images
    'successfully_classified': int,     # Images classifiées avec succès
    'unique_rooms_detected': int,       # Pièces uniques (sans doublons)
    'duplicate_images_found': int,      # Nombre d'images dupliquées
    'room_classifications': list,       # Détails par image
    'room_summary': dict,              # Résumé par type (sans doublons)
    'room_summary_with_duplicates': dict, # Résumé avec doublons
    'habitable_rooms_count': int,      # Nombre de pièces habitables uniques
    'analysis_complete': bool
}
```

#### `get_room_type_by_id(room_id: str) -> Dict`
Récupère les détails d'un type de pièce par son ID.

#### `save_analysis_results(results: Dict, output_file: str)`
Sauvegarde les résultats dans un fichier JSON.

## 🔍 Détection des Pièces Identiques

Le système utilise l'IA Gemini pour comparer les images et détecter quand plusieurs photos montrent la même pièce physique. Cette fonctionnalité permet :

- **Comptage précis** des pièces réelles (sans compter les doublons)
- **Identification des angles multiples** d'une même pièce
- **Analyse plus fiable** de la superficie habitable

### Critères de Détection
Le système considère deux images comme montrant la même pièce si :
- Les meubles principaux sont identiques ou très similaires
- La disposition générale est la même
- Les fenêtres, portes et éléments architecturaux correspondent
- Seul l'angle de vue diffère

## 🔍 Format des Résultats

### Classification par Image
```python
{
    'image_index': int,                # Index de l'image (0-based)
    'image_url': str,                  # URL de l'image
    'room_type_id': str,              # ID du type de pièce
    'room_type_details': dict,         # Détails complets du type
    'is_habitable': bool,             # True si habitable
    'same_room_as': list,             # Indices des autres images de la même pièce
    'is_duplicate': bool              # True si cette image est un doublon
}
```

### Résumé des Pièces
```python
{
    'living_room': 1,                 # 1 salon
    'bedroom': 2,                     # 2 chambres
    'bathroom': 1,                    # 1 salle de bain
    'kitchen': 1                      # 1 cuisine
}
```

## ⚠️ Limitations et Considérations

### Limitations de l'API Gemini
- **Taille d'image** : Maximum 1024x1024 pixels (redimensionnement automatique)
- **Quota** : Vérifiez vos limites de quotas API
- **Coût** : Chaque analyse d'image consomme des tokens

### Précision de Classification
- La précision dépend de la qualité des images
- Certaines pièces ambiguës peuvent être classifiées comme 'other'
- Les images de mauvaise qualité peuvent affecter les résultats

### Gestion d'Erreurs
- Timeout automatique (30s pour téléchargement, 60s pour API)
- Retry automatique non implémenté
- Les erreurs de classification sont marquées mais n'arrêtent pas le processus

## 🐛 Dépannage

### Erreur "GEMINI_API_KEY non définie"
```bash
export GEMINI_API_KEY='votre_clé_api'
echo $GEMINI_API_KEY  # Vérifier que c'est défini
```

### Erreur 429 "Too Many Requests"
Si vous rencontrez des erreurs de limite de taux :

```python
# Solution 1: Augmenter le délai entre les appels
analyzer = RoomAnalyzer(api_key, api_delay=3.0)

# Solution 2: Désactiver la détection des doublons
analyzer = RoomAnalyzer(api_key, enable_duplicate_detection=False)

# Solution 3: Configuration optimale pour quota limité
analyzer = RoomAnalyzer(
    api_key, 
    enable_duplicate_detection=False,
    api_delay=4.0  # 15 requêtes max par minute
)
```

### Erreur de téléchargement d'images
- Vérifiez votre connexion internet
- Certains sites peuvent bloquer les requêtes automatisées
- Essayez avec un user-agent différent

### Erreur "room_type_classes.json non trouvé"
- Assurez-vous d'être dans le bon répertoire
- Le fichier doit être dans le même dossier que le script

### Classification incorrecte
- Vérifiez la qualité des images
- Certaines pièces peuvent nécessiter plus de contexte
- Considérez l'ajout de nouveaux types de pièces si nécessaire

## 🔮 Améliorations Futures

- [ ] Support pour d'autres sites immobiliers
- [ ] Cache local des images
- [ ] Interface web
- [ ] Analyse de la superficie par pièce
- [ ] Détection des caractéristiques spéciales (fenêtres, balcons, etc.)
- [ ] Export vers différents formats (Excel, PDF)
- [ ] Analyse de la qualité des pièces
- [ ] Système de retry automatique

## 📄 License

Ce projet est sous licence MIT. Voir le fichier LICENSE pour plus de détails.

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :

1. Fork le projet
2. Créer une branche pour votre fonctionnalité
3. Commit vos changements
4. Push vers la branche
5. Ouvrir une Pull Request

## 📞 Support

Pour toute question ou problème :
1. Vérifiez d'abord ce README
2. Regardez les issues existantes
3. Créez une nouvelle issue avec les détails

---

**Note :** Ce système utilise l'IA générative et peut parfois produire des classifications incorrectes. Toujours vérifier les résultats importants manuellement. 