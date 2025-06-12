"""Celery task definitions for asynchronous image analysis with Gemini."""
import os
import logging
from celery import Celery
from typing import List

from back_end.analyze_the_rooms import RoomAnalyzer
from back_end.models import db, AnalysisResult
from back_end.vault_client import get_secret

logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
app = Celery("tasks", broker=CELERY_BROKER_URL, backend=CELERY_BROKER_URL)

_api_key = get_secret("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
_analyzer = RoomAnalyzer(gemini_api_key=_api_key) if _api_key else None


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=5, retry_kwargs={"max_retries": 3})
def analyze_images_task(self, listing_id: str, image_urls: List[str]):
    if not _analyzer:
        _logger.warning("RoomAnalyzer not configured (GEMINI_API_KEY missing). Skipping analysis.")
        return
    _logger.info("Analyzing %d images for listing %s", len(image_urls), listing_id)
    try:
        result = _analyzer.analyze_listing_rooms(image_urls)
        # Persist to DB
        db.session.add(AnalysisResult(listing_id=listing_id, **result))
        db.session.commit()
        _logger.info("Analysis stored for %s", listing_id)
    except Exception as e:
        _logger.error("Analysis failed for %s: %s", listing_id, e)
        raise


# ------------------ Scraping task ------------------

from back_end.otodom_scraper import scrape_otodom_search  # noqa: E402 at end of file


@app.task(bind=True, autoretry_for=(Exception,), retry_backoff=10, retry_kwargs={"max_retries": 5})
def scrape_otodom_task(self, max_pages: int = 3):
    """Celery task to scrape Otodom listings and persist to DB/CSV."""
    _logger.info("Scrape task started (max_pages=%s)", max_pages)
    try:
        listings = scrape_otodom_search(max_pages=max_pages)
        _logger.info("Scrape task finished: %s listings scraped", len(listings))
        return len(listings)
    except Exception as e:
        _logger.error("Scrape task failed: %s", e)
        raise
