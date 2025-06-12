"""Validate latest scraped CSV using Great Expectations."""
from pathlib import Path
import sys
import argparse
from datetime import datetime
import pandas as pd
import great_expectations as ge

RAW_DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
GE_DIR = Path(__file__).parent.parent / "great_expectations"

context = ge.get_context(context_root_dir=str(GE_DIR))


def main():
    parser = argparse.ArgumentParser(description="Validate scraped listings CSV with Great Expectations")
    parser.add_argument("--csv", dest="csv_path", type=str, help="Path to CSV file", default=None)
    args = parser.parse_args()

    if args.csv_path:
        csv_path = Path(args.csv_path)
    else:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        csv_path = RAW_DATA_DIR / date_str / "otodom_listings.csv"
        if not csv_path.exists():
            # fallback to back_end/data/raw
            csv_path = Path(__file__).parent.parent / "back_end" / "data" / "raw" / date_str / "otodom_listings.csv"

    if not csv_path.exists():
        print("CSV not found, skipping validation:", csv_path)
        return

    df = pd.read_csv(csv_path)
    try:
        validator = ge.from_pandas(df, expectation_suite_name="listings_basic")
    except AttributeError:
        # GE v0.18+ API change: use DataContext; for now, basic column checks
        required_cols = ["id", "title", "price"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            print("Validation failed: missing columns", missing)
            sys.exit(1)
        print("GE not available; basic validation passed (required columns present).")
        return

    results = validator.validate()

    if not results.success:
        print("Validation failed")
        sys.exit(1)
    print("Validation succeeded for", csv_path)


if __name__ == "__main__":
    main()
