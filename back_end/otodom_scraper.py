import requests
import json
import logging
import time
import re
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
from back_end.analyze_the_rooms import RoomAnalyzer
from back_end.tasks import analyze_images_task
import math
from typing import Optional, Dict, List
from bs4 import BeautifulSoup
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from fetch_pro_helpers import ProFetcher
from cache import http_get_cached, http_set_cached, geo_get_cached, geo_set_cached
from schemas import ListingSchema
from metrics import SCRAPED_LISTINGS, SCRAPE_ERRORS, REQUEST_LATENCY, start_metrics_server
from datetime import datetime
import pandas as pd
from pathlib import Path
from db import upsert_listings

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# Start metrics on import
start_metrics_server(int(os.getenv("METRICS_PORT", "8000")))

BASE_OTODOM_SEARCH_URL_WROCLAW = (
    "https://www.otodom.pl/pl/oferty/sprzedaz/mieszkanie/wroclaw"
    "?distanceRadius=0&limit=36&viewType=listing&page={page}"
)
DEFAULT_MAX_PAGES = 3  # can be overridden

# Initialize Nominatim geocoder
# Using a custom user_agent is good practice as per Nominatim's usage policy
geolocator = Nominatim(user_agent="real_estate_agent_v2_scraper/1.0")

# ----------------------------- Otodom Offer API -----------------------------
OTODOM_OFFER_API = "https://www.otodom.pl/api/v1/offers/{id}"

# --------------------------- GraphQL Fallback ---------------------------
OTODOM_GRAPHQL_ENDPOINT = "https://www.otodom.pl/api/graphql"

GQL_OFFER_QUERY = (
    "query OfferBasic($id: ID!) {\n"
    "  offer(id: $id) {\n"
    "    id\n"
    "    description\n"
    "    location { latitude longitude }\n"
    "    parameters { key value }\n"
    "  }\n"
    "}\n"
)

# Toggle for hitting extra detail endpoints (Offer API / Detail HTML / GraphQL).
# Detail fetch toggled via env var; default True for richer data
ENABLE_DETAIL_FETCH = os.getenv("ENABLE_DETAIL_FETCH", "true").lower() == "true"
try:
    from selenium_detail_fetch import fetch_details_with_selenium  # type: ignore
    _SEL_AVAILABLE = True
except Exception:
    _SEL_AVAILABLE = False

DETAIL_MAX_WORKERS = int(os.getenv("DETAIL_MAX_WORKERS", "8"))  # Parallel detail fetchers

# Field aliases for robust extraction across API/key variants
FIELD_ALIASES = {
    "floor": ["floor", "floorLevel", "poziom"],
    "total_floors": ["totalFloors", "floorsTotal"],
    "year_built": ["constructionYear", "yearOfConstruction", "rokBudowy"],
    "building_type": ["buildingType", "buildingtype"],
    "condition": ["condition", "stan"],
    "parking_spaces": ["parkingCount", "parkingSpaces"],
    "balcony_area": ["balconyArea", "balconyarea"],
    "heating_type": ["heatingType", "heating", "heatType"],
}

# ----------------------------- ProFetcher -----------------------------
# Resolve data/raw relative to project root if env not set
RAW_DATA_DIR = os.getenv(
    "RAW_DATA_DIR",
    str(Path(__file__).resolve().parent.parent / "data" / "raw"),
)
FETCHER = ProFetcher(
    rate_limit=float(os.getenv("REQUEST_RATE_LIMIT", "0.5")),
    proxies=os.getenv("PROXY_LIST", "").split(",") if os.getenv("PROXY_LIST") else None,
)  # Handles retries + proxy rotation

def _get_from_param(param_map: Dict[str, any], field: str):
    """Return first non-empty value for any alias of field in param_map."""
    for alias in FIELD_ALIASES.get(field, []):
        val = param_map.get(alias)
        if val not in (None, "", [], {}):
            return val
    return None


def _merge_missing(dst: Dict[str, any], src: Dict[str, any]):
    """Fill missing keys in dst with values from src (non-destructive)."""
    for k, v in src.items():
        if dst.get(k) in (None, "", [], {}):
            dst[k] = v


