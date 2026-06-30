from unittest.mock import AsyncMock, MagicMock

from src.agent.nodes.evaluate import evaluate_node
from src.agent.nodes.execute import execute_node, _parse_plan_line
from src.agent.nodes.intent import intent_node, _fallback_intent
from src.agent.nodes.plan import plan_node
from src.agent.nodes.synthesize import synthesize_node
from src.agent.nodes.validate import validate_node


class TestParsePlanLine:
    def test_parses_simple_call(self):
        result = _parse_plan_line("1. search_web(query=\"studio\", count=10)")
        assert result is not None
        assert result[0] == "search_web"
        assert result[1]["query"] == "studio"

    def test_parses_without_quotes(self):
        result = _parse_plan_line("2. scrape_url(url=$url_1)")
        assert result is not None
        assert result[0] == "scrape_url"

    def test_returns_none_for_invalid_line(self):
        result = _parse_plan_line("invalid line")
        assert result is None


class TestPlanNode:
    async def test_generates_plan(self):
        state = {
            "query": "test query",
            "intent": {"keywords": ["test", "query"], "location": "delhi", "property_type": "PG"},
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 0,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "plan" in result
        assert "search_web(query=" in result["plan"]
        assert "count=8" in result["plan"]
        assert "magicbricks 99acres" in result["plan"]
        assert result["step_index"] == 0
        assert result["iteration"] == 1

    async def test_builds_query_from_intent(self):
        state = {
            "query": "find a place",
            "intent": {
                "property_type": "PG",
                "location": "Jaipur",
                "keywords": ["PG", "Jaipur"],
            },
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 0,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "PG" in result["plan"]
        assert "Jaipur" in result["plan"]
        assert "magicbricks 99acres" in result["plan"]

    async def test_preserves_existing_accommodation_keywords(self):
        state = {
            "query": "PG in Mansarovar Extension",
            "intent": {"keywords": ["PG", "Mansarovar", "Extension"]},
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 0,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "PG in Mansarovar Extension" in result["plan"]

    async def test_increases_count_at_higher_constraint_tier(self):
        state = {
            "query": "2 BHK in Jaipur",
            "intent": {"budget_max": 10000, "location": "Jaipur", "bedrooms": 2},
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 1,
            "constraint_tier": 2,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "count=12" in result["plan"]
        assert "scrape_url" in result["plan"]

    async def test_specific_intent_uses_fewer_steps(self):
        state = {
            "query": "2 BHK in Jaipur under 15000",
            "intent": {"location": "Jaipur", "property_type": "apartment", "budget_max": 15000, "bedrooms": 2},
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 0,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "count=5" in result["plan"]

    async def test_vague_intent_uses_more_steps(self):
        state = {
            "query": "Jaipur",
            "intent": {"location": "Jaipur", "keywords": ["Jaipur"]},
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 0,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "count=15" in result["plan"]

    async def test_drops_domain_hints_at_higher_tier(self):
        state = {
            "query": "test",
            "intent": {"location": "Jaipur"},
            "plan": "",
            "step_index": 0,
            "max_steps": 5,
            "results": [],
            "synthesized_answer": None,
            "error": None,
            "iteration": 1,
            "constraint_tier": 2,
        }
        config = {"configurable": {"context": {"tool_schemas": [], "bedrock_client": None}}}
        result = await plan_node(state, config)
        assert "magicbricks" not in result["plan"]


class TestIntentNode:
    async def test_uses_bedrock_when_available(self):
        mock_bedrock = MagicMock()
        mock_bedrock.analyze_intent = AsyncMock(return_value={
            "budget_max": 15000,
            "bedrooms": 2,
            "property_type": "PG",
            "location": "Jaipur",
            "keywords": ["PG", "Jaipur", "15000"],
        })
        state = {"query": "PG in Jaipur under 15000", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": mock_bedrock}}}
        result = await intent_node(state, config)
        assert result["intent"]["budget_max"] == 15000
        assert result["intent"]["property_type"] == "PG"

    async def test_falls_back_to_regex_when_no_bedrock(self):
        state = {"query": "2 BHK in Jaipur for boys under 15000", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["intent"]["budget_max"] == 15000
        assert result["intent"]["bedrooms"] == 2
        assert result["intent"]["location"] == "Jaipur"
        assert result["intent"]["gender_preference"] == "boys"


class TestGreeting:
    async def test_hi_gets_welcome(self):
        state = {"query": "hi", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "help you find" in result["clarification_message"].lower()

    async def test_hello_gets_welcome(self):
        state = {"query": "hello", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "help you find" in result["clarification_message"].lower()


class TestNonAccommodation:
    async def test_rejects_unrelated_query(self):
        state = {"query": "sex worker", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "only help with accommodation" in result["clarification_message"].lower()

    async def test_rejects_weather_query(self):
        state = {"query": "what is the weather today", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "only help with accommodation" in result["clarification_message"].lower()

    async def test_rejects_cooking_query(self):
        state = {"query": "how to cook pasta", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "only help with accommodation" in result["clarification_message"].lower()


class TestVagueAccommodation:
    async def test_needs_clarification_for_bare_bhk(self):
        state = {"query": "2 BHK", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "location" in result["clarification_message"].lower()

    async def test_needs_clarification_for_bare_pg(self):
        state = {"query": "PG", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "location" in result["clarification_message"].lower()

    async def test_no_clarification_for_complete_query(self):
        state = {"query": "PG in Jaipur under 15000 near airport", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result.get("needs_clarification") is False or "needs_clarification" not in result

    async def test_no_clarification_for_location_only(self):
        state = {"query": "in Jaipur", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result.get("needs_clarification") is False or "needs_clarification" not in result

    async def test_clarification_message_mentions_missing_fields(self):
        state = {"query": "2 BHK", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert "location" in result["clarification_message"].lower()
        assert "accommodation" in result["clarification_message"].lower() or "budget" in result["clarification_message"].lower()

    async def test_needs_clarification_when_no_location_with_budget_and_bhk(self):
        state = {"query": "2 BHK under 15000", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result["needs_clarification"] is True
        assert "location" in result["clarification_message"].lower()

    async def test_no_clarification_for_budget_bhk_with_location(self):
        state = {"query": "2 BHK in Jaipur under 15000", "intent": {}}
        config = {"configurable": {"context": {"bedrock_client": None}}}
        result = await intent_node(state, config)
        assert result.get("needs_clarification") is False or "needs_clarification" not in result


class TestFallbackIntent:
    def test_extracts_budget(self):
        intent = _fallback_intent("under 15000")
        assert intent["budget_max"] == 15000

    def test_extracts_bedrooms(self):
        intent = _fallback_intent("2 BHK")
        assert intent["bedrooms"] == 2

    def test_extracts_studio(self):
        intent = _fallback_intent("studio apartment")
        assert intent["bedrooms"] == 0
        assert intent["property_type"] == "studio"

    def test_extracts_gender(self):
        intent = _fallback_intent("PG for girls")
        assert intent["gender_preference"] == "girls"

    def test_extracts_location(self):
        intent = _fallback_intent("apartment in Mumbai")
        assert intent["location"] == "Mumbai"

    def test_extracts_property_type(self):
        intent = _fallback_intent("PG in Delhi")
        assert intent["property_type"] == "PG"

    def test_extracts_amenities(self):
        intent = _fallback_intent("AC WiFi parking")
        assert "ac" in intent["requirements"]
        assert "wifi" in intent["requirements"]
        assert "parking" in intent["requirements"]

    def test_extracts_budget_min_above(self):
        intent = _fallback_intent("above 5000")
        assert intent["budget_min"] == 5000

    def test_extracts_budget_min_at_least(self):
        intent = _fallback_intent("at least 10000")
        assert intent["budget_min"] == 10000

    def test_extracts_budget_range(self):
        intent = _fallback_intent("from 10000 to 20000")
        assert intent["budget_min"] == 10000
        assert intent["budget_max"] == 20000

    def test_budget_min_and_max_separate(self):
        intent = _fallback_intent("above 5000 under 15000")
        assert intent["budget_min"] == 5000
        assert intent["budget_max"] == 15000

    def test_empty_query_returns_defaults(self):
        intent = _fallback_intent("")
        assert intent["budget_max"] is None
        assert intent["budget_min"] is None
        assert intent["bedrooms"] is None


class TestExecuteNode:
    async def test_skips_if_no_more_steps(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 5,
            "results": [],
            "intent": {},
            "page_stats": [],
            "step_vars": {},
        }
        config = {"configurable": {"context": {"tools": {}}}}
        result = await execute_node(state, config)
        assert result["step_index"] == 6

    async def test_returns_error_for_unknown_tool(self):
        state = {
            "plan": "1. unknown_tool(x=1)",
            "step_index": 0,
            "results": [],
            "intent": {},
            "page_stats": [],
            "step_vars": {},
        }
        config = {"configurable": {"context": {"tools": {}}}}
        result = await execute_node(state, config)
        assert "error" in result
        assert "not found" in result["error"].lower()

    async def test_calls_search_web_and_stores_urls(self):
        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(return_value=[
            {"url": "https://example.com/1", "title": "Listing 1", "snippet": "desc", "engine": "mock"},
        ])

        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 0,
            "results": [],
            "intent": {},
            "page_stats": [],
            "step_vars": {},
        }
        config = {"configurable": {"context": {"tools": {"search_web": mock_tool}}}}
        result = await execute_node(state, config)
        assert result["step_index"] == 1
        assert result["step_vars"]["result_url_1"] == "https://example.com/1"
        assert "result1" not in result.get("results", [])

    async def test_extract_property_tracks_page_stats(self):
        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(return_value=[
            {"title": "Apt 1", "price_monthly": 1000, "confidence": 0.5},
        ])

        state = {
            "plan": "1. extract_property(markdown=\"test\", source_url=\"https://example.com/1\")",
            "step_index": 0,
            "results": [],
            "query": "test",
            "intent": {},
            "page_stats": [],
            "step_vars": {},
        }
        config = {"configurable": {"context": {"tools": {"extract_property": mock_tool}}}}
        result = await execute_node(state, config)
        assert len(result["page_stats"]) == 1
        assert result["page_stats"][0]["url"] == "https://example.com/1"
        assert result["page_stats"][0]["properties_found"] == 1


class TestEvaluateNode:
    async def test_routes_to_synthesize_when_done(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 1,
            "results": [{"title": "Apt"}],
            "iteration": 1,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "synthesize"

    async def test_routes_to_execute_when_steps_remain(self):
        state = {
            "plan": "1. search_web(query=\"test\")\n2. scrape_url(url=\"x\")",
            "step_index": 0,
            "results": [],
            "iteration": 1,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "execute"

    async def test_routes_to_synthesize_on_max_iterations(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 0,
            "results": [],
            "iteration": 10,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "synthesize"

    async def test_routes_to_plan_with_constraint_tier_on_zero_results(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 1,
            "results": [],
            "iteration": 1,
            "constraint_tier": 0,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "plan"
        assert result["constraint_tier"] == 1

    async def test_gives_up_after_tier_3(self):
        state = {
            "plan": "1. search_web(query=\"test\")",
            "step_index": 1,
            "results": [],
            "iteration": 1,
            "constraint_tier": 3,
        }
        config = {"configurable": {"context": {"max_iterations": 5}}}
        result = await evaluate_node(state, config)
        assert result["decision"] == "synthesize"


class TestSynthesizeNode:
    async def test_uses_synthesize_tool_when_available(self):
        mock_tool = MagicMock()
        mock_tool.run = AsyncMock(return_value="Found 3 apartments")

        state = {
            "query": "studio",
            "results": [{"title": "Apt"}],
        }
        config = {
            "configurable": {
                "context": {
                    "tools": {"synthesize_answer": mock_tool},
                    "bedrock_client": None,
                }
            }
        }
        result = await synthesize_node(state, config)
        assert result["synthesized_answer"] == "Found 3 apartments"

    async def test_generates_default_when_no_tool(self):
        state = {
            "query": "studio near UCLA",
            "results": [{"title": "Apt 1"}],
        }
        config = {"configurable": {"context": {"tools": {}, "bedrock_client": None}}}
        result = await synthesize_node(state, config)
        assert "studio" in result["synthesized_answer"].lower()


class TestValidateNode:
    async def test_noop_when_no_results(self):
        state = {"query": "test", "results": [], "intent": {}}
        config = {"configurable": {"context": {}}}
        result = await validate_node(state, config)
        assert result["validation_report"]["method"] == "noop"
        assert result["validation_report"]["passed"] is True

    async def test_strips_pii_from_results(self):
        state = {
            "query": "apartment",
            "results": [
                {
                    "title": "Nice flat",
                    "description": "Call me at +91-9876543210",
                    "price_monthly": 15000,
                },
            ],
            "intent": {},
        }
        config = {"configurable": {"context": {}}}
        result = await validate_node(state, config)
        assert "9876543210" not in result["results"][0]["description"]
        assert "<PHONE>" in result["results"][0]["description"]

    async def test_filters_irrelevant_properties_by_budget(self):
        state = {
            "query": "2 BHK under 10000",
            "results": [
                {
                    "title": "Luxury Villa",
                    "price_monthly": 50000,
                    "bedrooms": 4,
                    "confidence": 0.3,
                },
                {
                    "title": "Budget Flat",
                    "price_monthly": 8000,
                    "bedrooms": 2,
                    "confidence": 0.6,
                },
            ],
            "intent": {"budget_max": 10000, "bedrooms": 2},
        }
        config = {"configurable": {"context": {}}}
        result = await validate_node(state, config)
        titles = [p["title"] for p in result["results"]]
        assert "Budget Flat" in titles
        assert "Luxury Villa" not in titles

    async def test_passes_complete_mode(self):
        state = {
            "query": "test",
            "results": [
                {"title": "Good Apt", "price_monthly": 8000, "confidence": 0.8},
            ],
            "intent": {},
        }
        config = {"configurable": {"context": {}}}
        result = await validate_node(state, config)
        assert result["validation_report"]["passed"] is True

    async def test_sets_error_on_issues(self):
        state = {
            "query": "2 BHK under 10000",
            "results": [
                {
                    "title": "Luxury Villa",
                    "price_monthly": 50000,
                    "confidence": 0.3,
                },
            ],
            "intent": {"budget_max": 10000},
        }
        config = {"configurable": {"context": {}}}
        result = await validate_node(state, config)
        assert result["error"] is not None
