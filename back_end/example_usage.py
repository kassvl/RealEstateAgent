#!/usr/bin/env python3
"""
Exemple d'utilisation de l'analyseur de pièces.
Ce script montre comment utiliser la classe RoomAnalyzer pour analyser 
les pièces d'une annonce immobilière.
"""

import os
import time
import logging # Added import
from analyze_the_rooms import RoomAnalyzer
from dotenv import load_dotenv  # NEW: import load_dotenv to read .env

# NEW: Load environment variables from .env if present
load_dotenv()

def analyze_property_example():
    """Exemple d'analyse d'une propriété."""
    
    # Vérifiez que votre clé API Gemini est définie
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Erreur: Définissez d'abord votre clé API Gemini:")
        print("   export GEMINI_API_KEY='votre_clé_api_ici'")
        return
    
    print("🏠 Démarrage de l'analyse des pièces...")
    
    # Configuration - vous pouvez changer batch_mode selon vos besoins
    BATCH_MODE = True  # Changez à False pour utiliser le mode individuel
    
    if BATCH_MODE:
        print("\n🚀 === MODE BATCH (UNE SEULE REQUÊTE LLM) ===")
        analyzer = RoomAnalyzer(
            api_key, 
            enable_duplicate_detection=True,  # Détection des doublons incluse dans la requête batch
            api_delay=1.0,  # Délai moins important en mode batch
            batch_mode=True  # Mode batch activé
        )
    else:
        print("\n🔄 === MODE INDIVIDUEL (REQUÊTES MULTIPLES) ===")
        analyzer = RoomAnalyzer(
            api_key, 
            enable_duplicate_detection=True,
            api_delay=2.0,  # Délai plus long nécessaire pour les requêtes multiples
            batch_mode=False  # Mode traditionnel
        )
    
    # URLs d'exemple - vous pouvez modifier ces URLs
    test_urls = [
        "https://www.otodom.pl/pl/oferta/mieszkanie-siedlce-ul-pomorska-do-wprowadzenia-ID4voOa",
        # Ajoutez d'autres URLs ici si nécessaire
    ]
    
    for i, url in enumerate(test_urls, 1):
        print(f"\n📊 Analyse de la propriété {i}/{len(test_urls)}")
        print(f"🔗 URL: {url}")
        
        # Mesurer le temps d'exécution
        start_time = time.time()
        
        # Analyser l'annonce
        results = analyzer.analyze_listing_rooms(url)
        
        execution_time = time.time() - start_time
        
        if 'error' in results:
            print(f"❌ Erreur: {results['error']}")
            continue
        
        # Afficher les résultats de manière formatée
        print_formatted_results(results, analyzer, execution_time, BATCH_MODE)
        
        # Sauvegarder les résultats
        mode_suffix = "batch" if BATCH_MODE else "individual"
        output_filename = f'analysis_results_{mode_suffix}_{i}.json'
        analyzer.save_analysis_results(results, output_filename)
        print(f"💾 Résultats sauvegardés dans {output_filename}")

