from back_end.otodom_scraper import _normalize_listing_fields

def test_normalize_int_fields():
    raw = {"floor": "3"}
    norm = _normalize_listing_fields(raw.copy())
    assert isinstance(norm["floor"], int)
    assert norm["floor"] == 3
