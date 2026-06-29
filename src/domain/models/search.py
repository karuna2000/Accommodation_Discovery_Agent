from pydantic import BaseModel


class SearchQuery(BaseModel):
    raw: str
    location_hint: str | None = None
    max_price: float | None = None
    min_bedrooms: int | None = None
    tags: list[str] = []


class SearchResult(BaseModel):
    properties: list[dict]
    synthesized_answer: str | None = None
    total_found: int = 0
