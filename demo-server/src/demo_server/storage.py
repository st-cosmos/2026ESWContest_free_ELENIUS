"""JSON 파일 기반 저장소 (V-PASS 애플리케이션과 동일한 구현).

임시 파일에 먼저 쓰고 os.replace 로 원자적으로 교체한다.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path, default: Any):
        self._path = path
        self._default = default
        self._lock = threading.Lock()

    def load(self) -> Any:
        with self._lock:
            return self._read()

    def save(self, data: Any) -> None:
        with self._lock:
            self._write(data)

    def update(self, fn) -> Any:
        """load → 변형 → save 를 한 번의 락 안에서 수행한다."""
        with self._lock:
            data = self._read()
            result = fn(data)
            self._write(data if result is None else result)
            return data if result is None else result

    def _read(self) -> Any:
        if not self._path.exists():
            return json.loads(json.dumps(self._default))
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(self._default))

    def _write(self, data: Any) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._path)
