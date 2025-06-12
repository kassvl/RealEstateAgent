#!/usr/bin/env python3
"""
Interface web pour l'analyseur de pièces immobilières.
Permet de tester l'analyse en entrant simplement une URL.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for
import os
import json
import time
from analyze_the_rooms import RoomAnalyzer
import threading
from models import db, Listing, ListingDetail, Image, RoomClassification, SameRoomRelation, AnalysisResult
from otodom_scraper import scrape_otodom_page, OTODOM_SEARCH_URL_WROCLAW

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Nécessaire pour les sessions

# Configuration de la base de données
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////Users/kadirhan/Desktop/ev/real_estate_agent_v2/back_end/real_estate_analysis.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Configuration
BATCH_MODE = True  # Changez à False pour utiliser le mode individuel
UPLOAD_FOLDER = 'static/results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DEFAULT_LANGUAGE = 'fr'  # Langue par défaut

# Variable globale pour stocker les résultats en cours (pour compatibilité)
analysis_results = {}

# Chargement des traductions
def load_translations():
    try:
        with open('translations.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Erreur lors du chargement des traductions: {e}")
        return {'fr': {}, 'en': {}}

# Traductions
translations = load_translations()

# Fonction pour obtenir une traduction
def get_text(key):
    lang = session.get('language', DEFAULT_LANGUAGE)
    if lang not in translations:
        lang = DEFAULT_LANGUAGE
    return translations[lang].get(key, key)

@app.route('/')
def index():
    """Page principale avec le formulaire."""
    # S'assurer que la langue est définie dans la session
    if 'language' not in session:
        session['language'] = DEFAULT_LANGUAGE
    
    return render_template('index.html', 
                           texts=translations[session.get('language', DEFAULT_LANGUAGE)],
                           current_lang=session.get('language', DEFAULT_LANGUAGE))

@app.route('/set_language/<lang>')
def set_language(lang):
    """Définit la langue de l'interface."""
    if lang in translations:
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/analyze', methods=['POST'])
def analyze():
    """Endpoint pour lancer l'analyse d'une URL."""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL manquante'}), 400
        
        # Vérifier la clé API
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            return jsonify({
                'error': 'Clé API Gemini non configurée. Définissez GEMINI_API_KEY dans les variables d\'environnement.'
            }), 500
        
        # Générer un ID unique pour cette analyse
        analysis_id = str(int(time.time()))
        
        # Veritabanında analiz kaydı oluştur
        with app.app_context():
            new_analysis = AnalysisResult(
                analysis_id=analysis_id,
                status='starting',
                progress=0,
                message='Initialisation de l\'analyse...'
            )
            db.session.add(new_analysis)
            db.session.commit()
        
        # Geriye dönük uyumluluk için global değişkene de ekle
        analysis_results[analysis_id] = {
            'status': 'starting',
            'progress': 0,
            'message': 'Initialisation de l\'analyse...',
            'url': url
        }
        
        # Récupérer la langue actuelle pour la passer au thread
        current_lang = session.get('language', DEFAULT_LANGUAGE)
        
        # Lancer l'analyse en arrière-plan
        thread = threading.Thread(
            target=run_analysis, 
            args=(analysis_id, url, api_key, current_lang)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'analysis_id': analysis_id,
            'message': 'Analyse démarrée',
            'batch_mode': BATCH_MODE
        })
        
    except Exception as e:
        return jsonify({'error': f'Erreur lors du démarrage: {str(e)}'}), 500

@app.route('/status/<analysis_id>')
def get_status(analysis_id):
    """Récupère le statut d'une analyse."""
    # Veritabanından analiz durumunu al
    with app.app_context():
        analysis = AnalysisResult.query.filter_by(analysis_id=analysis_id).first()
        
        if not analysis:
            # Geriye dönük uyumluluk için global değişkene bak
            if analysis_id not in analysis_results:
                return jsonify({'error': 'Analyse non trouvée'}), 404
            return jsonify(analysis_results[analysis_id])
        
        # Veritabanından alınan bilgileri JSON formatına dönüştür
        result = {
            'status': analysis.status,
            'progress': analysis.progress,
            'message': analysis.message,
            'execution_time': analysis.execution_time
        }
        
        # Eğer sonuçlar varsa ekle
        if analysis.room_summary:
            try:
                result['results'] = json.loads(analysis.room_summary)
            except:
                result['results'] = {}
        
        return jsonify(result)

