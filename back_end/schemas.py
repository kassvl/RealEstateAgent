"""Pydantic data models for validation of scraper output."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, validator


class ListingSchema(BaseModel):
    id: str
    title: str
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str]
    price_per_sqm: Optional[float] = Field(None, ge=0)
    area_sqm: Optional[float] = Field(None, ge=0)
    rooms: Optional[int] = Field(None, ge=0)
    street_name: Optional[str]
    city_name: str
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    detail_url: Optional[HttpUrl]
    images: Optional[List[HttpUrl]]
    date_created: Optional[str]
    is_private_owner: Optional[bool]

    # Professional extras
    floor: Optional[int]
    total_floors: Optional[int]
    year_built: Optional[int]
    building_type: Optional[str]
    condition: Optional[str]
    parking_spaces: Optional[int]
    balcony_area: Optional[float]
    heating_type: Optional[str]

    @validator("currency", pre=True, always=True)
    def upper_currency(cls, v):
        return v.upper() if isinstance(v, str) else v
