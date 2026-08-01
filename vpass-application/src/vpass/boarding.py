"""선원 출석(승선) 관리.

출항 화면에서 얼굴 인식이 성공하면 승선 목록에 추가한다.
- 구명조끼 장치가 배정된 선원은 착용 상태여야 승선 처리된다(한국 어선 착용 의무).
- 시동 잠금 해제와 출항 신고는 여기서 하지 않는다. 선장이 승선 인원을 확인하고
  '출항 확정'을 눌렀을 때 Runtime.confirm_departure() 가 수행한다.
- 모든 승선 이력은 boarding_logs.json 에 누적 저장된다(보관 기간 1년).
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

from .config import REBOARD_MESSAGE_COOLDOWN

# 오버레이 색상 (design.pen 토큰과 동일)
COLOR_OK = "#00FFA3"
COLOR_WARN = "#FF9F0A"
COLOR_DANGER = "#FF375F"
COLOR_INFO = "#0A84FF"


class Overlay:
    """카메라 화면 위에 잠시 표시되는 안내 메시지."""

    def __init__(self, ttl: float = 2.5):
        self._lock = threading.Lock()
        self._ttl = ttl
        self._msg = {"text": "", "color": "", "timestamp": 0.0}

    def set(self, text: str, color: str) -> None:
        with self._lock:
            self._msg = {"text": text, "color": color, "timestamp": time.time()}

    def get(self) -> dict:
        with self._lock:
            if time.time() - self._msg["timestamp"] > self._ttl:
                self._msg = {"text": "", "color": "", "timestamp": 0.0}
            return {"text": self._msg["text"], "color": self._msg["color"]}


class BoardingManager:
    def __init__(self, users_store, logs_store, device_registry, engine, overlay: Overlay,
                 on_board=None):
        self._users = users_store
        self._logs = logs_store
        self._devices = device_registry
        self._engine = engine
        self._overlay = overlay
        self._on_board = on_board

        self._lock = threading.Lock()
        self._session: list[dict] = []      # [{user_id, name, phone, time, lifejacket}]
        self._boarded_ids: set[str] = set()
        self._notice_times: dict[str, float] = {}  # 중복 안내 쿨다운

    # ── 얼굴 인식 콜백 (카메라 스레드에서 호출) ─────────────────────────
    def handle_recognition(self, user: dict) -> None:
        user_id = user.get("id") or user.get("name", "")
        name = user.get("name", "")

        with self._lock:
            if user_id in self._boarded_ids:
                if self._cooldown_ok(f"re:{user_id}"):
                    self._overlay.set(f"이미 승선 확인된 선원입니다 ({name})", COLOR_WARN)
                return

            worn = self._devices.is_worn(user.get("device_id"))
            if worn is False:
                # 구명조끼 장치가 배정됐는데 미착용 → 승선 거부
                if self._cooldown_ok(f"nj:{user_id}"):
                    self._overlay.set(
                        f"{name} 님 구명조끼 미착용 · 착용 후 다시 인식해 주세요", COLOR_DANGER
                    )
                return

            now = datetime.now()
            entry = {
                "user_id": user_id,
                "name": name,
                "phone": user.get("phone", ""),
                "time": now.strftime("%H:%M:%S"),
                "lifejacket": worn,  # True(착용 확인) | None(장치 미배정)
            }
            self._session.append(entry)
            self._boarded_ids.add(user_id)

        # 파일 기록 (락 밖에서)
        self._logs.update(
            lambda logs: logs
            + [
                {
                    "date": now.strftime("%Y-%m-%d"),
                    "name": name,
                    "phone": user.get("phone", ""),
                    "time": entry["time"],
                    "lifejacket": worn,
                }
            ]
        )

        suffix = " · 구명조끼 착용 확인" if worn else ""
        self._overlay.set(f"{name} 님 승선 확인{suffix}", COLOR_OK)

        # 운항 중이라면 해당 운항의 승선 명단도 최신화한다
        if self._on_board:
            self._on_board(self.session())

    def handle_unknown(self) -> None:
        if self._cooldown_ok("unknown"):
            self._overlay.set("등록되지 않은 사람입니다", COLOR_DANGER)

    def handle_no_model(self) -> None:
        if self._cooldown_ok("nomodel"):
            self._overlay.set("등록된 사용자가 없습니다 · 사용자를 먼저 등록해 주세요", COLOR_INFO)

    def _cooldown_ok(self, key: str) -> bool:
        now = time.time()
        last = self._notice_times.get(key)
        if last is not None and now - last < REBOARD_MESSAGE_COOLDOWN:
            return False
        self._notice_times[key] = now
        return True

    def is_boarded(self, user_id: str) -> bool:
        with self._lock:
            return user_id in self._boarded_ids

    # ── 세션 관리 ────────────────────────────────────────────────────────
    def reset_session(self, relock: bool = True) -> None:
        with self._lock:
            self._session.clear()
            self._boarded_ids.clear()
            self._notice_times.clear()
        if relock:
            self._engine.lock()

    def session(self) -> list[dict]:
        with self._lock:
            return list(self._session)

    def count(self) -> int:
        with self._lock:
            return len(self._session)

    def summary(self) -> dict:
        """출항 확정 화면용 요약 (총원 / 구명조끼 착용 확인 인원)."""
        session = self.session()
        return {
            "total": len(session),
            "lifejacket_confirmed": sum(1 for e in session if e["lifejacket"]),
            "crew": session,
        }
