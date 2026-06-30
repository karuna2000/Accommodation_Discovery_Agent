import json
import re
from typing import Any

import aioboto3

from src.domain.models.property import CrawledProperty
from src.infrastructure.resilience.bulkhead import Bulkhead
from src.infrastructure.resilience.circuit_breaker import CircuitBreaker
from src.infrastructure.resilience.retry import retry_with_backoff
from src.infrastructure.resilience.timeout import with_timeout

PRIMARY_MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"
FALLBACK_MODEL = "anthropic.claude-3-haiku-20240307-v1:0"
EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"

SYSTEM_PROMPTS = {
    "extract": (
        "You are a property listing extractor. Extract structured data from the "
        "listing text into JSON. Only return valid JSON, no preamble, no markdown."
    ),
    "synthesize": (
        "You are a helpful accommodation assistant. Given search results and a "
        "user query, write a brief, conversational summary of available listings."
    ),
}


def _strip_code_blocks(text: str) -> str:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.strip()
    return text


class BedrockClient:
    def __init__(
        self,
        aws_region: str = "us-east-1",
        primary_model: str = "anthropic.claude-3-sonnet-20240229-v1:0",
        fallback_model: str = "anthropic.claude-3-haiku-20240307-v1:0",
        embedding_model: str = "amazon.titan-embed-text-v2:0",
        bulkhead: Bulkhead | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        timeout: float = 30.0,
        retry_max: int = 2,
    ):
        self._region = aws_region
        self._primary_model = primary_model
        self._fallback_model = fallback_model
        self._embedding_model = embedding_model
        self._timeout = timeout
        self._retry_max = retry_max
        self._bulkhead = bulkhead or Bulkhead("bedrock", max_concurrent=3)
        self._circuit_breaker = circuit_breaker or CircuitBreaker("bedrock")

    async def invoke_with_fallback(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1024,
    ) -> str:
        return await self._bulkhead.execute(
            self._circuit_breaker.call,
            self._try_both_models,
            prompt,
            system,
            max_tokens,
        )

    async def _try_both_models(
        self,
        prompt: str,
        system: str,
        max_tokens: int,
    ) -> str:
        try:
            return await self._invoke_model(self._primary_model, prompt, system, max_tokens)
        except Exception:
            return await self._invoke_model(self._fallback_model, prompt, system, max_tokens)

    async def _invoke_model(
        self,
        model_id: str,
        prompt: str,
        system: str,
        max_tokens: int,
    ) -> str:
        return await retry_with_backoff(
            self._do_invoke,
            model_id,
            prompt,
            system,
            max_tokens,
            max_retries=self._retry_max,
        )

    async def _do_invoke(
        self,
        model_id: str,
        prompt: str,
        system: str,
        max_tokens: int,
    ) -> str:
        return await with_timeout(
            self._send_request,
            model_id,
            prompt,
            system,
            max_tokens,
            timeout=self._timeout,
        )

    async def _send_request(
        self,
        model_id: str,
        prompt: str,
        system: str,
        max_tokens: int,
    ) -> str:
        session = aioboto3.Session()
        async with session.client("bedrock-runtime", region_name=self._region) as client:
            if "nova" in model_id.lower():
                body: dict[str, Any] = {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"max_new_tokens": max_tokens},
                }
                if system:
                    body["system"] = [{"text": system}]
            else:
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system:
                    body["system"] = system

            response = await client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            response_body = json.loads(await response["body"].read())

            if "nova" in model_id.lower():
                return response_body["output"]["message"]["content"][0]["text"]
            return response_body["content"][0]["text"]

    async def analyze_intent(self, query: str) -> dict[str, Any]:
        prompt = (
            "You are an accommodation search intent analyzer. Extract the user's "
            "requirements as JSON with these exact fields:\n"
            "- budget_min: number or null (minimum budget if mentioned)\n"
            "- budget_max: number or null (maximum budget, \"under X\" -> max)\n"
            "- bedrooms: number or null (minimum bedrooms, e.g. 2 for \"2 BHK\")\n"
            "- property_type: string or null (\"PG\", \"apartment\", \"flat\", \"studio\", "
            "\"house\", \"hostel\", or null)\n"
            "- location: string or null (area, city, neighborhood)\n"
            "- gender_preference: string or null (\"boys\", \"girls\", or null)\n"
            "- requirements: list of strings (amenities wanted: AC, WiFi, parking, etc.)\n"
            "- keywords: list of strings (important search terms from the query)\n\n"
            f"User query: {query}\n\n"
            "Return ONLY valid JSON. No explanation, no markdown, no code blocks."
        )
        try:
            result = await self.invoke_with_fallback(prompt, max_tokens=512)
            result = _strip_code_blocks(result)
            return json.loads(result)
        except Exception:
            return {}

    async def extract_property(self, markdown: str, url: str) -> CrawledProperty:
        prompt = (
            f"Extract property listing details from this page content. "
            f"Source URL: {url}\n\nContent:\n{markdown}\n\n"
            "Return ONLY valid JSON with these fields: "
            "title (str), description (str | null), "
            "price_monthly (float | null), bedrooms (int | null), "
            "bathrooms (int | null), address (str | null), "
            "latitude (float | null), longitude (float | null), "
            "images (list[str]), amenities (list[str]), tags (list[str]), "
            "reviews_summary (str | null), "
            "deposit (float | null), lease_term (str | null), "
            "availability_date (str | null), house_rules (list[str]), "
            "maintenance (float | null), furnishing_status (str | null), "
            "food_included (bool | null).\n\n"
            "No explanation, no markdown, no code blocks — just the JSON object."
        )
        result = await self.invoke_with_fallback(prompt, system=SYSTEM_PROMPTS["extract"])
        result = _strip_code_blocks(result)
        data = json.loads(result)
        loc = None
        if data.get("latitude") is not None or data.get("longitude") is not None or data.get("address"):
            from src.domain.models.property import Location
            loc = Location(
                lat=data.get("latitude"),
                lng=data.get("longitude"),
                address=data.get("address"),
            )
        return CrawledProperty(
            source_url=url,
            source_site=self._extract_domain(url),
            title=data.get("title", ""),
            description=data.get("description"),
            location=loc,
            price_monthly=data.get("price_monthly"),
            bedrooms=data.get("bedrooms"),
            bathrooms=data.get("bathrooms"),
            amenities=data.get("amenities", []),
            tags=data.get("tags", []),
            images=data.get("images", []),
            reviews_summary=data.get("reviews_summary"),
            deposit=data.get("deposit"),
            lease_term=data.get("lease_term"),
            availability_date=data.get("availability_date"),
            house_rules=data.get("house_rules", []),
            maintenance=data.get("maintenance"),
            furnishing_status=data.get("furnishing_status"),
            food_included=data.get("food_included"),
        )

    async def synthesize(self, properties: list[dict], query: str) -> str:
        prompt = (
            f"User searched for: {query}\n\n"
            f"Found {len(properties)} listings:\n{json.dumps(properties, indent=2, default=str)}\n\n"
            "Write a brief, conversational response summarizing the available "
            "listings for the user. Mention key details like prices, locations, "
            "and amenities. For each listing, explain WHY it matches the user's "
            "search query (e.g. 'under budget', 'correct bedrooms', 'in requested area'). "
            "If no properties found, say so helpfully."
        )
        return await self.invoke_with_fallback(prompt, system=SYSTEM_PROMPTS["synthesize"])

    async def generate_embedding(self, text: str) -> list[float]:
        return await self._bulkhead.execute(
            self._circuit_breaker.call,
            self._do_embedding,
            text,
        )

    async def _do_embedding(self, text: str) -> list[float]:
        return await with_timeout(
            self._send_embedding_request,
            text,
            timeout=self._timeout,
        )

    async def _send_embedding_request(self, text: str) -> list[float]:
        session = aioboto3.Session()
        async with session.client("bedrock-runtime", region_name=self._region) as client:
            if "cohere" in self._embedding_model.lower():
                body = json.dumps({"texts": [text], "input_type": "search_document"})
            else:
                body = json.dumps({"inputText": text})
            response = await client.invoke_model(
                modelId=self._embedding_model,
                contentType="application/json",
                accept="application/json",
                body=body,
            )
            response_body = json.loads(await response["body"].read())
            if "cohere" in self._embedding_model.lower():
                return response_body["embeddings"][0]
            return response_body["embedding"]

    @staticmethod
    def _extract_domain(url: str) -> str:
        from urllib.parse import urlparse
        return urlparse(url).netloc
