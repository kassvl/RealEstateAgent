"""Prepare tabular dataset for ML model training.

Steps:
1. Load `listings` table from specified database.
2. Clean and convert price/price_per_m2 strings to numeric.
3. Keep essential numeric features (price, price_per_m2, latitude, longitude).
4. Drop rows with any missing values.
5. Export to CSV for further feature engineering / model training.

Run:
    python prepare_dataset.py --db sqlite:///otodom.db --out data/dataset.csv
"""

import argparse
import os
import re
from pathlib import Path

import numpy as np
import math
# H3 import compatibility is optional because wheels may be unavailable on newer Python versions.
# If import fails, we will skip H3-based features gracefully.
try:
    import h3.api.basic_int as h3  # type: ignore
    HAS_H3 = True
except Exception:  # pragma: no cover
    try:
        import h3  # type: ignore
        HAS_H3 = True
    except Exception:
        h3 = None  # type: ignore
        HAS_H3 = False
import pandas as pd
from sqlalchemy import create_engine
from models import db, Listing

PRICE_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)?")


def to_numeric(value):
    if value is None:
        return np.nan
    if isinstance(value, (int, float)):
        return value
    match = PRICE_RE.search(str(value))
    if not match:
        return np.nan
    # Replace comma with dot, remove thousand separators
    num = match.group(0).replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return np.nan


def load_dataframe(db_url: str) -> pd.DataFrame:
    engine = create_engine(db_url)
    df = pd.read_sql_table("listings", engine)

    # NOTE: We only import models to ensure the ORM is available if needed, but
    # `prepare_dataset.py` should not depend on migrating the DB schema being up-to-date.
    # Therefore we defensively handle missing columns below.

    # ---------- Ensure expected columns exist ----------
    expected_optional_cols = {
        "area_sqm": np.nan,
        "rooms": 0,
        "image_count": 0,
        "is_private_owner": 0,
        "date_created": pd.NaT,
    }
    for col, default_val in expected_optional_cols.items():
        if col not in df.columns:
            df[col] = default_val

    # Numeric conversions
    df["price"] = df["price"].apply(to_numeric)
    df["price_per_m2"] = df["price_per_m2"].apply(to_numeric)
    df["area_sqm"] = df["area_sqm"].apply(to_numeric)

    # Derived – use date_created if available
    if "date_created" in df.columns and df["date_created"].notna().any():
        df["listing_age_days"] = (
            pd.Timestamp("now", tz="UTC") - pd.to_datetime(df["date_created"], utc=True)
        ).dt.days
    else:
        df["listing_age_days"] = np.nan

    df["rooms"] = df["rooms"].fillna(0)
    df["image_count"] = df["image_count"].fillna(0)
    df["is_private_owner"] = df["is_private_owner"].fillna(0).astype(float)  # 0/1

    # ---------------- Spatial features ----------------
    # Constants
    RYNEK = (51.1091, 17.0326)

    def haversine_km(lat1, lon1, lat2, lon2):
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        return 2 * R * math.asin(math.sqrt(a))

    if HAS_H3:
        # Helper to get H3 cell id across different package versions
        def _h3_index(lat, lon, res=7):
            if hasattr(h3, "geo_to_h3"):
                return h3.geo_to_h3(lat, lon, res)  # type: ignore
            # v4 API: latlng_to_cell
            if hasattr(h3, "latlng_to_cell"):
                return h3.latlng_to_cell(lat, lon, res)  # type: ignore
            # Fallback coarse
            return None

        df["h3_7"] = df.apply(lambda r: _h3_index(r.latitude, r.longitude, 7), axis=1)

        if df["h3_7"].isna().any():
            # Fallback for rows where indexing failed
            df.loc[df["h3_7"].isna(), "h3_7"] = df.apply(
                lambda r: f"{round(r.latitude,2)}_{round(r.longitude,2)}", axis=1
            )

        # Local mean price per m2 within same hex
        df["local_price_mean"] = df.groupby("h3_7")["price_per_m2"].transform("mean")
    else:
        # Fallback: use coarse lat/lon rounding cell id
        df["h3_7"] = df.apply(lambda r: f"{round(r.latitude,2)}_{round(r.longitude,2)}", axis=1)
        df["local_price_mean"] = df.groupby("h3_7")["price_per_m2"].transform("mean")

    # Distance to Rynek Wrocław (city center)
    df["dist_to_rynek_km"] = df.apply(
        lambda r: haversine_km(r.latitude, r.longitude, RYNEK[0], RYNEK[1]), axis=1
    )

    # Keep only useful columns for now
    keep_cols = [
        "listing_id",
        "price",
        "price_per_m2",
        "area_sqm",
        "rooms",
        "image_count",
        "is_private_owner",
        "listing_age_days",
        "latitude",
        "longitude",
        "h3_7",
        "local_price_mean",
        "dist_to_rynek_km",
    ]
    # Some optional columns may be entirely missing; drop those from keep_cols
    keep_cols = [c for c in keep_cols if c in df.columns]
    df = df[keep_cols]

    # Drop rows with any NaNs
    df = df.dropna()
    return df


def main():
    parser = argparse.ArgumentParser(description="Prepare dataset from listings DB")
    parser.add_argument("--db", default="sqlite:///otodom.db", help="SQLAlchemy DB URL")
    parser.add_argument("--out", default="data/dataset.csv", help="Output CSV path")
    args = parser.parse_args()

    df = load_dataframe(args.db)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Dataset saved to {out_path} with {len(df)} rows and {len(df.columns)} features.")


if __name__ == "__main__":
    main()
