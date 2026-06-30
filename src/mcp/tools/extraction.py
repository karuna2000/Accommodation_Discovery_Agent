import re
from typing import Any

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

_BOILERPLATE_SECTION_RE = re.compile(
    r"(?:related\s*(?:listings?|properties?|pages?|posts?)|"
    r"you\s+may\s+also\s+like|similar\s*(?:properties?|listings?)|"
    r"recommended\s*(?:properties?|listings?)|"
    r"top\s*(?:properties?|listings?)|"
    r"property\s*(?:for\s+)?rent\s+(?:in|near|at)\s)",
    re.IGNORECASE,
)
_BOILERPLATE_LINE_RE = re.compile(
    r"^(home|about\s*us|contact\s*us|privacy\s*policy|terms?\s*of\s*service|"
    r"sign\s*(?:in|up)|login|register|menu|navigation|"
    r"all\s*rights\s*reserved|powered\s*by|copyright|©|"
    r"follow\s*us|subscribe|share\s*this|"
    r"advertisement|sponsored|promoted)\b",
    re.IGNORECASE,
)
_DEPOSIT_RE = re.compile(
    r"(?:deposit|security\s*deposit|refundable\s*deposit)\s*[:\-–]?\s*"
    r"(?:₹|Rs\.?\s*|INR\s*|\$|USD\s*)?(\d[\d,.]*)",
    re.IGNORECASE,
)
_LEASE_TERM_RE = re.compile(
    r"(\d+)\s*(?:month|year|yr)s?\s*(?:lease|contract|tenancy|agreement|rental)",
    re.IGNORECASE,
)
_AVAILABILITY_RE = re.compile(
    r"(?:available\s*(?:from|on|date)?|move\s*[-\s]?in\s*(?:date|by)?|"
    r"vacant\s*(?:from|on)?)\s*[:\-–]?\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_HOUSE_RULES_RE = re.compile(
    r"\b(no\s*(?:smoking|pets|drinking|parties|overnight\s*guests?|"
    r"visitors?\s*after|unmarried\s*couples)|"
    r"visiting\s*hours?\s*[:\-–]\s*[\d:]+|"
    r"quiet\s*hours?\s*[:\-–]\s*[\d:]+)\b",
    re.IGNORECASE,
)
_MAINTENANCE_RE = re.compile(
    r"(?:maintenance|maintenance\s*charges?|society\s*fees?|maintenance\s*fees?)\s*[:\-–]?\s*"
    r"(?:₹|Rs\.?\s*|INR\s*|\$|USD\s*)?(\d[\d,.]*)",
    re.IGNORECASE,
)
_FURNISHING_RE = re.compile(
    r"\b(furnished|semi[-\s]furnished|unfurnished|fully\s*furnished)\b",
    re.IGNORECASE,
)
_FOOD_INCLUDED_RE = re.compile(
    r"\b(meals?\s*(?:included|provided|available|cooked)|"
    r"food\s*(?:included|provided|available)|"
    r"breakfast|dinner\s*included|breakfast\s*and\s*dinner)\b",
    re.IGNORECASE,
)


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


def _split_listings(markdown: str) -> list[str]:
    """Split a page markdown into individual property listing chunks."""
    lines = markdown.split("\n")

    def _dedupe(chunks: list[str], min_len: int = 50) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for c in chunks:
            key = c.strip()[:100]
            if key not in seen and len(c.strip()) >= min_len:
                seen.add(key)
                deduped.append(c)
        return deduped

    # Strategy 1: split on ## headers (most common for markdown listings)
    chunks: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## ") and current:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    if len(chunks) >= 2:
        return _dedupe(chunks)

    # Strategy 2: split on horizontal rules
    chunks = []
    current = []
    for line in lines:
        if line.strip() in ("---", "***", "___") and current:
            chunks.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    if len(chunks) >= 2:
        return _dedupe(chunks)

    # Strategy 3: split on numbered list items (1. Title, 2. Title, etc.)
    chunks = []
    current = []
    for line in lines:
        if re.match(r"^\d+[.)]\s", line) and current:
            chunks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current))
    if len(chunks) >= 2:
        return _dedupe(chunks)

    return [markdown]


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


