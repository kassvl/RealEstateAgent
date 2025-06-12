import requests
import json
import base64
from io import BytesIO
from PIL import Image
import os
import time
import random
from typing import List, Dict, Optional, Tuple
import re
from back_end.scraper_otodom import get_listing_details
import sqlite3
from collections import Counter
import datetime
import logging
import uuid
import statistics

class RoomAnalyzer:
    def __init__(self, gemini_api_key: str, enable_duplicate_detection: bool = True, api_delay: float = 0.5, batch_mode: bool = True):
        if not gemini_api_key or len(gemini_api_key) < 10:
            print("⚠️ UYARI: Geçersiz API anahtarı formatı. API anahtarı en az 10 karakter olmalıdır.")
        
       
        # Use the API key as provided, without 'Alza' to 'AIza' correction.
        corrected_key = gemini_api_key 
        # self.logger.debug(f"Using API key as provided (no 'Alza' correction): {str(corrected_key)[:10]}...") # Log a portion for confirmation
        # Ensure logger is available if we want to use it here, or use print
        print(f"[DEBUG] Using API key as provided (no 'Alza' correction): {str(corrected_key)[:10]}...")
        
        self.gemini_api_key = corrected_key
        
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={corrected_key}"
        print(f"[DEBUG] API anahtarı uzunluğu: {len(corrected_key) if corrected_key else 0} karakter")
        print(f"[DEBUG] API URL: {self.gemini_url[:60]}...")
        
       
        if corrected_key and not (corrected_key.startswith('AIza') and len(corrected_key) > 30):
            print("⚠️ UYARI: API anahtarı 'AIza' ile başlamıyor veya çok kısa. Doğru formatta olmayabilir.")
        print(f"[DEBUG] Using Gemini API URL: {self.gemini_url}")
        self.enable_duplicate_detection = enable_duplicate_detection
        self.api_delay = api_delay
        self.batch_mode = batch_mode

        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            ch = logging.StreamHandler()
            ch.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
        self.last_api_call = 0
        self.db_path = '/Users/kadirhan/Desktop/ev/real_estate_agent_v2/back_end/real_estate_analysis.db'
        self._init_db()
        
        # Pre-load feature/issue vocabulary (may be empty)
        self._feature_issue_vocab = self._load_feature_issue_vocab()
        
    def _load_room_types(self) -> List[Dict]:
        file_path = os.path.join(os.path.dirname(__file__), 'room_type_classes.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.error(f"room_type_classes.json bulunamadı: {file_path}")
            return []
        except json.JSONDecodeError:
            self.logger.error("room_type_classes.json geçersiz JSON içeriyor.")
            return []
    
    def _load_feature_issue_vocab(self) -> Dict[str, List[str]]:
        """Load characteristic / issue vocabulary from generated JSON file."""
        vocab_path = os.path.join(os.path.dirname(__file__), 'gemini_feature_issue_vocab.json')
        if not os.path.exists(vocab_path):
            self.logger.warning("Feature/issue vocab file not found. Run generate_feature_issue_vocab.py after you have some analyses.")
            return {"characteristics": [], "visible_issues": []}
        try:
            with open(vocab_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ensure lists
                return {
                    "characteristics": data.get("characteristics", []),
                    "visible_issues": data.get("visible_issues", [])
                }
        except Exception as e:
            self.logger.error(f"Could not load feature/issue vocab: {e}")
            return {"characteristics": [], "visible_issues": []}
    
    def _create_room_types_prompt(self) -> str:
        """Generate a textual prompt section describing available room type IDs.

        Gemini can use this information to map its free-text understanding to the
        discrete IDs we maintain locally (and later in the DB). If the JSON file
        is missing, we still return a short placeholder to avoid breaking the
        calling code.
        """
        room_types = self._load_room_types()

        if not room_types:
            self.logger.warning("_create_room_types_prompt: No room types available; returning placeholder text.")
            return "Known room types are currently unavailable."

        lines = ["Here is the list of valid room_type_id values you MUST use in JSON responses:"]
        for rt in room_types:
            rt_id = rt.get("id") or rt.get("room_type_id") or rt.get("identified_room_type_id") or "unknown"
            rt_name = rt.get("name") or rt_id.replace("_", " ").title()
            lines.append(f"- {rt_id}: {rt_name}")

        return "\n".join(lines)
    
    def _init_db(self):
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Create property_analyses table (based on save_listing_scrape_data)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS property_analyses (
                    listing_id TEXT UNIQUE NOT NULL,
                    scraped_title TEXT,
                    scraped_street_address TEXT,
                    scraped_price REAL,
                    scraped_area REAL,
                    scraped_latitude REAL,
                    scraped_longitude REAL,
                    analysis_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (listing_id)
                )
            ''')
            self.logger.debug("Ensured property_analyses table exists.")

            # Create analysis_results table (based on _save_analysis_to_db)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analysis_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    listing_id TEXT,
                    analysis_id TEXT UNIQUE,
                    total_images INTEGER,
                    successfully_classified INTEGER,
                    unique_rooms_detected INTEGER,
                    duplicate_images_found INTEGER,
                    execution_time REAL,
                    batch_mode_used BOOLEAN,
                    status TEXT,
                    progress REAL,
                    message TEXT,
                    created_at TEXT,
                    room_summary TEXT,
                    avg_impression_score REAL,
                    dominant_clutter_level TEXT,
                    max_renovation_need TEXT,
                    property_summary_text TEXT,
                    key_features_text TEXT,
                    visible_issues_text TEXT,
                    numeric_visual_features_json TEXT,
                    raw_gemini_response TEXT,
                    overall_condition TEXT,
                    dominant_style TEXT,
                    overall_lighting TEXT,
                    overall_impression_score_avg REAL,
                    overall_impression_score_median REAL,
                    clutter_level_mode TEXT,
                    estimated_renovation_need_mode TEXT,
                    habitable_room_ratio REAL,
                    duplicate_ratio REAL,
                    total_unique_rooms INTEGER,
                    FOREIGN KEY (listing_id) REFERENCES property_analyses (listing_id)
                )
            ''')
            self.logger.debug("Ensured analysis_results table exists.")

            # --- NEW: Ensure numeric_visual_features_json column exists (for older schemas) ---
            cursor.execute("PRAGMA table_info(analysis_results)")
            existing_cols = [row[1] for row in cursor.fetchall()]
            if 'numeric_visual_features_json' not in existing_cols:
                self.logger.info("Adding missing column 'numeric_visual_features_json' to analysis_results table...")
                cursor.execute("ALTER TABLE analysis_results ADD COLUMN numeric_visual_features_json TEXT")
                self.logger.info("Column 'numeric_visual_features_json' added successfully.")

            # --- NEW: Ensure frequently queried numeric columns exist ---
            common_cols_types = {
                "overall_impression_score_avg": "REAL",
                "overall_impression_score_median": "REAL",
                "clutter_level_mode": "TEXT",
                "estimated_renovation_need_mode": "TEXT",
                "habitable_room_ratio": "REAL",
                "duplicate_ratio": "REAL",
                "total_unique_rooms": "INTEGER"
            }

            for col, col_type in common_cols_types.items():
                if col not in existing_cols:
                    self.logger.info(f"Adding missing column '{col}' to analysis_results table...")
                    cursor.execute(f"ALTER TABLE analysis_results ADD COLUMN {col} {col_type}")
            conn.commit()
            self.logger.info(f"Database initialized/verified at {self.db_path}")
        except sqlite3.Error as e:
            self.logger.error(f"Database error during _init_db: {e}")
            if conn:
                conn.rollback()
        except Exception as e:
            self.logger.error(f"General error during _init_db: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def save_listing_scrape_data(self, listing_id: str, title: Optional[str], street_address: Optional[str], 
                                 price: Optional[float], area: Optional[float], 
                                 latitude: Optional[float], longitude: Optional[float]):
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            self.logger.debug(f"Attempting to save/update scrape data for listing_id: {listing_id}")
            
            # Convert to float or None, handling empty strings for numeric types
            db_price = float(price) if price is not None and str(price).strip() != '' else None
            db_area = float(area) if area is not None and str(area).strip() != '' else None
            db_latitude = float(latitude) if latitude is not None and str(latitude).strip() != '' else None
            db_longitude = float(longitude) if longitude is not None and str(longitude).strip() != '' else None

            cursor.execute("""
                INSERT INTO property_analyses (
                    listing_id, 
                    scraped_title, 
                    scraped_street_address, 
                    scraped_price, 
                    scraped_area, 
                    scraped_latitude, 
                    scraped_longitude,
                    analysis_timestamp 
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(listing_id) DO UPDATE SET
                    scraped_title = excluded.scraped_title,
                    scraped_street_address = excluded.scraped_street_address,
                    scraped_price = excluded.scraped_price,
                    scraped_area = excluded.scraped_area,
                    scraped_latitude = excluded.scraped_latitude,
                    scraped_longitude = excluded.scraped_longitude,
                    analysis_timestamp = excluded.analysis_timestamp;
            """, (listing_id, title, street_address, db_price, db_area, db_latitude, db_longitude))
            conn.commit()
            self.logger.info(f"Successfully saved/updated scrape data for listing_id: {listing_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Database error while saving scrape data for {listing_id}: {e}")
            if conn:
                conn.rollback()
        except ValueError as e: 
            self.logger.error(f"Data type error for listing {listing_id} before DB save (e.g., converting price/area to float): {e}")
        finally:
            if conn:
                conn.close()


    def _wait_for_api_rate_limit(self):
        
        current_time = time.time()
        time_since_last_call = current_time - self.last_api_call
        
        if time_since_last_call < self.api_delay:
            wait_time = self.api_delay - time_since_last_call
            print(f"⏳ Attente de {wait_time:.1f}s pour respecter les limites API...")
            time.sleep(wait_time)
        
        self.last_api_call = time.time()

    def _generate_property_summary(self, gemini_analysis_results: List[Dict]) -> Dict:
        
        if not gemini_analysis_results:
            self.logger.warning("_generate_property_summary: No analysis results to process.")
            return {}

        self.logger.debug(f"Received {len(gemini_analysis_results)} analysis results.")

        room_types = [res.get('room_type') for res in gemini_analysis_results if isinstance(res, dict) and res.get('room_type')]
        conditions = [res.get('condition') for res in gemini_analysis_results if isinstance(res, dict) and res.get('condition')]
        styles = [res.get('style') for res in gemini_analysis_results if isinstance(res, dict) and res.get('style')]
        lightings = [res.get('lighting') for res in gemini_analysis_results if isinstance(res, dict) and res.get('lighting')]
        
        all_features = []
        for res in gemini_analysis_results:
            if isinstance(res, dict):
                if res.get('features') and isinstance(res.get('features'), list):
                    all_features.extend(f for f in res.get('features') if isinstance(f, str))
            else:
                self.logger.warning(f"Skipping non-dict item in gemini_analysis_results (features extraction): type {type(res)} - content (truncated): {str(res)[:100]}")

        all_issues = []
        for res in gemini_analysis_results:
            if isinstance(res, dict):
                if res.get('visible_issues') and isinstance(res.get('visible_issues'), list):
                    valid_issues = [i for i in res.get('visible_issues') if isinstance(i, dict) and 'issue' in i and 'severity' in i]
                    all_issues.extend(valid_issues)
            else:
                self.logger.warning(f"Skipping non-dict item in gemini_analysis_results (issues extraction): type {type(res)} - content (truncated): {str(res)[:100]}")

        # Benzersiz sorunları alırken dict'lerin hashable olmaması sorununu çöz
        unique_issues_tuples = {tuple(sorted(d.items())) for d in all_issues if isinstance(d, dict)}
        unique_issues_list = [dict(t) for t in unique_issues_tuples]

        summary = {
            'room_counts': dict(Counter(room_types)) if room_types else {},
            'overall_condition': Counter(conditions).most_common(1)[0][0] if conditions else None,
            'dominant_style': Counter(styles).most_common(1)[0][0] if styles else None,
            'key_features': list(set(all_features)), # Benzersiz string özellikler
            'visible_issues': unique_issues_list,
            'overall_lighting': Counter(lightings).most_common(1)[0][0] if lightings else None,
            'property_summary_text': ""
        }
        self.logger.debug(f"Initial structured summary: {summary}")

        
        prompt_details = {
            "objective": "Extract key points from the property analysis into a bulleted list.",
            "role": "You are an AI assistant summarizing property data.",
            "property_analysis": {
                "room_summary": summary['room_counts'],
                "overall_condition": summary['overall_condition'],
                "dominant_style": summary['dominant_style'],
                "overall_lighting": summary['overall_lighting'],
                "highlighted_features": [feat[:70] + '...' if len(feat) > 70 else feat for feat in summary['key_features'][:5]],
                "notable_issues": [
                    {
                        'issue': issue_item['issue'][:100] + '...' if len(issue_item['issue']) > 100 else issue_item['issue'], 
                        'severity': issue_item['severity']
                    } 
                    for issue_item in summary['visible_issues'][:3]
                ]
            },
            "instructions": "Based on the property analysis data, create a concise bullet-point list. Include 3-5 main positive selling points and up to 2 notable issues. Start each point with a dash (-). Keep the entire response under 200 tokens."
        }
        
        
        try:
            prompt_text_for_gemini = f"Please act as a {prompt_details['role']}. {prompt_details['objective']}. {prompt_details['instructions']}\n\nHere is the property analysis data:\n```json\n{json.dumps(prompt_details['property_analysis'], indent=2, ensure_ascii=False)}\n```"
            self.logger.debug(f"Length of detailed prompt for Gemini: {len(prompt_text_for_gemini)}")
            # Log a larger portion of the prompt, or all of it if not excessively long
            log_prompt_display = prompt_text_for_gemini if len(prompt_text_for_gemini) < 2000 else prompt_text_for_gemini[:2000] + "... (prompt truncated for logging)"
            self.logger.debug(f"Detailed prompt for Gemini (up to 2000 chars): {log_prompt_display}")
            payload = {
                "contents": [
                    {
                        "parts": [{"text": prompt_text_for_gemini}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.6
                }
            }
            
            self.logger.info("CASCADE_DEBUG: _generate_property_summary: Requesting detailed textual summary from Gemini...")
            # Truncate payload for logging if it's too large
            payload_str_for_log = json.dumps(payload, indent=2)
            if len(payload_str_for_log) > 1000:
                payload_str_for_log = payload_str_for_log[:1000] + "... (payload truncated for logging)"
            self.logger.debug(f"CASCADE_DEBUG: Payload for detailed Gemini summary: {payload_str_for_log}")
            
            detailed_summary_response = self._make_gemini_request(payload, max_retries=2) # Changed max_retries to 2
            
            # Log the type and a truncated version of the response
            response_type = type(detailed_summary_response)
            response_content_for_log = str(detailed_summary_response)
            if len(response_content_for_log) > 500:
                response_content_for_log = response_content_for_log[:500] + "... (response truncated for logging)"
            self.logger.debug(f"CASCADE_DEBUG: Raw response from detailed Gemini summary call: {response_content_for_log}")
            self.logger.debug(f"CASCADE_DEBUG: Type of detailed_summary_response: {response_type}")

            if not isinstance(detailed_summary_response, dict):
                self.logger.error(f"CASCADE_DEBUG: detailed_summary_response IS NOT A DICT. Content (truncated): {response_content_for_log}")
            
            self.logger.debug("CASCADE_DEBUG: Entering processing block for detailed_summary_response.")
            if detailed_summary_response and isinstance(detailed_summary_response, dict) and detailed_summary_response.get('candidates'):
                self.logger.debug("CASCADE_DEBUG: detailed_summary_response is a dict and has 'candidates'.")
                candidates = detailed_summary_response.get('candidates', [])
                if candidates and isinstance(candidates, list) and len(candidates) > 0:
                    content = candidates[0].get('content', {})
                    parts = content.get('parts', [{}])
                    generated_text = parts[0].get('text', '')
                    
                    if generated_text.strip():
                        summary['property_summary_text'] = generated_text.strip()
                        self.logger.info("CASCADE_DEBUG: _generate_property_summary: Successfully generated detailed summary from Gemini.")
                        # self.logger.debug(f"CASCADE_DEBUG: Detailed summary text: {summary['property_summary_text']}")
                    else:
                        self.logger.warning("CASCADE_DEBUG: _generate_property_summary: Gemini returned empty text for detailed summary. Will raise ValueError.")
                        raise ValueError("Empty text from Gemini for detailed summary")
                else:
                    self.logger.warning(f"CASCADE_DEBUG: 'candidates' list is empty or not structured as expected in detailed_summary_response. Candidates: {candidates}")
                    raise ValueError("No valid candidates structure from Gemini for detailed summary")
            else:
                self.logger.warning(f"CASCADE_DEBUG: _generate_property_summary: No candidates found or issue with Gemini response structure. Response (truncated): {response_content_for_log}")
                # If detailed_summary_response is None or not a dict, this path will be taken.
                # If it's a dict but no 'candidates', this is also taken.
                raise ValueError("No valid response or structure from Gemini for detailed summary")

        except Exception as e:
            self.logger.error(f"CASCADE_DEBUG: _generate_property_summary: Error during detailed summary generation: {e}", exc_info=True)
            # Fallback: Basit bir özet metin oluşturma
            summary_parts = []
            if summary['room_counts']:
                rc = summary['room_counts']
                room_details_str = ", ".join([f"{self.get_room_type_by_id(rt)['name'] if self.get_room_type_by_id(rt) else rt}: {rc[rt]}" for rt in rc])
                summary_parts.append(f"{len(rc)} çeşit oda ({sum(rc.values())} toplam) bulundu: {room_details_str}.")
            if summary['overall_condition']:
                summary_parts.append(f"Genel durum: {summary['overall_condition']}.")
            if summary['dominant_style']:
                summary_parts.append(f"Baskın stil: {summary['dominant_style']}.")
            if summary['key_features']:
                summary_parts.append(f"Öne çıkan özellikler: {', '.join(summary['key_features'][:5])}{'...' if len(summary['key_features']) > 5 else ''}.")
            if summary['visible_issues']:
                issues_str = ", ".join([f"{issue.get('issue', 'Bilinmeyen sorun')} (Ciddiyet: {issue.get('severity', 'N/A')})" for issue in summary['visible_issues'][:3]])
                summary_parts.append(f"{len(summary['visible_issues'])} görünür sorun tespit edildi: {issues_str}{'...' if len(summary['visible_issues']) > 3 else ''}.")
            
            if not summary_parts: # Eğer hiçbir bilgi yoksa genel bir mesaj
                summary_parts.append("Mülk hakkında temel özet bilgileri çıkarılamadı.")
                    
            summary['property_summary_text'] = " ".join(summary_parts)
            print("[INFO] _generate_property_summary: Using fallback simple summary text.")
        
        print(f"[DEBUG] _generate_property_summary: Final summary object: {{... 'property_summary_text': '{summary['property_summary_text'][:100]}...'}}")
        return summary

    def _save_analysis_to_db(self, analysis_id: str, listing_id_url: str, total_images: int, 
                         successfully_classified_images: int, unique_rooms_detected: int, 
                         duplicate_images_found: int, execution_time: float, batch_mode_used: bool,
                         room_summary_data: Optional[Dict], avg_impression_score: Optional[float],
                         dominant_clutter_level: Optional[str], max_renovation_need: Optional[str],
                         property_summary_text: Optional[str], key_features_text: Optional[List[str]],
                         visible_issues_text: Optional[List[str]], raw_gemini_response: Optional[str],
                         overall_condition: Optional[str], dominant_style: Optional[str],
                         overall_lighting: Optional[str], numeric_visual_features: Optional[Dict]=None,
                         overall_impression_score_avg: Optional[float]=None,
                         overall_impression_score_median: Optional[float]=None,
                         clutter_level_mode: Optional[str]=None,
                         estimated_renovation_need_mode: Optional[str]=None,
                         habitable_room_ratio: Optional[float]=None,
                         duplicate_ratio: Optional[float]=None,
                         total_unique_rooms: Optional[int]=None):
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO analysis_results (
                    analysis_id, listing_id, total_images, successfully_classified, 
                    unique_rooms_detected, duplicate_images_found, execution_time, batch_mode_used, 
                    status, progress, message, created_at, 
                    room_summary, avg_impression_score, dominant_clutter_level, max_renovation_need,
                    property_summary_text, key_features_text, visible_issues_text, raw_gemini_response,
                    overall_condition, dominant_style, overall_lighting, numeric_visual_features_json,
                    overall_impression_score_avg, overall_impression_score_median, clutter_level_mode,
                    estimated_renovation_need_mode, habitable_room_ratio, duplicate_ratio, total_unique_rooms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                analysis_id,
                listing_id_url, # This is the URL, maps to listing_id in the table
                total_images,
                successfully_classified_images,
                unique_rooms_detected,
                duplicate_images_found,
                execution_time,
                batch_mode_used,
                'completed',  # status
                100.0,  # progress
                'Analysis completed successfully.',  # message
                datetime.datetime.now(), # created_at
                json.dumps(room_summary_data) if room_summary_data else None,
                avg_impression_score,
                dominant_clutter_level,
                max_renovation_need,
                property_summary_text,
                json.dumps(key_features_text) if key_features_text else None,
                json.dumps(visible_issues_text) if visible_issues_text else None,
                raw_gemini_response,
                overall_condition,
                dominant_style,
                overall_lighting,
                json.dumps(numeric_visual_features) if numeric_visual_features else None,
                (numeric_visual_features or {}).get("overall_impression_score_avg", overall_impression_score_avg),
                (numeric_visual_features or {}).get("overall_impression_score_median", overall_impression_score_median),
                (numeric_visual_features or {}).get("clutter_level_mode", clutter_level_mode),
                (numeric_visual_features or {}).get("estimated_renovation_need_mode", estimated_renovation_need_mode),
                (numeric_visual_features or {}).get("habitable_room_ratio", habitable_room_ratio),
                (numeric_visual_features or {}).get("duplicate_ratio", duplicate_ratio),
                (numeric_visual_features or {}).get("total_unique_rooms", total_unique_rooms)
            ))
            conn.commit()
            self.logger.info(f"[DB] Analysis for '{listing_id_url}' (ID: {analysis_id}) saved/updated in analysis_results.")
        except sqlite3.Error as e:
            self.logger.error(f"[DB] Database error while saving analysis for {listing_id_url} (ID: {analysis_id}): {e}")
            if conn:
                conn.rollback()
        except Exception as e:
            self.logger.error(f"[DB] General error during _save_analysis_to_db for {listing_id_url} (ID: {analysis_id}): {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def _make_gemini_request(self, payload, retry_count=0, max_retries=3):
        if retry_count >= max_retries:
            self.logger.error(f"❌ Échec de la requête Gemini après {max_retries} tentatives.")
            return None

        headers = {'Content-Type': 'application/json'}
        token_estimate = self._estimate_token_usage(payload)
        self.logger.debug(f"Estimation des jetons pour cette requête : {token_estimate}")

        num_parts = 0
        if 'contents' in payload and len(payload['contents']) > 0:
            content = payload['contents'][0]
            if 'parts' in content:
                parts = content['parts']
                num_parts = len(parts)
                self.logger.debug(f"Structure de la charge utile de la requête : {num_parts} parties.")
                if num_parts > 0:
                    first_part_type = 'image' if 'inlineData' in parts[0] else parts[0].get('text', 'Type de partie inconnu')
                    self.logger.debug(f"Type de la première partie : {first_part_type}")
                    self.logger.debug(f"Types des parties (max 3) : {[type(p).__name__ for p in parts[:3]]}...")

        # Timeout: 90s for multi-part (likely image), 45s for single-part (likely text/summary)
        timeout = 90 if num_parts > 1 else 45
        payload_size_kb = len(str(payload)) // 1024
        self.logger.debug(f"Timeout de la requête réglé à {timeout} secondes (taille de la charge utile : {payload_size_kb} Ko)")

        try:
            response = requests.post(self.gemini_url, headers=headers, json=payload, timeout=timeout)
            self.logger.debug(f"Statut de la réponse Gemini : {response.status_code}")

            if response.status_code == 200:
                try:
                    response_json = response.json()
                    if not isinstance(response_json, dict):
                        self.logger.error(f"Réponse Gemini API OK (200) mais le JSON n'est pas un dictionnaire. Type: {type(response_json)}, Contenu (tronqué): {str(response_json)[:500]}")
                        return None
                    self.logger.debug(f"Structure de la réponse JSON Gemini (clés) : {list(response_json.keys()) if response_json else 'Vide'}")
                    return response_json
                except ValueError as json_err: # Catches JSONDecodeError
                    self.logger.error(f"Erreur de décodage JSON de la réponse Gemini (statut 200) : {json_err}. Texte de la réponse (tronqué): {response.text[:500]}")
                    return None
            elif response.status_code == 429:
                self.logger.warning("Limite de taux Gemini dépassée. Attente et nouvelle tentative...")
                time.sleep(5 * (retry_count + 1))
                return self._make_gemini_request(payload, retry_count + 1, max_retries)
            else:
                self.logger.error(f"Erreur API Gemini : {response.status_code} - {response.text[:500]}") # Truncate response text
                if retry_count < max_retries - 1:
                    self.logger.info(f"Nouvelle tentative {retry_count + 2}/{max_retries}...")
                    time.sleep(2 * (retry_count + 1))
                    return self._make_gemini_request(payload, retry_count + 1, max_retries)
                return None
        except requests.exceptions.Timeout:
            self.logger.error(f"Exception de timeout lors de la requête API Gemini après {timeout} secondes.")
            if retry_count < max_retries - 1:
                self.logger.warning(f"Requête volumineuse ou API lente. Nouvelle tentative {retry_count + 2}/{max_retries}...")
                return self._make_gemini_request(payload, retry_count + 1, max_retries) # Consider increasing timeout for retry here if needed
            return None
        except Exception as e:
            self.logger.error(f"Exception inattendue dans _make_gemini_request : {e}", exc_info=True)
            if retry_count < max_retries - 1:
                self.logger.info(f"Nouvelle tentative {retry_count + 2}/{max_retries}...")
                time.sleep(2 * (retry_count + 1))
                return self._make_gemini_request(payload, retry_count + 1, max_retries)
            return None

    def _estimate_token_usage(self, payload):
        text_tokens = 0
        # {{ ... }} was removed here.
        image_count = 0
        
        # Basic token estimation logic
        if payload and 'contents' in payload:
            for content_item in payload['contents']:
                if 'parts' in content_item:
                    for part in content_item['parts']:
                        if 'text' in part and isinstance(part['text'], str):
                            # Approximate: 1 token per 4 characters for English text
                            text_tokens += len(part['text']) // 4 
                        elif 'inline_data' in part:
                            # Each image part typically has a fixed token cost
                            image_count += 1
        
        # Gemini pricing: 258 tokens per image part, text tokens depend on model.
        estimated_tokens = text_tokens + (image_count * 258) 
        return estimated_tokens
    
    def _download_and_encode_image(self, image_url: str) -> Optional[str]:
       
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=5, verify=False)
            response.raise_for_status()
            
            image = Image.open(BytesIO(response.content))
            
            max_size = (800, 800) 
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=75)  # Lower quality for faster processing
            image_data = buffer.getvalue()
            
            return base64.b64encode(image_data).decode('utf-8')
            
        except Exception as e:
            print(f"❌ Erreur lors du téléchargement de l'image {image_url}: {e}")
            return None
    
    def _classify_room_with_gemini(self, image_base64: str) -> Tuple[Optional[str], Optional[Dict]]:
       
        try:
            prompt = """
You are an expert real estate property assessor specializing in the Wroclaw, Poland market.
Analyze the provided image of a room and return a JSON object with the following structure.
DO NOT include any text outside of the JSON object.

{
  "identified_room_type_id": "string",
  "confidence_score": "float",
  "main_characteristics": ["string"],
  "potential_issues": [
    {
      "issue": "string",
      "severity": "string"
    }
  ],
  "estimated_condition": "string",
  "dominant_style_elements": ["string"],
  "lighting_quality": "string",
  "renovation_need_impression": "string",
  "is_likely_habitable": "boolean",
  "additional_notes": "string"
}

Analyze the following image:
"""
        
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/jpeg", "data": image_base64}}
                        ]
                    }
                ],
                "generationConfig": {
                    "response_mime_type": "application/json", # Gemini'nin JSON formatında yanıt vermesini sağlamak için
                }
            }
        
            raw_gemini_response = self._make_gemini_request(payload)
        
            if not raw_gemini_response:
                self.logger.error("Gemini API'den yanıt alınamadı.")
                return None, None
        
            
            analysis_json = None
            if 'candidates' in raw_gemini_response and len(raw_gemini_response['candidates']) > 0:
                candidate = raw_gemini_response['candidates'][0]
                if 'content' in candidate and 'parts' in candidate['content'] and len(candidate['content']['parts']) > 0:
                    part = candidate['content']['parts'][0]
                    if 'text' in part: # Eğer yanıt 'text' içinde bir JSON string ise
                        try:
                            analysis_json = json.loads(part['text'])
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Gemini yanıtı JSON olarak parse edilemedi (text field): {e}")
                            self.logger.debug(f"Alınan text: {part['text']}")
                            return None, raw_gemini_response 
                    elif isinstance(part, dict): 
                        analysis_json = part 

            if not analysis_json:
                self.logger.error("Gemini yanıtından geçerli bir analiz JSON'u çıkarılamadı.")
                self.logger.debug(f"Ham Gemini Yanıtı: {raw_gemini_response}")
                return None, raw_gemini_response
            
            
            required_keys = ["identified_room_type_id", "confidence_score", "main_characteristics"]
            if not all(key in analysis_json for key in required_keys):
                self.logger.warning(f"Gemini'den gelen JSON'da beklenen bazı anahtar alanlar eksik. Gelen JSON: {analysis_json}")
                
                

            return analysis_json, raw_gemini_response
        
        except Exception as e:
            self.logger.error(f"_classify_room_with_gemini içinde beklenmedik hata: {e}", exc_info=True)
            return None, None
    
    def _compare_images_with_gemini(self, image1_base64: str, image2_base64: str) -> bool:
        
        try:
            prompt = """
Comparez ces deux images et déterminez si elles montrent la MÊME pièce physique.

Considérez comme la même pièce si:
- Les meubles principaux sont identiques ou très similaires
- La disposition générale est la même
- Les fenêtres, portes et éléments architecturaux correspondent
- L'angle de vue est différent mais la pièce est reconnaissable

Répondez UNIQUEMENT par "oui" si c'est la même pièce, ou "non" si ce sont des pièces différentes.
"""
            
            payload = {
                "contents": [
                    {
                        "parts": [
                            {
                                "text": prompt
                            },
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": image1_base64
                                }
                            },
                            {
                                "inline_data": {
                                    "mime_type": "image/jpeg",
                                    "data": image2_base64
                                }
                            }
                        ]
                    }
                ]
            }
            
            result = self._make_gemini_request(payload)
            
            if not result:
                return False
            
            if 'candidates' in result and len(result['candidates']) > 0:
                content = result['candidates'][0].get('content', {})
                parts = content.get('parts', [])
                if parts and 'text' in parts[0]:
                    answer = parts[0]['text'].strip().lower()
                    return answer == 'oui'
            
            return False
            
        except Exception as e:
            print(f"Erreur lors de la comparaison d'images: {e}")
            return False
    
    def _create_batch_analysis_prompt(self, images_data: List[Tuple[int, str, str]]) -> str:
        
        room_types_prompt = self._create_room_types_prompt()
        
        prompt = f"""
        You are a **superhuman-level visual analyst**, specialized in residential architecture, interior design, and real estate assessment. You perceive and evaluate every pixel with expert scrutiny.
        Your knowledge combines the expertise of **licensed appraisers, interior designers, real estate agents, and structural inspectors**.
        You deliver **structured, detailed, and evidence-based insights** based on industry standards.
        Your task is to extract the **maximum amount of high-quality structured intelligence** from each photo — with **zero hallucination, high factuality, and context continuity across images**.
        
        You are analyzing {len(images_data)} images of a residential property listing.
        
        Perform a full, structured, high-fidelity analysis of each image according to the criteria below. Use rich architectural and real estate terminology. Be hyper-precise and concise. Justify your answers with **visible visual evidence** only — do not infer based on assumptions.
        
        For each image, provide the following analysis:
        
        1. **Room Type & Function**
           - Primary room classification (from: {room_types_prompt})
           - Function certainty (High / Medium / Low)
           - Is this room multi-functional? (e.g., open-plan kitchen-living)
        
        2. **Repetition Check**
           - Has this room appeared in any previous image(s)? (Yes/No)
           - If yes, which image index(es)?
           - Justify using distinctive visual anchors: flooring, furniture, windows, structural elements.
        
        3. **Physical Condition Assessment**
           - Rate: Excellent / Good / Fair / Poor
           - Describe evidence: wall/ceiling condition, fixture age, wear & tear, flooring quality, modernity.
        
        4. **Design & Style Classification**
           - Primary interior style (from: Modern, Minimalist, Scandinavian, Rustic, Classic, Industrial, Traditional, Boho, Japandi, Contemporary, Eclectic, Mediterranean, Art Deco, Other)
           - Justify style using visual elements: materials, color palette, furniture shapes, spatial layout, textures.
        
        5. **Natural Lighting Quality**
           - Rate: Excellent / Good / Average / Poor
           - Evaluate based on: number/size of windows, light direction, daylight diffusion, window treatments.
        
        6. **Room Size Estimation**
           - Size: Small (<10m²), Medium (10–20m²), Large (>20m²)
           - Reason using depth perception, ceiling height, furniture scale, visible layout.
        
        7. **Notable Architectural or Functional Features**
           - List visible features (e.g., fireplace, balcony access, kitchen island, built-in shelves, exposed beams, skylight, smart controls, walk-in closet)
           - Briefly describe function and appeal.
        
        8. **Visible Issues / Red Flags**
           - List any problems (e.g., water damage, mold, cracked tiles, clutter (distinct from general tidiness), outdated fixtures, wear)
           - Rate severity: Minor / Moderate / Major
           - Optional: Suggest potential remediation

        9. **Clutter Level**
           - Rate: Very Tidy / Minimal Clutter / Moderate Clutter / Significant Clutter / Very Cluttered
           - Assess the level of disorganization or excessive items visible in the room, impacting its presentation or usability.

        10. **Estimated Renovation Need**
            - Rate: None / Minor Cosmetic Updates / Moderate Renovation / Significant Renovation / Full Gut Renovation
            - Based on the visible condition, style, and fixtures, estimate the level of renovation likely required to modernize or bring the space to a high standard. Consider age, wear, and outdated elements.

        11. **Overall Impression Score**
            - Rate: 1 (Very Poor) / 2 (Poor) / 3 (Average) / 4 (Good) / 5 (Excellent)
            - Provide a subjective overall impression score based on the combined impact of condition, style, lighting, and perceived appeal. This reflects how inviting and desirable the space appears.
        
        Return your analysis in the following structured JSON format for EACH image:
        ```json
        [
          {{
            "image_index": 0,
            "room_type": "bedroom",
            "function_certainty": "High",
            "is_multi_functional": false,
            "same_room_as": [],
            "condition": "Good",
            "style": "Modern",
            "lighting": "Good",
            "size": "Medium",
            "features": ["Balcony access", "Radiator"],
            "visible_issues": [
              {{
                "issue": "Slight wear on wooden floor",
                "severity": "Minor"
              }}
            ],
            "clutter_level": "Minimal Clutter",
            "estimated_renovation_need": "Minor Cosmetic Updates",
            "overall_impression_score": 4
          }},
          // Continue for all images
        ]
        ```
        
        Important rules:
        - Always provide justification for each answer, if applicable or requested by the specific criterion.
        - Do not assume; base conclusions solely on visual cues.
        - If image is unclear or obstructed, state limitations.
        - Use professional vocabulary. Avoid vague terms like "nice" or "ugly".
        - Maintain continuity across multiple images (e.g., for room repetition or layout inference).
        - For room_type, use ONLY the identifiers from the list provided above.
        """
        
        return prompt
        
    def _analyze_all_images_batch(self, images_data: List[Tuple[int, str, str]]) -> List[Dict]:
        
      
        try:
            # Créer le prompt global
            prompt = self._create_batch_analysis_prompt(images_data)
            
            # Construire le payload avec toutes les images
            parts = [{"text": prompt}]
            
            for image_index, image_url, image_base64 in images_data:
                parts.append({
                    "text": f"\nImage {image_index}: {image_url}"
                })
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                })
            
            payload = {
                "contents": [{"parts": parts}]
            }
            
            print(f"🚀 Envoi d'une seule requête pour {len(images_data)} images...")
            result = self._make_gemini_request(payload)
            
            if not result:
                print("❌ Erreur dans la requête batch")
                return self._fallback_to_individual_analysis(images_data)
            
            # Parser la réponse JSON
            print(f"[DEBUG] API Response structure: {list(result.keys()) if result else 'None'}")
            print(f"[DEBUG] Full API response: {json.dumps(result)[:500]}...")
            if 'candidates' in result and len(result['candidates']) > 0:
                content = result['candidates'][0].get('content', {})
                parts = content.get('parts', [])
                print(f"[DEBUG] Response parts count: {len(parts)}")
                if parts and 'text' in parts[0]:
                    response_text = parts[0]['text'].strip()
                    print(f"[DEBUG] Response text (first 100 chars): {response_text[:100]}...")
                    print(f"[DEBUG] Full response text: {response_text}")
                    
                    
                    try:
                        
                        json_start = response_text.find('[')
                        json_end = response_text.rfind(']') + 1
                        if json_start >= 0 and json_end > json_start:
                            json_text = response_text[json_start:json_end]
                            print(f"[DEBUG] Extracted JSON (first 100 chars): {json_text[:100]}...")
                            parsed_result = json.loads(json_text)
                            print(f"[DEBUG] Parsed JSON contains {len(parsed_result)} items")
                            
                            
                            if isinstance(parsed_result, list):
                                print(f"[DEBUG] Analysis entries: {len(parsed_result)}")
                                
                                analysis_results = parsed_result
                                
                                for result in analysis_results:
                                    if 'room_type' not in result or not result['room_type']:
                                        result['room_type'] = 'other'
                                    if 'same_room_as' not in result:
                                        result['same_room_as'] = []
                                processed_classifications = self._process_batch_results(analysis_results, images_data)
                                return processed_classifications, result
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Erreur de parsing JSON: {e}")
                        print(f"Réponse reçue: {response_text[:500]}...")
            else:
                print(f"[DEBUG] No text found in response parts")
            
            print("⚠️ Réponse invalide, basculement vers l'analyse individuelle")
            return self._fallback_to_individual_analysis(images_data)
            
        except Exception as e:
            print(f"❌ Erreur dans l'analyse batch: {e}")
            return self._fallback_to_individual_analysis(images_data)
    
    def _process_batch_results(self, analysis_results: List[Dict], images_data: List[Tuple[int, str, str]]) -> List[Dict]:
                        
        room_classifications = []
        
        
        print(f"[DEBUG] Processing batch results: {len(analysis_results)} analysis results, {len(images_data)} images")
        
        for i, (image_index, image_url, _) in enumerate(images_data):
            
            result = None
            for analysis in analysis_results:
                if analysis.get('image_index') == image_index:
                    result = analysis
                    break
            
            if not result and i < len(analysis_results):
                
                result = analysis_results[i]
                print(f"[DEBUG] Using result at index {i} for image index {image_index}")
            
            if not result:
                print(f"[DEBUG] No result found for image index {image_index}, using default")
                room_classifications.append({
                    'image_index': image_index,
                    'image_url': image_url,
                    'room_type_id': 'other',  
                    'room_type_details': self.get_room_type_by_id('other'), 
                    'is_habitable': None,
                    'confidence_score': None,
                    'main_characteristics': [],
                    'potential_issues': [],
                    'estimated_condition': None,
                    'dominant_style_elements': [],
                    'lighting_quality': None,
                    'renovation_need_impression': None,
                    'additional_notes': None,
                    'same_room_as': [],
                    'is_duplicate': False,
                    'raw_analysis_json': analysis_result_dict  # Stocker l'analyse JSON analysée de Gemini
                })
                continue

            self.logger.debug(f"[DEBUG] Result for image {image_index}: {result}")

            room_type = result.get('room_type', 'other')
            
            
            raw_same_room_as = result.get('same_room_as', [])
            processed_same_room_as = []
            if isinstance(raw_same_room_as, list):
                for item in raw_same_room_as:
                    if isinstance(item, int):
                        processed_same_room_as.append(item)
                    elif isinstance(item, dict):
                        idx = item.get('image_index', item.get('index', item.get('id')))
                        if isinstance(idx, int):
                            processed_same_room_as.append(idx)
                        else:
                            self.logger.warning(f"[DEBUG] Discarding invalid item in same_room_as for image {image_index}: {item}")
                    else:
                        self.logger.warning(f"[DEBUG] Discarding unexpected item type in same_room_as for image {image_index}: {item}")
            else:
                self.logger.warning(f"[DEBUG] 'same_room_as' for image {image_index} is not a list: {raw_same_room_as}. Defaulting to empty list.")
            
            same_room_as = processed_same_room_as

            
            room_details = self.get_room_type_by_id(room_type)
            if not room_details:
                room_type = 'other'
                room_details = self.get_room_type_by_id('other')
            
            
            is_duplicate = len(same_room_as) > 0
            
            room_classifications.append({
                'image_index': image_index,
                'image_url': image_url,
                'room_type_id': room_type,
                'room_type_details': room_details,
                'is_habitable': room_details['is_habitable'] if room_details else None,
                'same_room_as': same_room_as,
                'is_duplicate': is_duplicate
            })
        
        
        for classification in room_classifications:
            for same_index in classification['same_room_as']:
                
                for other_classification in room_classifications:
                    if other_classification['image_index'] == same_index:
                        if classification['image_index'] not in other_classification['same_room_as']:
                            other_classification['same_room_as'].append(classification['image_index'])
        
        return room_classifications
    
    def _fallback_to_individual_analysis(self, images_data: List[Tuple[int, str, str]]) -> Tuple[List[Dict], List[str]]:
        
        self.logger.info("🔄 Basculement vers l'analyse individuelle des images...")
        room_classifications = []
        image_data_cache = {}  
        individual_raw_json_strings = [] 
        for image_index, image_url, image_base64 in images_data:
            image_data_cache[image_index] = image_base64
            
            analysis_result_dict, raw_json_response_str = self._classify_room_with_gemini(image_base64)
            
            if raw_json_response_str:
                individual_raw_json_strings.append(raw_json_response_str)
            
            
            classification_entry = {
                'image_index': image_index,
                'image_url': image_url,
                'room_type_id': 'other',  
                'room_type_details': self.get_room_type_by_id('other'), 
                'is_habitable': None,
                'confidence_score': None,
                'main_characteristics': [],
                'potential_issues': [],
                'estimated_condition': None,
                'dominant_style_elements': [],
                'lighting_quality': None,
                'renovation_need_impression': None,
                'additional_notes': None,
                'same_room_as': [],
                'is_duplicate': False,
                'raw_analysis_json': analysis_result_dict  # Stocker l'analyse JSON analysée de Gemini
            }

            if analysis_result_dict:  # Si Gemini a renvoyé un JSON analysé valide
                classification_entry['room_type_id'] = analysis_result_dict.get('identified_room_type_id', 'other')
                classification_entry['is_habitable'] = analysis_result_dict.get('is_likely_habitable')  # Directement de l'évaluation de Gemini
                classification_entry['confidence_score'] = analysis_result_dict.get('confidence_score')
                classification_entry['main_characteristics'] = analysis_result_dict.get('main_characteristics', [])
                classification_entry['potential_issues'] = analysis_result_dict.get('potential_issues', [])
                classification_entry['estimated_condition'] = analysis_result_dict.get('estimated_condition')
                classification_entry['dominant_style_elements'] = analysis_result_dict.get('dominant_style_elements', [])
                classification_entry['lighting_quality'] = analysis_result_dict.get('lighting_quality')
                classification_entry['renovation_need_impression'] = analysis_result_dict.get('renovation_need_impression')
                classification_entry['additional_notes'] = analysis_result_dict.get('additional_notes')
                
                # Obtenir room_type_details de notre liste locale
                current_identified_type = classification_entry['room_type_id']
                if current_identified_type and current_identified_type != 'other':
                    room_details_from_local = self.get_room_type_by_id(current_identified_type)
                    if room_details_from_local:
                        classification_entry['room_type_details'] = room_details_from_local
                        # Si Gemini n'a pas fourni 'is_likely_habitable', essayez d'utiliser les données locales, mais celles de Gemini sont préférées.
                        if classification_entry['is_habitable'] is None:
                             classification_entry['is_habitable'] = room_details_from_local.get('is_habitable')
                    else: # Gemini a identifié un type qui ne figure pas dans notre liste locale
                        self.logger.warning(f"Gemini a identifié le type de pièce '{current_identified_type}' qui ne figure pas dans room_type_classes.json local pour l'image {image_url}")
                        classification_entry['room_type_details'] = self.get_room_type_by_id('other') # Revenir aux détails 'other'
                elif current_identified_type == 'other': # Assurez-vous que les détails 'other' sont définis si le type est 'other'
                     classification_entry['room_type_details'] = self.get_room_type_by_id('other')

            else:  # L'appel à Gemini a échoué ou a renvoyé un JSON vide/invalide
                self.logger.warning(f"Aucun JSON d'analyse valide reçu de Gemini pour l'image {image_url}. Utilisation des valeurs par défaut.")
                # Les valeurs par défaut sont déjà définies, 'raw_analysis_json' sera None ou un dict vide

            room_classifications.append(classification_entry)
        
            # Phase 2: Détection des doublons si activée
        if self.enable_duplicate_detection:
            self.logger.info("🕵️ Détection des doublons activée pour l'analyse individuelle...")
            for i in range(len(room_classifications)):
                current_entry = room_classifications[i]
                current_room_type_id = current_entry.get('room_type_id') 
                
                if not current_room_type_id or current_room_type_id == 'other': # Ignorer la comparaison si le type de pièce est 'other' ou non identifié
                    continue
                    
                for j in range(i + 1, len(room_classifications)):
                    next_entry = room_classifications[j]
                    next_room_type_id = next_entry.get('room_type_id')
                    
                    if not next_room_type_id or next_room_type_id == 'other':
                        continue
                    
                    if current_room_type_id == next_room_type_id:
                        self.logger.debug(f"Comparaison de l'image {current_entry['image_index']} et {next_entry['image_index']} pour la duplication (type: {current_room_type_id})")
                        try:
                            is_same_room = self._compare_images_with_gemini(
                                image_data_cache[current_entry['image_index']], 
                                image_data_cache[next_entry['image_index']]
                            )
                            
                            if is_same_room:
                                self.logger.info(f"Doublon détecté: L'image {next_entry['image_index']} est la même que {current_entry['image_index']}")
                                current_entry['same_room_as'].append(next_entry['image_index'])
                                next_entry['same_room_as'].append(current_entry['image_index'])
                                next_entry['is_duplicate'] = True
                        except Exception as e:
                            self.logger.error(f"Erreur lors de la comparaison des images {current_entry['image_index']} et {next_entry['image_index']} pour la duplication: {e}")

        return room_classifications, individual_raw_json_strings
        
    def analyze_listing_rooms(self, listing_url: str) -> Dict:
        
        
        
        
        print(f"Analyse de l'annonce: {listing_url}")
        start_time = time.time()
    
        
        listing_details = get_listing_details(listing_url)
        if not listing_details or 'image_urls' not in listing_details:
            return {
                'error': 'Impossible de récupérer les images de l\'annonce',
                'listing_url': listing_url
            }
        
        image_urls = listing_details['image_urls']
        if not image_urls:
            return {
                'error': 'Aucune image trouvée dans l\'annonce',
                'listing_url': listing_url
            }
        
        print(f"Trouvé {len(image_urls)} images à analyser")
        
        
        images_data = []
        failed_images = []
        
        for i, image_url in enumerate(image_urls):
            print(f"Téléchargement de l'image {i+1}/{len(image_urls)}: {image_url}")
            
            # Télécharge et encode l'image
            image_base64 = self._download_and_encode_image(image_url)
            if image_base64:
                images_data.append((i, image_url, image_base64))
            else:
                failed_images.append({
                    'image_index': i,
                    'image_url': image_url,
                    'room_type_id': None,
                    'room_type_details': None,
                    'is_habitable': None,
                    'error': 'Impossible de télécharger l\'image',
                    'same_room_as': [],
                    'is_duplicate': False
                })
        
        print(f"✅ {len(images_data)} images téléchargées avec succès, {len(failed_images)} échecs")
        
        # Analyse les images selon le mode choisi
        if self.batch_mode and len(images_data) > 0:
            print("🚀 Mode batch activé - analyse de toutes les images en une seule requête")
            batch_mode_raw_outputs = []
            # Limité à 8 images par lot pour optimiser la vitesse
            max_batch_size = 8
            if len(images_data) > max_batch_size:
                print(f"Trop d'images pour un seul lot ({len(images_data)}), division en lots de {max_batch_size}")
                all_classifications = []
                for i in range(0, len(images_data), max_batch_size):
                    batch = images_data[i:i+max_batch_size]
                    print(f"Traitement du lot {i//max_batch_size + 1}/{(len(images_data) + max_batch_size - 1)//max_batch_size}")
                    batch_classifications, batch_raw_json = self._analyze_all_images_batch(batch)
                    if batch_classifications:
                        all_classifications.extend(batch_classifications)
                    if batch_raw_json:
                        batch_mode_raw_outputs.append(batch_raw_json)
                room_classifications = all_classifications
            else:
                classifications, raw_json = self._analyze_all_images_batch(images_data)
                room_classifications = classifications if classifications is not None else []
                if raw_json:
                    batch_mode_raw_outputs.append(raw_json)
        else:
            print("🔄 Mode individuel - analyse image par image")
            individual_mode_raw_output = [] # Initialize
            classifications, raw_jsons = self._fallback_to_individual_analysis(images_data)
            room_classifications = classifications if classifications is not None else []
            if raw_jsons:
                individual_mode_raw_output = raw_jsons
        
        # Ajouter les images qui ont échoué au téléchargement
        room_classifications.extend(failed_images)
        
        # Trier par index d'image pour maintenir l'ordre
        room_classifications.sort(key=lambda x: x['image_index'])
        
        # Calculer les statistiques finales
        unique_rooms = set()
        duplicate_count = 0
        room_counts = {}
        room_counts_with_duplicates = {}
        habitable_rooms = 0
        
        print(f"[DEBUG] Calculating statistics from {len(room_classifications)} classifications")
        
        for classification in room_classifications:
            room_type = classification['room_type_id']
            is_duplicate = classification['is_duplicate']
            
            print(f"[DEBUG] Processing room: {room_type}, is_duplicate: {is_duplicate}")
            
            # Compter les pièces uniques
            if not is_duplicate:
                unique_rooms.add(room_type)
                
                # Incrémenter le compteur pour ce type de pièce
                if room_type in room_counts:
                    room_counts[room_type] += 1
                else:
                    room_counts[room_type] = 1
                    
                if classification.get('is_habitable'):
                    habitable_rooms += 1
            else:
                duplicate_count += 1
                
            # Toujours incrémenter le compteur avec doublons
            if room_type in room_counts_with_duplicates:
                room_counts_with_duplicates[room_type] += 1
            else:
                room_counts_with_duplicates[room_type] = 1
                
        print(f"[DEBUG] Final statistics: unique_rooms={len(unique_rooms)}, duplicate_count={duplicate_count}")
        print(f"[DEBUG] Room counts (unique): {room_counts}")
        print(f"[DEBUG] Room counts (with duplicates): {room_counts_with_duplicates}")
        print(f"[DEBUG] Habitable rooms (unique): {habitable_rooms}")

        # Traiter les classifications pour obtenir les détails nécessaires pour le résumé
        room_classifications_processed = []
        for classification in room_classifications:
            room_details = self.get_room_type_by_id(classification['room_type_id'])
            processed_classification = classification.copy()
            processed_classification['room_type_details'] = room_details
            room_classifications_processed.append(processed_classification)

        # Déterminer la source des résultats bruts de Gemini
        actual_raw_gemini_output_for_summary_and_db = None # Utilisé pour le résumé et la sauvegarde DB
        actual_raw_gemini_output_for_metrics = None    # Spécifiquement pour _calculate_aggregated_visual_metrics

        if self.batch_mode:
            if 'batch_mode_raw_outputs' in locals() and batch_mode_raw_outputs:
                if len(batch_mode_raw_outputs) == 1:
                    actual_raw_gemini_output_for_summary_and_db = batch_mode_raw_outputs[0]
                    actual_raw_gemini_output_for_metrics = batch_mode_raw_outputs[0]
                elif len(batch_mode_raw_outputs) > 1:
                    self.logger.warning("Multiple batch raw outputs found. Using the first batch for aggregated metrics. Consider a more robust merging strategy for summary/DB.")
                    actual_raw_gemini_output_for_summary_and_db = batch_mode_raw_outputs # Conserver la liste pour le moment
                    actual_raw_gemini_output_for_metrics = batch_mode_raw_outputs[0] # Métriques sur le premier lot
                else:
                    self.logger.warning("Batch mode raw results were empty.")
            elif len(images_data) > 0:
                self.logger.warning("Batch mode was active but no raw outputs were captured.")
        else:  # Mode individuel
            if 'individual_mode_raw_output' in locals() and individual_mode_raw_output:
                actual_raw_gemini_output_for_summary_and_db = individual_mode_raw_output  # Liste de chaînes JSON
                try:
                    # Pour les métriques, nous avons besoin d'une chaîne JSON d'une liste de dicts
                    parsed_individual_outputs = [json.loads(s) for s in individual_mode_raw_output]
                    actual_raw_gemini_output_for_metrics = json.dumps(parsed_individual_outputs)
                except json.JSONDecodeError as e:
                    self.logger.error(f"Error processing individual mode raw outputs for metrics: {e}")
            elif len(images_data) > 0:
                self.logger.warning("Individual mode raw results were empty.")

        # Générer le résumé de la propriété
        # _generate_property_summary attend une liste de dictionnaires (résultats d'analyse Gemini parsés)
        # actual_raw_gemini_output_for_summary_and_db peut être une chaîne JSON (batch unique) ou une liste de chaînes JSON (individuel/batch multiple)
        # Nous devons le normaliser pour _generate_property_summary
        summary_input_data = [] 
        if actual_raw_gemini_output_for_summary_and_db:
            for item in actual_raw_gemini_output_for_summary_and_db:
                # Déterminer si l'élément est déjà un objet Python (dict ou list) ou une chaîne JSON
                if isinstance(item, str):
                    try:
                        parsed_item = json.loads(item)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse an item from raw output list for summary: {e}")
                        continue
                else:
                    parsed_item = item  # Déjà analysé

                # Traiter l'élément analysé
                if isinstance(parsed_item, dict) and 'image_analyses' in parsed_item and isinstance(parsed_item['image_analyses'], list):
                    summary_input_data.extend(parsed_item['image_analyses'])
                elif isinstance(parsed_item, list):  # Liste d'analyses
                    summary_input_data.extend(parsed_item)
                elif isinstance(parsed_item, dict):  # Analyse unique
                    summary_input_data.append(parsed_item)

        property_summary_dict = self._generate_property_summary(summary_input_data if summary_input_data else room_classifications_processed)

        # Calculer les métriques visuelles agrégées
        self.logger.debug(f"CASCADE_DEBUG: Content of actual_raw_gemini_output_for_metrics before calling _calculate_aggregated_visual_metrics (type: {type(actual_raw_gemini_output_for_metrics)}): {str(actual_raw_gemini_output_for_metrics)[:1000]}...")
        visual_metrics = self._calculate_aggregated_visual_metrics(actual_raw_gemini_output_for_metrics)
        
        # Encode numeric visual features
        numeric_visual_features = self._encode_numeric_visual_features(
            visual_metrics,
            room_counts,
            property_summary_dict,
            total_images=len(image_urls),
            duplicate_count=duplicate_count,
            habitable_rooms=habitable_rooms,
            room_classifications=room_classifications
        )

        # Sauvegarder dans la base de données
        if actual_raw_gemini_output_for_summary_and_db: # S'assurer qu'il y a quelque chose à sauvegarder
            try:
                # Pour la base de données, nous voulons stocker la chaîne JSON brute telle quelle (ou une représentation en chaîne de la liste)
                if isinstance(actual_raw_gemini_output_for_summary_and_db, list):
                    raw_gemini_json_string_for_db = json.dumps(actual_raw_gemini_output_for_summary_and_db)
                else: # C'est déjà une chaîne (espérons-le)
                    raw_gemini_json_string_for_db = actual_raw_gemini_output_for_summary_and_db

                analysis_id = uuid.uuid4().hex
                current_execution_time = time.time() - start_time # Recalculer pour inclure le traitement du résumé

                self._save_analysis_to_db(
                    analysis_id=analysis_id,
                    listing_id_url=listing_url,
                    total_images=len(image_urls),
                    successfully_classified_images=len(room_classifications) - len(failed_images),
                    unique_rooms_detected=len(unique_rooms),
                    duplicate_images_found=duplicate_count,
                    execution_time=current_execution_time,
                    batch_mode_used=self.batch_mode,
                    room_summary_data=property_summary_dict.get('room_counts', {}),
                    avg_impression_score=numeric_visual_features.get("overall_impression_score_avg"),
                    dominant_clutter_level=numeric_visual_features.get("dominant_clutter_level"),
                    max_renovation_need=numeric_visual_features.get("max_renovation_need"),
                    property_summary_text=property_summary_dict.get('property_summary_text', ''),
                    key_features_text=property_summary_dict.get('key_features', []),
                    visible_issues_text=property_summary_dict.get('visible_issues', []),
                    raw_gemini_response=raw_gemini_json_string_for_db,
                    overall_condition=property_summary_dict.get('overall_condition', ''),
                    dominant_style=property_summary_dict.get('dominant_style', ''),
                    overall_lighting=property_summary_dict.get('overall_lighting', ''),
                    numeric_visual_features=numeric_visual_features,
                    overall_impression_score_avg=numeric_visual_features.get("overall_impression_score_avg"),
                    overall_impression_score_median=numeric_visual_features.get("overall_impression_score_median"),
                    clutter_level_mode=numeric_visual_features.get("clutter_level_mode"),
                    estimated_renovation_need_mode=numeric_visual_features.get("estimated_renovation_need_mode"),
                    habitable_room_ratio=numeric_visual_features.get("habitable_room_ratio"),
                    duplicate_ratio=numeric_visual_features.get("duplicate_ratio"),
                    total_unique_rooms=numeric_visual_features.get("total_unique_rooms")
                )
                self.logger.info(f"[DB] Analysis for '{listing_url}' (ID: {analysis_id}) saved/updated in analysis_results.")
            except Exception as e:
                self.logger.error(f"[DB ERROR] Failed to save analysis for '{listing_url}': {e}", exc_info=True)
        else:
            self.logger.warning("No raw Gemini output available to generate summary or save to DB.")

        # Créer l'objet de résultats final
        final_results_object = {
            'listing_url': listing_url,
            'listing_details': listing_details,
            'total_images': len(image_urls),
            'successfully_downloaded': len(images_data),
            'failed_to_download': len(failed_images),
            'room_classifications_processed': room_classifications_processed,
            'room_summary': room_counts, # Pièces uniques
            'room_summary_with_duplicates': room_counts_with_duplicates, # Avec doublons
            'unique_rooms_detected': len(unique_rooms),
            'unique_room_types_detected': len(unique_rooms),  # alias for backward compatibility
            'duplicate_images_found': duplicate_count,
            'habitable_rooms_unique_count': habitable_rooms,
            'habitable_rooms_count': habitable_rooms,  # alias for backward compatibility
            'property_summary': property_summary_dict, # Contient le texte et les détails structurés
            'raw_gemini_analysis': actual_raw_gemini_output_for_summary_and_db, # La sortie brute consolidée
            'visual_metrics': visual_metrics,
            'numeric_visual_features': numeric_visual_features,
            'analysis_mode': "batch" if self.batch_mode else "individual",
            'execution_time': time.time() - start_time
        }

        return final_results_object
    
    def get_room_type_by_id(self, room_id: str) -> Optional[Dict]:
        """Retourne les détails d'un type de pièce par son ID."""
        room_types = self._load_room_types()
        return next((room for room in room_types if room['id'] == room_id), None)
    
    def _encode_numeric_visual_features(
        self,
        visual_metrics: Dict,
        room_counts: Dict,
        property_summary: Dict,
        *,
        total_images: int = None,
        duplicate_count: int = None,
        habitable_rooms: int = None,
        room_classifications: List[Dict] = None
    ) -> Dict:
        """Convert multiple visual & summary metrics into numeric form for ML."""
        numeric: Dict[str, float] = {}

        # 1. Visual metrics (from GEMINI aggregated)
        if visual_metrics:
            if visual_metrics.get("avg_impression_score") is not None:
                numeric["avg_impression_score"] = float(visual_metrics["avg_impression_score"])

            clutter_map = {
                "Minimal Clutter": 0,
                "Low": 0,
                "Slight Clutter": 1,
                "Medium": 1,
                "Moderate Clutter": 2,
                "High": 2,
                "Heavy Clutter": 3
            }
            clut = visual_metrics.get("dominant_clutter_level")
            if clut in clutter_map:
                numeric["dominant_clutter_level"] = clutter_map[clut]

            renovation_map = {
                "None": 0,
                "Minor Cosmetic Updates": 1,
                "Moderate Renovation": 2,
                "Significant Renovation": 3,
                "Full Gut Renovation": 4
            }
            reno = visual_metrics.get("max_renovation_need")
            if reno in renovation_map:
                numeric["max_renovation_need"] = renovation_map[reno]

            # Yeni ayrıntılı metrik sözlüğünü işle
            detailed = visual_metrics.get("metrics")
            if isinstance(detailed, dict):
                def _slug(text: str) -> str:
                    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:40]

                for dk, dv in detailed.items():
                    if isinstance(dv, (int, float)):
                        # Sayısal değerleri doğrudan ekle
                        numeric[dk] = float(dv)
                    elif isinstance(dv, bool):
                        numeric[dk] = 1.0 if dv else 0.0
                    elif isinstance(dv, str):
                        # Kategorik değerler için one-hot (değer başına 1)
                        slug_val = _slug(dv)
                        numeric[f"{dk}_{slug_val}"] = 1
                    # list/diğer tipleri şimdilik atla – genellikle ratio olarak zaten sayısal geliyor

        # 2. Room stats
        if room_counts:
            numeric["total_unique_rooms"] = int(sum(room_counts.values()))
            for rt, count in room_counts.items():
                numeric[f"room_count_{rt}"] = int(count)
                # presence flag
                numeric[f"has_{rt}"] = 1

            total_rooms = numeric.get("total_unique_rooms", 0)
            if total_rooms > 0 and habitable_rooms is not None:
                numeric["habitable_room_ratio"] = round(habitable_rooms / total_rooms, 3)

        # Duplicate / image stats
        if total_images is not None:
            numeric["total_images"] = total_images
        if duplicate_count is not None and total_images:
            numeric["duplicate_ratio"] = round(duplicate_count / total_images, 3)

        # 3. Property summary metrics (textual -> numeric)
        if property_summary:
            # Overall condition ordinal
            cond_map = {"Excellent": 3, "Good": 2, "Fair": 1, "Poor": 0}
            cond = property_summary.get("overall_condition")
            if cond in cond_map:
                numeric["overall_condition"] = cond_map[cond]

            # Dominant style id mapping
            style_map = {
                "Modern": 1,
                "Scandinavian": 2,
                "Loft": 3,
                "Classic": 4,
                "Rustic": 5,
                "Industrial": 6,
                "Minimalist": 7,
                "Other": 0
            }
            style = property_summary.get("dominant_style")
            if style in style_map:
                numeric["dominant_style_id"] = style_map[style]

            # Lighting quality
            light_map = {"Dark": 0, "Normal": 1, "Bright": 2}
            light = property_summary.get("overall_lighting")
            if light in light_map:
                numeric["overall_lighting"] = light_map[light]

            # Key feature / visible issue counts
            kf = property_summary.get("key_features")
            if isinstance(kf, list):
                numeric["key_feature_count"] = len(kf)

            vis_iss = property_summary.get("visible_issues")
            if isinstance(vis_iss, list):
                numeric["visible_issue_count"] = len(vis_iss)
                # severity distribution
                sev_map = {"Minor": 1, "Moderate": 2, "Major": 3, "Critical": 4}
                for sev_label in sev_map.keys():
                    numeric[f"issue_severity_{sev_label.lower()}"] = 0
                for issue in vis_iss:
                    sev = issue.get("severity")
                    if sev in sev_map:
                        key = f"issue_severity_{sev.lower()}"
                        numeric[key] = numeric.get(key, 0) + 1

        # 4. Detailed per-room analyses (optional)
        if room_classifications:
            confidences = [rc.get("confidence_score") for rc in room_classifications if isinstance(rc.get("confidence_score"), (int, float))]
            if confidences:
                numeric["avg_confidence_score"] = round(sum(confidences)/len(confidences), 3)

            # Estimated condition mapping
            cond_ord = {"excellent": 3, "very good": 2, "good": 1, "fair": 0, "poor": 0}
            cond_vals = []
            reno_vals = []
            lighting_vals = []
            habitable_flags = []
            style_counter: Dict[str,int] = {}
            for rc in room_classifications:
                est_cond = rc.get("estimated_condition")
                if est_cond:
                    key = str(est_cond).lower()
                    if key in cond_ord:
                        cond_vals.append(cond_ord[key])

                ren_need = rc.get("renovation_need_impression")
                if ren_need:
                    rn_key = str(ren_need).lower()
                    ren_map = {
                        "none": 0,
                        "low": 1,
                        "minor cosmetic updates": 1,
                        "minor": 1,
                        "moderate": 2,
                        "moderate renovation": 2,
                        "significant": 3,
                        "significant renovation": 3,
                        "full": 4,
                        "full gut renovation": 4
                    }
                    if rn_key in ren_map:
                        reno_vals.append(ren_map[rn_key])

                light_q = rc.get("lighting_quality")
                if light_q:
                    lq_key = str(light_q).lower()
                    light_map_det = {
                        "poor": 0,
                        "adequate": 1,
                        "good": 2,
                        "excellent": 3
                    }
                    for k,v in light_map_det.items():
                        if k in lq_key:
                            lighting_vals.append(v)
                            break

                habitable_flags.append(1 if rc.get("is_likely_habitable") else 0)

                # styles
                styles = rc.get("dominant_style_elements")
                if isinstance(styles, list):
                    for st in styles:
                        st_lower = str(st).strip().lower()
                        style_counter[st_lower] = style_counter.get(st_lower,0)+1

            if cond_vals:
                numeric["avg_estimated_condition"] = round(sum(cond_vals)/len(cond_vals),3)
            if reno_vals:
                numeric["avg_renovation_need"] = round(sum(reno_vals)/len(reno_vals),3)
            if lighting_vals:
                numeric["avg_lighting_quality"] = round(sum(lighting_vals)/len(lighting_vals),3)
            if habitable_flags:
                numeric["habitable_image_ratio"] = round(sum(habitable_flags)/len(habitable_flags),3)

            # encode top styles frequency (top 5)
            top_styles = sorted(style_counter.items(), key=lambda x: x[1], reverse=True)[:5]
            for st, cnt in top_styles:
                numeric[f"style_freq_{st.replace(' ','_')}"] = cnt

            # Potential issue statistics
            total_issues = 0
            severity_map_num = {"minor": 1, "low":1, "moderate":2, "medium":2, "major":3, "significant":3, "critical":4}
            severity_values = []
            condition_dist: Dict[str,int] = {}
            for rc in room_classifications:
                issues = rc.get("potential_issues")
                if isinstance(issues, list):
                    total_issues += len(issues)
                    for iss in issues:
                        sev = str(iss.get("severity", "")).lower()
                        if sev in severity_map_num:
                            severity_values.append(severity_map_num[sev])

                # condition distribution per room
                cond_raw = str(rc.get("estimated_condition", "")).lower()
                if cond_raw:
                    condition_bucket = cond_raw.split()[0]  # get first word
                    condition_dist[condition_bucket] = condition_dist.get(condition_bucket,0)+1

            numeric["total_potential_issues"] = total_issues
            if severity_values:
                numeric["avg_issue_severity"] = round(sum(severity_values)/len(severity_values),3)

            # encode condition distribution counts
            for cond_label, cnt in condition_dist.items():
                numeric[f"condition_freq_{cond_label}"] = cnt

            # style diversity
            numeric["unique_style_count"] = len(style_counter)

            # weighted renovation need score (max)
            if reno_vals:
                numeric["max_renovation_need"] = max(reno_vals)

        # 6. Characteristic & Issue frequencies (vocab based)
        vocab = getattr(self, "_feature_issue_vocab", {"characteristics": [], "visible_issues": []})
        chars_vocab = vocab.get("characteristics", [])
        issues_vocab = vocab.get("visible_issues", [])

        if room_classifications and (chars_vocab or issues_vocab):
            # Initialize counters
            char_counts: Dict[str, int] = {c: 0 for c in chars_vocab}
            issue_counts: Dict[str, int] = {i: 0 for i in issues_vocab}

            total_images_local = len(room_classifications)

            for rc in room_classifications:
                for feat in rc.get("main_characteristics", []):
                    key = str(feat).strip().lower()
                    if key in char_counts:
                        char_counts[key] += 1
                for iss in rc.get("visible_issues", []):
                    if isinstance(iss, dict):
                        key = str(iss.get("issue", "")).strip().lower()
                        if key in issue_counts:
                            issue_counts[key] += 1

            def _slug(text: str) -> str:
                return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]

            # Add to numeric dict: ratio per item (0-1)
            for k, cnt in char_counts.items():
                slug = _slug(k)
                numeric[f"char_{slug}_ratio"] = round(cnt / total_images_local, 3) if total_images_local else 0.0
            for k, cnt in issue_counts.items():
                slug = _slug(k)
                numeric[f"issue_{slug}_ratio"] = round(cnt / total_images_local, 3) if total_images_local else 0.0

        return numeric

    def _calculate_aggregated_visual_metrics(self, raw_gemini_json_string: Optional[str]) -> Dict:
        """Gemini'den gelen tüm görsel analizleri tarayarak dinamik ve kapsamlı metrikler
        üretir.

        Çıktı yapısı örnek:
        {
            "avg_impression_score": 4.2,
            "dominant_clutter_level": "Minimal Clutter",
            "max_renovation_need": "Moderate Renovation",
            "metrics": {               # 250+ öğe potansiyeli
                "overall_impression_score_avg": 4.2,
                "clutter_level_mode": "Minimal Clutter",
                "estimated_condition_mode": "Good",
                "visible_issues_count": 17,
                "feature_Balcony access_ratio": 0.25,
                ...
            }
        }
        """

        if not raw_gemini_json_string:
            return {
                "avg_impression_score": None,
                "dominant_clutter_level": None,
                "max_renovation_need": None,
                "metrics": {}
            }

        # raw_gemini_json_string could be (1) list, (2) dict with 'image_analyses', (3) JSON string
        if isinstance(raw_gemini_json_string, list):
            all_image_analyses = raw_gemini_json_string
        elif isinstance(raw_gemini_json_string, dict):
            if "image_analyses" in raw_gemini_json_string and isinstance(raw_gemini_json_string["image_analyses"], list):
                all_image_analyses = raw_gemini_json_string["image_analyses"]
            else:
                # dict already represents a single analysis entry
                all_image_analyses = [raw_gemini_json_string]
        else:
            try:
                all_image_analyses = json.loads(raw_gemini_json_string)
            except Exception as e:
                self.logger.error(f"_calculate_aggregated_visual_metrics: JSON decode error: {e}")
                return {
                    "avg_impression_score": None,
                    "dominant_clutter_level": None,
                    "max_renovation_need": None,
                    "metrics": {}
                }

        if not isinstance(all_image_analyses, list) or not all_image_analyses:
            self.logger.warning("_calculate_aggregated_visual_metrics: No image analyses found – skipping aggregation.")
            return {
                "avg_impression_score": None,
                "dominant_clutter_level": None,
                "max_renovation_need": None,
                "metrics": {}
            }

        from collections import defaultdict, Counter
        import statistics
        numeric_sum: Dict[str, float] = defaultdict(float)
        numeric_count: Dict[str, int] = defaultdict(int)
        numeric_values: Dict[str, list] = defaultdict(list)  # store each numeric for median/min/max
        categorical_counter: Dict[str, Counter] = defaultdict(Counter)
        list_counter: Dict[str, Counter] = defaultdict(Counter)

        # Walk through each analysis dict
        for analysis in all_image_analyses:
            if not isinstance(analysis, dict):
                continue
            for key, value in analysis.items():
                if value is None:
                    continue
                # Numeric (int / float)
                if isinstance(value, (int, float)):
                    f_val = float(value)
                    numeric_sum[key] += f_val
                    numeric_count[key] += 1
                    numeric_values[key].append(f_val)
                # Boolean -> treat as numeric 0/1
                elif isinstance(value, bool):
                    f_val = 1.0 if value else 0.0
                    numeric_sum[key] += f_val
                    numeric_count[key] += 1
                    numeric_values[key].append(f_val)
                # String categorical
                elif isinstance(value, str):
                    categorical_counter[key][value] += 1
                # List handling: list[str] or list[dict]
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            list_counter[key][item] += 1
                        elif isinstance(item, dict):
                            # Flatten dict items by key=value string
                            for k2, v2 in item.items():
                                list_counter[f"{key}_{k2}"][str(v2)] += 1
                # Dict value – flatten one level
                elif isinstance(value, dict):
                    for k2, v2 in value.items():
                        if isinstance(v2, (int, float)):
                            nk = f"{key}_{k2}"
                            numeric_sum[nk] += float(v2)
                            numeric_count[nk] += 1
                            numeric_values[nk].append(float(v2))
                        else:
                            categorical_counter[f"{key}_{k2}"][str(v2)] += 1
                else:
                    # Skip unsupported types
                    continue

        aggregated_metrics: Dict[str, any] = {}

        # Numeric statistics (avg, min, max, median)
        for k, total in numeric_sum.items():
            cnt = numeric_count.get(k, 0)
            if not cnt:
                continue
            vals = numeric_values.get(k, [])
            aggregated_metrics[f"{k}_avg"] = round(total / cnt, 3)
            aggregated_metrics[f"{k}_min"] = round(min(vals), 3)
            aggregated_metrics[f"{k}_max"] = round(max(vals), 3)
            aggregated_metrics[f"{k}_median"] = round(statistics.median(vals), 3)

        # Categorical modes
        for k, counter in categorical_counter.items():
            if counter:
                most_common_val, _ = counter.most_common(1)[0]
                aggregated_metrics[f"{k}_mode"] = most_common_val
                # also ratio of mode occurrence
                aggregated_metrics[f"{k}_mode_ratio"] = round(counter[most_common_val] / len(all_image_analyses), 3)

        # List counters -> ratio of each item (limit top 20 for brevity)
        for k, counter in list_counter.items():
            total_images = len(all_image_analyses)
            for item, cnt in counter.most_common(20):
                slug = re.sub(r"[^a-z0-9]+", "_", str(item).lower()).strip("_")[:40]
                aggregated_metrics[f"{k}_{slug}_ratio"] = round(cnt / total_images, 3)

        # Build raw_lists section for downstream detailed inspection
        raw_lists: Dict[str, Dict[str, int]] = {k: dict(counter) for k, counter in list_counter.items()}

        # Retain legacy primary metrics for backward compatibility
        avg_impression = aggregated_metrics.get("overall_impression_score_avg")
        dominant_clutter = aggregated_metrics.get("clutter_level_mode")
        max_reno_candidate = None
        # Determine most severe renovation need if available
        if "estimated_renovation_need_mode" in aggregated_metrics:
            renovation_order = [
                "Full Gut Renovation",
                "Significant Renovation",
                "Moderate Renovation",
                "Minor Cosmetic Updates",
                "None"
            ]
            mode_val = aggregated_metrics["estimated_renovation_need_mode"]
            if mode_val in renovation_order:
                max_reno_candidate = mode_val

        return {
            "avg_impression_score": avg_impression,
            "dominant_clutter_level": dominant_clutter,
            "max_renovation_need": max_reno_candidate,
            "metrics": aggregated_metrics,
            "raw_lists": raw_lists
        }
    
    def get_all_listings_for_map(self) -> List[Dict]:
        """Fetches all listings from the database that have coordinate data."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        listings_for_map = []
        try:
            cursor.execute("""
                SELECT 
                    listing_id, 
                    scraped_title, 
                    scraped_street_address, 
                    scraped_price, 
                    scraped_area, 
                    scraped_latitude, 
                    scraped_longitude
                FROM property_analyses
                WHERE scraped_latitude IS NOT NULL AND scraped_longitude IS NOT NULL;
            """)
            rows = cursor.fetchall()
            for row in rows:
                listings_for_map.append({
                    'id': row[0],  # Using listing_id as 'id' for map consistency
                    'title': row[1],
                    'address': row[2],
                    'price': row[3],
                    'area': row[4],
                    'latitude': row[5],
                    'longitude': row[6],
                    'detail_url': row[0]  # listing_id is the detail_url
                })
            self.logger.info(f"Fetched {len(listings_for_map)} listings with coordinates for map view.")
        except sqlite3.Error as e:
            self.logger.error(f"Database error while fetching listings for map: {e}")
        finally:
            if conn:
                conn.close()
        return listings_for_map

    def save_analysis_results(self, results: Dict, output_file: str = 'room_analysis_results.json'):
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Résultats sauvegardés dans {output_file}")
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde: {e}", exc_info=True)

if __name__ == "__main__":
    import os
    import logging
    import json  # Ensure json is imported for the main block if not already globally
    import textwrap  # Added for pretty printing the summary
    from dotenv import load_dotenv

    # Load environment variables from .env file if it exists
    # Try parent directory first, then current directory
    dotenv_path_parent = os.path.join(os.path.dirname(__file__), '..', '.env')
    dotenv_path_current = os.path.join(os.path.dirname(__file__), '.env')

    if os.path.exists(dotenv_path_parent):
        load_dotenv(dotenv_path_parent)
        print(f"Loaded .env file from: {dotenv_path_parent}")
    elif os.path.exists(dotenv_path_current):
        load_dotenv(dotenv_path_current)
        print(f"Loaded .env file from: {dotenv_path_current}")
    else:
        print("No .env file found in parent or current directory. Ensure GEMINI_API_KEY is set in your environment.")

    # Configure basic logging for the test
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') # Changed to DEBUG
    logger = logging.getLogger("analyze_the_rooms_main") # Specific logger name for main execution

    # Get Gemini API Key
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logger.error("GEMINI_API_KEY not found in environment variables or .env file.")
        exit(1)
    
    # Initialize RoomAnalyzer
    # Test with batch_mode=True and enable_duplicate_detection=True for a more comprehensive test
    analyzer = RoomAnalyzer(gemini_api_key=gemini_api_key, enable_duplicate_detection=True, batch_mode=True)
    
    # Example usage with a test Otodom URL
    test_listing_url = "https://www.otodom.pl/pl/oferta/krzyki-premium-2pok-tanio-vivaldiego-balkon-top-ID4wD4b"
    # test_listing_url = "https://www.otodom.pl/pl/oferta/mieszkanie-na-sprzedaz-3-pokoje-60m2-warszawa-ID4p77L" # Another example
    # test_listing_url = "https://www.otodom.pl/pl/oferta/przytulne-2-pokojowe-mieszkanie-z-balkonem-ID4oXjE" # Test with fewer images

    logger.info(f"Starting analysis for listing: {test_listing_url}")
    analysis_results = analyzer.analyze_listing_rooms(test_listing_url)
    
    if analysis_results and 'error' not in analysis_results:
        logger.info("Analysis completed successfully.")
        # Save results to a JSON file
        # Sanitize URL for filename
        safe_url_part = test_listing_url.split('/')[-1] if test_listing_url.split('/')[-1] else 'listing'
        output_filename = f"analysis_results_{safe_url_part}.json"
        analyzer.save_analysis_results(analysis_results, output_file=output_filename)
        logger.info(f"Full analysis results saved to {output_filename}")
        
        # Print a summary of the results
        print("\n--- Analysis Summary ---")
        print(f"Listing URL: {analysis_results.get('listing_url')}")
        print(f"Total Images: {analysis_results.get('total_images')}")
        print(f"Successfully Downloaded: {analysis_results.get('successfully_downloaded')}")
        print(f"Unique Room Types Detected: {analysis_results.get('unique_room_types_detected')}")
        print(f"Duplicate Images Found: {analysis_results.get('duplicate_images_found')}")
        print(f"Habitable Rooms (Unique): {analysis_results.get('habitable_rooms_unique_count')}")
        print(f"Analysis Mode: {analysis_results.get('analysis_mode')}")
        print(f"Execution Time: {analysis_results.get('execution_time'):.2f} seconds")
        
        if analysis_results.get('property_summary'):
            print("\nProperty Summary Text:")
            print(textwrap.fill(analysis_results['property_summary'].get('property_summary_text', 'N/A'), width=100))
            print("\nKey Features:")
            for feature in analysis_results['property_summary'].get('key_features', []):
                print(f"- {feature}")
            print("\nVisible Issues:")
            for issue in analysis_results['property_summary'].get('visible_issues', []):
                print(f"- {issue}")
        
        if analysis_results.get('visual_metrics'):
            print("\nVisual Metrics:")
            print(f"  Average Impression Score: {analysis_results['visual_metrics'].get('avg_impression_score')}")
            print(f"  Dominant Clutter Level: {analysis_results['visual_metrics'].get('dominant_clutter_level')}")
            print(f"  Max Renovation Need: {analysis_results['visual_metrics'].get('max_renovation_need')}")

        print("\nRoom Classification Details (Processed):")
        if analysis_results.get('room_classifications_processed'):
            for room_info in analysis_results['room_classifications_processed']:
                # Safely handle cases where 'room_type_details' might be None
                room_type_details = room_info.get('room_type_details') or {}
                room_name = room_type_details.get('name', 'Unknown')
                room_type_id = room_info.get('room_type_id', 'N/A')
                is_duplicate = room_info.get('is_duplicate')
                is_habitable = room_info.get('is_habitable')
                print(f"  - Image Index {room_info.get('image_index')}: {room_name} ({room_type_id}), Duplicate: {is_duplicate}, Habitable: {is_habitable}")
        else:
            print("  No processed room classifications available.")
            
    elif analysis_results and 'error' in analysis_results:
        logger.error(f"Analysis for {test_listing_url} failed: {analysis_results.get('error')}")
    else:
        logger.error(f"Analysis for {test_listing_url} returned no results or an unexpected structure.")

    logger.info("Test script finished. Check logs and database for details.")
