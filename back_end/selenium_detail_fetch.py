"""Fetch detailed listing info via headless Chrome using selenium-wire.
Returns dict with extra fields (description, floor, year_built, etc.).
This module is optional; if Selenium dependencies are missing, import will fail gracefully.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# selenium-wire and undetected-chromedriver are heavy; import guarded
try:
    from seleniumwire import webdriver  # type: ignore
    import undetected_chromedriver as uc  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("selenium-wire or undetected-chromedriver not installed: " + str(e))

logger = logging.getLogger(__name__)

# REGEX helpers for parameters extraction
FLOOR_KEYS = {"floor", "floorlevel", "floor_no", "floor_no_literal"}
YEAR_KEYS = {"constructionyear", "yearofconstruction", "build_year"}


def _extract_from_parameters(params: Dict) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {"floor": None, "year_built": None}
    if not isinstance(params, (list, dict)):
        return out
    if isinstance(params, list):
        kv = {str(p.get("key")).lower(): p.get("value") for p in params if isinstance(p, dict)}
    else:
        kv = {str(k).lower(): v for k, v in params.items()}
    for k, v in kv.items():
        if k in FLOOR_KEYS:
            out["floor"] = v
        if k in YEAR_KEYS:
            out["year_built"] = v
    return out


def fetch_details_with_selenium(detail_url: str, timeout: int = 15) -> Dict[str, Optional[str]]:
    """Load listing page in headless Chrome, grab description text and parse network JSON."""
    logger.info("[SELENIUM] Fetching details for %s", detail_url)

    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=chrome_options)  # type: ignore
    driver.scopes = [r".*otodom\.pl/.*(graphql|offers).*"]  # capture only relevant requests

    try:
        driver.get(detail_url)

        # Wait for description element to appear
        try:
            desc_el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='ad-description']"))
            )
            description = desc_el.text.strip()
        except Exception:
            description = None

        extra: Dict[str, Optional[str]] = {"description": description}

        # Examine captured requests for API JSON
        for req in reversed(driver.requests):  # newest first
            if not req.response:
                continue
            if req.response.status_code != 200:
                continue
            if b"application/json" not in (req.response.headers.get("Content-Type", "").encode()):
                continue
            try:
                body = req.response.body
                data = json.loads(body.decode())
            except Exception:
                continue

            # GraphQL wrapper
            if "data" in data and data.get("data", {}).get("offer"):
                offer = data["data"]["offer"]
                extra.update(
                    {
                        "latitude": offer.get("location", {}).get("latitude"),
                        "longitude": offer.get("location", {}).get("longitude"),
                    }
                )
                extra.update(_extract_from_parameters(offer.get("parameters", [])))
                break
            # REST /offers response
            if isinstance(data, dict) and data.get("id"):
                extra.update(
                    {
                        "latitude": data.get("location", {}).get("lat") or data.get("location", {}).get("latitude"),
                        "longitude": data.get("location", {}).get("lon") or data.get("location", {}).get("longitude"),
                    }
                )
                extra.update(_extract_from_parameters(data.get("parameters", [])))
                if not extra.get("description"):
                    extra["description"] = data.get("description")
                break

        return {k: v for k, v in extra.items() if v not in (None, "", [])}
    except Exception as e:
        logger.warning("[SELENIUM] Failed to fetch details via Selenium: %s", e)
        return {}
    finally:
        try:
            driver.quit()
        except Exception:
            pass
