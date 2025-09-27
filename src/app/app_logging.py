from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any


class JsonFormatter(logging.Formatter):
    """Минимальный JSON-форматтер без внешних зависимостей."""

    _std_keys = set(
        logging.LogRecord(name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None).__dict__.keys()
    )

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": datetime.utcfromtimestamp(record.created).isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)

        # переносим любые extra-поля в "ctx"
        ctx = {}
        for k, v in record.__dict__.items():
            if k not in self._std_keys and not k.startswith("_"):
                try:
                    json.dumps(v)  # проверим сериализуемость
                    ctx[k] = v
                except Exception:
                    ctx[k] = str(v)
        if ctx:
            data["ctx"] = ctx

        return json.dumps(data, ensure_ascii=False)


def _parse_bool(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def setup_logger(level: str = "INFO", json_enabled: bool | None = None) -> None:
    """Инициализирует рут-логгер. Если LOG_JSON=true — включает JSON-формат."""
    if json_enabled is None:
        json_enabled = _parse_bool(os.getenv("LOG_JSON"))

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    handler = logging.StreamHandler(sys.stdout)
    if json_enabled:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(handler)
