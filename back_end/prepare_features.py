"""Generate enriched feature CSV for Feast offline store."""
import os
from pathlib import Path
from datetime import datetime
import pandas as pd
from sentence_transformers import SentenceTransformer
import h3
from back_end.datahub_emitter import emit_lineage

DATASET_CSV = Path(os.getenv("DATASET_CSV", "./back_end/data/dataset.csv"))
OUTPUT_CSV = Path("../feature_repo/../back_end/data/features.csv").resolve()
OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)

print("Loading dataset", DATASET_CSV)

df = pd.read_csv(DATASET_CSV)

# Basic feature engineering
df["event_timestamp"] = pd.to_datetime(df.get("date_created", datetime.utcnow()))
df["created"] = datetime.utcnow()
# H3 index at resolution 8 (≈1km)
print("Computing H3 indices...")
df["h3_index"] = df.apply(lambda r: h3.geo_to_h3(r.latitude, r.longitude, 8) if pd.notnull(r.latitude) else None, axis=1)

# Sentence embedding of description
print("Generating MiniLM description embeddings...")
minilm = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L6-v2")
mini_emb = minilm.encode(df["description"].fillna("").tolist(), show_progress_bar=True, batch_size=64)
mini_df = pd.DataFrame(mini_emb, columns=[f"desc_emb_{i}" for i in range(mini_emb.shape[1])])

print("Generating CLIP description embeddings (ViT-B-32)...")
clip_model = SentenceTransformer("clip-ViT-B-32")
clip_emb = clip_model.encode(df["description"].fillna("").tolist(), show_progress_bar=True, batch_size=32)
clip_df = pd.DataFrame(clip_emb, columns=[f"clip_desc_emb_{i}" for i in range(clip_emb.shape[1])])

df_features = pd.concat([df, mini_df, clip_df], axis=1)

feature_cols = [
    "listing_id",
    "event_timestamp",
    "created",
    "area_sqm",
    "rooms",
    "year_built",
    "floor",
    "h3_index",
] + list(mini_df.columns) + list(clip_df.columns)

print("Writing features to", OUTPUT_CSV)

df_features[feature_cols].to_csv(OUTPUT_CSV, index=False)
try:
    emit_lineage("raw_listings", "feast_offline_store")
except Exception as e:
    print("DataHub emit failed", e)
