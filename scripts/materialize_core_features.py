"""Prepare core listing features from Postgres and materialize with Feast."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import h3
from sqlalchemy import text, create_engine
from feast import FeatureStore

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://realestate:realestate@localhost:5432/realestate"
)

FEATURE_CSV = Path(__file__).resolve().parent.parent / "back_end" / "data" / "features.csv"
FEATURE_CSV.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

QUERY = """
SELECT id, area_sqm, rooms, year_built, floor, latitude, longitude, date_created
FROM listings
WHERE area_sqm IS NOT NULL AND rooms IS NOT NULL;
"""


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # h3 index (level 8) – requires valid lat/lon
    df["h3_index"] = df.apply(
        lambda row: h3.geo_to_h3(row["latitude"], row["longitude"], 8)
        if pd.notna(row["latitude"]) and pd.notna(row["longitude"])
        else None,
        axis=1,
    )

    # Feast mandatory columns
    now = datetime.now(timezone.utc)
    df["event_timestamp"] = now
    df["created"] = now
    df.rename(columns={"id": "listing_id"}, inplace=True)

    return df[
        [
            "listing_id",
            "area_sqm",
            "rooms",
            "year_built",
            "floor",
            "h3_index",
            "event_timestamp",
            "created",
        ]
    ]


def main():
    with engine.begin() as conn:
        df = pd.read_sql(text(QUERY), conn)

    features_df = compute_features(df)
    features_df.to_csv(FEATURE_CSV, index=False)
    print("Wrote features to", FEATURE_CSV)

    store = FeatureStore(repo_path="feature_repo")
    store.apply()  # sync registry if changed
    store.materialize_incremental(end_date=datetime.utcnow())
    print("Materialization complete")


if __name__ == "__main__":
    main()
