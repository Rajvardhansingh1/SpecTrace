import logging
import re

LOGGER_NAME = "spectrace"

# user:password@ inside any URL, and key=value / key: value pairs for credential-like names.
_URL_CREDENTIALS = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.\-]*://)[^\s/@]*:[^\s/@]*@")
_SECRET_PAIR = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization)\b(\s*[=:]\s*)\S+"
)
# Control characters would let a crafted value forge extra log lines.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def redact(text: str) -> str:
    text = _URL_CREDENTIALS.sub(r"\g<scheme>***@", text)
    text = _SECRET_PAIR.sub(r"\1\2***", text)
    return _CONTROL.sub(" ", text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def get_logger() -> logging.Logger:
    """The one application logger. Messages carry identifiers and codes, never request content."""
    logger = logging.getLogger(LOGGER_NAME)
    if not any(isinstance(f, RedactingFilter) for f in logger.filters):
        logger.addFilter(RedactingFilter())
        logger.setLevel(logging.INFO)
        if not logging.getLogger().handlers and not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
    return logger
