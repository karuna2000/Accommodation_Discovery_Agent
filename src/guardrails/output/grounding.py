import re


PRICE_PATTERN = re.compile(r"\$\d[\d,]*")
BEDROOM_PATTERN = re.compile(r"(\d+)\s*bedroom")


def check_grounding(
    synthesized: str,
    properties: list[dict],
) -> tuple[bool, list[str]]:
    issues: list[str] = []

    mentioned_prices = PRICE_PATTERN.findall(synthesized)
    actual_prices: list[str] = []
    for p in properties:
        if not isinstance(p, dict):
            continue
        pm = p.get("price_monthly")
        if pm is not None:
            actual_prices.append(f"${int(pm)}")

    for mp in mentioned_prices:
        normalized = mp.replace(",", "")
        actual_price_strs = [
            str(int(float(str(pm).replace("$", ""))))
            for p in properties
            if isinstance(p, dict)
            for pm in [p.get("price_monthly")]
            if pm is not None and isinstance(pm, (int, float, str))
        ]
        if normalized not in actual_prices and str(round(float(normalized.replace("$", "")))) not in actual_price_strs:
            issues.append(f"Price {mp} not found in properties")

    mentioned_bedrooms = BEDROOM_PATTERN.findall(synthesized.lower())
    actual_bedrooms = [str(p.get("bedrooms", "")) for p in properties if isinstance(p, dict) and p.get("bedrooms") is not None]
    for mb in mentioned_bedrooms:
        if mb not in actual_bedrooms:
            issues.append(f"{mb} bedroom claim not in properties")

    return len(issues) == 0, issues
