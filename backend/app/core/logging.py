"""JSON logs with request/job correlation. Never pass passwords, keys or page text."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            data["request_id"] = request_id
        data.update(getattr(record, "fields", None) or {})
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(level="INFO"):
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Third-party request logs would duplicate ours or include full URLs with queries.
    for noisy in ("uvicorn.access", "httpx", "httpcore", "primp", "ddgs"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def log_event(logger, event, level=logging.INFO, exc_info=False, **fields):
    logger.log(level, event, exc_info=exc_info, extra={"fields": fields})
