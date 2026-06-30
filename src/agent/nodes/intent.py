import re
from typing import Any

from langgraph.types import RunnableConfig

_QUERY_BUDGET_RE = re.compile(
    r"(?:under|max(?:imum)?|budget|within|below|upto|up to)\s*"
    r"(?:₹|Rs\.?\s*|INR\s*|\$|USD\s*)?(\d[\d,.]*)",
    re.IGNORECASE,
)
_QUERY_BUDGET_MIN_RE = re.compile(
    r"(?:above|min(?:imum)?|at\s*least|starting\s*(?:from|at)|from)\s*"
    r"(?:₹|Rs\.?\s*|INR\s*|\$|USD\s*)?(\d[\d,.]*)",
    re.IGNORECASE,
)
_QUERY_BHK_RE = re.compile(r"(\d+)\s*B[Hh][Kk]", re.IGNORECASE)
_QUERY_STUDIO_RE = re.compile(r"\bstudio\b", re.IGNORECASE)
_QUERY_BOYS_RE = re.compile(r"\b(boys?|gents?|male)\b", re.IGNORECASE)
_QUERY_GIRLS_RE = re.compile(r"\b(girls?|ladies?|female|women|womens)\b", re.IGNORECASE)
_QUERY_LOCATION_RE = re.compile(
    r"(?:in|near|at|around)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)",
)
_QUERY_PG_RE = re.compile(r"\bPG\b", re.IGNORECASE)
_QUERY_APARTMENT_RE = re.compile(r"\b(?:apartment|flat|apt)\b", re.IGNORECASE)
_QUERY_HOUSE_RE = re.compile(r"\b(?:house|villa|bungalow)\b", re.IGNORECASE)
_QUERY_HOSTEL_RE = re.compile(r"\bhostel\b", re.IGNORECASE)
_AMENITY_RE = re.compile(
    r"\b(?:AC|air.?condition|WiFi|wifi|parking|furnished|unfurnished|"
    r"semi.?furnished|pool|gym|security|power.?backup|laundry|"
    r"cooking|lift|elevator|balcony|terrace|garden|pet)\b",
    re.IGNORECASE,
)

_GREETING_RE = re.compile(
    r"^(hi|hello|hey|hii|helloo|heyy?|"
    r"good\s*(morning|afternoon|evening|day)|"
    r"what'?s\s*up|sup|howdy|namaste|"
    r"greetings|yo)\s*[.!?]*$",
    re.IGNORECASE,
)

_ACCOMMODATION_TERMS: set[str] = {
    "pg", "apartment", "flat", "studio", "house", "villa", "hostel", "dorm",
    "room", "condo", "bhk", "suite", "penthouse",
    "rent", "lease", "accommodation", "housing", "living", "stay", "property",
    "listing", "bedroom", "bathroom", "furnished", "unfurnished",
    "balcony", "terrace", "garden", "parking", "gym", "pool", "security",
    "neighborhood", "locality", "sector", "phase", "colony",
}


def _fallback_intent(query: str) -> dict[str, Any]:
    intent: dict[str, Any] = {
        "budget_min": None,
        "budget_max": None,
        "bedrooms": None,
        "property_type": None,
        "location": None,
        "gender_preference": None,
        "requirements": [],
        "keywords": [],
    }

    for m in _QUERY_BUDGET_RE.finditer(query):
        val = float(m.group(1).replace(",", ""))
        if intent["budget_max"] is None or val < intent["budget_max"]:
            intent["budget_max"] = val

    range_max = None
    range_match = re.search(r"(\d[\d,.]*)\s*(?:-|to)\s*(\d[\d,.]*)", query)
    if range_match:
        lo = float(range_match.group(1).replace(",", ""))
        hi = float(range_match.group(2).replace(",", ""))
        intent["budget_min"] = min(lo, hi)
        intent["budget_max"] = max(lo, hi)
        range_max = intent["budget_max"]

    for m in _QUERY_BUDGET_MIN_RE.finditer(query):
        val = float(m.group(1).replace(",", ""))
        if range_max is not None and val >= range_max:
            continue
        if intent["budget_min"] is None or val < intent["budget_min"]:
            intent["budget_min"] = val

    bhk_m = _QUERY_BHK_RE.search(query)
    if bhk_m:
        intent["bedrooms"] = int(bhk_m.group(1))
    elif _QUERY_STUDIO_RE.search(query):
        intent["bedrooms"] = 0

    if _QUERY_STUDIO_RE.search(query):
        intent["property_type"] = "studio"
    elif _QUERY_PG_RE.search(query):
        intent["property_type"] = "PG"
    elif _QUERY_APARTMENT_RE.search(query):
        intent["property_type"] = "apartment"
    elif _QUERY_HOUSE_RE.search(query):
        intent["property_type"] = "house"
    elif _QUERY_HOSTEL_RE.search(query):
        intent["property_type"] = "hostel"

    if _QUERY_BOYS_RE.search(query):
        intent["gender_preference"] = "boys"
    elif _QUERY_GIRLS_RE.search(query):
        intent["gender_preference"] = "girls"

    for m in _QUERY_LOCATION_RE.finditer(query):
        place = m.group(1).strip()
        if place.lower() not in ("the", "a", "an", "for", "under", "with", "near", "around"):
            intent["location"] = place
            break

    intent["requirements"] = [m.group(0).lower() for m in _AMENITY_RE.finditer(query)]

    # Filter common/noise words from keywords
    stopwords = {"a", "an", "the", "in", "near", "at", "for", "under", "with", "around",
                 "and", "or", "of", "to", "is", "i", "want", "looking", "need", "find"}
    words = [w for w in query.split() if w.lower() not in stopwords and len(w) > 1]
    intent["keywords"] = list(dict.fromkeys(w.strip(",.!") for w in words))

    return intent


