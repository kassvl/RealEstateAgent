from datetime import timedelta
from feast import Entity, FileSource, Field, FeatureView
from feast.types import Float32, Int64, String

# Entities
listing = Entity(name="listing_id", join_keys=["listing_id"])
h3_entity = Entity(name="h3_index", join_keys=["h3_index"])

# File sources
listing_source = FileSource(
    path="../back_end/data/features.csv",
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
)

# Geo source
geo_source = FileSource(
    path="../back_end/data/geo_features.csv",
    timestamp_field="event_timestamp",
    created_timestamp_column="created",
)

# Feature View
listing_fv = FeatureView(
    name="listing_features",
    entities=["listing_id"],
    ttl=timedelta(days=365),
    schema=[
        Field(name="area_sqm", dtype=Float32),
        Field(name="rooms", dtype=Int64),
        Field(name="year_built", dtype=Int64),
        Field(name="floor", dtype=Int64),
        Field(name="h3_index", dtype=Int64),
        Field(name="desc_embedding", dtype=Float32, shape=(384,)),
        Field(name="clip_desc_embedding", dtype=Float32, shape=(512,)),
    ],
    online=True,
    source=listing_source,
)

# Geo Feature View
geo_fv = FeatureView(
    name="wro_geo_features",
    entities=["h3_index"],
    ttl=timedelta(days=365),
    schema=[
        Field(name="green_ratio", dtype=Float32),
        Field(name="tram_stop_dist_m", dtype=Float32),
    ],
    online=True,
    source=geo_source,
)
