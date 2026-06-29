from src.guardrails.input.classifier import classify_intent, filter_content, validate_input
from src.guardrails.input.rate_limiter import SlidingWindowRateLimiter
from src.guardrails.output.grounding import check_grounding
from src.guardrails.output.pii import strip_pii


class TestClassifier:
    def test_passes_valid_query(self):
        ok, reason = classify_intent("studio near UCLA under $1500")
        assert ok is True
        assert reason is None

    def test_rejects_short_query(self):
        ok, reason = classify_intent("hi")
        assert ok is False
        assert "short" in reason.lower()

    def test_rejects_non_accommodation_query(self):
        ok, reason = classify_intent("what is the weather today")
        assert ok is False
        assert "accommodation" in reason.lower()


class TestContentFilter:
    def test_passes_normal_query(self):
        ok, reason = filter_content("nice apartment near campus")
        assert ok is True

    def test_blocks_script_tags(self):
        ok, reason = filter_content("<script>alert('xss')</script>")
        assert ok is False

    def test_blocks_toxic_patterns(self):
        ok, reason = filter_content("how to make a bomb")
        assert ok is False


class TestValidateInput:
    def test_returns_none_for_valid(self):
        result = validate_input("studio for rent in LA")
        assert result is None

    def test_returns_reason_for_invalid(self):
        result = validate_input("hi")
        assert result is not None


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
