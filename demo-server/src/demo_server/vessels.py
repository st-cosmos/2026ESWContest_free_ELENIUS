"""관제 대상 선박 레지스트리.

- 수동 등록 선박(데모용 직접 입력) + V-PASS 단말에서 실시간 수집되는 선박을 함께 관리
- 출항(departed) 선박은 위치를 시뮬레이션으로 이동시켜 실시간 GPS 를 흉내 낸다
- 정렬: 출항 선박을 앞쪽에, 입항 선박을 뒤쪽에 배치
"""

from __future__ import annotations

import random
import threading
import time
import uuid
from datetime import datetime

from .config import LIVE_TIMEOUT_SEC, REGIONS
from .geo import advance, format_position

STATUS_DEPARTED = "departed"
STATUS_DOCKED = "docked"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class VesselRegistry:
    def __init__(self, store):
        self._store = store
        self._lock = threading.Lock()

    # ── 조회 ────────────────────────────────────────────────────────────
    def _public(self, v: dict) -> dict:
        live = False
        if v.get("source") == "vpass":
            live = (time.time() - v.get("last_seen_ts", 0)) < LIVE_TIMEOUT_SEC
        return {
            "id": v["id"],
            "vessel_id": v.get("vessel_id", "-"),
            "name": v.get("name", "미상"),
            "region": v.get("region", "남해"),
            "lat": round(v.get("lat", 0.0), 6),
            "lon": round(v.get("lon", 0.0), 6),
            "position": format_position(v.get("lat", 0.0), v.get("lon", 0.0)),
            "course": round(v.get("course", 0)) % 360,
            "speed_kn": round(v.get("speed_kn", 0.0), 1),
            "crew": int(v.get("crew", 0)),
            "status": v.get("status", STATUS_DOCKED),
            "source": v.get("source", "manual"),
            "live": live,
            "updated_at": v.get("updated_at", ""),
        }

    def list_public(self) -> list[dict]:
        vessels = [self._public(v) for v in self._store.load()]
        # 출항(departed) 선박을 앞쪽에, 그 안에서는 최근 갱신 순
        order = {STATUS_DEPARTED: 0, STATUS_DOCKED: 1}
        vessels.sort(key=lambda v: (order.get(v["status"], 2), v["name"]))
        return vessels

    def stats(self) -> dict:
        vessels = self._store.load()
        departed = sum(1 for v in vessels if v.get("status") == STATUS_DEPARTED)
        return {
            "total": len(vessels),
            "departed": departed,
            "docked": len(vessels) - departed,
        }

    # ── 등록/수정/삭제 (수동) ───────────────────────────────────────────
    def add(self, data: dict) -> dict:
        vessel = {
            "id": uuid.uuid4().hex[:12],
            "vessel_id": data["vessel_id"],
            "name": data["name"],
            "region": data.get("region") if data.get("region") in REGIONS else "남해",
            "lat": float(data.get("lat", 34.8)),
            "lon": float(data.get("lon", 128.42)),
            "course": float(data.get("course", 0)),
            "speed_kn": float(data.get("speed_kn", 0)),
            "crew": int(data.get("crew", 0)),
            "status": data.get("status") if data.get("status") in (STATUS_DEPARTED, STATUS_DOCKED) else STATUS_DOCKED,
            "source": "manual",
            "updated_at": _now(),
        }
        self._store.update(lambda vs: vs + [vessel])
        return self._public(vessel)

    def update(self, vessel_id: str, data: dict) -> dict | None:
        found = {}

        def _upd(vs):
            for v in vs:
                if v["id"] == vessel_id:
                    for key in ("vessel_id", "name", "region", "status"):
                        if data.get(key) is not None:
                            v[key] = data[key]
                    for key in ("lat", "lon", "course", "speed_kn"):
                        if data.get(key) is not None:
                            v[key] = float(data[key])
                    if data.get("crew") is not None:
                        v["crew"] = int(data["crew"])
                    v["updated_at"] = _now()
                    found.update(v)
            return vs

        self._store.update(_upd)
        return self._public(found) if found else None

    def delete(self, vessel_id: str) -> bool:
        before = self._store.load()
        if not any(v["id"] == vessel_id for v in before):
            return False
        self._store.update(lambda vs: [v for v in vs if v["id"] != vessel_id])
        return True

    def set_status(self, vessel_id: str, status: str) -> dict | None:
        """출항/입항 전환. 변경되면 kind('departure'|'arrival')를 함께 돌려준다."""
        if status not in (STATUS_DEPARTED, STATUS_DOCKED):
            return None
        result = {}

        def _upd(vs):
            for v in vs:
                if v["id"] == vessel_id:
                    changed = v.get("status") != status
                    v["status"] = status
                    if status == STATUS_DEPARTED and v.get("speed_kn", 0) < 1:
                        v["speed_kn"] = round(random.uniform(8.0, 13.0), 1)
                        if not v.get("course"):
                            v["course"] = round(random.uniform(0, 359))
                    elif status == STATUS_DOCKED:
                        v["speed_kn"] = 0.0
                    v["updated_at"] = _now()
                    result["vessel"] = dict(v)
                    result["changed"] = changed
            return vs

        self._store.update(_upd)
        if not result:
            return None
        v = result["vessel"]
        return {
            "vessel": self._public(v),
            "changed": result["changed"],
            "kind": "departure" if status == STATUS_DEPARTED else "arrival",
        }

    # ── V-PASS 실시간 수집 (upsert by vessel_id) ────────────────────────
    def upsert_live(self, payload: dict) -> dict:
        vid = payload.get("vessel_id") or "-"
        result = {}

        def _upd(vs):
            target = next((v for v in vs if v.get("vessel_id") == vid), None)
            if target is None:
                target = {"id": uuid.uuid4().hex[:12], "vessel_id": vid}
                vs.append(target)
            target["source"] = "vpass"
            target["name"] = payload.get("name", target.get("name", "V-PASS 선박"))
            if payload.get("region"):
                target["region"] = payload["region"]
            for key in ("lat", "lon", "course", "speed_kn"):
                if payload.get(key) is not None:
                    target[key] = float(payload[key])
            if payload.get("crew") is not None:
                target["crew"] = int(payload["crew"])
            if payload.get("status") in (STATUS_DEPARTED, STATUS_DOCKED):
                target["status"] = payload["status"]
            target["last_seen_ts"] = time.time()
            target["updated_at"] = _now()
            result.update(target)
            return vs

        self._store.update(_upd)
        return self._public(result)

    # ── 시뮬레이션: 출항 선박 위치 이동 ─────────────────────────────────
    def simulate_step(self, dt: float) -> None:
        def _upd(vs):
            moved = False
            for v in vs:
                # V-PASS 라이브 선박은 단말이 위치를 직접 보내므로 건드리지 않는다
                if v.get("source") == "vpass":
                    continue
                if v.get("status") == STATUS_DEPARTED and v.get("speed_kn", 0) > 0.1:
                    v["course"] = (v.get("course", 0) + random.uniform(-1.5, 1.5)) % 360
                    v["lat"], v["lon"] = advance(
                        v.get("lat", 34.8), v.get("lon", 128.4),
                        v["course"], v.get("speed_kn", 0), dt,
                    )
                    moved = True
            return vs if moved else None

        self._store.update(_upd)