def print_formatted_results(results, analyzer, execution_time, batch_mode):
    """Affiche les résultats de manière formatée."""
    
    mode_name = "BATCH" if batch_mode else "INDIVIDUEL"
    mode_emoji = "🚀" if batch_mode else "🔄"
    
    print("\n" + "="*60)
    print(f"📋 RÉSULTATS DE L'ANALYSE - MODE {mode_name} {mode_emoji}")
    print("="*60)
    
    # Informations générales
    listing_details = results.get('listing_details', {})
    print(f"🏷️  Titre: {listing_details.get('title', 'Non disponible')}")
    print(f"📍 Localisation: {listing_details.get('location_string', 'Non disponible')}")
    print(f"💰 Prix: {listing_details.get('price', 'Non disponible')} {listing_details.get('currency', '')}")
    
    # Informations sur les performances
    print(f"\n⚡ PERFORMANCE")
    print(f"   • Temps d'exécution: {execution_time:.1f} secondes")
    print(f"   • Mode utilisé: {mode_name}")
    
    if batch_mode:
        estimated_individual_requests = results['total_images'] + results.get('duplicate_images_found', 0)
        print(f"   • Requêtes économisées: {estimated_individual_requests - 1} (par rapport au mode individuel)")
    
    # Statistiques d'analyse
    print(f"\n📊 STATISTIQUES D'ANALYSE")
    print(f"   • Images totales: {results['total_images']}")
    classified_count = sum(v for k, v in results.get('room_summary', {}).items() if k != 'other')
    print(f"   • Pièces uniques classifiées (hors 'other'): {classified_count}")
    print(f"   • Pièces uniques détectées: {results['unique_rooms_detected']}")
    print(f"   • Images identifiées comme doublons: {results.get('duplicate_images_found', 0)}")
    print(f"   • Pièces habitables (uniques): {results['habitable_rooms_count']}")
    
    # Résumé des pièces
    if results['room_summary']:
        print(f"\n🏠 TYPES DE PIÈCES DÉTECTÉES")
        for room_type_id, count in results['room_summary'].items():
            room_details = analyzer.get_room_type_by_id(room_type_id)
            if room_details:
                habitable_emoji = "🛏️" if room_details['is_habitable'] else "🚿"
                print(f"   {habitable_emoji} {room_details['name']}: {count} pièce(s)")
            else:
                print(f"   ❓ {room_type_id}: {count} pièce(s)")
    
    # Détails par image (version condensée)
    print(f"\n🖼️  ANALYSE DÉTAILLÉE PAR IMAGE")
    for classification in results.get('room_classifications_processed', []):
        image_num = classification['image_index'] + 1
        room_type_id = classification.get('room_type_id')
        
        if room_type_id:
            room_details = classification.get('room_type_details', {})
            room_name = room_details.get('name', room_type_id) if room_details else room_type_id
            habitable = room_details.get('is_habitable') if room_details else None
            
            # Détermine le statut de l'image
            if classification.get('is_duplicate', False):
                status_emoji = "🔄"  # Emoji pour doublon
                duplicate_text = " (DOUBLON)"
            else:
                status_emoji = "✅" if room_type_id != 'other' else "❓"
                duplicate_text = ""
            
            habitable_text = " (habitable)" if habitable is True else " (non-habitable)" if habitable is False else ""
            
            # Affiche les informations de base
            print(f"   {status_emoji} Image {image_num}: {room_name}{habitable_text}{duplicate_text}")
            
            # Affiche les liens avec d'autres images si c'est la même pièce
            same_room_as = classification.get('same_room_as', [])
            if same_room_as:
                linked_images = [str(idx + 1) for idx in same_room_as]
                print(f"      🔗 Même pièce que image(s): {', '.join(linked_images)}")
        else:
            error_msg = classification.get('error', 'Classification échouée')
            print(f"   ❌ Image {image_num}: {error_msg}")

def show_available_room_types():
    """Affiche les types de pièces disponibles."""
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Clé API non définie")
        return
    
    analyzer = RoomAnalyzer(api_key)
    
    print("\n🏠 TYPES DE PIÈCES DISPONIBLES")
    print("=" * 40)
    
    habitable_rooms = []
    non_habitable_rooms = []
    
    for room_type in analyzer.room_types:
        if room_type['is_habitable']:
            habitable_rooms.append(room_type)
        else:
            non_habitable_rooms.append(room_type)
    
    print(f"\n✅ PIÈCES HABITABLES ({len(habitable_rooms)}):")
    for room in habitable_rooms:
        print(f"  • {room['name']} ({room['id']})")
        print(f"    {room['description']}")
    
    print(f"\n🚫 PIÈCES NON-HABITABLES ({len(non_habitable_rooms)}):")
    for room in non_habitable_rooms:
        print(f"  • {room['name']} ({room['id']})")
        print(f"    {room['description']}")

if __name__ == '__main__':
    # Configure logging to see DEBUG messages from RoomAnalyzer
    logger = logging.getLogger('analyze_the_rooms.RoomAnalyzer') # Get the specific logger
    logger.setLevel(logging.DEBUG) # Set it to DEBUG
    # Add a console handler if it doesn't have one
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    print("🏠 Analyseur de Pièces Immobilières")
    print("=" * 40)
    print("\n🚀 Lancement direct de l'analyse de propriété pour test...")
    analyze_property_example()
    print("\n✅ Analyse terminée.") 