def _relax_intent(intent: dict[str, Any], tier: int) -> dict[str, Any]:
    relaxed = dict(intent)
    if tier >= 1:
        relaxed.pop("budget_max", None)
        relaxed.pop("budget_min", None)
    if tier >= 2:
        relaxed.pop("property_type", None)
        relaxed.pop("gender_preference", None)
        relaxed.pop("requirements", None)
    if tier >= 3:
        loc = relaxed.get("location")
        if loc and len(loc.split()) >= 2:
            parts = loc.split()
            relaxed["location"] = parts[-1]
    return relaxed


def _is_greeting(query: str) -> bool:
    return bool(_GREETING_RE.match(query.strip().rstrip(".!?")))


def _is_accommodation_related(intent: dict[str, Any], raw_query: str) -> bool:
    if any(intent.get(k) for k in ("location", "property_type", "requirements")):
        return True
    if intent.get("budget_max") is not None:
        return True
    if intent.get("bedrooms") is not None:
        return True

    lower = raw_query.lower()
    if any(term in lower for term in _ACCOMMODATION_TERMS):
        return True
    if re.search(r"\b(in|near|at|around)\s+\w+", lower):
        return True
    if re.search(r"\b\d+\s*bhk\b", lower):
        return True

    return False


def _needs_clarification(intent: dict[str, Any], raw_query: str) -> bool:
    has_location = bool(intent.get("location"))

    if has_location:
        return False

    words = [w for w in raw_query.strip().split() if len(w) > 1]
    if len(words) <= 1 and len(raw_query.strip()) < 15:
        return True

    return True


def _clarification_message(intent: dict[str, Any], raw_query: str) -> str:
    missing: list[str] = []

    if not intent.get("location"):
        missing.append("a location (city or area)")
    if not intent.get("property_type"):
        missing.append("the type of accommodation (PG, apartment, flat, hostel, etc.)")
    if intent.get("budget_max") is None:
        missing.append("a budget range")
    if intent.get("bedrooms") is None:
        missing.append("the number of bedrooms")

    if missing:
        return (
            "Could you please provide more details? I need **"
            + "**, and **".join(missing)
            + "** to find the best options for you."
        )

    return (
        "Could you please provide more details like location, "
        "budget, or type of accommodation you're looking for?"
    )


async def intent_node(state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
    query = state["query"]
    ctx = config.get("configurable", {}).get("context", {})
    bedrock = ctx.get("bedrock_client")

    if _is_greeting(query):
        return {
            "needs_clarification": True,
            "clarification_message": (
                "Hi! I can help you find accommodation. "
                "What kind of place are you looking for and where?"
            ),
        }

    intent: dict[str, Any] = {}
    if bedrock:
        try:
            parsed = await bedrock.analyze_intent(query)
            if parsed.get("keywords"):
                intent = parsed
        except Exception:
            pass

    if not intent.get("keywords"):
        intent = _fallback_intent(query)

    if not _is_accommodation_related(intent, query):
        return {
            "needs_clarification": True,
            "clarification_message": (
                "I can only help with accommodation searches. "
                "Please tell me what you're looking for — for example: "
                "**\\\"2 BHK in Jaipur under 15000\\\"** or "
                "**\\\"PG near university\\\"**."
            ),
        }

    if _needs_clarification(intent, query):
        return {
            "intent": intent,
            "needs_clarification": True,
            "clarification_message": _clarification_message(intent, query),
        }

    return {"intent": intent}
