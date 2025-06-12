#!/usr/bin/env python3
"""
Script de démarrage pour l'interface web de l'analyseur de pièces.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

def check_requirements():
    """Vérifie que les dépendances sont installées."""
    try:
        import flask
        import requests
        import PIL
        from analyze_the_rooms import RoomAnalyzer
        print("✅ Toutes les dépendances sont installées")
        return True
    except ImportError as e:
        print(f"❌ Dépendance manquante: {e}")
        print("💡 Installez les dépendances avec: pip install -r requirements.txt")
        return False

def check_api_key():
    """Vérifie que la clé API est configurée."""
    api_key = os.getenv('GEMINI_API_KEY')
    if api_key:
        print("✅ Clé API Gemini configurée")
        return True
    else:
        print("⚠️  Clé API Gemini non configurée")
        print("💡 Définissez-la avec: export GEMINI_API_KEY='votre_clé_api'")
        print("🔗 Obtenez une clé sur: https://makersuite.google.com/app/apikey")
        return False

def main():
    """Fonction principale."""
    print("🌐 Démarrage de l'Interface Web - Analyseur de Pièces")
    print("=" * 55)
    
    # Vérifications
    if not check_requirements():
        sys.exit(1)
    
    check_api_key()  # Pas bloquant, juste informatif
    
    print("\n🚀 Lancement du serveur web...")
    print("📍 URL: http://localhost:5002")
    print("🛑 Arrêtez avec Ctrl+C")
    print("-" * 40)
    
    # Importer et lancer l'application
    try:
        from web_interface import app
        app.run(debug=False, host='0.0.0.0', port=5002)
    except KeyboardInterrupt:
        print("\n👋 Serveur arrêté")
    except Exception as e:
        print(f"\n❌ Erreur lors du démarrage: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 