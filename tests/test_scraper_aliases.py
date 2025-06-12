import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1] / "back_end"))

import pytest
from otodom_scraper import _get_from_param, _normalize_listing_fields, FIELD_ALIASES


def test_get_from_param_aliases():
    sample_map = {
        "floorLevel": "3",
        "constructionYear": "2010",
        "balconyArea": "12.5",
    }
    assert _get_from_param(sample_map, "floor") == "3"
    assert _get_from_param(sample_map, "year_built") == "2010"
    assert _get_from_param(sample_map, "balcony_area") == "12.5"
    # non-existing key returns None
    assert _get_from_param(sample_map, "parking_spaces") is None


def test_normalize_listing_fields():
    listing = {
        "floor": "2",
        "total_floors": "5",
        "year_built": "1999",
        "balcony_area": "10,3",
        "parking_spaces": "1",
    }
    norm = _normalize_listing_fields(listing.copy())
    assert isinstance(norm["floor"], int) and norm["floor"] == 2
    assert isinstance(norm["balcony_area"], float) and abs(norm["balcony_area"] - 10.3) < 1e-4
