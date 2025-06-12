#!/usr/bin/env python3
"""
Script de test pour démontrer l'optimisation du mode batch.
Compare l'ancien mode (requêtes multiples) avec le nouveau mode batch (1 seule requête).
"""

import os
import time
from analyze_the_rooms import RoomAnalyzer

def test_batch_optimization():
    """Test comparatif entre mode batch et mode individuel."""
    
    # Vérifier la clé API
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Erreur: Définissez votre clé API Gemini:")
        print("   export GEMINI_API_KEY='votre_clé_api_ici'")
        return
    
    print("🚀 TEST D'OPTIMISATION - MODE BATCH vs MODE INDIVIDUEL")
    print("=" * 60)
    
    # URL de test
    test_url = "https://www.otodom.pl/pl/oferta/mieszkanie-siedlce-ul-pomorska-do-wprowadzenia-ID4voOa"
    print(f"🏠 URL de test: {test_url}")
    
    # Configuration des analyseurs
    print("\n⚙️ Configuration des analyseurs...")
    
    # Mode batch - UNE SEULE requête LLM
    analyzer_batch = RoomAnalyzer(
        gemini_api_key=api_key,
        enable_duplicate_detection=True,
        api_delay=1.0,
        batch_mode=True  # ✨ NOUVELLE FONCTIONNALITÉ
    )
    
    # Mode individuel - MULTIPLES requêtes LLM
    analyzer_individual = RoomAnalyzer(
        gemini_api_key=api_key,
        enable_duplicate_detection=True,
        api_delay=1.0,
        batch_mode=False  # Mode traditionnel
    )
    
    print("✅ Analyseurs configurés")
    
    # TEST 1: Mode batch
    print(f"\n🚀 TEST 1: MODE BATCH (1 requête LLM)")
    print("-" * 40)
    start_time = time.time()
    
    results_batch = analyzer_batch.analyze_listing_rooms(test_url)
    
    batch_time = time.time() - start_time
    batch_success = 'error' not in results_batch
    
    if batch_success:
        print(f"✅ Mode batch réussi!")
        print(f"⏱️  Temps d'exécution: {batch_time:.1f} secondes")
        print(f"📊 Images analysées: {results_batch['successfully_classified']}/{results_batch['total_images']}")
        print(f"🏠 Pièces habitables: {results_batch['habitable_rooms_count']}")
        print(f"🔍 Doublons détectés: {results_batch['duplicate_images_found']}")
    else:
        print(f"❌ Mode batch échoué: {results_batch.get('error', 'Erreur inconnue')}")
    
    # TEST 2: Mode individuel
    print(f"\n🔄 TEST 2: MODE INDIVIDUEL (requêtes multiples)")
    print("-" * 40)
    start_time = time.time()
    
    results_individual = analyzer_individual.analyze_listing_rooms(test_url)
    
    individual_time = time.time() - start_time
    individual_success = 'error' not in results_individual
    
    if individual_success:
        print(f"✅ Mode individuel réussi!")
        print(f"⏱️  Temps d'exécution: {individual_time:.1f} secondes")
        print(f"📊 Images analysées: {results_individual['successfully_classified']}/{results_individual['total_images']}")
        print(f"🏠 Pièces habitables: {results_individual['habitable_rooms_count']}")
        print(f"🔍 Doublons détectés: {results_individual['duplicate_images_found']}")
    else:
        print(f"❌ Mode individuel échoué: {results_individual.get('error', 'Erreur inconnue')}")
    
    # COMPARAISON DES RÉSULTATS
    print(f"\n📊 COMPARAISON DES RÉSULTATS")
    print("=" * 40)
    
    if batch_success and individual_success:
        # Comparaison temporelle
        print(f"⏱️  PERFORMANCE:")
        print(f"   Mode batch:     {batch_time:.1f}s")
        print(f"   Mode individuel: {individual_time:.1f}s")
        
        if batch_time > 0:
            speedup = individual_time / batch_time
            print(f"   Accélération:   {speedup:.1f}x")
            
            if speedup > 1:
                time_saved = individual_time - batch_time
                print(f"   ⚡ Gain de temps: {time_saved:.1f}s ({((speedup-1)*100):.1f}% plus rapide)")
            else:
                print(f"   ⚠️ Le mode batch n'est pas plus rapide dans ce cas")
        
        # Comparaison des résultats
        print(f"\n🎯 PRÉCISION:")
        batch_rooms = results_batch['habitable_rooms_count']
        individual_rooms = results_individual['habitable_rooms_count']
        
        print(f"   Pièces habitables (batch):     {batch_rooms}")
        print(f"   Pièces habitables (individuel): {individual_rooms}")
        
        if batch_rooms == individual_rooms:
            print(f"   ✅ Résultats identiques!")
        else:
            diff = abs(batch_rooms - individual_rooms)
            print(f"   ⚠️ Différence de {diff} pièce(s)")
        
        # Comparaison des doublons
        batch_duplicates = results_batch['duplicate_images_found']
        individual_duplicates = results_individual['duplicate_images_found']
        
        print(f"   Doublons détectés (batch):     {batch_duplicates}")
        print(f"   Doublons détectés (individuel): {individual_duplicates}")
        
        if batch_duplicates == individual_duplicates:
            print(f"   ✅ Détection des doublons identique!")
        else:
            diff = abs(batch_duplicates - individual_duplicates)
            print(f"   ⚠️ Différence de {diff} doublon(s)")
        
        # Estimation des requêtes économisées
        total_images = results_batch['total_images']
        estimated_requests_individual = total_images + batch_duplicates  # classification + comparaisons
        estimated_requests_batch = 1  # Une seule requête
        
        print(f"\n💰 ÉCONOMIES API:")
        print(f"   Requêtes estimées (individuel): {estimated_requests_individual}")
        print(f"   Requêtes utilisées (batch):     {estimated_requests_batch}")
        requests_saved = estimated_requests_individual - estimated_requests_batch
        print(f"   🎉 Requêtes économisées: {requests_saved}")
        
    elif batch_success and not individual_success:
        print("✅ Seul le mode batch a fonctionné")
        print("💡 Le mode batch est plus robuste pour cette annonce")
        
    elif not batch_success and individual_success:
        print("⚠️ Seul le mode individuel a fonctionné")
        print("💡 Le mode batch nécessite peut-être des ajustements")
        
    else:
        print("❌ Les deux modes ont échoué")
        print("💡 Vérifiez votre clé API et votre connexion")
    
    # Conseils d'utilisation
    print(f"\n💡 RECOMMANDATIONS")
    print("=" * 30)
    if batch_success:
        print("✅ Utilisez le mode batch pour:")
        print("   • Analyses rapides")
        print("   • Économiser les requêtes API")
        print("   • Réduire les coûts")
        print("\n   Exemple de code:")
        print("   analyzer = RoomAnalyzer(api_key, batch_mode=True)")
    
    if individual_success:
        print("\n🔄 Utilisez le mode individuel pour:")
        print("   • Maximum de précision")
        print("   • Débogage détaillé")
        print("   • Compatibilité avec l'ancien code")
        print("\n   Exemple de code:")
        print("   analyzer = RoomAnalyzer(api_key, batch_mode=False)")

if __name__ == '__main__':
    test_batch_optimization() 