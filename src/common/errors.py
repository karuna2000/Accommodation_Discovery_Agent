class AppError(Exception):
    def __init__(self, message: str, code: str, status: int = 500):
        self.message = message
        self.code = code
        self.status = status


class QueryBlockedError(AppError):
    def __init__(self, reason: str):
        super().__init__(f"Query blocked: {reason}", "QUERY_BLOCKED", 400)


class RateLimitError(AppError):
    def __init__(self):
        super().__init__("Rate limit exceeded", "RATE_LIMITED", 429)


class ServiceError(AppError):
    pass


class ServiceTimeoutError(ServiceError):
    def __init__(self, service: str, timeout: float):
        super().__init__(
            f"Service {service} timed out after {timeout}s",
            "SERVICE_TIMEOUT", 504,
        )


class CircuitBreakerOpenError(ServiceError):
    def __init__(self, service: str):
        super().__init__(
            f"Service {service} is temporarily unavailable",
            "CIRCUIT_OPEN", 503,
        )


class ToolExecutionError(AppError):
    def __init__(self, tool: str, detail: str):
        super().__init__(
            f"Tool {tool} failed: {detail}",
            "TOOL_ERROR", 502,
        )


class NonRetryableError(ServiceError):
    def __init__(self, service: str, reason: str):
        super().__init__(
            f"Non-retryable error from {service}: {reason}",
            "NON_RETRYABLE", 400,
        )


class IdempotencyKeyReplayedError(AppError):
    def __init__(self, key: str):
        super().__init__(
            f"Request with key {key} is still in progress",
            "IDEMPOTENCY_IN_PROGRESS", 409,
        )
