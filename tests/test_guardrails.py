from unittest.mock import AsyncMock, MagicMock

from src.guardrails.input.classifier import sanitize, validate_input
from src.guardrails.input.rate_limiter import SlidingWindowRateLimiter
from src.guardrails.output.grounding import check_grounding
from src.guardrails.output.guard import (
    strip_pii_from_properties,
    validate_results,
    _query_matches_intent,
    _filter_vague_properties,
    _score_completeness,
    _flag_low_confidence,
)
from src.guardrails.output.pii import strip_pii


class TestSanitize:
    def test_strips_html_tags(self):
        assert sanitize("<script>alert('xss')</script>") == "alert('xss')"

    def test_strips_html_with_attributes(self):
        assert sanitize('<img src=x onerror=alert(1)>') == ""

    def test_passes_clean_text(self):
        assert sanitize("2 BHK in Jaipur under 15000") == "2 BHK in Jaipur under 15000"


class TestValidateInput:
    def test_passes_accommodation_query(self):
        query, reason = validate_input("2 BHK in Jaipur under 15000")
        assert query is not None
        assert reason is None

    def test_passes_greeting(self):
        query, reason = validate_input("hi")
        assert query is not None
        assert reason is None

    def test_sanitizes_html_in_query(self):
        query, reason = validate_input("<script>alert(1)</script> 2 BHK")
        assert query is not None
        assert reason is None
        assert "<" not in query
        assert ">" not in query
        assert "2 BHK" in query

    def test_blocks_prohibited_terms(self):
        query, reason = validate_input("how to make a bomb")
        assert query is None
        assert reason is not None
        assert "prohibited" in reason.lower()

    def test_blocks_dangerous_uri(self):
        query, reason = validate_input("javascript:alert(1)")
        assert query is None
        assert reason is not None

    def test_rejects_empty_query(self):
        query, reason = validate_input("")
        assert query is None
        assert reason is not None


class TestRateLimiter:
    def test_allows_first_request(self):
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
        assert limiter.is_allowed("user-1") is True

    def test_blocks_after_exceeding(self):
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        assert limiter.is_allowed("user-2") is True
        assert limiter.is_allowed("user-2") is True
        assert limiter.is_allowed("user-2") is True
        assert limiter.is_allowed("user-2") is False


class TestPiiStripper:
    def test_removes_email(self):
        text = "Contact me at john@example.com for details"
        result = strip_pii(text)
        assert "<EMAIL>" in result
        assert "john@example.com" not in result

    def test_removes_phone(self):
        text = "Call 555-123-4567 for info"
        result = strip_pii(text)
        assert "<PHONE>" in result

    def test_leaves_normal_text(self):
        text = "This apartment has 2 bedrooms and costs $1500"
        result = strip_pii(text)
        assert result == text


class TestGrounding:
    def test_passes_when_prices_match(self):
        text = "Found an apartment for $1500"
        props = [{"price_monthly": 1500}]
        ok, issues = check_grounding(text, props)
        assert ok is True

    def test_identifies_ungrounded_claims(self):
        text = "Found an apartment for $999"
        props = [{"price_monthly": 1500}]
        ok, issues = check_grounding(text, props)
        assert ok is False
        assert any("$999" in i for i in issues)


class TestStripPiiFromProperties:
    def test_strips_email_from_description(self):
        props = [{"title": "Nice flat", "description": "Email me@here.com"}]
        cleaned = strip_pii_from_properties(props)
        assert "<EMAIL>" in cleaned[0]["description"]
        assert "me@here.com" not in cleaned[0]["description"]

    def test_strips_phone_from_address(self):
        props = [{"title": "Flat", "location": {"address": "Call 555-123-4567"}}]
        cleaned = strip_pii_from_properties(props)
        assert "<PHONE>" in cleaned[0]["location"]["address"]

    def test_strips_pii_from_tags(self):
        props = [{"title": "Flat", "tags": ["AC", "call 555-123-4567"]}]
        cleaned = strip_pii_from_properties(props)
        assert any("<PHONE>" in t for t in cleaned[0]["tags"])

    def test_strips_pii_from_amenities(self):
        props = [{"title": "Flat", "amenities": ["WiFi", "email x@y.z"]}]
        cleaned = strip_pii_from_properties(props)
        assert any("<EMAIL>" in a for a in cleaned[0]["amenities"])

    def test_leaves_clean_text(self):
        props = [{"title": "Nice 2 BHK", "description": "AC, WiFi, parking"}]
        cleaned = strip_pii_from_properties(props)
        assert cleaned[0]["title"] == "Nice 2 BHK"
        assert cleaned[0]["description"] == "AC, WiFi, parking"

    def test_handles_non_dict_items(self):
        props = ["not a dict", {"title": "Flat", "price": 100}]
        cleaned = strip_pii_from_properties(props)
        assert len(cleaned) == 2
        assert cleaned[0] == "not a dict"


