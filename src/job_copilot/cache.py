import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .logging_config import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class CacheKey:
    namespace: str
    payload: dict[str, Any]

    def digest(self) -> str:
        raw = json.dumps(
            {"namespace": self.namespace, "payload": self.payload},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, path: Path, enabled: bool = True) -> None:
        self.path = path
        self.enabled = enabled
        self._lock = threading.Lock()

    def get(self, key: CacheKey) -> str | None:
        if not self.enabled:
            return None
        with self._lock:
            data = self._read()
            value = data.get(key.digest())
            return str(value) if value is not None else None

    def set(self, key: CacheKey, value: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            data = self._read()
            data[key.digest()] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring unreadable response cache %s: %s", self.path, exc)
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): str(value) for key, value in data.items()}