@app.route('/results/<analysis_id>')
def get_results(analysis_id):
    """Récupère les résultats complets d'une analyse."""
    # Veritabanından analiz sonuçlarını al
    with app.app_context():
        analysis = AnalysisResult.query.filter_by(analysis_id=analysis_id).first()
        
        if not analysis:
            # Geriye dönük uyumluluk için global değişkene bak
            if analysis_id not in analysis_results:
                return jsonify({'error': 'Analyse non trouvée'}), 404
            result = analysis_results[analysis_id]
        else:
            # Vérifier si l'analyse est terminée
            if analysis.status != 'completed':
                return jsonify({'error': 'Analyse en cours ou échouée'}), 400
            
            # Veritabanından alınan bilgileri JSON formatına dönüştür
            result = {
                'status': analysis.status,
                'progress': analysis.progress,
                'message': analysis.message,
                'execution_time': analysis.execution_time
            }
            
            # Eğer sonuçlar varsa ekle
            if analysis.room_summary:
                try:
                    result_json = json.loads(analysis.room_summary)
                    print(f"[DEBUG] Room summary loaded from DB: {result_json.keys() if result_json else 'None'}")
                    result['results'] = result_json
                except Exception as e:
                    print(f"[ERROR] Failed to parse room summary: {e}")
                    result['results'] = {}
        
    return jsonify(result)

