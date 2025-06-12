"""Extract numeric_visual_features from SQLite and build a wide feature table.

Usage:
    python feature_etl.py --db ../analysis_results.db --out features.parquet

The script will:
1. Read analysis_results table.
2. Flatten numeric_visual_features_json into columns.
3. Merge with explicit numeric columns already present.
4. Write a Parquet file ready for model training.
"""
import argparse
import json
import os
from typing import Dict, Any

import pandas as pd
import sqlite3

DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "..", "analysis_results.db")


def flatten_json(row_json: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten first-level keys of the numeric_visual_features_json field."""
    if not isinstance(row_json, dict):
        return {}
    flat: Dict[str, Any] = {}
    for k, v in row_json.items():
        # Accept only primitives (num, str, bool)
        if isinstance(v, (int, float, str, bool)):
            flat[k] = v
    return flat


def main(db_path: str, out_path: str):
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    # Read entire table; for production use, incremental loads can use created_at > last_ts
    df = pd.read_sql_query("SELECT * FROM analysis_results", conn)
    conn.close()

    # Parse JSON column
    if "numeric_visual_features_json" in df.columns:
        flat_records = df["numeric_visual_features_json"].apply(lambda x: flatten_json(json.loads(x) if x else {}))
        flat_df = pd.json_normalize(flat_records)
        df = pd.concat([df.drop(columns=["numeric_visual_features_json"]), flat_df], axis=1)

    # Ensure all non-numeric are dropped except identifiers and label placeholders
    id_cols = ["listing_id", "analysis_id", "created_at"]
    keep_cols = id_cols + [c for c in df.columns if df[c].dtype != "object" or c in id_cols]
    df = df[keep_cols]

    # Write Parquet
    df.to_parquet(out_path, index=False)
    print(f"[ETL] Wrote {len(df)} rows, {len(df.columns)} columns to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_SQLITE_PATH, help="Path to SQLite DB.")
    parser.add_argument("--out", default="features.parquet", help="Output Parquet file.")
    args = parser.parse_args()
    main(args.db, args.out)