def _normalize_listing_fields(listing: Dict[str, any]):
    int_fields = [
        "floor",
        "total_floors",
        "year_built",
        "parking_spaces",
    ]
    float_fields = ["balcony_area"]
    for f in int_fields:
        try:
            listing[f] = int(str(listing[f]).split()[0])  # strip units if any
        except (TypeError, ValueError):
            pass
    for f in float_fields:
        try:
            listing[f] = float(str(listing[f]).replace(",", "."))
        except (TypeError, ValueError):
            pass
    return listing


# ----------------------------- Detail enrichment helper -----------------------------

def _enrich_listing_details(listing: Dict[str, any]):
    """Fetch additional detail sources and merge into listing dict."""
    if not ENABLE_DETAIL_FETCH:
        return listing
    offer_id = listing.get("id")
    detail_url = listing.get("detail_url")
    try:
        api_data = fetch_offer_api(offer_id, detail_url) or {}
        gql_data = fetch_offer_graphql(offer_id) or {}
        html_data = fetch_detail_info(detail_url) or {}
        for extra in (api_data, gql_data, html_data):
            _merge_missing(listing, extra)
        _normalize_listing_fields(listing)
        # Eksik alanları doldur
        _fill_missing_fields(listing)
    except Exception as e:
        logging.debug(f"Detail enrichment failed for {offer_id}: {e}")
    return listing


def get_coordinates_for_address(address_str, city_name="Wrocław"):
    """Geocodes an address string to (latitude, longitude) using Nominatim after normalization."""
    
    normalized_address_str = address_str
    if normalized_address_str and isinstance(normalized_address_str, str):
        # Replace '/' with space
        normalized_address_str = normalized_address_str.replace('/', ' ')
        
        # Remove common prefixes (case-insensitive) and strip whitespace
        # This regex looks for 'ul.', 'al.', 'os.' possibly followed by a space, at the beginning of words.
        # It also handles cases where these might be part of a longer string if not careful, so we ensure they are somewhat standalone.
        prefixes_to_remove = [r'^ul\.\s*', r'^al\.\s*', r'^os\.\s*', r'^ulica\s+', r'^aleja\s+', r'^osiedle\s+']
        for prefix_pattern in prefixes_to_remove:
            normalized_address_str = re.sub(prefix_pattern, '', normalized_address_str, flags=re.IGNORECASE).strip()
        
        # Remove any remaining standalone 'ul', 'al', 'os' if they are full words after prefix removal
        # This is a bit more aggressive and might need refinement
        # standalone_words_to_remove = [r'\b(ul|al|os)\b\.?']
        # for word_pattern in standalone_words_to_remove:
        #     normalized_address_str = re.sub(word_pattern, '', normalized_address_str, flags=re.IGNORECASE).strip()
            
        # Final strip
        normalized_address_str = normalized_address_str.strip()
        
        if not normalized_address_str: # If stripping prefixes leaves an empty string
            full_address = city_name
        else:
            full_address = f"{normalized_address_str}, {city_name}"
    else:
        # If original address_str is missing or not a string, try with city only
        full_address = city_name

    logging.debug(f"Original address: '{address_str}', Normalized for geocoding: '{full_address}'")

    try:
        # Add a small delay to comply with usage policies (1 request per second)
        time.sleep(1)
        # Ensure country code is used for better accuracy, Nominatim default might be okay but explicit is better.
        location = geolocator.geocode(full_address, timeout=10, country_codes='pl') 
        if location:
            return location.latitude, location.longitude
        else:
            logging.warning(f"Could not geocode address: '{full_address}'. Location not found.")
            # Try again with just the city if normalization resulted in a specific address that failed
            if normalized_address_str and normalized_address_str != city_name:
                logging.info(f"Retrying geocoding with city only for: '{city_name}'")
                time.sleep(1)
                location_city = geolocator.geocode(city_name, timeout=10, country_codes='pl')
                if location_city:
                    return location_city.latitude, location_city.longitude
                else:
                    logging.warning(f"Could not geocode city: '{city_name}'. Location not found.")
            return None, None
    except GeocoderTimedOut:
        logging.error(f"Geocoding service timed out for address: '{full_address}'")
        return None, None
    except GeocoderUnavailable:
        logging.error(f"Geocoding service unavailable for address: '{full_address}'")
        return None, None
    except Exception as e:
        logging.error(f"An unexpected error occurred during geocoding for '{full_address}': {e}")
        return None, None