def run_analysis(analysis_id, url, api_key, lang=DEFAULT_LANGUAGE):
    """Exécute l'analyse en arrière-plan."""
    try:
        # Veritabanında analiz durumunu güncelle
        with app.app_context():
            analysis = AnalysisResult.query.filter_by(analysis_id=analysis_id).first()
            if analysis:
                analysis.status = 'processing'
                analysis.progress = 10
                analysis.message = translations[lang].get('status_starting', 'Démarrage de l\'analyse...')
                db.session.commit()
        
        # Geriye dönük uyumluluk için global değişkeni de güncelle
        if analysis_id in analysis_results:
            analysis_results[analysis_id].update({
                'status': 'processing',
                'progress': 10,
                'message': translations[lang].get('status_starting', 'Démarrage de l\'analyse...')
            })
        
        # Créer l'analyseur
        analyzer = RoomAnalyzer(
            gemini_api_key=api_key,
            enable_duplicate_detection=True,
            api_delay=1.0 if BATCH_MODE else 2.0,
            batch_mode=BATCH_MODE
        )
        
        # Veritabanında ilerleme durumunu güncelle
        with app.app_context():
            analysis = AnalysisResult.query.filter_by(analysis_id=analysis_id).first()
            if analysis:
                analysis.progress = 20
                analysis.message = translations[lang].get('status_images', 'Récupération des images de l\'annonce...')
                db.session.commit()
        
        # Geriye dönük uyumluluk için global değişkeni de güncelle
        if analysis_id in analysis_results:
            analysis_results[analysis_id].update({
                'progress': 20,
                'message': translations[lang].get('status_images', 'Récupération des images de l\'annonce...')
            })
        
        # Lancer l'analyse
        start_time = time.time()
        results = analyzer.analyze_listing_rooms(url)
        execution_time = time.time() - start_time
        
        if 'error' in results:
            # Veritabanında hata durumunu güncelle
            with app.app_context():
                analysis = AnalysisResult.query.filter_by(analysis_id=analysis_id).first()
                if analysis:
                    analysis.status = 'error'
                    analysis.progress = 100
                    analysis.message = f'Erreur: {results["error"]}'
                    db.session.commit()
            
            # Geriye dönük uyumluluk için global değişkeni de güncelle
            if analysis_id in analysis_results:
                analysis_results[analysis_id].update({
                    'status': 'error',
                    'progress': 100,
                    'message': f'Erreur: {results["error"]}',
                    'error': results['error']
                })
            return
        
        # Ajouter des informations sur l'exécution
        results['execution_time'] = execution_time
        results['batch_mode_used'] = BATCH_MODE
        results['analysis_id'] = analysis_id
        
        # Sauvegarder les résultats
        output_file = os.path.join(UPLOAD_FOLDER, f'analysis_{analysis_id}.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        # Veritabanında tamamlanma durumunu güncelle
        with app.app_context():
            analysis = AnalysisResult.query.filter_by(analysis_id=analysis_id).first()
            if analysis:
                analysis.status = 'completed'
                analysis.progress = 100
                analysis.message = translations[lang].get('status_complete', 'Analyse terminée avec succès!')
                analysis.execution_time = execution_time
                analysis.room_summary = json.dumps(results)
                db.session.commit()
        
        # Geriye dönük uyumluluk için global değişkeni de güncelle
        if analysis_id in analysis_results:
            analysis_results[analysis_id].update({
                'status': 'completed',
                'progress': 100,
                'message': translations[lang].get('status_complete', 'Analyse terminée avec succès!'),
                'results': results,
                'execution_time': execution_time,
                'output_file': f'analysis_{analysis_id}.json'
            })
        
    except Exception as e:
        # Veritabanında hata durumunu güncelle
        with app.app_context():
            analysis = AnalysisResult.query.filter_by(analysis_id=analysis_id).first()
            if analysis:
                analysis.status = 'error'
                analysis.progress = 100
                analysis.message = f'{translations[lang].get("status_error", "Erreur inattendue")}: {str(e)}'
                db.session.commit()
        
        # Geriye dönük uyumluluk için global değişkeni de güncelle
        if analysis_id in analysis_results:
            analysis_results[analysis_id].update({
                'status': 'error',
                'progress': 100,
                'message': f'{translations[lang].get("status_error", "Erreur inattendue")}: {str(e)}',
                'error': str(e)
            })

@app.route('/download/<filename>')
def download_file(filename):
    """Télécharge un fichier de résultats."""
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route('/config')
def get_config():
    """Retourne la configuration actuelle."""
    return jsonify({
        'batch_mode': BATCH_MODE,
        'api_configured': bool(os.getenv('GEMINI_API_KEY')),
        'available_languages': list(translations.keys()),
        'current_language': session.get('language', DEFAULT_LANGUAGE)
    })

@app.route('/translations/<lang>')
def get_translations(lang):
    """Retourne les traductions pour une langue spécifique."""
    if lang in translations:
        return jsonify(translations[lang])
    return jsonify(translations[DEFAULT_LANGUAGE])

@app.route('/map')
def show_map():
    """Route to display a map with listings fetched from the database."""
    try:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            # API anahtarı yoksa RoomAnalyzer'ı başlatamayız, bu bir sorun.
            # Ya da RoomAnalyzer'ı API anahtarı olmadan da veritabanı işlemleri için kullanılabilecek şekilde tasarlamalıyız.
            # Şimdilik, API anahtarı yoksa hata döndürelim veya boş liste gösterelim.
            app.logger.error("GEMINI_API_KEY is not set. Cannot initialize RoomAnalyzer for map view.")
            return render_template('map_view.html', listings_json=json.dumps([]), error_message="GEMINI_API_KEY not set.")

        analyzer = RoomAnalyzer(gemini_api_key=api_key)
        app.logger.info("Map route: Fetching listings from database for map display...")
        map_listings = analyzer.get_all_listings_for_map() # This method should return a list of dicts
        app.logger.info(f"Map route: Found {len(map_listings)} listings with coordinates in DB.")
        
        # The format from get_all_listings_for_map should already be suitable for map_view.html
        # It expects 'latitude', 'longitude', 'title', 'price', 'area_sqm', 'detail_url'
        # We need to ensure 'currency' and 'rooms' are handled if map_view.html expects them.
        # For now, let's assume the new DB fields cover the essentials.

        return render_template('map_view.html', listings_json=json.dumps(map_listings))
    
    except Exception as e:
        app.logger.error(f"Error in /map route: {e}", exc_info=True)
        return render_template('map_view.html', listings_json=json.dumps([]), error_message=str(e))

@app.route('/scrape_otodom')
def trigger_otodom_scrape():
    """Endpoint to trigger scraping Otodom listings and saving them to the database."""
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'status': 'error', 'message': 'GEMINI_API_KEY not set. Cannot initialize RoomAnalyzer for scraping.'}), 500

    try:
        analyzer = RoomAnalyzer(gemini_api_key=api_key)
        app.logger.info("Scrape route: Starting Otodom scrape...")
        # scrape_otodom_page now expects an analyzer_instance
        # We can scrape a fixed number of pages or make it configurable later
        # For now, let's stick to the first page as defined by OTODOM_SEARCH_URL_WROCLAW
        scraped_listings = scrape_otodom_page(OTODOM_SEARCH_URL_WROCLAW, analyzer_instance=analyzer)
        
        if scraped_listings:
            message = f"Successfully scraped and attempted to save {len(scraped_listings)} listings from Otodom."
            app.logger.info(message)
            return jsonify({'status': 'success', 'message': message, 'listings_found': len(scraped_listings)})
        else:
            message = "No listings were scraped from Otodom, or an error occurred during scraping."
            app.logger.warning(message)
            return jsonify({'status': 'warning', 'message': message, 'listings_found': 0})
            
    except Exception as e:
        app.logger.error(f"Error in /scrape_otodom route: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    # Vérifier si le fichier de traductions existe
    if not os.path.exists('translations.json'):
        print("⚠️  ATTENTION: Fichier translations.json non trouvé!")
    else:
        print(f"✅ Traductions chargées ({', '.join(translations.keys())})")
    
    print("🌐 Démarrage de l'Interface Web - Analyseur de Pièces")
    print("=======================================================")
    print(f"🚀 Mode: {'BATCH (1 requête LLM)' if BATCH_MODE else 'INDIVIDUEL (requêtes multiples)'}")    
    
    # Vérifier la clé API
    if not os.getenv('GEMINI_API_KEY'):
        print("⚠️  ATTENTION: Variable GEMINI_API_KEY non définie!")
        print("   Définissez-la avec: export GEMINI_API_KEY='votre_clé_api'")
    app.run(debug=True, host='0.0.0.0', port=5002)