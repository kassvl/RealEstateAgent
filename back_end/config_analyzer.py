#!/usr/bin/env python3
"""
Script de configuration pour l'analyseur de pièces.
Aide à ajuster les paramètres selon vos limites API.
"""

import os
from analyze_the_rooms import RoomAnalyzer

def test_api_limits():
    """Teste les limites de l'API et suggère des paramètres optimaux."""
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Erreur: Définissez d'abord votre clé API Gemini:")
        print("   export GEMINI_API_KEY='votre_clé_api_ici'")
        return
    
    print("🔧 Configuration de l'Analyseur de Pièces")
    print("=" * 50)
    
    # Test avec différents délais
    test_delays = [0.5, 1.0, 2.0, 3.0]
    
    for delay in test_delays:
        print(f"\n🧪 Test avec délai de {delay}s entre les appels...")
        
        try:
            # Créer un analyseur de test
            analyzer = RoomAnalyzer(
                api_key, 
                enable_duplicate_detection=False,  # Désactivé pour le test
                api_delay=delay
            )
            
            # Test simple avec une image factice
            test_payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": "Test de connexion API"
                            }
                        ]
                    }
                ]
            }
            
            result = analyzer._make_gemini_request(test_payload)
            
            if result:
                print(f"✅ Délai de {delay}s fonctionne")
                recommended_delay = delay
                break
            else:
                print(f"❌ Délai de {delay}s insuffisant")
                
        except Exception as e:
            print(f"❌ Erreur avec délai de {delay}s: {e}")
    
    # Recommandations
    print("\n📋 RECOMMANDATIONS")
    print("=" * 30)
    
    if 'recommended_delay' in locals():
        print(f"✅ Délai recommandé: {recommended_delay}s")
        
        if recommended_delay <= 1.0:
            print("🚀 Votre API supporte un traitement rapide")
            print("   → Vous pouvez activer la détection des doublons")
            duplicate_detection = True
        else:
            print("⚠️ Votre API nécessite des délais plus longs")
            print("   → Considérez désactiver la détection des doublons pour de gros volumes")
            duplicate_detection = False
            
        # Génère le code de configuration
        print(f"\n💻 CODE DE CONFIGURATION RECOMMANDÉ:")
        print("-" * 40)
        print(f"analyzer = RoomAnalyzer(")
        print(f"    api_key,")
        print(f"    enable_duplicate_detection={duplicate_detection},")
        print(f"    api_delay={recommended_delay}")
        print(f")")
        
    else:
        print("❌ Impossible de déterminer un délai optimal")
        print("   → Essayez avec un délai de 5.0s ou plus")
        print("   → Vérifiez votre quota API Gemini")

def show_quota_info():
    """Affiche des informations sur les quotas API."""
    
    print("\n📊 INFORMATIONS SUR LES QUOTAS GEMINI")
    print("=" * 45)
    print("🔗 Consultez vos quotas: https://makersuite.google.com/app/apikey")
    print()
    print("📈 Limites typiques (version gratuite):")
    print("   • 15 requêtes par minute")
    print("   • 1 500 requêtes par jour")
    print("   • 32 000 tokens par minute")
    print()
    print("⚡ Conseils d'optimisation:")
    print("   • Utilisez api_delay >= 4.0s pour rester sous 15 req/min")
    print("   • Désactivez la détection des doublons pour de gros volumes")
    print("   • Traitez les annonces par petits lots")
    print("   • Surveillez votre usage quotidien")

def interactive_config():
    """Configuration interactive."""
    
    print("\n🎛️ CONFIGURATION INTERACTIVE")
    print("=" * 35)
    
    # Nombre d'images typique
    try:
        num_images = int(input("📸 Nombre d'images typique par annonce (ex: 15): "))
    except ValueError:
        num_images = 15
    
    # Fréquence d'utilisation
    print("\n📅 Fréquence d'utilisation prévue:")
    print("1. Occasionnelle (quelques annonces par jour)")
    print("2. Régulière (10-20 annonces par jour)")
    print("3. Intensive (50+ annonces par jour)")
    
    try:
        frequency = int(input("Votre choix (1-3): "))
    except ValueError:
        frequency = 1
    
    # Calcul des recommandations
    if frequency == 1:
        recommended_delay = 1.0
        enable_duplicates = True
        batch_size = "Toutes les images d'un coup"
    elif frequency == 2:
        recommended_delay = 2.0
        enable_duplicates = True
        batch_size = "Par groupes de 10 images"
    else:
        recommended_delay = 4.0
        enable_duplicates = False
        batch_size = "Par groupes de 5 images"
    
    # Estimation du temps
    time_per_image = recommended_delay
    if enable_duplicates:
        # Temps supplémentaire pour les comparaisons
        comparisons = (num_images * (num_images - 1)) // 2
        time_per_image += (comparisons * recommended_delay) / num_images
    
    total_time = num_images * time_per_image
    
    print(f"\n⏱️ ESTIMATION DU TEMPS DE TRAITEMENT")
    print("-" * 40)
    print(f"📸 {num_images} images par annonce")
    print(f"⏳ ~{total_time:.1f} secondes par annonce")
    print(f"🔄 Détection des doublons: {'Activée' if enable_duplicates else 'Désactivée'}")
    print(f"📦 Traitement recommandé: {batch_size}")
    
    print(f"\n💻 CONFIGURATION RECOMMANDÉE:")
    print("-" * 35)
    print(f"analyzer = RoomAnalyzer(")
    print(f"    api_key,")
    print(f"    enable_duplicate_detection={enable_duplicates},")
    print(f"    api_delay={recommended_delay}")
    print(f")")

if __name__ == '__main__':
    print("🏠 Configurateur d'Analyseur de Pièces")
    print("=====================================")
    
    while True:
        print("\n📋 OPTIONS DISPONIBLES:")
        print("1. 🧪 Tester les limites API")
        print("2. 📊 Informations sur les quotas")
        print("3. 🎛️ Configuration interactive")
        print("4. 🚪 Quitter")
        
        try:
            choice = int(input("\nVotre choix (1-4): "))
        except ValueError:
            choice = 0
        
        if choice == 1:
            test_api_limits()
        elif choice == 2:
            show_quota_info()
        elif choice == 3:
            interactive_config()
        elif choice == 4:
            print("👋 Au revoir !")
            break
        else:
            print("❌ Choix invalide, veuillez réessayer.") 