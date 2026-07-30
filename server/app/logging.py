import json
import logging
from datetime import UTC, datetime
from typing import Any

SAFE_CONTEXT_FIELDS = (
    "component",
    "operation",
    "request_id",
    "room_id_hash",
    "player_id_hash",
    "command_type",
    "event_id",
    "ai_latency_ms",
    "ai_attempt",
    "error_code",
    "validation_error_count",
)


class JsonFormatter(logging.Formatter):
    """Emit only explicitly approved context fields as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in SAFE_CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
