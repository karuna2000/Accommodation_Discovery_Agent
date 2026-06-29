from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.external.bedrock import BedrockClient


@pytest.fixture
def mock_bedrock():
    session = MagicMock()
    client = AsyncMock()
    session.client.return_value.__aenter__.return_value = client
    return session, client


class TestBedrockClient:
    async def test_invoke_returns_text(self, mock_bedrock):
        session, client = mock_bedrock
        client.invoke_model.return_value = {
            "body": AsyncMock(
                read=AsyncMock(
                    return_value=b'{"content": [{"text": "Hello world"}]}'
                )
            )
        }

        with patch("aioboto3.Session", return_value=session):
            bedrock = BedrockClient(timeout=5, retry_max=0)
            result = await bedrock.invoke_with_fallback("Hello")

        assert result == "Hello world"

    async def test_fallback_on_primary_failure(self, mock_bedrock):
        session, client = mock_bedrock
        call_count = 0

        async def invoke_model(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise TimeoutError("primary timeout")
            return {
                "body": AsyncMock(
                    read=AsyncMock(
                        return_value=b'{"content": [{"text": "Fallback response"}]}'
                    )
                )
            }

        client.invoke_model.side_effect = invoke_model

        with patch("aioboto3.Session", return_value=session):
            bedrock = BedrockClient(timeout=5, retry_max=0)
            result = await bedrock.invoke_with_fallback("Hello")

        assert result == "Fallback response"
        assert call_count == 2

    async def test_generate_embedding(self, mock_bedrock):
        session, client = mock_bedrock
        client.invoke_model.return_value = {
            "body": AsyncMock(
                read=AsyncMock(
                    return_value=b'{"embedding": [0.1, 0.2, 0.3]}'
                )
            )
        }

        with patch("aioboto3.Session", return_value=session):
            bedrock = BedrockClient(timeout=5, retry_max=0)
            result = await bedrock.generate_embedding("test text")

        assert result == [0.1, 0.2, 0.3]
