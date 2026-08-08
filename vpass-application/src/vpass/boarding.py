"""선원 출석(승선) 관리.

출항 화면에서 얼굴 인식이 성공하면 승선 목록에 추가한다.
- 구명조끼 착용은 두 신호를 **모두** 만족해야 인정한다(착용 의무 + 치팅 방지).
  1) 카메라 시각 확인(jacketvision) — 얼굴 아래 상체에서 조끼가 보여야 한다
  2) 모듈(홀센서) 착용 신호 — 스캔 시점에 아직 아무에게도 매칭되지 않은
     착용 장치를 그 선원에게 매칭한다(장치-선원 동적 매칭).
  모듈 신호만 믿으면 조끼를 입지 않은 채 버클만 채우는 치팅이 가능하고,
  카메라만 믿으면 색상 위장이 가능하므로 둘을 교차 확인한다.
- 동적 매칭은 '착용 직후 스캔' 순서를 전제로 하며, 여러 명이 미리 착용해
  두는 등 순서가 어긋나는 경우의 예외 처리는 추후 보강한다.
- 승선 세션은 한 항차(출항~입항) 단위다. 입항하면 초기화되고, 입항이 다른 경로로
  처리돼 명단이 남아 있어도 다음 인식 때 새 항차로 보고 비운다(_sync_session_epoch).
  그래서 입항 이력이 있어도 다음 출항에서는 다시 환영 인사와 함께 승선한다.
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
                 on_board=None, arrival_epoch=None):
        self._users = users_store
        self._logs = logs_store
        self._devices = device_registry
        self._engine = engine
        self._overlay = overlay
        self._on_board = on_board
        self._arrival_epoch = arrival_epoch  # () -> int (VoyageManager.arrival_epoch)

        self._lock = threading.Lock()
        self._session: list[dict] = []      # [{user_id, name, phone, time, device_id, ...}]
        self._boarded_ids: set[str] = set()
        self._claimed_devices: set[str] = set()    # 이번 세션에서 매칭이 끝난 장치
        self._notice_times: dict[str, float] = {}  # 중복 안내 쿨다운
        self._session_epoch: int | None = None     # 이 세션이 시작된 시점의 입항 횟수

    # ── 얼굴 인식 콜백 (카메라 스레드에서 호출) ─────────────────────────
    def handle_recognition(self, user: dict, jacket_check: dict | None = None) -> None:
        """얼굴 인식된 선원의 승선을 처리한다.

        구명조끼 착용은 두 관문을 모두 통과해야 인정한다.
          1) 카메라 시각 확인 — jacket_check(jacketvision.assess_jacket 결과).
             None 이면 시각 확인이 꺼진 것(config)으로 보고 이 관문만 건너뛴다.
          2) 모듈 착용 신호 — 미매칭 착용 장치를 이 선원에게 동적으로 매칭한다.
        """
        user_id = user.get("id") or user.get("name", "")
        name = user.get("name", "")

        with self._lock:
            # 지난 항차(입항 완료)의 명단이 남아 있으면 새 승선 세션으로 시작한다
            self._sync_session_epoch()

            if user_id in self._boarded_ids:
                if self._cooldown_ok(f"re:{user_id}"):
                    self._overlay.set(f"이미 승선 확인된 선원입니다 ({name})", COLOR_WARN)
                return

            # 1) 카메라 시각 확인 — 조끼가 화면에서 보여야 한다
            visual = None if jacket_check is None else jacket_check.get("visible")
            if jacket_check is not None and visual is not True:
                if visual is None:
                    # 상체가 화면 밖 — 판단 불가 상태로 통과시키면 치팅 구멍이 된다
                    if self._cooldown_ok(f"jr:{user_id}"):
                        self._overlay.set(
                            f"{name} 님 구명조끼 확인 불가 · 상체가 화면에 나오게 서 주세요",
                            COLOR_WARN,
                        )
                elif self._cooldown_ok(f"jv:{user_id}"):
                    self._overlay.set(
                        f"{name} 님 구명조끼가 카메라에 확인되지 않습니다 · 착용 후 다시 인식해 주세요",
                        COLOR_DANGER,
                    )
                return
            jacket_visual = True if visual is True else None

            # 2) 모듈 착용 신호 — 시각 확인을 통과한 뒤에만 장치를 매칭(소모)한다
            device = self._claim_device()
            if device is None:
                if self._cooldown_ok(f"nd:{user_id}"):
                    self._overlay.set(
                        f"{name} 님 구명조끼 착용 신호가 없습니다 · 착용 후 다시 인식해 주세요",
                        COLOR_DANGER,
                    )
                return

            now = datetime.now()
            entry = {
                "user_id": user_id,
                "name": name,
                "phone": user.get("phone", ""),
                "time": now.strftime("%H:%M:%S"),
                "device_id": device,             # 이번 승선에서 매칭된 구명조끼 장치
                "lifejacket": True,              # 모듈 착용 신호 확인됨
                "jacket_visual": jacket_visual,  # True(카메라 확인) | None(시각 확인 꺼짐)
            }
            self._session.append(entry)
            self._boarded_ids.add(user_id)
            # 카메라는 같은 얼굴을 초당 여러 번 다시 인식한다. 재안내 쿨다운을 지금
            # 시작해 두지 않으면 환영 인사가 곧바로 '이미 승선 확인된 선원입니다'로
            # 덮여, 승선에 성공해도 경고 문구만 계속 보이게 된다.
            self._notice_times[f"re:{user_id}"] = time.time()

        # 파일 기록 (락 밖에서)
        self._logs.update(
            lambda logs: logs
            + [
                {
                    "date": now.strftime("%Y-%m-%d"),
                    "name": name,
                    "phone": user.get("phone", ""),
                    "time": entry["time"],
                    "device_id": device,
                    "lifejacket": True,
                    "jacket_visual": jacket_visual,
                }
            ]
        )

        checked = "모듈·카메라" if jacket_visual else "모듈"
        self._overlay.set(f"{name} 님 환영합니다 · 승선 확인(구명조끼 {checked})", COLOR_OK)

        # 운항 중이라면 해당 운항의 승선 명단도 최신화한다
        if self._on_board:
            self._on_board(self.session())

    def _sync_session_epoch(self) -> None:
        """입항 이후 첫 인식이면 지난 항차의 승선 세션을 비운다. (락 안에서 호출)

        입항하면 Runtime 이 세션을 초기화하지만(_handle_arrival), 입항이 다른 경로로
        처리되면 지난 항차의 명단이 남아 다음 출항 때 '이미 승선 확인된 선원입니다'
        안내만 반복된다. 마지막 입항 횟수가 세션 시작 시점과 달라졌으면 새 항차로
        보고 명단을 비워, 다시 환영 인사와 함께 승선하도록 한다.
        """
        epoch = self._arrival_epoch() if self._arrival_epoch else None
        if not self._session:
            self._session_epoch = epoch  # 새 세션은 지금의 입항 상태를 기준으로 시작
        elif epoch != self._session_epoch:
            self._clear_session()
            self._session_epoch = epoch

    def _clear_session(self) -> None:
        """승선 명단·매칭·안내 쿨다운을 비운다. (락 안에서 호출)"""
        self._session.clear()
        self._boarded_ids.clear()
        self._claimed_devices.clear()
        self._notice_times.clear()

    def _claim_device(self) -> str | None:
        """미매칭 착용 장치 중 가장 최근에 착용된 장치를 이 선원 몫으로 선점한다.

        '착용 직후 스캔' 순서를 전제로 한 동적 매칭이다. 여러 명이 미리 착용해
        둔 경우의 오매칭 예외 처리는 추후 보강한다. (호출자가 락을 잡고 있어야 함)
        """
        candidates = [
            d for d in self._devices.worn_devices()
            if d["device"] not in self._claimed_devices
        ]
        if not candidates:
            return None
        newest = max(candidates, key=lambda d: d["worn_since"] or 0)
        self._claimed_devices.add(newest["device"])
        return newest["device"]

    def device_user(self, device_id: str) -> dict | None:
        """이번 승선 세션에서 device_id 를 매칭받은 선원 항목(없으면 None)."""
        with self._lock:
            for e in self._session:
                if e.get("device_id") == device_id:
                    return dict(e)
        return None

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
            self._clear_session()
            self._session_epoch = None  # 다음 인식 때 현재 입항 상태로 다시 잡는다
        if relock:
            self._engine.lock()

    def session(self) -> list[dict]:
        with self._lock:
            return list(self._session)

    def count(self) -> int:
        with self._lock:
            return len(self._session)

    def summary(self) -> dict:
        """출항 확정 화면용 요약 (총원 / 구명조끼 확인 인원)."""
        session = self.session()
        return {
            "total": len(session),
            "lifejacket_confirmed": sum(
                1 for e in session if e["lifejacket"] or e.get("jacket_visual")
            ),
            "crew": session,
        }
