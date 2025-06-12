"""Utility script to scrape a configurable number of Otodom pages and persist the
results to a local SQLite database as well as an optional CSV file.

Run:
    python store_listings.py --pages 20 --db sqlite:///otodom.db --csv data/otodom.csv

By default it will create `otodom.db` in the current directory and insert/update
rows in the `listings` table defined in `models.py`.
"""

import argparse
from pathlib import Path
from typing import List, Dict

from otodom_scraper import scrape_otodom_search
from models import db, Listing
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import pandas as pd
from datetime import datetime
from dateutil.parser import parse as dateutil_parse


DEFAULT_DB_URL = "sqlite:///otodom.db"


def upsert_listings(listings: List[Dict], session):
    """Insert or update listings based on unique listing_id."""
    for item in listings:
        listing_obj = (
            session.query(Listing).filter_by(listing_id=item["id"]).one_or_none()
        )
        if listing_obj is None:
            listing_obj = Listing(listing_id=item["id"])
            session.add(listing_obj)

        # basic fields we store
        listing_obj.url = item.get("detail_url")
        listing_obj.title = item.get("title")
        listing_obj.price = str(item.get("price"))
        listing_obj.currency = item.get("currency")
        listing_obj.price_per_m2 = str(item.get("price_per_sqm"))
        listing_obj.area_sqm = item.get("area_sqm")
        # rooms comes as enums; map to int if possible
        rooms_map = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}
        listing_obj.rooms = rooms_map.get(item.get("rooms"), None)
        listing_obj.location_string = item.get("street_name") or item.get("city_name")
        listing_obj.latitude = item.get("latitude")
        listing_obj.longitude = item.get("longitude")
        listing_obj.image_count = len(item.get("images", [])) if item.get("images") else None
        listing_obj.is_private_owner = bool(item.get("is_private_owner")) if item.get("is_private_owner") is not None else None
        # date_created may come as ISO string; convert to datetime or None
        raw_dt = item.get("date_created")
        if isinstance(raw_dt, str):
            try:
                raw_dt = dateutil_parse(raw_dt)
            except Exception:
                raw_dt = None
        listing_obj.date_created = raw_dt if isinstance(raw_dt, datetime) else None
        # professional extras
        listing_obj.floor = item.get("floor")
        listing_obj.total_floors = item.get("total_floors")
        listing_obj.year_built = item.get("year_built")
        listing_obj.building_type = item.get("building_type")
        listing_obj.condition = item.get("condition")
        listing_obj.parking_spaces = item.get("parking_spaces")
        listing_obj.balcony_area = item.get("balcony_area")
        listing_obj.heating_type = item.get("heating_type")

    session.commit()


def main():
    parser = argparse.ArgumentParser(description="Scrape Otodom and store to DB/CSV")
    parser.add_argument("--pages", type=int, default=5, help="Number of pages to scrape")
    parser.add_argument(
        "--db", type=str, default=DEFAULT_DB_URL, help="SQLAlchemy database URL"
    )
    parser.add_argument(
        "--csv", type=str, default=None, help="Optional path to save CSV export"
    )
    args = parser.parse_args()

    print(f"Scraping {args.pages} pages from Otodom…")
    data = scrape_otodom_search(max_pages=args.pages)
    print(f"Fetched {len(data)} listings")

    engine = create_engine(args.db)
    db.Model.metadata.create_all(engine)

    # --------- lightweight schema migration (SQLite) ---------
    def ensure_listing_schema(_engine):
        """Add missing columns for backward-compat databases (SQLite)."""
        try:
            with _engine.begin() as conn:
                res = conn.execute(text("PRAGMA table_info(listings)"))
                existing_cols = {row[1] for row in res}

                required_cols = {
                    "area_sqm": "REAL",
                    "rooms": "INTEGER",
                    "image_count": "INTEGER",
                    "is_private_owner": "INTEGER",  # SQLite lacks BOOLEAN
                    "date_created": "DATETIME",
                    "floor": "INTEGER",
                    "total_floors": "INTEGER",
                    "year_built": "INTEGER",
                    "building_type": "TEXT",
                    "condition": "TEXT",
                    "parking_spaces": "INTEGER",
                    "balcony_area": "REAL",
                    "heating_type": "TEXT",
                }
                for col, col_type in required_cols.items():
                    if col not in existing_cols:
                        print(f"Adding missing column '{col}' to listings table…")
                        conn.execute(text(f"ALTER TABLE listings ADD COLUMN {col} {col_type}"))
        except Exception as e:
            print(f"Schema check failed: {e}")

    ensure_listing_schema(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    upsert_listings(data, session)
    print("Database upsert completed.")

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(data).to_csv(csv_path, index=False)
        print(f"CSV saved to {csv_path}")


if __name__ == "__main__":
    main()