class TestQueryMatchesIntent:
    def test_budget_overage_low_confidence_excluded(self):
        prop = {"price_monthly": 20000, "confidence": 0.3}
        assert _query_matches_intent(prop, "under 10000", {"budget_max": 10000}) is False

    def test_budget_overage_high_confidence_included(self):
        prop = {"price_monthly": 20000, "confidence": 0.6}
        assert _query_matches_intent(prop, "under 10000", {"budget_max": 10000}) is True

    def test_bedrooms_too_few_excluded(self):
        prop = {"bedrooms": 1, "confidence": 0.3}
        assert _query_matches_intent(prop, "2 BHK", {"bedrooms": 2}) is False

    def test_gender_mismatch_excluded(self):
        prop = {"tags": ["boys"]}
        assert _query_matches_intent(prop, "girls PG", {"gender_preference": "girls"}) is False

    def test_passes_all_checks(self):
        prop = {"title": "Apt", "price_monthly": 8000, "bedrooms": 2, "confidence": 0.8}
        assert _query_matches_intent(prop, "2 BHK under 10000", {"budget_max": 10000, "bedrooms": 2}) is True

    def test_budget_min_too_low_excluded(self):
        prop = {"price_monthly": 3000, "confidence": 0.3}
        assert _query_matches_intent(prop, "above 5000", {"budget_min": 5000}) is False

    def test_budget_min_high_confidence_included(self):
        prop = {"price_monthly": 3000, "confidence": 0.8}
        assert _query_matches_intent(prop, "above 5000", {"budget_min": 5000}) is True

    def test_budget_min_and_max_respected(self):
        prop = {"price_monthly": 6000, "confidence": 0.6}
        assert _query_matches_intent(prop, "above 5000 under 10000", {"budget_min": 5000, "budget_max": 10000}) is True

    def test_budget_min_too_high_excluded(self):
        prop = {"price_monthly": 15000, "confidence": 0.3}
        assert _query_matches_intent(prop, "above 5000 under 10000", {"budget_min": 5000, "budget_max": 10000}) is False


class TestFilterVagueProperties:
    def test_removes_non_matching(self):
        props = [
            {"title": "Good", "price_monthly": 8000, "confidence": 0.8},
            {"title": "Bad", "price_monthly": 50000, "confidence": 0.2},
        ]
        filtered, issues = _filter_vague_properties(props, "under 10000", {"budget_max": 10000})
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Good"
        assert len(issues) == 1


class TestValidateResults:
    async def test_fallback_strips_pii_and_filters(self):
        props = [
            {"title": "Flat", "description": "Call 555-123-4567", "price_monthly": 8000, "confidence": 0.8},
        ]
        cleaned, report = await validate_results(props, "under 10000", {"budget_max": 10000})
        assert "<PHONE>" in cleaned[0]["description"]
        assert report["method"] == "fallback"
        assert report["passed"] is True

    async def test_fallback_removes_irrelevant(self):
        props = [
            {"title": "Luxury", "price_monthly": 50000, "confidence": 0.3},
        ]
        cleaned, report = await validate_results(props, "under 10000", {"budget_max": 10000})
        assert len(cleaned) == 0
        assert report["properties_filtered"] == 1

    async def test_llm_path_called_when_bedrock_available(self):
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_with_fallback = AsyncMock(return_value='{"results": [{"title": "Validated"}], "issues": [], "properties_filtered": 0, "passed": true}')
        props = [{"title": "Raw", "price_monthly": 8000}]
        cleaned, report = await validate_results(props, "test", {}, mock_bedrock)
        assert len(cleaned) == 1
        assert report["method"] == "llm"

    async def test_llm_fallback_to_regex_on_parse_error(self):
        mock_bedrock = MagicMock()
        mock_bedrock.invoke_with_fallback = AsyncMock(return_value="not valid json")
        props = [{"title": "Flat", "price_monthly": 8000, "confidence": 0.8}]
        cleaned, report = await validate_results(props, "test", {}, mock_bedrock)
        assert len(cleaned) >= 1
        assert report["method"] == "fallback"


class TestCompletenessScoring:
    def test_scores_complete_property_high(self):
        score = _score_completeness({
            "title": "Nice Apt", "price_monthly": 15000, "bedrooms": 2, "source_url": "https://x.com",
            "location": {"address": "Jaipur"}, "amenities": ["AC", "WiFi"],
        })
        assert score["core_percent"] >= 75
        assert score["low_confidence"] is False

    def test_scores_sparse_property_low(self):
        score = _score_completeness({
            "title": "Some Place", "price_monthly": None, "bedrooms": None, "source_url": "",
        })
        assert score["low_confidence"] is True

    def test_very_low_excluded_by_flag(self):
        props = [{"title": "Poor", "price_monthly": None, "bedrooms": None, "source_url": ""}]
        kept, issues = _flag_low_confidence(props)
        assert len(kept) == 0
        assert len(issues) == 1
