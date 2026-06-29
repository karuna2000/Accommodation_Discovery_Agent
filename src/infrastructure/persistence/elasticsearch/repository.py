from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch, NotFoundError

from src.domain.models.property import CrawledProperty, Location
from src.domain.models.search import SearchQuery

INDEX_MAPPING = {
    "dynamic": False,
    "properties": {
        "property_id": {"type": "keyword"},
        "source_url": {"type": "keyword", "index": False},
        "source_site": {"type": "keyword"},
        "title": {"type": "text", "analyzer": "standard"},
        "description": {"type": "text", "analyzer": "standard"},
        "address": {"type": "text", "analyzer": "standard"},
        "location": {"type": "geo_point"},
        "price_monthly": {"type": "float"},
        "bedrooms": {"type": "integer"},
        "bathrooms": {"type": "integer"},
        "amenities": {"type": "keyword"},
        "tags": {"type": "keyword"},
        "images": {"type": "keyword", "index": False},
        "reviews_summary": {"type": "text", "analyzer": "standard"},
        "embedding": {
            "type": "dense_vector",
            "dims": 1024,
            "index": True,
            "similarity": "cosine",
        },
        "crawled_at": {"type": "date"},
        "confidence": {"type": "float"},
    },
}

SETTINGS = {
    "number_of_shards": 1,
    "number_of_replicas": 0,
}


def today_index(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}"


def _to_es_doc(prop: CrawledProperty) -> dict:
    doc = prop.model_dump(mode="json", exclude={"location"})
    if prop.location:
        doc["address"] = prop.location.address
        if prop.location.lat is not None and prop.location.lng is not None:
            doc["location"] = {"lat": prop.location.lat, "lon": prop.location.lng}
    else:
        doc["address"] = None
    doc.pop("property_id", None)
    return doc


def _from_es_doc(source: dict, doc_id: str) -> CrawledProperty:
    source["property_id"] = doc_id
    loc_raw = source.pop("location", None)
    address = source.pop("address", None)
    if loc_raw and isinstance(loc_raw, dict):
        source["location"] = Location(
            lat=loc_raw.get("lat"),
            lng=loc_raw.get("lon"),
            address=address,
        )
    elif address:
        source["location"] = Location(address=address)
    return CrawledProperty(**source)


class CrawledPropertyESRepository:
    def __init__(self, es: AsyncElasticsearch, index_prefix: str):
        self._es = es
        self._index_prefix = index_prefix

    async def ensure_index(self) -> None:
        index = today_index(self._index_prefix)
        exists = await self._es.indices.exists(index=index)
        if not exists:
            await self._es.indices.create(
                index=index,
                body={"settings": SETTINGS, "mappings": INDEX_MAPPING},
            )

    async def store(self, prop: CrawledProperty) -> None:
        await self.ensure_index()
        index = today_index(self._index_prefix)
        doc = _to_es_doc(prop)
        await self._es.index(index=index, id=prop.property_id, body=doc, refresh="wait_for")

    async def search_hybrid(
        self,
        query: SearchQuery,
        embedding: list[float] | None = None,
        size: int = 20,
    ) -> list[CrawledProperty]:
        await self.ensure_index()
        index = today_index(self._index_prefix)

        must: list[dict] = []
        filters: list[dict] = []

        if query.raw:
            must.append({
                "multi_match": {
                    "query": query.raw,
                    "fields": ["title^3", "description", "reviews_summary", "address"],
                    "type": "best_fields",
                }
            })

        if query.max_price is not None:
            filters.append({"range": {"price_monthly": {"lte": query.max_price}}})

        if query.min_bedrooms is not None:
            filters.append({"range": {"bedrooms": {"gte": query.min_bedrooms}}})

        if query.tags:
            filters.append({"terms": {"tags": query.tags}})

        if query.location_hint:
            filters.append({
                "multi_match": {
                    "query": query.location_hint,
                    "fields": ["address", "source_site"],
                }
            })

        body: dict = {
            "query": {"bool": {"must": must if must else [{"match_all": {}}], "filter": filters}},
            "size": size,
            "sort": [{"_score": {"order": "desc"}}],
        }

        try:
            response = await self._es.search(index=index, body=body)
        except NotFoundError:
            return []

        results: list[CrawledProperty] = []
        for hit in response["hits"]["hits"]:
            results.append(_from_es_doc(hit["_source"], hit["_id"]))

        return results

    async def delete_old_indices(self, retention_days: int = 2) -> int:
        deleted = 0
        try:
            indices = await self._es.indices.get(index=f"{self._index_prefix}-*")
        except NotFoundError:
            return 0
        cutoff = datetime.now(timezone.utc).timestamp() - retention_days * 86400
        for index_name in indices:
            parts = index_name.split("-")[-1].split(".")
            if len(parts) == 3:
                try:
                    index_ts = datetime(
                        int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=timezone.utc
                    ).timestamp()
                    if index_ts < cutoff:
                        await self._es.indices.delete(index=index_name)
                        deleted += 1
                except (ValueError, IndexError):
                    continue
        return deleted
