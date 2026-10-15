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
