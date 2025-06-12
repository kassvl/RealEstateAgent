import requests
from bs4 import BeautifulSoup
import json
import re # For cleaning description

def get_listing_details(url):
    """
    Scrapes listing details from an Otodom URL.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    scraped_data = {}

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # --- Primary Method: Extracting data from __NEXT_DATA__ script tag ---
        script_tag = soup.find('script', {'id': '__NEXT_DATA__'})
        if script_tag:
            try:
                json_data = json.loads(script_tag.string)
                ad_data = json_data.get('props', {}).get('pageProps', {}).get('ad', {})

                if not ad_data: # Sometimes data is directly under pageProps
                    ad_data = json_data.get('props', {}).get('pageProps', {})


                # Basic Info
                scraped_data['url'] = url
                scraped_data['title'] = ad_data.get('title')
                scraped_data['listing_id'] = ad_data.get('id') or ad_data.get('publicId') # Try both possible keys

                # Price
                target_data = ad_data.get('target', {}) # Some data might be nested here
                price_info = ad_data.get('price', {})
                if price_info and isinstance(price_info, dict): # New structure
                    scraped_data['price'] = price_info.get('value')
                    scraped_data['currency'] = price_info.get('currency')
                    # price_per_m2 might be in characteristics or calculated
                elif target_data.get('Price'): # Older structure
                    scraped_data['price'] = target_data.get('Price')
                    scraped_data['currency'] = target_data.get('PriceCurrency', 'PLN') # Assume PLN if not found
                else: # Fallback for price if not in JSON under expected keys
                    price_element = soup.find('strong', {'data-cy': 'adPageHeaderPrice'})
                    if price_element:
                        scraped_data['price'] = price_element.get_text(strip=True)
                        # Currency might need separate extraction if not with price

                # Price per m2
                if target_data.get('Price_per_m'):
                    scraped_data['price_per_m2'] = f"{target_data.get('Price_per_m')} {scraped_data.get('currency', 'PLN')}/m²"
                else:
                    # Try to find it in characteristics
                    for char_item in ad_data.get('characteristics', []):
                        if char_item.get('key') == 'price_per_m':
                            scraped_data['price_per_m2'] = char_item.get('localizedValue')
                            break
                    if not scraped_data.get('price_per_m2'):
                        price_m2_el = soup.find('div', {'aria-label': 'Cena za metr kwadratowy'})
                        if price_m2_el:
                             scraped_data['price_per_m2'] = price_m2_el.get_text(strip=True)


                # Location
                location_data = ad_data.get('location', {})
                address_data = location_data.get('address', {})
                loc_parts = []
                # Use breadcrumbs for a more complete location string if available
                breadcrumbs = ad_data.get('breadcrumbs', [])
                if breadcrumbs and len(breadcrumbs) > 1:
                    # Last breadcrumb is usually the title, second to last is often the most specific location
                    # However, concatenating relevant parts might be better
                    # Example: "Bolszewo, Wejherowo, wejherowski, pomorskie"
                    loc_breadcrumb_text = []
                    for bc in breadcrumbs[:-1]: # Exclude the last one (title)
                        if bc.get('label') and bc['label'].lower() not in ["dom na sprzedaż", "mieszkanie na sprzedaż", "rynek pierwotny", "rynek wtórny", "ogłoszenia"]:
                            loc_breadcrumb_text.append(bc['label'])
                    if loc_breadcrumb_text:
                         scraped_data['location_string'] = ", ".join(reversed(loc_breadcrumb_text)) # Reverse to get specific to general
                    else: # Fallback to address object if breadcrumbs are not helpful
                        if address_data.get('street') and isinstance(address_data['street'], dict) and address_data['street'].get('name'):
                            loc_parts.append(address_data['street']['name'])
                        if address_data.get('city') and isinstance(address_data['city'], dict) and address_data['city'].get('name'):
                            loc_parts.append(address_data['city']['name'])
                        if address_data.get('district') and isinstance(address_data['district'], dict) and address_data['district'].get('name'):
                            loc_parts.append(address_data['district']['name'])
                        if address_data.get('county') and isinstance(address_data['county'], dict) and address_data['county'].get('name'):
                            loc_parts.append(address_data['county']['name'])
                        if address_data.get('province') and isinstance(address_data['province'], dict) and address_data['province'].get('name'):
                            loc_parts.append(address_data['province']['name'])
                        scraped_data['location_string'] = ", ".join(filter(None, loc_parts))
                else: # Fallback to map link text
                    map_link = soup.find('a', {'href': '#map'})
                    if map_link:
                        scraped_data['location_string'] = map_link.get_text(strip=True)

                scraped_data['latitude'] = location_data.get('coordinates', {}).get('latitude')
                scraped_data['longitude'] = location_data.get('coordinates', {}).get('longitude')

                # Description - remove HTML tags
                description_html = ad_data.get('description', '')
                if description_html:
                    desc_soup = BeautifulSoup(description_html, 'html.parser')
                    scraped_data['description'] = desc_soup.get_text(separator='\n', strip=True)
                else: # Fallback for description
                    desc_div = soup.find('div', {'data-cy': 'adPageAdDescription'})
                    if desc_div:
                        # Need to click "show more" usually, so this might be truncated
                        scraped_data['description'] = desc_div.get_text(separator='\n', strip=True)


                # Characteristics / Details
                details = {}
                for char_item in ad_data.get('characteristics', []):
                    if char_item.get('key') and char_item.get('localizedValue'):
                        details[char_item.get('label')] = char_item.get('localizedValue')

                # topInformation can also have useful details
                for info_item in ad_data.get('topInformation', []):
                    label = info_item.get('label')
                    # Otodom uses codes like "area", "rooms_num", convert to human-readable if needed
                    # For now, let's use the label as is, or map it if we know the common ones
                    human_label = label # Placeholder for mapping, e.g. {"area": "Powierzchnia"}
                    value_list = info_item.get('values', [])
                    unit = info_item.get('unit', '')
                    if value_list:
                        val_str = ", ".join(value_list)
                        full_val = f"{val_str} {unit}".strip()
                        if human_label not in details or details[human_label] != full_val : # Add if not already present or different
                            details[human_label.replace("_", " ").capitalize()] = full_val


                # additionalInformation
                for info_item in ad_data.get('additionalInformation', []):
                    label = info_item.get('label')
                    value_list = info_item.get('values', [])
                    if value_list:
                        val_str = ", ".join(value_list)
                        if label not in details: # Add if not already present
                             details[label.replace("_", " ").capitalize()] = val_str

                scraped_data['details'] = details

                # Fallback pour le prix si pas trouvé dans les structures principales
                if not scraped_data.get('price') and details:
                    # Cherche le prix dans les détails avec différentes clés possibles
                    price_keys = ['Cena', 'Price', 'Cena za m²', 'price']
                    for key in price_keys:
                        if key in details and details[key]:
                            price_text = details[key]
                            # Extrait seulement la partie numérique et devise
                            if 'zł' in price_text:
                                scraped_data['price'] = price_text
                                scraped_data['currency'] = 'PLN'
                                break
                            elif '€' in price_text:
                                scraped_data['price'] = price_text
                                scraped_data['currency'] = 'EUR'
                                break
                            elif '$' in price_text:
                                scraped_data['price'] = price_text
                                scraped_data['currency'] = 'USD'
                                break

                # Features (e.g. balcony, garage)
                features_list = []
                for category in ad_data.get('featuresByCategory', []):
                    features_list.extend(category.get('values', []))
                if not features_list: # Fallback if featuresByCategory is empty
                    features_list = ad_data.get('features', [])
                scraped_data['features'] = list(set(features_list)) # Unique features

                # Seller/Agency Info
                owner_data = ad_data.get('owner', {})
                agency_data = ad_data.get('agency', {})

                if agency_data and agency_data.get('name'):
                    scraped_data['seller_name'] = agency_data.get('name')
                    scraped_data['seller_type'] = agency_data.get('type', 'agency') # 'developer' or 'agency'
                    scraped_data['agency_url'] = agency_data.get('url')
                elif owner_data and owner_data.get('name'):
                    scraped_data['seller_name'] = owner_data.get('name')
                    scraped_data['seller_type'] = owner_data.get('type', 'private') # 'private' or 'business'
                else: # Fallback for seller name
                    seller_name_el = soup.find('p', {'data-sentry-element': 'SellerName'})
                    if seller_name_el:
                        scraped_data['seller_name'] = seller_name_el.get_text(strip=True)
                    else: # Try another common pattern for agency name
                        agency_name_el = soup.find('strong', {'aria-label': 'Nazwa agencji'})
                        if agency_name_el:
                            scraped_data['seller_name'] = agency_name_el.get_text(strip=True)


                # Images
                images_data = ad_data.get('images', [])
                scraped_data['image_urls'] = [img.get('large') for img in images_data if img.get('large')]
                if not scraped_data['image_urls']: # Fallback for main image
                    og_image = soup.find('meta', property='og:image')
                    if og_image and og_image.get('content'):
                        scraped_data['image_urls'] = [og_image['content']]

                # Date posted/updated
                scraped_data['created_at'] = ad_data.get('createdAt')
                scraped_data['updated_at'] = ad_data.get('modifiedAt')


            except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e:
                print(f"Error parsing JSON from __NEXT_DATA__: {e}")
                print("Attempting fallback scraping for some fields if JSON parsing failed or was incomplete.")
                # Implement more CSS selector fallbacks here if needed, for critical fields

        else:
            print("Could not find __NEXT_DATA__ script tag. This scraper relies heavily on it.")
            # Basic CSS selector fallbacks (less reliable for complex data)
            scraped_data['title'] = soup.find('h1', {'data-cy': 'adPageAdTitle'}).get_text(strip=True) if soup.find('h1', {'data-cy': 'adPageAdTitle'}) else None
            price_el = soup.find('strong', {'data-cy': 'adPageHeaderPrice'})
            if price_el: scraped_data['price'] = price_el.get_text(strip=True)

            map_link = soup.find('a', {'href': '#map'})
            if map_link: scraped_data['location_string'] = map_link.get_text(strip=True)
            # ... and so on for other critical fields if __NEXT_DATA__ is missing.

        return scraped_data

    except requests.exceptions.HTTPError as e:
        print(f"HTTP error for {url}: {e}")
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error for {url}: {e}")
    except requests.exceptions.Timeout:
        print(f"Timeout error for {url}")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {url}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return None


if __name__ == '__main__':
    # Use the canonical URL from the <head> of your example HTML for testing
    listing_url = "https://www.otodom.pl/pl/oferta/bolszewo-strazacka-szereg-7-1-ostatnie-3-z-garazem-ID4wxxa"
    # Or another example:
    # listing_url = "https://www.otodom.pl/pl/oferta/mieszkanie-z-balkonem-w-kamienicy-po-rewitalizacji-ID4pXk4"
    # listing_url = "https://www.otodom.pl/pl/oferta/wynajem-bezposrednio-mieszkanie-3-pokoje-ID4q03G"


    print(f"Scraping: {listing_url}")
    details = get_listing_details(listing_url)

    if details:
        print("\n--- Scraped Details ---")
        for key, value in details.items():
            if isinstance(value, dict):
                print(f"{key.replace('_', ' ').capitalize()}:")
                for k, v in value.items():
                    print(f"  {k}: {v}")
            elif isinstance(value, list) and key == 'image_urls':
                print(f"Image URLs ({len(value)}):")
                for i, img_url in enumerate(value[:3]): # Print first 3 image URLs
                    print(f"  - {img_url}")
                if len(value) > 3:
                    print(f"  ... and {len(value) - 3} more.")
            elif isinstance(value, list):
                print(f"{key.replace('_', ' ').capitalize()}: {', '.join(map(str, value))}")
            else:
                print(f"{key.replace('_', ' ').capitalize()}: {value}")
    else:
        print("Failed to scrape details.")