"""Build Wrocław H3-level-8 geo features (population density, green ratio, tram stop distance)."""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import h3
import osmnx as ox
import pandas as pd
from shapely.geometry import Polygon, Point
from sqlalchemy import create_engine, text
from datetime import datetime, timezone

DB_URL = "postgresql://realestate:realestate@localhost:5432/realestate"
OUTPUT_CSV = Path(__file__).resolve().parent.parent / "back_end" / "data" / "geo_features.csv"

# Coordinates for Wrocław city boundary via OSM relation 62422
CITY_RELATION_ID = 62422


def download_city_boundary() -> gpd.GeoDataFrame:
    boundary = ox.geometries_from_relation(CITY_RELATION_ID, tags={"type": "boundary"})
    boundary = boundary.reset_index()
    return boundary.iloc[[0]].to_crs(4326)  # ensure WGS84


def generate_hexes(city_poly: Polygon) -> list[str]:
    bbox = city_poly.bounds  # (minx, miny, maxx, maxy)
    hexes = list(h3.polyfill_geojson(json.loads(gpd.GeoSeries([city_poly]).to_json())['features'][0]['geometry'], 8))
    return hexes


def compute_green_ratio(hex_poly: Polygon, green_gdf: gpd.GeoDataFrame) -> float:
    inter = green_gdf.intersection(hex_poly)
    green_area = inter.area.sum()
    return float(green_area / hex_poly.area) if hex_poly.area else 0.0


def main():
    boundary_gdf = download_city_boundary()
    city_poly = boundary_gdf.geometry.iloc[0]

    # generate hex ids
    hex_ids = generate_hexes(city_poly)
    records = []

    # prepare green areas (parks, grass, forest)
    green_tags = {"landuse": ["forest"], "leisure": ["park", "garden"], "natural": ["grassland"]}
    green_gdf = ox.geometries_from_place("Wrocław, Poland", tags=green_tags).to_crs(4326)

    # tram/metro stops
    stops = ox.geometries_from_place("Wrocław, Poland", tags={"railway": "tram_stop"}).to_crs(4326)
    stop_points = stops.centroid

    for hex_id in hex_ids:
        center_lat, center_lon = h3.h3_to_geo(hex_id)
        hex_poly = Polygon(h3.h3_to_geo_boundary(hex_id, geo_json=True))

        # closest stop distance (meters)
        if not stop_points.empty:
            distances = stop_points.distance(Point(center_lon, center_lat)) * 111_000  # deg->m approx
            min_dist = distances.min()
        else:
            min_dist = None

        green_ratio = compute_green_ratio(hex_poly, green_gdf)

        records.append({
            "h3_index": int(hex_id, 16),
            "green_ratio": green_ratio,
            "tram_stop_dist_m": min_dist,
        })

    df = pd.DataFrame(records)
    now = datetime.now(timezone.utc)
    df["event_timestamp"] = now
    df["created"] = now
    df.to_csv(OUTPUT_CSV, index=False)
    print("Geo features written to", OUTPUT_CSV)

    engine = create_engine(DB_URL)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS geo_features (
                h3_index BIGINT PRIMARY KEY,
                green_ratio FLOAT,
                tram_stop_dist_m FLOAT,
                event_timestamp TIMESTAMP,
                created TIMESTAMP
            );
        """))
        df.to_sql("geo_features", con=conn, if_exists="replace", index=False)


if __name__ == "__main__":
    main()
