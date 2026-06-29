from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    es_host: str = "elasticsearch"
    es_port: int = 9200
    es_index_prefix: str = "properties"

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_cache_ttl: int = 86400
    redis_cache_threshold: float = 0.90

    brave_api_key: str = ""
    firecrawl_api_key: str = ""

    agent_max_iterations: int = 5
    agent_max_tool_calls: int = 20

    rate_limit_per_minute: int = 100

    idempotency_ttl: int = 86400

    brave_cb_failure_threshold: int = 5
    brave_cb_recovery_timeout: float = 30.0
    firecrawl_cb_failure_threshold: int = 5
    firecrawl_cb_recovery_timeout: float = 60.0
    bedrock_cb_failure_threshold: int = 3
    bedrock_cb_recovery_timeout: float = 60.0
    es_cb_failure_threshold: int = 3
    es_cb_recovery_timeout: float = 10.0
    redis_cb_failure_threshold: int = 3
    redis_cb_recovery_timeout: float = 10.0

    brave_timeout: float = 10.0
    firecrawl_timeout: float = 30.0
    bedrock_timeout: float = 60.0
    titan_timeout: float = 15.0
    es_timeout: float = 5.0
    redis_timeout: float = 2.0

    brave_max_concurrent: int = 2
    firecrawl_max_concurrent: int = 3
    bedrock_max_concurrent: int = 1

    model_config = SettingsConfigDict(env_file=".env")