def extract_next_data(html_content):
    """Extracts the JSON content from the __NEXT_DATA__ script tag, more robustly."""
    try:
        # More robust search for the start of the script tag
        script_tag_start_str = '<script id="__NEXT_DATA__"'
        script_tag_start_idx = html_content.find(script_tag_start_str)

        if script_tag_start_idx == -1:
            # Try with single quotes as well for id attribute
            script_tag_start_str = "<script id='__NEXT_DATA__'"
            script_tag_start_idx = html_content.find(script_tag_start_str)
            if script_tag_start_idx == -1:
                logging.error(f"Initial marker for __NEXT_DATA__ script tag not found (tried double and single quotes for id).")
                return None

        # Find the closing '>' of the script tag that contains __NEXT_DATA__
        json_start_marker_end_idx = html_content.find('>', script_tag_start_idx)
        if json_start_marker_end_idx == -1:
            logging.error("Could not find closing '>' for __NEXT_DATA__ script tag.")
            return None
        
        json_start_idx = json_start_marker_end_idx + 1

        # Find the end of the script tag
        end_marker = '</script>'
        json_end_idx = html_content.find(end_marker, json_start_idx)
        if json_end_idx == -1:
            logging.error(f"Closing marker '{end_marker}' for __NEXT_DATA__ not found after JSON content.")
            return None
        
        json_data_str = html_content[json_start_idx:json_end_idx]
        return json.loads(json_data_str)
        
    except Exception as e:
        logging.error(f"Error extracting or parsing __NEXT_DATA__ (robust attempt): {e}")
        return None

def _parse_jsonld_scripts(html: str) -> Dict[str, any]:
    """Parse first JSON-LD block and return dict; if multiple merge shallowly."""
    soup = BeautifulSoup(html, "html.parser")
    data: Dict[str, any] = {}
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            txt = script.get_text(strip=True)
            if not txt:
                continue
            j = json.loads(txt)
            if isinstance(j, list):
                for o in j:
                    if isinstance(o, dict):
                        data.update(o)
            elif isinstance(j, dict):
                data.update(j)
        except Exception:
            continue
    return data

def fetch_detail_info(detail_url: str, delay: float = 0.5) -> Dict[str, Optional[any]]:
    """Fetch Otodom detail page and extract floor, year_built, lat/lon, description via JSON-LD."""
    if not detail_url:
        return {}
    try:
        cached = http_get_cached(detail_url)
        if cached:
            text_html = cached
        else:
            time.sleep(delay)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/114.0'
            }
            r = FETCHER.get(detail_url, headers=headers, timeout=15)
            r.raise_for_status()
            text_html = r.text
            http_set_cached(detail_url, text_html, ttl=86400*7)
        jsonld = _parse_jsonld_scripts(text_html)
        out: Dict[str, Optional[any]] = {}
        geo = jsonld.get("geo") or {}
        out["latitude"] = geo.get("latitude")
        out["longitude"] = geo.get("longitude")

        # floor level may appear as "floorLevel" or inside additionalProperty list
        if "floorLevel" in jsonld:
            out["floor"] = jsonld.get("floorLevel")
        else:
            for prop in jsonld.get("additionalProperty", []) or []:
                if prop.get("name", "").lower().startswith("floor"):
                    out["floor"] = prop.get("value")
                if prop.get("name", "").lower().startswith("year") or "rok" in prop.get("name", "").lower():
                    out["year_built"] = prop.get("value")

        if "dateCreated" in jsonld:
            out["date_created"] = jsonld["dateCreated"]
        if "description" in jsonld:
            out["description"] = jsonld["description"]
        return out
    except Exception as e:
        logging.warning(f"Failed to fetch detail {detail_url}: {e}")
        return {}

