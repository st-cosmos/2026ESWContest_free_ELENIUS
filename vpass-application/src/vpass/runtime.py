"""애플리케이션 런타임 — 모든 매니저를 생성하고 배선한다."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime

from . import config
from .boarding import COLOR_DANGER, COLOR_OK, COLOR_WARN, BoardingManager, Overlay
from .camera import CameraManager
from .demo_bridge import DemoBridge
from .facerec import (
    detect_largest_face,
    imwrite_unicode,
    load_face_cascade,
    safe_filename,
)
from .killswitch import EngineController
from .jacketble import BleJacketScanner
from .lifejacket import DeviceRegistry
from .sos import SosManager
from .storage import JsonStore
from .telemetry import RemoteSimFeed, TelemetryRouter, create_telemetry
from .voyage import VoyageManager
from .weather import get_weather


class SimJacket:
    """하드웨어 없이 구명조끼 장치를 흉내 내는 시뮬레이터(개발/시연용).

    실제 ESP8266 장치와 동일한 경로(레지스트리 호출)로 신호를 넣는다.
    - wear/doff:  착용 토글(홀센서)
    - fall:       낙상 후 정상 복귀(ping 지속) → 오경보 아님
    - overboard:  낙상 + 신호 두절 → 익수 시나리오
    - silence:    신호만 두절(수중 전파 차단) → 익수 시나리오
    - resume:     신호 재개(구조 후)
    """

    def __init__(self, registry: DeviceRegistry, device_id: str,
                 set_battery=None, on_low_batt=None):
        self._registry = registry
        self._set_battery = set_battery    # (device_id, mv) — 표시용 배터리 주입
        self._on_low_batt = on_low_batt    # (device_id, mv) — 교체요망 경고
        self.device_id = device_id
        self.worn = False
        self.pinging = False
        self.batt_mv: int | None = None
        self._thread: threading.Thread | None = None
        self._stop = False

    def _ping_loop(self) -> None:
        while not self._stop and self.worn:
            if self.pinging:
                self._registry.ping(self.device_id)
            time.sleep(config.PING_INTERVAL)

    def apply(self, action: str) -> None:
        if action == "wear":
            self.worn = True
            self.pinging = True
            self._registry.set_wearing(self.device_id, True)
            self._registry.ping(self.device_id)
            # 교체요망 배터리 상태로 착용하면 경고 (BLE 경로와 동일 동작)
            if (self.batt_mv and self.batt_mv < config.JACKET_BATT_WARN_MV
                    and self._on_low_batt):
                self._on_low_batt(self.device_id, self.batt_mv)
            if self._thread is None or not self._thread.is_alive():
                self._stop = False
                self._thread = threading.Thread(target=self._ping_loop, daemon=True)
                self._thread.start()
        elif action == "doff":
            self.worn = False
            self.pinging = False
            self._registry.set_wearing(self.device_id, False)
        elif action == "fall":
            self._registry.fall(self.device_id, 3.2)
            self._registry.ping(self.device_id)  # 펌웨어와 동일: 낙상 직후 ping
        elif action == "overboard":
            self._registry.fall(self.device_id, 4.8)
            self.pinging = False
        elif action == "silence":
            self.pinging = False
        elif action == "resume":
            self.pinging = True
            self._registry.ping(self.device_id)
        elif action == "lowbatt":
            # 배터리 교체요망 상태 주입 (BLE 장치의 저전압 플래그와 동일 경로)
            self.batt_mv = 2100
            if self._set_battery:
                self._set_battery(self.device_id, self.batt_mv)
            if self.worn and self._on_low_batt:
                self._on_low_batt(self.device_id, self.batt_mv)
        elif action == "battok":
            self.batt_mv = 3300
            if self._set_battery:
                self._set_battery(self.device_id, self.batt_mv)
        else:
            raise ValueError(f"알 수 없는 동작: {action}")

    def snapshot(self) -> dict:
        return {"device": self.device_id, "worn": self.worn, "pinging": self.pinging}


class Runtime:
    def __init__(self):
        config.ensure_dirs()

        # 저장소
        self.users_store = JsonStore(config.USERS_FILE, [])
        self.boarding_logs_store = JsonStore(config.BOARDING_LOGS_FILE, [])
        self.voyages_store = JsonStore(config.VOYAGES_FILE, [])
        self.vessel_store = JsonStore(config.VESSEL_FILE, None)

        # 코어 상태
        self.overlay = Overlay()
        # 실측 GPS 우선, 미수신일 때만 데모 서버 시뮬레이터 좌표를 사용한다
        self.sim_feed = RemoteSimFeed()
        self.telemetry = TelemetryRouter(create_telemetry(), self.sim_feed)
        self.engine = EngineController()
        # 운항 중 구명조끼 해제(버클 풀림) 경고 — UI 모달용, 폴링으로 노출
        self.jacket_doff_alert: dict | None = None
        # 배터리 교체요망 상태로 착용 감지 시 경고 — UI 모달용
        self.jacket_batt_alert: dict | None = None
        self.devices = DeviceRegistry(
            on_mob=self._handle_mob, on_wearing=self._handle_wearing_change
        )
        # BLE 구명조끼 수신기 (nRF52840 펌웨어) — 광고 패킷을 레지스트리로 변환
        self.jacket_ble = BleJacketScanner(
            self.devices, on_low_batt=self._handle_low_batt
        )
        self.sos = SosManager(self.telemetry, self.vessel_store)
        self.boarding = BoardingManager(
            self.users_store, self.boarding_logs_store,
            self.devices, self.engine, self.overlay,
            # VoyageManager 는 아래에서 생성되므로 지연 호출로 연결한다
            on_board=lambda crew: self.voyage.sync_active_crew(),
            arrival_epoch=lambda: self.voyage.arrival_epoch(),
        )
        self.camera = CameraManager(self.users_store, self.boarding, config.APP_DIR)
        self.voyage = VoyageManager(
            self.voyages_store, self.telemetry, self.overlay,
            crew_provider=self.boarding.session,
            on_depart=self._handle_departure,
            on_arrive=self._handle_arrival,
        )

        # 시뮬레이터 (개발/시연용)
        self.sim_jackets: dict[str, SimJacket] = {}

        # 데모 관제 서버 연동 (선택)
        self.demo: DemoBridge | None = None
        if config.DEMO_SERVER_URL:
            self.demo = DemoBridge(
                config.DEMO_SERVER_URL, self._demo_vessel_payload,
                sim_feed=self.sim_feed,
                on_port_command=self._handle_port_command,
                on_engine_command=self._handle_engine_command,
            )

        # 엔진이 차단되면 배는 반드시 멈춘다
        self.engine.on_change(self._on_engine_change)

    # ── 수명 주기 ────────────────────────────────────────────────────────
    def start(self) -> None:
        self.telemetry.start()
        self.devices.start()
        self.jacket_ble.start()
        self.camera.start()
        self.voyage.start()
        if self.demo:
            self.demo.start()

    def stop(self) -> None:
        if self.demo:
            self.demo.stop()
        self.voyage.stop()
        self.camera.stop()
        self.jacket_ble.stop()
        self.devices.stop()
        self.telemetry.stop()

    # ── 이벤트 배선 ─────────────────────────────────────────────────────
    def _on_engine_change(self, engine_snap: dict) -> None:
        if engine_snap["engaged"]:
            self.telemetry.set_cruising(False)
        elif not engine_snap["locked"] and not engine_snap["killed"]:
            # 시동 잠금 해제 → (시연) 자동으로 출항 항해 시작
            self.telemetry.set_cruising(True)

    def _handle_mob(self, device_snap: dict) -> None:
        """익수 감지: 킬 스위치 작동 + SOS 자동 발보."""
        device_id = device_snap["device"]
        user = self.resolve_device_user(device_id)
        who = f"{user['name']} 님" if user else f"장치 {device_id}"
        cause_txt = (
            "낙상 후 신호 두절" if device_snap["mob_cause"] == "fall" else "무선 신호 두절"
        )
        self.engine.kill(f"익수 감지 — {who} ({cause_txt})")
        report = self.sos.trigger("mob", detail=f"{who} 익수 의심 ({cause_txt})")
        self._report_to_demo(report)
        self.overlay.set(f"⚠ 익수 감지! {who} — 엔진 비상 정지", COLOR_DANGER)
        print(f"[MOB] {who} 익수 감지 → 킬 스위치 작동 + SOS 발보")

    def _handle_wearing_change(self, device_id: str, worn: bool) -> None:
        """운항 중 구명조끼 해제(버클 풀림) 경고 관리.

        - 운항 중 착용 → 해제 전환: 경고 발생 (UI 가 state 폴링으로 모달 표시)
        - 같은 장치를 다시 착용하면 경고 자동 해제
        - 정박 중 탈의는 정상 동작이라 무시한다
        """
        if worn:
            alert = self.jacket_doff_alert
            if alert and alert["device"] == device_id:
                self.jacket_doff_alert = None
            return
        # 탈의 = 배터리 교체 중일 수 있으니 해당 장치의 배터리 경고는 해제
        if self.jacket_batt_alert and self.jacket_batt_alert["device"] == device_id:
            self.jacket_batt_alert = None
        if self.voyage.active_voyage() is None:
            return
        user = self.resolve_device_user(device_id)
        who = f"{user['name']} 님" if user else f"장치 {device_id}"
        self.jacket_doff_alert = {
            "device": device_id,
            "who": who,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        self.overlay.set(f"⚠ 운항 중 구명조끼 해제 감지 · {who}", COLOR_DANGER)
        # 주의: 콘솔 로그는 cp949(Windows) 안전 문자만 사용
        print(f"[jacket] 운항 중 구명조끼 해제 감지: {who} ({device_id})")

    def ack_jacket_alert(self) -> None:
        """구명조끼 해제 경고 확인(모달 닫기)."""
        self.jacket_doff_alert = None

    def _handle_low_batt(self, device_id: str, batt_mv: int) -> None:
        """배터리 교체요망 상태로 착용 감지 → 경고 (착용 세션당 1회)."""
        user = self.resolve_device_user(device_id)
        who = f"{user['name']} 님" if user else f"장치 {device_id}"
        self.jacket_batt_alert = {
            "device": device_id,
            "who": who,
            "batt_mv": batt_mv,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        self.overlay.set(
            f"구명조끼 배터리 교체 필요 · {who} ({batt_mv / 1000:.2f}V)", COLOR_WARN
        )
        print(f"[jacket] 배터리 교체요망 착용 감지: {who} ({device_id}, {batt_mv}mV)")

    def ack_jacket_batt_alert(self) -> None:
        """배터리 교체 경고 확인(모달 닫기)."""
        self.jacket_batt_alert = None

    def _handle_departure(self, voyage: dict) -> None:
        """출항: 데모 관제 서버에 출항 이벤트 전송."""
        self._port_to_demo("departure", voyage["departed_at"])

    def _handle_arrival(self, voyage: dict) -> None:
        """입항: 시동 재잠금 + 승선 세션 초기화 + 데모 관제 서버 통보."""
        self.boarding.reset_session(relock=True)
        self.jacket_doff_alert = None  # 입항 후 탈의는 정상
        self._port_to_demo("arrival", voyage.get("arrived_at") or "")

    # ── 데모 관제 서버 전송 헬퍼 ────────────────────────────────────────
    def _demo_vessel_payload(self) -> dict | None:
        vessel = self.vessel_store.load()
        if not vessel:
            return None
        tel = self.telemetry.snapshot()
        active = self.voyage.active_voyage() is not None
        return {
            "vessel_id": vessel.get("vessel_id", "-"),
            "name": vessel.get("name", "V-PASS 선박"),
            "region": vessel.get("region"),
            "lat": tel["lat"],
            "lon": tel["lon"],
            "course": tel["course"],
            "speed_kn": tel["speed_kn"],
            "crew": len(self.boarding.session()),
            "status": "departed" if active else "docked",
            # 관제 서버가 '이 단말이 실측 GPS 를 쓰는지'를 알 수 있게 함께 보낸다
            "gps_source": tel["source"],
        }

    def _report_to_demo(self, report: dict) -> None:
        if self.demo:
            vessel = self.vessel_store.load() or {}
            self.demo.push_report(report, region=vessel.get("region"))

    def _port_to_demo(self, kind: str, time_str: str) -> None:
        if self.demo:
            vessel = self.vessel_store.load() or {}
            self.demo.push_port(
                kind, vessel.get("name", "V-PASS 선박"),
                vessel.get("vessel_id", "-"), time_str,
            )

    # ── 시동 허용 / 출항 / 입항 ─────────────────────────────────────────
    def allow_engine_start(self) -> dict:
        """승선 인원을 확인하고 시동을 켤 수 있는 상태로 만든다.

        출항 신고는 여기서 하지 않는다. 출항/입항은 데모 관제 서버의 지오펜스
        판정으로 자동 등록된다(_handle_port_command).
        """
        session = self.boarding.session()
        if not session:
            raise ValueError("승선한 선원이 없습니다. 얼굴 인식으로 승선을 먼저 진행해 주세요.")
        if self.engine.snapshot()["killed"]:
            raise ValueError("비상 정지 상태입니다. SOS 상황 확인 후 다시 시도해 주세요.")

        self.engine.unlock()
        self.overlay.set("승선 확인 완료 · 시동 허용", COLOR_OK)
        return {"crew": len(session)}

    def _handle_port_command(self, kind: str) -> None:
        """지오펜스 판정 결과(데모 관제 서버 → 단말)를 운항 기록에 반영한다."""
        try:
            if kind == "departure":
                if self.voyage.active_voyage() is None:
                    self.voyage.start_voyage()
                    print("[geofence] 지오펜스 통과 → 자동 출항 등록")
            elif kind == "arrival":
                if self.voyage.active_voyage() is not None:
                    self.confirm_arrival()
                    print("[geofence] 지오펜스 진입 → 자동 입항 등록")
        except Exception as e:
            print(f"[geofence] 출입항 처리 실패: {e}")

    def _handle_engine_command(self, action: str) -> None:
        """킬 스위치 원격 명령(데모 관제 서버 → 단말)을 엔진에 반영한다.

        EngineController 가 상태 변경 시 GPIO/BLE 출력까지 함께 밀어내므로
        여기서는 kill/restore 만 호출하면 킬 스위치 펌웨어까지 전달된다.
        """
        try:
            if action == "kill":
                if not self.engine.snapshot()["killed"]:
                    self.engine.kill("관제 센터 원격 차단")
                    self.overlay.set("⚠ 관제 센터 원격 차단 — 엔진 비상 정지", COLOR_DANGER)
                    print("[killswitch] 관제 센터 원격 차단 명령 수신")
            elif action == "restore":
                if self.engine.snapshot()["killed"]:
                    self.engine.restore()
                    self.overlay.set("관제 센터 차단 해제 — 엔진 복구", COLOR_OK)
                    print("[killswitch] 관제 센터 차단 해제 명령 수신")
        except Exception as e:
            print(f"[killswitch] 원격 명령 처리 실패: {e}")

    def confirm_departure(self) -> dict:
        """수동 출항 신고 (지오펜스를 쓰지 않는 환경용 대체 경로)."""
        if self.voyage.active_voyage() is not None:
            raise ValueError("이미 운항 중입니다.")
        if self.engine.snapshot()["killed"]:
            raise ValueError("비상 정지 상태입니다. SOS 상황 확인 후 다시 시도해 주세요.")
        return self.voyage.start_voyage()

    def confirm_arrival(self) -> dict:
        """입항을 확정한다. 시동 재잠금과 승선 세션 초기화가 뒤따른다."""
        if self.voyage.active_voyage() is None:
            raise ValueError("진행 중인 운항이 없습니다.")
        self.telemetry.set_cruising(False)
        voyage = self.voyage.end_voyage()
        if voyage is None:
            raise ValueError("입항 처리에 실패했습니다.")
        return voyage

    # ── SOS ─────────────────────────────────────────────────────────────
    def trigger_sos_manual(self) -> dict:
        report = self.sos.trigger("manual", detail="선내 SOS 버튼")
        self._report_to_demo(report)
        return report

    def ack_sos(self) -> None:
        """상황 확인: SOS 해제 + 익수 래치 해제 + 엔진 복구."""
        self.sos.ack()
        self.devices.ack()
        if self.engine.snapshot()["killed"]:
            self.engine.restore()
            # 복구 후에도 자동 재출발은 하지 않는다 (구조 상황 고려)
            self.telemetry.set_cruising(False)

    # ── 사용자 관리 ─────────────────────────────────────────────────────
    def register_user(self, name: str, phone: str, device_id: str | None = None) -> dict:
        frame = self.camera.get_register_frame()
        if frame is None:
            raise ValueError("카메라 프레임을 읽을 수 없습니다. 카메라 연결을 확인해 주세요.")

        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # 카메라 스레드의 cascade 를 공유하면 detectMultiScale 이 경합한다 — 요청 전용 인스턴스 사용
        box = detect_largest_face(load_face_cascade(), gray)
        if box is None:
            raise ValueError("얼굴이 감지되지 않았습니다. 카메라 정면을 응시해 주세요.")

        x, y, w, h = box
        h_img, w_img = frame.shape[:2]
        pad_x, pad_y = int(w * 0.1), int(h * 0.1)
        face_img = frame[
            max(0, y - pad_y):min(h_img, y + h + pad_y),
            max(0, x - pad_x):min(w_img, x + w + pad_x),
        ]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_filename(name)}_{timestamp}.jpg"
        saved_path = config.FACES_DIR / filename
        if not imwrite_unicode(saved_path, face_img):
            raise ValueError("사진 저장에 실패했습니다.")

        record = {
            "id": uuid.uuid4().hex[:12],
            "name": name,
            "phone": phone,
            "device_id": device_id or None,
            "photo": saved_path.relative_to(config.APP_DIR).as_posix(),
            "registered_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.users_store.update(lambda users: users + [record])
        self.camera.train_model()
        return record

    def delete_user(self, user_id: str) -> dict:
        users = self.users_store.load()
        target = next((u for u in users if u.get("id") == user_id), None)
        if target is None:
            raise KeyError("삭제하려는 사용자를 찾을 수 없습니다.")

        photo_rel = target.get("photo")
        if photo_rel:
            photo_path = config.APP_DIR / photo_rel
            if photo_path.exists():
                try:
                    photo_path.unlink()
                except OSError:
                    pass

        self.users_store.update(
            lambda us: [u for u in us if u.get("id") != user_id]
        )
        self.camera.train_model()
        return target

    def resolve_device_user(self, device_id: str) -> dict | None:
        """장치를 착용한 선원을 해석한다 (익수 알림 · 구명조끼 모니터 표시용).

        이번 승선 세션의 동적 매칭(승선 스캔 시 장치-선원 연결)을 우선 사용하고,
        없으면 사용자 등록의 고정 배정 필드로 폴백한다.
        """
        session_user = self.boarding.device_user(device_id)
        if session_user is not None:
            return session_user
        for u in self.users_store.load():
            if u.get("device_id") == device_id:
                return u
        return None

    # ── 시뮬레이터 ──────────────────────────────────────────────────────
    def sim_jacket(self, device_id: str) -> SimJacket:
        if device_id not in self.sim_jackets:
            self.sim_jackets[device_id] = SimJacket(
                self.devices, device_id,
                set_battery=self.jacket_ble.sim_battery,
                on_low_batt=self._handle_low_batt,
            )
        return self.sim_jackets[device_id]

    # ── 통합 상태 (UI 1초 폴링용) ───────────────────────────────────────
    def state_snapshot(self) -> dict:
        session = self.boarding.session()
        devices = self.devices.snapshot()
        for d in devices:
            user = self.resolve_device_user(d["device"])
            d["user_name"] = user["name"] if user else None
            # BLE 광고(또는 시뮬레이터)로 수신한 배터리 상태를 합친다
            batt = self.jacket_ble.battery_info(d["device"])
            d["battery_mv"] = batt["mv"] if batt else None
            d["battery_low"] = batt["low"] if batt else False

        active_voyage = self.voyage.active_voyage()
        latest = self.voyage.latest_summary()

        return {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "telemetry": self.telemetry.snapshot(),
            "vessel": self.vessel_store.load(),
            "engine": self.engine.snapshot(),
            "camera_ok": self.camera.camera_ok,
            "camera_mode": self.camera.mode,
            "overlay": self.overlay.get(),
            "boarding": {
                "count": len(session),
                "session": session,
            },
            "lifejacket": {
                "devices": devices,
                "worn_count": self.devices.worn_count(),
                "mob_alarm": self.devices.any_mob(),
                "doff_alert": self.jacket_doff_alert,
                "batt_alert": self.jacket_batt_alert,
                "ble": self.jacket_ble.snapshot(),
            },
            "voyage": {
                "active": active_voyage is not None,
                "current_id": active_voyage["id"] if active_voyage else None,
                "departed_at": active_voyage["departed_at"] if active_voyage else None,
                "latest": latest,
                "last_report": self.voyage.last_report,
            },
            "sos": self.sos.active(),
            "weather": self._weather_snapshot(),
            "platform": {
                "raspberry_pi": config.IS_RASPBERRY_PI,
            },
        }

    def _weather_snapshot(self) -> dict:
        """기본 시뮬레이션 기상에 데모 관제 서버의 관할 기상을 덮어쓴다.

        데모 서버에서 관할 기상을 '흐림' 등으로 바꾸면 V-PASS 에도 자동 반영된다.
        """
        weather = get_weather()
        if self.demo:
            demo = self.demo.cached_weather()
            if demo and demo.get("condition"):
                weather["condition"] = demo["condition"]
                for key in (
                    "temp_c",
                    "wind",
                    # 풍향·풍속·해류는 관제 서버의 표류 예측과 같은 입력값이라
                    # 개별 필드까지 그대로 받아 화면에 같은 수치를 보여준다
                    "wind_dir",
                    "wind_speed_ms",
                    "gust_ms",
                    "current_dir",
                    "current_kn",
                    "wave_height_m",
                    "water_temp_c",
                    "advisory",
                    "precip_prob",
                    "updated_at",
                ):
                    if demo.get(key) is not None:
                        weather[key] = demo[key]
                weather["source"] = "데모 관제 서버"
        return weather