_REVIEW_RE = re.compile(
    r"(?:(?:customer|user|tenant|resident|guest)\s*(?:reviews?|ratings?|feedback|testimonials?)|"
    r"(?:reviews?|ratings?)\s*(?:from|customers?|users?|tenants?))\s*"
    r"[:\-–]\s*(.+?)(?:\n\n|\n---|\n###|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_RATING_LINE_RE = re.compile(r"(?:rating|score|stars?)[:\-–]?\s*(\d+(?:\.\d+)?)\s*/\s*5", re.IGNORECASE)


def _parse_reviews(markdown: str) -> str | None:
    m = _REVIEW_RE.search(markdown)
    if m:
        text = m.group(1).strip()
        text = re.sub(r"\n+", " ", text)[:500]
        return text
    # Try extracting rating line as minimal review signal
    m2 = _RATING_LINE_RE.search(markdown)
    if m2:
        return f"Rated {m2.group(1)}/5"
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


def _strip_boilerplate(markdown: str) -> str:
    lines = markdown.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append(line)
            continue
        if _BOILERPLATE_LINE_RE.match(stripped):
            continue
        cleaned.append(line)
    result = "\n".join(cleaned)
    m = _BOILERPLATE_SECTION_RE.search(result)
    if m:
        result = result[:m.start()]
    return result.strip()


def _extract_from_chunk(markdown: str, source_url: str, bedrock: Any = None) -> dict | None:
    """Extract a single property from a markdown chunk. Tries Bedrock first, then heuristic."""
    if bedrock:
        try:
            prop = bedrock.extract_property(markdown, source_url)
            if hasattr(prop, "model_dump"):
                return prop.model_dump(mode="json")
            if isinstance(prop, dict):
                return prop
        except Exception:
            pass

    titles = _parse_titles(markdown)
    if not titles:
        return None

    price_val, _currency = _parse_price(markdown)
    bedrooms = _parse_bedrooms(markdown)
    amenities = _parse_amenities(markdown)
    images = _parse_images(markdown)
    tags = _parse_tags(markdown)
    desc = _parse_description(markdown)
    location = _parse_location(markdown)
    source_site = _parse_site(source_url)
    reviews_summary = _parse_reviews(markdown)

    deposit_match = _DEPOSIT_RE.search(markdown)
    deposit_val = float(deposit_match.group(1).replace(",", "")) if deposit_match else None

    lease_match = _LEASE_TERM_RE.search(markdown)
    lease_str = lease_match.group(0).strip().lower() if lease_match else None

    avail_match = _AVAILABILITY_RE.search(markdown)
    avail_str = avail_match.group(1).strip() if avail_match else None

    rules = list(set(_HOUSE_RULES_RE.findall(markdown.lower())))

    maint_match = _MAINTENANCE_RE.search(markdown)
    maint_val = float(maint_match.group(1).replace(",", "")) if maint_match else None

    furnish_match = _FURNISHING_RE.search(markdown)
    furnish_str = furnish_match.group(1).lower() if furnish_match else None

    food_match = _FOOD_INCLUDED_RE.search(markdown)
    food_flag = bool(food_match)

    return CrawledProperty(
        source_url=source_url,
        source_site=source_site,
        title=titles[0],
        description=desc or None,
        location=location if location.address else None,
        price_monthly=price_val,
        bedrooms=bedrooms,
        amenities=amenities,
        tags=tags,
        images=images,
        reviews_summary=reviews_summary,
        deposit=deposit_val,
        lease_term=lease_str,
        availability_date=avail_str,
        house_rules=rules,
        maintenance=maint_val,
        furnishing_status=furnish_str,
        food_included=food_flag,
        confidence=0.4 if (price_val or bedrooms is not None) else 0.2,
    ).model_dump(mode="json")


@tool
class ExtractionTool(BaseTool):
    name = "extract_property"
    description = "Extract ALL structured property listings from raw page markdown. Returns an array of property objects."
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

    async def run(self, markdown: str, source_url: str) -> list[dict]:
        bedrock = self._deps.bedrock_client
        markdown = _strip_boilerplate(markdown)
        chunks = _split_listings(markdown)

        results: list[dict] = []
        for chunk in chunks:
            prop = _extract_from_chunk(chunk, source_url, bedrock)
            if prop:
                results.append(prop)

        return results if results else [{"title": "Property Listing", "source_url": source_url, "source_site": _parse_site(source_url), "confidence": 0.1}]