def fetch_offer_api(offer_id: str, detail_url: Optional[str] = None) -> Dict[str, Optional[any]]:
    """Query Otodom public offer API for additional structured data.

    Strategy:
      1. Raw GET to /api/v1/offers/{id}. If that returns 403/empty, continue.
      2. If a `detail_url` is provided, first visit that page with the same
         session to obtain cookies (CloudFront, visitorId, etc.). Then re-try
         the API call. This mimics a real browser flow without Selenium.
    """
    if not offer_id:
        return {}

    api_url = OTODOM_OFFER_API.format(id=offer_id)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/114.0",
        "Accept": "application/json, text/plain, */*"
    }

    session = FETCHER.session  # Use global session with retry/proxy settings

    def _attempt_api() -> Optional[dict]:
        try:
            r = session.get(api_url, headers=headers, timeout=15)
            if r.status_code != 200:
                return None
            data = r.json()
            # Heuristic: if data seems empty or contains error field, skip
            if not data or (isinstance(data, dict) and data.get("error")):
                return None
            return data
        except Exception:
            return None

    data = _attempt_api()

    # If empty & we have detail_url, try to prime cookies then retry
    if data is None and detail_url:
        try:
            session.get(detail_url, timeout=15, allow_redirects=True)
        except Exception:
            pass
        data = _attempt_api()

    if not data:
        logging.info(f"Offer API empty for {offer_id}")
        return {}

    out: Dict[str, Optional[any]] = {}

    out["description"] = data.get("description")

    parameters = data.get("parameters") or []
    param_map = {p.get("key"): p.get("value") for p in parameters if isinstance(p, dict)}
    try:
        logging.debug("PARAM_DEBUG Offer %s parameters: %s", offer_id, json.dumps(param_map, ensure_ascii=False))
    except Exception:
        pass

    out["floor"] = param_map.get("floor") or param_map.get("floorLevel")
    out["year_built"] = param_map.get("constructionYear") or param_map.get("yearOfConstruction")

    location = data.get("location") or {}
    out["latitude"] = location.get("latitude") or location.get("lat")
    out["longitude"] = location.get("longitude") or location.get("lon")

    return out

