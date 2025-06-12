"""SQLAlchemy session and table definitions for listings."""
from __future__ import annotations

import os
from sqlalchemy import (Column, Float, Integer, MetaData, String, Table,
                        create_engine, inspect)
from sqlalchemy.orm import sessionmaker

# Optional Postgres; fallback to no-op if unavailable
try:
    from sqlalchemy.dialects.postgresql import JSONB  # type: ignore
except Exception:
    # SQLite fallback type
    from sqlalchemy import JSON as JSONB  # type: ignore

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://realestate:realestate@localhost:5432/realestate",
)

try:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    _engine_available = True
except Exception:
    # Local dev: no database
    engine = None  # type: ignore
    _engine_available = False

metadata_obj = MetaData()

listings_table = Table(
    "listings",
    metadata_obj,
    Column("id", String, primary_key=True),
    Column("title", String),
    Column("price", Float),
    Column("currency", String(4)),
    Column("price_per_sqm", Float),
    Column("area_sqm", Float),
    Column("rooms", Integer),
    Column("city_name", String),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("detail_url", String),
    Column("images", JSONB),
    Column("date_created", String),
    Column("extras", JSONB),
)


def init_db():
    if not _engine_available:
        return
    inspector = inspect(engine)
    if not inspector.has_table("listings"):
        metadata_obj.create_all(engine)


def upsert_listings(listings: list[dict]):
    if not listings or not _engine_available:
        return 0
    init_db()
    from sqlalchemy.dialects.postgresql import insert  # type: ignore
    with engine.begin() as conn:
        # Prepare rows; combine miscellaneous cols into 'extras'
        rows = []
        for l in listings:
            core_cols = {
                "id": l["id"],
                "title": l.get("title"),
                "price": l.get("price"),
                "currency": l.get("currency"),
                "price_per_sqm": l.get("price_per_sqm"),
                "area_sqm": l.get("area_sqm"),
                "rooms": l.get("rooms"),
                "city_name": l.get("city_name"),
                "latitude": l.get("latitude"),
                "longitude": l.get("longitude"),
                "detail_url": l.get("detail_url"),
                "images": l.get("images"),
                "date_created": l.get("date_created"),
                "extras": {
                    k: v
                    for k, v in l.items()
                    if k not in {
                        "id",
                        "title",
                        "price",
                        "currency",
                        "price_per_sqm",
                        "area_sqm",
                        "rooms",
                        "city_name",
                        "latitude",
                        "longitude",
                        "detail_url",
                        "images",
                        "date_created",
                    }
                },
            }
            rows.append(core_cols)
        insert_stmt = listings_table.insert().prefix_with("ON CONFLICT (id) DO NOTHING")
        result = conn.execute(insert_stmt, rows)
        return result.rowcount
