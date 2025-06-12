# 🌐 Interface Web - Analyseur de Pièces Immobilières

Interface web simple et moderne pour tester l'analyseur de pièces. Entrez simplement une URL d'annonce Otodom et obtenez les résultats en temps réel.

## 🚀 Démarrage Rapide

### 1. Installation des dépendances
```bash
cd back_end
pip install -r requirements.txt
```

### 2. Configuration de la clé API
```bash
export GEMINI_API_KEY='votre_clé_api_gemini'
```

### 3. Lancement du serveur
```bash
python start_web.py
```

### 4. Accès à l'interface
Ouvrez votre navigateur sur : **http://localhost:5000**

## 🎯 Fonctionnalités

### ✨ **Interface Moderne**
- Design responsive et moderne
- Barre de progression en temps réel
- Affichage des résultats interactif
- Compatible mobile et desktop

### 🔍 **Analyse Simplifiée**
- **Entrée** : Collez simplement l'URL de l'annonce
- **Traitement** : Analyse automatique en arrière-plan
- **Résultats** : Affichage détaillé et téléchargement JSON

### ⚡ **Mode Batch Intégré**
- Utilise automatiquement le mode batch optimisé
- Une seule requête LLM pour toute l'analyse
- Temps d'exécution réduit de 80%

## 📊 Informations Affichées

### 📋 **Résumé de l'Annonce**
- Titre de la propriété
- Localisation
- Prix
- Statistiques générales

### 🏠 **Analyse des Pièces**
- Types de pièces détectées
- Nombre de pièces habitables
- Détection des doublons
- Classification détaillée par image

### 📈 **Métriques de Performance**
- Temps d'exécution
- Mode utilisé (Batch/Individuel)
- Nombre d'images analysées
- Requêtes API économisées

## 🛠️ Configuration

### Mode d'Analyse
Modifiez le mode dans `web_interface.py` :
```python
# Ligne 15
BATCH_MODE = True   # Mode batch (recommandé)
BATCH_MODE = False  # Mode individuel
```

### Port du Serveur
Changez le port dans `start_web.py` ou `web_interface.py` :
```python
app.run(debug=False, host='0.0.0.0', port=5000)  # Changez 5000
```

## 📁 Structure des Fichiers

```
back_end/
├── web_interface.py          # Serveur Flask principal
├── start_web.py             # Script de démarrage
├── templates/
│   └── index.html           # Interface utilisateur
├── static/
│   ├── css/                 # Styles (intégrés dans HTML)
│   ├── js/                  # Scripts (intégrés dans HTML)
│   └── results/             # Fichiers de résultats générés
└── requirements.txt         # Dépendances (Flask ajouté)
```

## 🔄 API Endpoints

### `GET /`
Page principale avec l'interface utilisateur

### `POST /analyze`
Lance une nouvelle analyse
```json
{
  "url": "https://www.otodom.pl/pl/oferta/..."
}
```

### `GET /status/<analysis_id>`
Récupère le statut d'une analyse en cours
```json
{
  "status": "running",
  "progress": 45,
  "message": "Analyse des images..."
}
```

### `GET /results/<analysis_id>`
Récupère les résultats complets d'une analyse terminée

### `GET /config`
Retourne la configuration actuelle
```json
{
  "batch_mode": true,
  "api_configured": true
}
```

### `GET /download/<filename>`
Télécharge un fichier de résultats JSON

## 🎨 Interface Utilisateur

### 🖥️ **Design Responsive**
- **Desktop** : Interface complète avec grilles
- **Mobile** : Layout adaptatif et optimisé
- **Tablette** : Affichage intermédiaire

### 🎯 **Expérience Utilisateur**
1. **Saisie** : Champ URL avec validation
2. **Progression** : Barre de progression animée
3. **Résultats** : Cartes organisées et lisibles
4. **Téléchargement** : Export JSON des résultats

### 🎨 **Éléments Visuels**
- **Couleurs** : Dégradés modernes bleu/violet
- **Icônes** : Emojis pour une interface friendly
- **Animations** : Transitions fluides
- **Feedback** : Messages d'état clairs

## 🐛 Dépannage

### Erreur "Module not found"
```bash
pip install -r requirements.txt
```

### Erreur "API Key not configured"
```bash
export GEMINI_API_KEY='votre_clé_api'
# Ou définissez-la dans votre .bashrc/.zshrc
```

### Port déjà utilisé
```bash
# Changez le port dans start_web.py
app.run(debug=False, host='0.0.0.0', port=5001)  # Nouveau port
```

### Analyse qui ne démarre pas
- Vérifiez votre connexion internet
- Vérifiez que l'URL Otodom est valide
- Vérifiez les logs du serveur dans le terminal

## 🔒 Sécurité

### 🛡️ **Considérations**
- L'interface est prévue pour un usage local/développement
- Pas d'authentification implémentée
- Les clés API sont stockées en variables d'environnement

### 🚀 **Pour la Production**
- Ajoutez une authentification
- Utilisez HTTPS
- Configurez un reverse proxy (nginx)
- Limitez les taux de requêtes

## 📈 Optimisations

### ⚡ **Performance**
- Traitement asynchrone des analyses
- Cache des résultats
- Compression des réponses JSON

### 💾 **Stockage**
- Résultats sauvegardés automatiquement
- Nettoyage automatique des anciens fichiers
- Export JSON pour archivage

## 🎉 Fonctionnalités Futures

- **Upload d'images** : Analyse d'images locales
- **Historique** : Sauvegarde des analyses précédentes
- **Comparaison** : Comparaison entre plusieurs annonces
- **API REST** : API complète pour intégrations
- **Authentification** : Système de comptes utilisateurs
- **Dashboard** : Tableau de bord avec statistiques 