def fetch_offer_graphql(offer_id: str) -> Dict[str, Optional[any]]:
    """Attempt a direct GraphQL POST to retrieve offer details.

    This relies on a public unauthenticated GraphQL endpoint which currently
    returns basic fields without requiring a token. If the schema changes or
    rate-limits apply, this may fail silently and return an empty dict.
    """
    if not offer_id:
        return {}

    payload = {
        "query": GQL_OFFER_QUERY,
        "operationName": "OfferBasic",
        "variables": {"id": str(offer_id)}
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Gecko/20100101 Firefox/114.0",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        cache_key = f"gql:{offer_id}"
        cached = http_get_cached(cache_key)
        if cached:
            res_json = json.loads(cached)
        else:
            r = FETCHER.post(OTODOM_GRAPHQL_ENDPOINT, headers=headers, json=payload, timeout=15)
            if r.status_code != 200:
                return {}
            res_json = r.json()
            http_set_cached(cache_key, json.dumps(res_json), ttl=86400*3)
        res = res_json
        if "errors" in res or not res.get("data"):
            return {}
        offer = res["data"].get("offer") or {}
        if not offer:
            return {}
        out: Dict[str, Optional[any]] = {
            "description": offer.get("description")
        }

        loc = offer.get("location") or {}
        out["latitude"] = loc.get("latitude")
        out["longitude"] = loc.get("longitude")

        params = offer.get("parameters") or []
        p_dict = {p.get("key"): p.get("value") for p in params if isinstance(p, dict)}
        out["floor"] = p_dict.get("floor") or p_dict.get("floorLevel")
        out["year_built"] = p_dict.get("constructionYear") or p_dict.get("yearOfConstruction")
        return {k: v for k, v in out.items() if v is not None}
    except Exception as e:
        logging.info(f"GraphQL offer fetch failed for {offer_id}: {e}")
        return {}

def parse_listings_from_next_data(next_data_json, analyzer_instance: RoomAnalyzer = None):
    """Parses listing information from the __NEXT_DATA__ JSON object."""
    listings = []
    if not next_data_json:
        return listings

    try:
        items = next_data_json['props']['pageProps']['data']['searchAds']['items']
        logging.info(f"Found {len(items)} items in __NEXT_DATA__.")

        # Build basic listing objects first
        basic_listings = []
        for idx, item in enumerate(items):
            try:
                if idx == 0:
                    try:
                        logging.debug("ITEM_KEYS %s", json.dumps(list(item.keys())))
                    except Exception:
                        pass
                # Robust URL & field extraction
                slug = item.get("slug")
                raw_url = item.get("url")

                # Construct absolute detail URL
                if raw_url and str(raw_url).startswith("http"):
                    detail_url = raw_url
                elif slug:
                    if str(slug).startswith("http"):
                        detail_url = slug
                    else:
                        # Otodom slugs are path-like, prefix with domain
                        detail_url = f"https://www.otodom.pl/{str(slug).lstrip('/')}"
                else:
                    detail_url = None

                # Ensure Otodom new format: /pl/oferta/<slug>
                if detail_url and detail_url.startswith("https://www.otodom.pl/") and "/pl/oferta/" not in detail_url:
                    # Insert /pl/oferta/ after domain
                    path_part = detail_url.split("https://www.otodom.pl/")[1].lstrip('/')
                    detail_url = f"https://www.otodom.pl/pl/oferta/{path_part}"

                # Price may be a dict or scalar
                price_raw = item.get("price")
                if isinstance(price_raw, dict):
                    price_val = price_raw.get("value") or price_raw.get("price") or price_raw.get("amount")
                else:
                    price_val = price_raw

                # Build listing skeleton
                basic = {
                    "id": item.get("id"),
                    "title": item.get("name") or item.get("title"),
                    "price": price_val,
                    "detail_url": detail_url,
                }
                
                # ---- Yeni alanlar ----
                loc = item.get("location") or {}
                if loc:
                    # city name
                    city_obj = loc.get("city") or {}
                    basic["city_name"] = city_obj.get("name")
                    # street
                    addr_obj = loc.get("address") or {}
                    basic["street_name"] = addr_obj.get("street")
                    # coordinates from list API (bazı ilanlarda mevcut)
                    basic["latitude"] = loc.get("latitude") or loc.get("lat")
                    basic["longitude"] = loc.get("longitude") or loc.get("lon")

                # images
                img_arr = item.get("images") or []
                if isinstance(img_arr, list):
                    # Otodom search listesinde {"large":url,"small":url}
                    basic["images"] = [img.get("large") or img.get("small") for img in img_arr if isinstance(img, dict)]

                # created date
                basic["date_created"] = item.get("createdAt") or item.get("created_at")

                # seller type -> is_private_owner
                stype = item.get("sellerType")
                if stype:
                    basic["seller_type"] = stype
                    basic["is_private_owner"] = stype.lower() == "private"

                # Address bits
                param_map = {p.get('key'): p.get('value') for p in item.get('parameters', []) if isinstance(p, dict)}

                street_name_val = item.get('streetName') or _get_from_param(param_map, 'streetName')
                city_name_val = item.get('cityName') or item.get('city')
                basic['street_name'] = street_name_val
                basic['city_name'] = city_name_val

                # Fallback: parse from label like "Wrocław, dolnośląskie"
                if not city_name_val:
                    loc_label = item.get('locationLabel') or item.get('location_label')
                    if isinstance(loc_label, str) and "," in loc_label:
                        city_name_val = loc_label.split(",")[0].strip()

                # Professional extras via alias helper
                for field in [
                    'floor',
                    'total_floors',
                    'year_built',
                    'building_type',
                    'condition',
                    'parking_spaces',
                    'balcony_area',
                    'heating_type',
                ]:
                    basic[field] = _get_from_param(param_map, field)

                # Geocoding (existing implementation)
                if city_name_val: # Only attempt to geocode if we have a city
                    addr_key = f"{street_name_val},{city_name_val}"
                    cached_geo = geo_get_cached(addr_key)
                    if cached_geo:
                        geo_dict = json.loads(cached_geo)
                        lat, lon = geo_dict.get("lat"), geo_dict.get("lon")
                    else:
                        lat, lon = get_coordinates_for_address(street_name_val, city_name_val)
                        if lat and lon:
                            geo_set_cached(addr_key, json.dumps({"lat": lat, "lon": lon}))
                    basic['latitude'] = lat
                    basic['longitude'] = lon

                    # Save to database and optionally run visual analysis if analyzer_instance provided
                    if analyzer_instance:
                        try:
                            analyzer_instance.save_listing_scrape_data(
                                listing_id=basic.get('detail_url'),
                                title=basic.get('title'),
                                street_address=street_name_val,
                                price=basic.get('price'),
                                area=basic.get('area_sqm'),
                                latitude=lat,
                                longitude=lon
                            )
                        except Exception as db_save_e:
                            logging.error(f"Error saving listing {basic.get('id')} to DB: {db_save_e}")

                        # ---- Visual analysis ----
                        try:
                            analysis_results = analyzer_instance.analyze_listing_rooms(listing_url=basic.get('detail_url'))
                            basic['unique_rooms_detected'] = analysis_results.get('unique_rooms_detected')
                            basic['habitable_rooms'] = analysis_results.get('habitable_rooms_unique_count')
                        except Exception as vis_e:
                            logging.error(f"Visual analysis failed for listing {basic.get('detail_url')}: {vis_e}")
                else:
                    logging.warning(f"Skipping geocoding for listing ID {basic.get('id', 'N/A')} due to missing city name.")

                # Try to validate; if fails, still include listing with best-effort fixes
                try:
                    _ = ListingSchema(**basic)
                except Exception as val_e:
                    # Make minimal fixes: cast id to str, ensure required keys exist
                    basic["id"] = str(basic.get("id"))
                    basic.setdefault("images", [])
                    basic.setdefault("date_created", None)
                    basic.setdefault("is_private_owner", None)
                    logging.warning(
                        f"Listing validation failed (ID {basic.get('id')}), will still keep: {val_e}"
                    )
                basic_listings.append(basic)
            except Exception as e:
                logging.warning(f"Error parsing a specific listing item (ID: {item.get('id', 'N/A')}): {e}")
                continue # Skip to the next item if one fails
        
        # ---------------- Enrich details concurrently ----------------
        if ENABLE_DETAIL_FETCH and DETAIL_MAX_WORKERS > 0:
            logging.info("Fetching additional detail data in parallel…")
            with ThreadPoolExecutor(max_workers=DETAIL_MAX_WORKERS) as executor:
                futures = {executor.submit(_enrich_listing_details, l): l for l in basic_listings}
                enriched: List[Dict[str, any]] = []
                for fut in as_completed(futures):
                    try:
                        enriched.append(fut.result())
                    except Exception:
                        enriched.append(futures[fut])
            listings = enriched
        else:
            # No concurrency – maybe sequential enrichment
            listings = [ _enrich_listing_details(l) for l in basic_listings ] if ENABLE_DETAIL_FETCH else basic_listings

        # Final normalization pass
        listings = [_normalize_listing_fields(l) for l in listings]
        SCRAPED_LISTINGS.inc(len(listings))

        # Dispatch analysis tasks
        for l in listings:
            if l.get("images"):
                try:
                    analyze_images_task.delay(l["id"], l["images"])
                except Exception:
                    logging.debug("Celery dispatch failed for %s", l.get("id"))
        return listings
    except KeyError as e:
        logging.error(f"KeyError while accessing searchAds items: {e}. Check __NEXT_DATA__ structure.")
    except Exception as e:
        logging.error(f"An unexpected error occurred while parsing listings: {e}")
        
    return listings

def scrape_otodom_page(url, analyzer_instance: RoomAnalyzer = None):
    """Scrapes a single Otodom search results page."""
    logging.info(f"Scraping URL: {url}")
    try:
        cached = http_get_cached(url)
        if cached:
            html_content = cached
        else:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/114.0'
            }
            with REQUEST_LATENCY.time():
                response = FETCHER.get(url, headers=headers, timeout=15)
            response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
            html_content = response.text
            http_set_cached(url, html_content)
        
        next_data_json = extract_next_data(html_content)
        
        if not next_data_json:
            debug_file_path = "debug_otodom_response.html"
            try:
                with open(debug_file_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                logging.info(f"Raw HTML response saved to {debug_file_path} for inspection.")
            except Exception as e_file:
                logging.error(f"Failed to save debug HTML response to {debug_file_path}: {e_file}")
            return [] # Return empty list as __NEXT_DATA__ was not found or parsed
            
        listings_data = parse_listings_from_next_data(next_data_json, analyzer_instance) # Pass analyzer_instance
        return listings_data
        
    except requests.exceptions.RequestException as e:
        SCRAPE_ERRORS.inc()
        logging.error(f"Request failed for {url}: {e}")
        return []
    except Exception as e:
        logging.error(f"An error occurred during scraping {url}: {e}")
        return []

# ----------------------------- Pagination Helper -----------------------------

def scrape_otodom_search(max_pages: int = DEFAULT_MAX_PAGES, analyzer_instance: RoomAnalyzer = None):
    """Scrape multiple pages of an Otodom search. Returns combined listing dicts list."""
    all_listings = []
    for page in range(1, max_pages + 1):
        url = BASE_OTODOM_SEARCH_URL_WROCLAW.format(page=page)
        listings = scrape_otodom_page(url, analyzer_instance=analyzer_instance)
        if not listings:
            logging.info(f"No listings found on page {page}. Stopping pagination.")
            break
        all_listings.extend(listings)
        # polite delay
        time.sleep(1)
    return all_listings

# ------------------------ Persistence Helper ------------------------

def _save_listings_csv(listings: List[dict], dedup: bool = True):
    """Persist listings to a dated CSV under RAW_DATA_DIR.

    Args:
        listings: list of dicts produced by scraper
        dedup: if True, drop duplicate ids within file
    """
    
    if not listings:
        logging.info("No listings to persist, skipping CSV save.")
        return

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    out_dir = Path(RAW_DATA_DIR) / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "otodom_listings.csv"

    df = pd.DataFrame(listings)
    if dedup:
        df.drop_duplicates(subset=["id"], inplace=True)

    header = not out_path.exists()
    df.to_csv(out_path, mode="a", index=False, header=header)
    logging.info("Persisted %s listings to %s", len(df), out_path)
    inserted = upsert_listings(listings)
    logging.info("Inserted %s new rows to Postgres", inserted)

# -------------------------- Utility: fill missing fields --------------------------
def _derive_city_name(location_str: Optional[str]) -> Optional[str]:
    """Attempt to extract city adını location_string'den regex ile (ör. ', Wrocław')."""
    if not location_str:
        return None
    # Örnek location_str: "ul. Marii Curie-Skłodowskiej, Plac Grunwaldzki, Śródmieście, Wrocław, dolnośląskie"
    parts = [p.strip() for p in location_str.split(',') if p.strip()]
    # Wrocław veya başka bir il ismi genelde sondan 2. parça oluyor
    for part in reversed(parts):
        if len(part) > 2 and part[0].isupper():  # basit heuristik
            return part
    return None

REQUIRED_FIELDS = ["city_name", "images", "date_created", "is_private_owner"]

def _fill_missing_fields(listing: Dict[str, any]):
    """Eksik temel alanları türet veya varsayılan ata."""
    # city_name
    if not listing.get("city_name"):
        cand = _derive_city_name(listing.get("location_string"))
        if cand:
            listing["city_name"] = cand
    # images (expect list[str])
    if not listing.get("images"):
        if listing.get("image_urls"):
            listing["images"] = listing["image_urls"]
    # date_created
    if not listing.get("date_created"):
        listing["date_created"] = listing.get("created_at") or datetime.utcnow().isoformat()
    # is_private_owner
    if listing.get("is_private_owner") is None:
        stype = listing.get("seller_type") or listing.get("sellerName")
        if isinstance(stype, str):
            listing["is_private_owner"] = stype.lower() in ("private", "osoba prywatna", "prywatny")
    # log missing fields after attempt
    missing_after = [f for f in REQUIRED_FIELDS if not listing.get(f)]
    if missing_after:
        logging.debug("MISSING_AFTER_ENRICH %s for id=%s", missing_after, listing.get("id"))
    return listing

if __name__ == '__main__':
    logging.info("Starting Otodom scraper (multi-page)…")
    
    import os
    api_key = os.getenv("GEMINI_API_KEY")
    analyzer_for_script = None
    if api_key:
        analyzer_for_script = RoomAnalyzer(gemini_api_key=api_key)
    else:
        logging.warning("GEMINI_API_KEY not set → listings will be scraped but images won’t be analyzed/saved to DB.")
    
    listings = scrape_otodom_search(max_pages=DEFAULT_MAX_PAGES, analyzer_instance=analyzer_for_script)
    
    logging.info(f"Total listings scraped: {len(listings)}")
    for i, listing in enumerate(listings[:5]):
        logging.info(f"--- Listing {i+1} ---")
        for k, v in listing.items():
            logging.info(f"  {k}: {v}")

    # Persist listings to CSV for later processing
    _save_listings_csv(listings)
