import re

from src.domain.models.property import CrawledProperty, Location
from src.mcp.registry import tool
from src.mcp.tools.base import BaseTool


_INDIAN_PRICE_RE = re.compile(
    r"(?:₹|Rs\.?\s*|INR\s*)(\d[\d,]*)(?:\s*[-–to]+\s*(?:₹|Rs\.?\s*|INR\s*)?(\d[\d,]*))?",
    re.IGNORECASE,
)
_FOREIGN_PRICE_RE = re.compile(
    r"(?:£|€|\$|USD\s*|GBP\s*|EUR\s*)(\d[\d,.]*)(?:\s*[-–to]+\s*(?:£|€|\$)?\s*(\d[\d,.]*))?",
    re.IGNORECASE,
)
_BEDROOM_RE = re.compile(
    r"(\d+)\s*(?:\s*[Bb][Hh][Kk]\s*|[-\s]*(?:[Bb]edroom|[Bb]ed\s*[Rr]oom|[Bb][Rr])s?\b)",
    re.IGNORECASE,
)
_TWIN_SINGLE_RE = re.compile(
    r"(Single\s*(?:Room|Sharing|Occupancy)|Twin\s*Sharing|Double\s*(?:Room|Occupancy|Sharing)|Triple\s*(?:Sharing|Occupancy)|Four\s*Sharing)",
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"^##\s+(.+?)(?:\n|$)", re.MULTILINE)
_AMENITY_RE = re.compile(
    r"\b(AC\b|Wi[-\s]?Fi\b|Power\s*Backup\b|Parking\b|Washing\s*Machine\b|Geyser\b|Food\b|Gym\b|Lift\b|Concierge\b|Security\b|CCTV\b|Laundry\b|Kitchen\b|TV\b|Internet\b)",
    re.IGNORECASE,
)
_SITE_RE = re.compile(r"https?://(?:www\.)?([^/]+)")
_RATING_RE = re.compile(r"(\d+(?:\.\d+)?)\s*/\s*5\s*Overall\s*Rating", re.IGNORECASE)
_IMAGE_RE = re.compile(r"!\[.*?\]\((https?://[^)]+)\)")
_NEXT_IMAGE_RE = re.compile(r"https?://[^\s()]+\.(?:jpe?g|png|webp)(?:\?[^\s()]*)?", re.IGNORECASE)


def _parse_price(text: str) -> tuple[float | None, str]:
    m = _INDIAN_PRICE_RE.search(text)
    if m:
        try:
            val = float(m.group(1).replace(",", ""))
            return val, "INR"
        except ValueError:
            pass
    m = _FOREIGN_PRICE_RE.search(text)
    if m:
        try:
            val = float(m.group(1).replace(",", ""))
            return val, "USD"
        except ValueError:
            pass
    return None, ""


def _parse_bedrooms(text: str) -> int | None:
    m = _BEDROOM_RE.search(text)
    if m:
        return int(m.group(1))
    if re.search(r"studio", text, re.IGNORECASE):
        return 0
    if _TWIN_SINGLE_RE.search(text):
        return 1
    return None


def _parse_site(url: str) -> str:
    m = _SITE_RE.search(url)
    return m.group(1) if m else "unknown"


def _parse_titles(markdown: str) -> list[str]:
    return [m.group(1).strip() for m in _TITLE_RE.finditer(markdown)][:5]


def _parse_amenities(markdown: str) -> list[str]:
    amenities: set[str] = set()
    for m in _AMENITY_RE.finditer(markdown):
        amenities.add(m.group(1).strip())
    return sorted(amenities)


def _parse_rating(markdown: str) -> str | None:
    m = _RATING_RE.search(markdown)
    if m:
        return f"{m.group(1)}/5"
    m2 = re.search(r"(\d+(?:\.\d+)?)\s*/\s*5", markdown)
    if m2:
        return f"{m2.group(1)}/5"
    return None


def _parse_images(markdown: str) -> list[str]:
    imgs = [m.group(1) for m in _IMAGE_RE.finditer(markdown)]
    if not imgs:
        imgs = [m.group(0) for m in _NEXT_IMAGE_RE.finditer(markdown)][:10]
    return imgs[:10]


def _parse_tags(markdown: str) -> list[str]:
    tags: list[str] = []
    for label, tag in {"Boys": "boys", "Girls": "girls", "Coed": "coed", "Unisex": "coed"}.items():
        if re.search(rf"(?:^|\W){label}(?:\W|$)", markdown, re.IGNORECASE):
            tags.append(tag)
            break
    if re.search(r"furnished", markdown, re.IGNORECASE):
        tags.append("furnished")
    if re.search(r"no\s*brokerage|without\s*brokerage", markdown, re.IGNORECASE):
        tags.append("no-brokerage")
    if re.search(r"verified", markdown, re.IGNORECASE):
        tags.append("verified")
    rating = _parse_rating(markdown)
    if rating:
        tags.append(f"rating:{rating}")
    return sorted(set(tags))


def _parse_description(markdown: str) -> str:
    lines = markdown.split("\n")
    desc_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("[", "!", "#", "*", "!")):
            continue
        if len(stripped) > 40:
            desc_lines.append(stripped)
        if len(desc_lines) >= 3:
            break
    return " | ".join(desc_lines) if desc_lines else ""


def _parse_location(markdown: str) -> Location:
    loc = Location()
    patterns = [
        r"\bin\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"Location\s*[:\-–]\s*(.+?)(?:\n|$)",
        r"(?:located|situated)\s+in\s+(.+?)(?:,|\.|\n)",
    ]
    for pat in patterns:
        m = re.search(pat, markdown)
        if m:
            loc.address = m.group(1).strip()
            break
    return loc


@tool
class ExtractionTool(BaseTool):
    name = "extract_property"
    description = "Extract structured property data from raw page markdown. Returns a complete property listing."
    input_schema = {
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": "The raw markdown content of the page to extract data from",
            },
            "source_url": {
                "type": "string",
                "description": "The original URL of the page",
            },
        },
        "required": ["markdown", "source_url"],
    }

    async def run(self, markdown: str, source_url: str) -> dict:
        bedrock = self._deps.bedrock_client
        if bedrock:
            try:
                prop = await bedrock.extract_property(markdown, source_url)
                return prop.model_dump(mode="json") if hasattr(prop, "model_dump") else dict(prop)
            except Exception:
                pass

        titles = _parse_titles(markdown)
        price_val, _currency = _parse_price(markdown)
        bedrooms = _parse_bedrooms(markdown)
        amenities = _parse_amenities(markdown)
        images = _parse_images(markdown)
        tags = _parse_tags(markdown)
        desc = _parse_description(markdown)
        location = _parse_location(markdown)

        title = titles[0] if titles else "Property Listing"
        source_site = _parse_site(source_url)

        return CrawledProperty(
            source_url=source_url,
            source_site=source_site,
            title=title,
            description=desc or None,
            location=location if location.address else None,
            price_monthly=price_val,
            bedrooms=bedrooms,
            amenities=amenities,
            tags=tags,
            images=images,
            confidence=0.4 if (price_val or bedrooms is not None) else 0.2,
        ).model_dump(mode="json")
