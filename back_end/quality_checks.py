"""Basic data-quality checks for the stored Otodom listings.

Run:
    python quality_checks.py --db sqlite:///otodom.db --report bad_rows.csv

It prints a summary of missing / invalid fields and optionally exports the rows
that fail any check to a CSV for manual review or correction.
"""

import argparse
import re
from typing import List, Dict

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import db, Listing

PRICE_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?")

def load_listings(session) -> List[Listing]:
    return session.query(Listing).all()

def listing_to_dict(obj: Listing) -> Dict:
    return {
        "listing_id": obj.listing_id,
        "url": obj.url,
        "title": obj.title,
        "price": obj.price,
        "currency": obj.currency,
        "latitude": obj.latitude,
        "longitude": obj.longitude,
        "location_string": obj.location_string,
    }

def is_price_valid(price_str: str) -> bool:
    if not price_str:
        return False
    return bool(PRICE_RE.search(price_str))

def run_quality_checks(listings: List[Listing]):
    total = len(listings)
    missing_price = 0
    invalid_price = 0
    missing_coords = 0

    bad_rows: List[Dict] = []

    for l in listings:
        bad = False
        if not l.price:
            missing_price += 1
            bad = True
        elif not is_price_valid(l.price):
            invalid_price += 1
            bad = True
        if l.latitude is None or l.longitude is None:
            missing_coords += 1
            bad = True
        if bad:
            bad_rows.append(listing_to_dict(l))

    print("----- Quality Report -----")
    print(f"Total rows          : {total}")
    print(f"Missing price       : {missing_price}")
    print(f"Invalid price format: {invalid_price}")
    print(f"Missing coordinates : {missing_coords}")
    print(f"Bad rows total      : {len(bad_rows)}")

    return bad_rows

def main():
    parser = argparse.ArgumentParser(description="Run data-quality checks on listings table")
    parser.add_argument("--db", type=str, default="sqlite:///otodom.db", help="SQLAlchemy DB URL")
    parser.add_argument("--report", type=str, default=None, help="Optional CSV path to export bad rows")
    args = parser.parse_args()

    engine = create_engine(args.db)
    db.Model.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    listings = load_listings(session)
    bad_rows = run_quality_checks(listings)

    if args.report and bad_rows:
        pd.DataFrame(bad_rows).to_csv(args.report, index=False)
        print(f"Bad rows exported to {args.report}")

if __name__ == "__main__":
    main()
