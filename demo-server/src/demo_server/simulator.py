"""운항 시뮬레이터 — 지도 위에서 선박을 움직여 V-PASS 단말에 좌표를 공급한다.

  1) 지도에서 선박을 드래그하면 그 지점의 위경도가 단말로 전달된다
  2) 항로(waypoint)를 찍으면 순서대로 일정 속력으로 이동한다
  3) 지오펜스(열린 선)를 넘어 바다 쪽으로 나가면 출항,
     바다에서 육지 쪽으로 들어오면 입항으로 판정해 단말에 명령을 내려보낸다
  4) SOS(수동/익수 자동)가 접수되면 킬 스위치로 배가 멈추므로 **항로 이동을 즉시
     중단하고 위치를 고정**한다. 다만 실제로는 정지한 배도 해류·바람에 밀리므로
     표류 벡터(drift.py)만큼은 계속 움직인다.

단말은 실측 GPS 가 잡히지 않을 때만 이 좌표를 사용한다(V-PASS telemetry 참고).
좌표 계산은 데모 해역(통영 인근) 규모에서 평면 근사로 충분하다.
"""

from __future__ import annotations

import math
import threading
import time
import uuid
from datetime import datetime

from .geo import advance, format_position

# 기본 위치: 통영 인근 (V-PASS 시뮬레이터와 동일한 홈 좌표)
HOME_LAT = 34 + 48.125 / 60
HOME_LON = 128 + 25.402 / 60
DEFAULT_SPEED_KN = 12.4
DEFAULT_TIME_SCALE = 30.0     # 시연용 배속(실시간 1x 로는 이동이 보이지 않는다)
TIME_SCALES = [1, 10, 30, 60]
MAX_EVENTS = 20
ARRIVE_EPS_NM = 0.002         # 웨이포인트 도달 판정 여유


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_plane(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    """위경도를 해리(nm) 단위 평면 좌표로 (동쪽 +x, 북쪽 +y)."""
    return (lon * math.cos(math.radians(lat0)) * 60.0, lat * 60.0)


def distance_nm(a: dict, b: dict) -> float:
    lat0 = (a["lat"] + b["lat"]) / 2
    ax, ay = _to_plane(a["lat"], a["lon"], lat0)
    bx, by = _to_plane(b["lat"], b["lon"], lat0)
    return math.hypot(bx - ax, by - ay)


def bearing_deg(a: dict, b: dict) -> float:
    lat0 = (a["lat"] + b["lat"]) / 2
    ax, ay = _to_plane(a["lat"], a["lon"], lat0)
    bx, by = _to_plane(b["lat"], b["lon"], lat0)
    return math.degrees(math.atan2(bx - ax, by - ay)) % 360


def _point(raw) -> dict | None:
    """[lat, lon] 또는 {"lat":..,"lon":..} 형태를 모두 받아들인다."""
    if isinstance(raw, dict):
        lat, lon = raw.get("lat"), raw.get("lon")
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        lat, lon = raw[0], raw[1]
    else:
        return None
    try:
        return {"lat": float(lat), "lon": float(lon)}
    except (TypeError, ValueError):
        return None


def _points(raw_list) -> list[dict]:
    if not isinstance(raw_list, (list, tuple)):
        return []
    return [p for p in (_point(r) for r in raw_list) if p is not None]


class Simulator:
    def __init__(self, store, drift_provider=None):
        self._store = store
        self._lock = threading.RLock()
        # () -> {"bearing": float, "speed_kn": float} — Runtime 이 관할 기상으로 계산
        self._drift_provider = drift_provider

        data = store.load() or {}
        self.lat = float(data.get("lat", HOME_LAT))
        self.lon = float(data.get("lon", HOME_LON))
        self.course = float(data.get("course", 245.0))
        self.speed_kn = float(data.get("speed_kn", DEFAULT_SPEED_KN))
        self.time_scale = float(data.get("time_scale", DEFAULT_TIME_SCALE))
        self.route: list[dict] = _points(data.get("route", []))
        self.fence: list[dict] = _points(data.get("fence", []))
        self.sea_side = int(data.get("sea_side", 1))
        self.port_state = data.get("port_state", "docked")
        self.events: list[dict] = list(data.get("events", []))[:MAX_EVENTS]
        self.command: dict | None = data.get("command")
        self.command_seq = int(data.get("command_seq", 0))

        self.running = False
        self.finished = bool(data.get("finished", False))
        self.target_index = int(data.get("target_index", 1))
        self.updated_at = _now()

        # SOS 위치 고정 상태
        self.sos_locked = bool(data.get("sos_locked", False))
        self.sos_info: dict | None = data.get("sos_info")
        self.drift_kn = float(data.get("drift_kn", 0.0))
        self.drift_bearing = float(data.get("drift_bearing", 0.0))
        self.drift_m = float(data.get("drift_m", 0.0))

    # ── 저장 ────────────────────────────────────────────────────────────
    def _persist(self) -> None:
        self._store.save({
            "lat": self.lat,
            "lon": self.lon,
            "course": self.course,
            "speed_kn": self.speed_kn,
            "time_scale": self.time_scale,
            "route": self.route,
            "fence": self.fence,
            "sea_side": self.sea_side,
            "port_state": self.port_state,
            "events": self.events,
            "command": self.command,
            "command_seq": self.command_seq,
            "target_index": self.target_index,
            "finished": self.finished,
            "sos_locked": self.sos_locked,
            "sos_info": self.sos_info,
            "drift_kn": self.drift_kn,
            "drift_bearing": self.drift_bearing,
            "drift_m": self.drift_m,
        })

    # ── 지오펜스 판정 ───────────────────────────────────────────────────
    def _side_of_fence(self, lat: float, lon: float) -> int:
        """가장 가까운 펜스 선분을 기준으로 어느 쪽에 있는지(+1 / -1 / 0)."""
        if len(self.fence) < 2:
            return 0
        lat0 = self.fence[0]["lat"]
        px, py = _to_plane(lat, lon, lat0)
        best_dist: float | None = None
        best_sign = 0
        for a, b in zip(self.fence, self.fence[1:]):
            ax, ay = _to_plane(a["lat"], a["lon"], lat0)
            bx, by = _to_plane(b["lat"], b["lon"], lat0)
            vx, vy = bx - ax, by - ay
            seg_len2 = vx * vx + vy * vy
            if seg_len2 <= 0:
                continue
            t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / seg_len2))
            dist = math.hypot(px - (ax + t * vx), py - (ay + t * vy))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                cross = vx * (py - ay) - vy * (px - ax)
                best_sign = 1 if cross > 0 else (-1 if cross < 0 else 0)
        return best_sign

    def _expected_port_state(self) -> str:
        side = self._side_of_fence(self.lat, self.lon)
        if side == 0:
            return self.port_state
        return "departed" if side == self.sea_side else "docked"

    def _evaluate_fence(self, emit: bool) -> None:
        """펜스 기준 현재 상태를 갱신하고, 바뀌었으면 단말 명령을 만든다."""
        state = self._expected_port_state()
        if state == self.port_state:
            return
        self.port_state = state
        if not emit:
            return
        kind = "departure" if state == "departed" else "arrival"
        self.command_seq += 1
        self.command = {
            "seq": self.command_seq,
            "kind": kind,
            "time": _now(),
            "position": format_position(self.lat, self.lon),
        }
        self.events.insert(0, {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "time": self.command["time"],
            "position": self.command["position"],
        })
        del self.events[MAX_EVENTS:]

    # ── SOS 위치 고정 / 표류 ────────────────────────────────────────────
    def lock_for_sos(self, info: dict | None = None) -> bool:
        """SOS 접수 → 항로 이동 중단 + 위치 고정. 이후 표류만 반영한다."""
        with self._lock:
            first = not self.sos_locked
            self.sos_locked = True
            self.running = False
            if info:
                self.sos_info = info
            if first:
                self.drift_m = 0.0
            self.updated_at = _now()
            self._persist()
            return first

    def release_sos(self) -> None:
        """상황 종료 → 위치 고정 해제 (운항 재개 가능)."""
        with self._lock:
            self.sos_locked = False
            self.sos_info = None
            self.drift_kn = 0.0
            self.drift_m = 0.0
            self.updated_at = _now()
            self._persist()

    def _drift_step(self, dt: float) -> None:
        """정지한 배가 해류·풍압에 밀리는 만큼만 위치를 갱신한다. (락 안에서 호출)

        지오펜스 판정은 하지 않는다 — 표류로 판정선을 넘었다고 출입항을 등록하면
        기록이 오염되기 때문이다.
        """
        vector = None
        if self._drift_provider is not None:
            try:
                vector = self._drift_provider()
            except Exception as e:
                print(f"[sim] 표류 벡터 계산 실패: {e}")
        if not vector:
            return
        speed = float(vector.get("speed_kn") or 0.0)
        bearing = float(vector.get("bearing") or 0.0)
        self.drift_kn, self.drift_bearing = speed, bearing
        if speed <= 0.0:
            return
        seconds = dt * self.time_scale
        self.lat, self.lon = advance(self.lat, self.lon, bearing, speed, seconds)
        self.course = bearing
        self.drift_m += speed * seconds / 3600.0 * 1852.0
        self.updated_at = _now()

    # ── 이동 루프 (Runtime 이 주기적으로 호출) ──────────────────────────
    def step(self, dt: float) -> None:
        with self._lock:
            if self.sos_locked:
                self._drift_step(dt)
                return
            if not self.running or len(self.route) < 2:
                return
            remaining = self.speed_kn * (dt * self.time_scale) / 3600.0
            while remaining > 0:
                if self.target_index >= len(self.route):
                    self.running = False
                    self.finished = True
                    self._persist()
                    break
                target = self.route[self.target_index]
                here = {"lat": self.lat, "lon": self.lon}
                gap = distance_nm(here, target)
                if gap <= max(remaining, ARRIVE_EPS_NM):
                    self.lat, self.lon = target["lat"], target["lon"]
                    self.target_index += 1
                    remaining -= gap
                    if self.target_index < len(self.route):
                        self.course = bearing_deg(target, self.route[self.target_index])
                    continue
                self.course = bearing_deg(here, target)
                ratio = remaining / gap
                self.lat += (target["lat"] - self.lat) * ratio
                self.lon += (target["lon"] - self.lon) * ratio
                remaining = 0.0
            self.updated_at = _now()
            self._evaluate_fence(emit=True)

    # ── 조작 ────────────────────────────────────────────────────────────
    def set_position(self, lat: float, lon: float) -> None:
        """지도에서 선박을 드래그해 놓은 위치."""
        with self._lock:
            self.lat, self.lon = float(lat), float(lon)
            self.running = False
            self.updated_at = _now()
            self._evaluate_fence(emit=True)
            self._persist()

    def set_route(self, points) -> None:
        with self._lock:
            self.route = _points(points)
            self.target_index = 1
            self.finished = False
            if not self.route:
                self.running = False
            self._persist()

    def set_fence(self, points) -> None:
        """펜스를 새로 그리면 선박이 있는 쪽을 '항내'로 보고 반대쪽을 바다로 잡는다."""
        with self._lock:
            self.fence = _points(points)
            if len(self.fence) >= 2:
                side = self._side_of_fence(self.lat, self.lon)
                self.sea_side = -side if side != 0 else 1
            self.port_state = self._expected_port_state()
            self._persist()

    def flip_sea_side(self) -> None:
        with self._lock:
            self.sea_side = -self.sea_side or 1
            self._evaluate_fence(emit=True)
            self._persist()

    def set_speed(self, speed_kn: float) -> None:
        with self._lock:
            self.speed_kn = max(0.0, min(40.0, float(speed_kn)))
            self._persist()

    def set_time_scale(self, scale: float) -> None:
        with self._lock:
            self.time_scale = max(1.0, min(120.0, float(scale)))
            self._persist()

    def run(self, action: str) -> None:
        with self._lock:
            if action == "start":
                if self.sos_locked:
                    raise ValueError(
                        "SOS 접수로 위치가 고정되어 있습니다. 신고를 종료한 뒤 다시 시도해 주세요."
                    )
                if len(self.route) < 2:
                    raise ValueError("항로 점을 2개 이상 찍어 주세요.")
                if self.finished or self.target_index >= len(self.route):
                    start = self.route[0]
                    self.lat, self.lon = start["lat"], start["lon"]
                    self.target_index = 1
                    self.finished = False
                self.running = True
            elif action == "pause":
                self.running = False
            elif action == "stop":
                self.running = False
                self.finished = False
                self.target_index = 1
                if self.route:
                    self.lat, self.lon = self.route[0]["lat"], self.route[0]["lon"]
            else:
                raise ValueError("알 수 없는 동작입니다.")
            self.updated_at = _now()
            self._evaluate_fence(emit=True)
            self._persist()

    def reset(self) -> None:
        with self._lock:
            self.route = []
            self.fence = []
            self.events = []
            self.running = False
            self.finished = False
            self.target_index = 1
            self.lat, self.lon = HOME_LAT, HOME_LON
            self.course = 245.0
            self.speed_kn = DEFAULT_SPEED_KN
            self.port_state = "docked"
            self.sos_locked = False
            self.sos_info = None
            self.drift_kn = 0.0
            self.drift_m = 0.0
            self.updated_at = _now()
            self._persist()

    # ── 조회 ────────────────────────────────────────────────────────────
    def _progress(self) -> dict:
        total = sum(distance_nm(a, b) for a, b in zip(self.route, self.route[1:]))
        done = sum(
            distance_nm(a, b)
            for a, b in zip(self.route[: self.target_index], self.route[1: self.target_index])
        )
        if 0 < self.target_index < len(self.route):
            done += distance_nm(self.route[self.target_index - 1],
                                {"lat": self.lat, "lon": self.lon})
        eta_min = None
        if self.speed_kn > 0.1 and total > done:
            eta_min = (total - done) / self.speed_kn * 60 / max(1.0, self.time_scale)
        return {
            "index": self.target_index,
            "total_nm": round(total, 2),
            "done_nm": round(min(done, total), 2),
            "percent": round(min(done / total, 1.0) * 100) if total > 0 else 0,
            "leg": min(self.target_index, max(1, len(self.route) - 1)),
            "legs": max(0, len(self.route) - 1),
            "eta_min": round(eta_min, 1) if eta_min is not None else None,
        }

    def telemetry(self) -> dict:
        # SOS 로 정지한 뒤에는 표류 속력을 그대로 단말에 보낸다 (엔진 정지 + 표류중)
        if self.running:
            speed = round(self.speed_kn, 1)
        elif self.sos_locked:
            speed = round(self.drift_kn, 2)
        else:
            speed = 0.0
        return {
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "course": round(self.course) % 360,
            "speed_kn": speed,
            "position": format_position(self.lat, self.lon),
            "updated_at": self.updated_at,
        }

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "vessel": {**self.telemetry(), "running": self.running},
                "route": list(self.route),
                "fence": list(self.fence),
                "sea_side": self.sea_side,
                "speed_kn": round(self.speed_kn, 1),
                "time_scale": self.time_scale,
                "time_scales": TIME_SCALES,
                "running": self.running,
                "finished": self.finished,
                "port_state": self.port_state,
                "progress": self._progress(),
                "events": list(self.events),
                "command_seq": self.command_seq,
                "sos": {
                    "locked": self.sos_locked,
                    "info": dict(self.sos_info) if self.sos_info else None,
                    "drift_kn": round(self.drift_kn, 2),
                    "drift_bearing": round(self.drift_bearing),
                    "drift_m": round(self.drift_m),
                },
            }

    def terminal_feed(self) -> dict:
        """V-PASS 단말이 주기적으로 받아가는 좌표 + 출입항 명령."""
        with self._lock:
            return {
                "active": True,
                "telemetry": self.telemetry(),
                # 단말이 운항 기록 간격을 배속에 맞춰 좁힐 수 있도록 함께 내려준다
                "time_scale": self.time_scale,
                "command": dict(self.command) if self.command else None,
            }
