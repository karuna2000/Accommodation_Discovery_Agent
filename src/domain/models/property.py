from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class Location(BaseModel):
    lat: float | None = None
    lng: float | None = None
    address: str | None = None


class CrawledProperty(BaseModel):
    property_id: str = Field(default_factory=lambda: str(uuid4()))
    source_url: str
    source_site: str
    title: str
    description: str | None = None
    location: Location | None = None
    price_monthly: float | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    amenities: list[str] = []
    tags: list[str] = []
    images: list[str] = []
    reviews_summary: str | None = None
    embedding: list[float] | None = None
    crawled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 0.5
