class SpecTraceError(Exception):
    code = "internal_error"
    status = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InputTooLarge(SpecTraceError):
    code = "input_too_large"
    status = 413


class UnsupportedInput(SpecTraceError):
    code = "unsupported_input"
    status = 415


class ParseError(SpecTraceError):
    code = "parse_error"
    status = 422


class LimitExceeded(SpecTraceError):
    code = "limit_exceeded"
    status = 422


class LLMUnavailable(SpecTraceError):
    """The language model or embedding service is not configured, not reachable, or failed."""

    code = "llm_unavailable"
    status = 503


class LLMRateLimited(SpecTraceError):
    code = "llm_rate_limited"
    status = 429


class LLMTimeout(SpecTraceError):
    code = "llm_timeout"
    status = 504


class LLMBadOutput(SpecTraceError):
    """The model answered, but not in a form the application can verify or use."""

    code = "llm_bad_output"
    status = 502


class BudgetExceeded(SpecTraceError):
    code = "budget_exceeded"
    status = 429


class OwnerRequired(SpecTraceError):
    code = "owner_required"
    status = 401
