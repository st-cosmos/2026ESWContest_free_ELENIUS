"""카메라 매니저.

백그라운드 스레드에서 프레임을 읽어 모드별로 처리한다.
  - idle:     대기 — 카메라 장치를 닫아 절전한다 (발열 저감)
  - scan:     출항 화면 — 얼굴 인식 + 구명조끼 시각 확인 → BoardingManager 에 전달
  - register: 등록 화면 — 얼굴 가이드 박스만 표시, 원본 프레임 보관

카메라는 scan/register 모드에서만 열리고, idle 로 돌아오면 해제된다.
얼굴 검출은 DETECT_EVERY_N_FRAMES 프레임마다 1회만 수행한다.
인식은 facerec 엔진(SFace, 없으면 LBPH)에 맡기고, 연속 검출의 시간 투표로
확정된 사람만 BoardingManager 에 넘긴다. 등록 모드에서는 얼굴이 보이는 동안
샘플 프레임을 모아 두어 다중 샘플 등록에 쓴다.

구명조끼 자세 검증(JACKET_TURN_CHECK): 얼굴 인식이 확정되면 바로 승선 처리하지
않고 jacketturn.TurnVerifier 로 넘긴다 — 정면에서 조끼(가슴+어깨)를 확인하고,
몸을 한쪽으로 돌린 옆모습에서도 조끼가 보여야 BoardingManager 에 넘긴다.
검증 중에는 얼굴 박스 연속성으로 같은 사람임을 유지하고 신원 투표는 쉰다
(옆모습은 인식률이 낮으므로). 랜드마크가 없는 LBPH 엔진에서는 건너뛴다.

카메라가 없는 개발 환경에서도 서버는 정상 동작하며 안내 프레임을 송출한다.
"""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from .config import (
    CAMERA_INDEX,
    DETECT_EVERY_N_FRAMES,
    JACKET_CAPTURE_DIR,
    JACKET_CAPTURE_ENABLED,
    JACKET_CAPTURE_INTERVAL,
    JACKET_SHOULDER_CHECK,
    JACKET_TURN_CHECK,
    JACKET_VISION_ENABLED,
    FACE_ENROLL_SAMPLE_INTERVAL,
    FACE_ENROLL_SAMPLES,
    FACE_VOTE_NEED,
    FACE_VOTE_SECONDS,
    FACE_VOTE_WINDOW,
)
from .facerec import Gallery, Match, RecognitionVoter, create_engine
from .jacketturn import TurnVerifier
from .jacketvision import assess_jacket, assess_shoulders, assess_side_profile

# 자세 검증 실패 뒤 같은 사람을 다시 검증하기까지 두는 간격(초) — 실패 안내가 읽히게
TURN_RETRY_HOLD_SEC = 2.0

GREEN = (163, 255, 0)   # BGR
RED = (95, 55, 255)
YELLOW = (255, 240, 0)
WHITE = (255, 255, 255)


class CameraManager:
    def __init__(self, users_store, boarding, base_dir):
        self._users_store = users_store
        self._boarding = boarding
        self._base_dir = base_dir

        self.lock = threading.Lock()
        self.mode = "idle"
        self.latest_frame = None          # 송출용(주석 포함)
        self.raw_register_frame = None    # 등록 촬영용 원본
        self.camera_ok = False

        # 엔진과 갤러리는 train_model() 이 새 인스턴스로 만들어 lock 아래서 교체한다.
        # cv2 검출기/인식기는 스레드 공유가 안전하지 않아 카메라 스레드만 사용한다.
        self._engine = None
        self._gallery = Gallery()
        self.engine_name = "-"
        self._voter = RecognitionVoter(FACE_VOTE_WINDOW, FACE_VOTE_NEED, FACE_VOTE_SECONDS)
        self._last_face_seen = 0.0
        self._register_samples: list[tuple[float, np.ndarray]] = []  # (시각, 원본 프레임)
        self._last_sample = 0.0

        self._cap = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_open_try = 0.0

        # 검출 스로틀 상태 (카메라 스레드 전용)
        self._frame_no = 0
        self._scan_note = None      # 마지막 검출 주석: (box, color, tag, thickness)
        self._jacket_note = None    # 마지막 구명조끼 확인 주석: (box, color, tag)
        self._register_box = None   # 마지막 검출 가이드 박스
        self._last_capture = 0.0    # 학습 데이터 수집(ROI 저장) 스로틀
        self._side_note = None      # 옆모습 단계 샌드위치 판정 표시

        # 구명조끼 자세 검증 (카메라 스레드 전용)
        self._turn: TurnVerifier | None = None
        self._turn_hold_until = 0.0     # 실패 직후 재시작 억제 만료 시각
        self._turn_skip_logged = False  # LBPH 등 랜드마크 없음 안내 1회

    # ── 수명 주기 ────────────────────────────────────────────────────────
    def start(self) -> None:
        self.train_model()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap is not None and self._cap.isOpened():
            self._cap.release()

    def train_model(self) -> None:
        """등록 사용자 사진으로 갤러리를 다시 만든다 (등록/삭제 후 호출).

        HTTP 요청 스레드에서 불리므로 카메라 스레드가 쓰는 엔진을 건드리지 않고
        새 엔진으로 만든 뒤 한 번에 교체한다.
        """
        users = self._users_store.load()
        engine = create_engine()
        gallery = engine.build_gallery(users, self._base_dir)
        with self.lock:
            self._engine = engine
            self._gallery = gallery
            self.engine_name = engine.name
            self._voter.reset()

    def set_mode(self, mode: str) -> None:
        with self.lock:
            self.mode = mode
            if mode == "register":
                self.raw_register_frame = None
                self._register_samples = []
            self._voter.reset()
            self._frame_no = 0
            self._scan_note = None
            self._jacket_note = None
            self._register_box = None
            self._turn = None
            self._side_note = None
        if mode in ("scan", "register"):
            self._last_open_try = 0.0  # 대기에서 복귀 시 3초 스로틀 없이 즉시 오픈

    def get_register_frames(self) -> list:
        """등록용 프레임 목록: 현재 프레임 + 최근 샘플(최신 순). 카메라가 없으면 빈 목록."""
        with self.lock:
            frames = [] if self.raw_register_frame is None else [self.raw_register_frame.copy()]
            frames += [f.copy() for _, f in reversed(self._register_samples)]
        return frames

    # ── 메인 루프 ────────────────────────────────────────────────────────
    def _open_camera(self) -> None:
        now = time.time()
        if now - self._last_open_try < 3.0:
            return
        self._last_open_try = now
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(CAMERA_INDEX)
        self.camera_ok = bool(self._cap.isOpened())

    def _close_camera(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.camera_ok = False

    def _loop(self) -> None:
        while self._running:
            with self.lock:
                mode = self.mode

            if mode == "idle":
                # 절전: 카메라를 닫아 센서/USB 스트리밍을 멈춘다 (발열 저감)
                self._close_camera()
                self._publish(self._placeholder("CAMERA STANDBY"))
                time.sleep(0.3)
                continue

            if self._cap is None or not self._cap.isOpened():
                self.camera_ok = False
                self._open_camera()
                if self._cap is None or not self._cap.isOpened():
                    self._publish(self._placeholder("CAMERA CONNECTING..."))
                    time.sleep(0.5)
                continue

            ret, frame = self._cap.read()
            if not ret:
                self.camera_ok = False
                self._publish(self._placeholder("NO CAMERA SIGNAL"))
                time.sleep(0.5)
                self._open_camera()
                continue

            self.camera_ok = True
            frame = cv2.flip(frame, 1)  # 거울 모드

            self._frame_no += 1
            detect_now = (self._frame_no - 1) % DETECT_EVERY_N_FRAMES == 0

            try:
                if mode == "scan":
                    self._process_scan(frame, detect_now)
                elif mode == "register":
                    self._process_register(frame, detect_now)
                else:
                    self._publish(frame)
            except Exception as e:
                # 프레임 1장의 처리 실패가 카메라 스레드 전체를 죽이지 않게 한다
                print(f"[camera] 프레임 처리 오류: {e}")

            time.sleep(0.01)

    def _process_scan(self, frame, detect_now: bool) -> None:
        display = frame.copy()

        if detect_now:
            with self.lock:
                engine, gallery = self._engine, self._gallery
            det = engine.detect_largest(frame) if engine is not None else None
            note = None
            jacket = None
            jacket_note = None
            now = time.time()
            if det is None:
                # 얼굴이 잠시 사라진 뒤 돌아오면 투표를 새로 시작한다
                if now - self._last_face_seen > FACE_VOTE_SECONDS:
                    self._voter.reset()
                # 자세 검증 중 얼굴이 오래 사라지면 추적을 끊는다
                if self._turn is not None and self._turn.lost(now):
                    self._turn = None
            else:
                self._last_face_seen = now
                box = det.box
                # 구명조끼 시각 확인(TFLite 분류기, 없으면 HSV 폴백) — 승선 판정과 화면 표시에 사용
                if JACKET_VISION_ENABLED:
                    jacket = assess_jacket(frame, box)
                    if jacket["box"] is not None:
                        ok = jacket["visible"] is True
                        tag = f"{'JACKET' if ok else 'NO JACKET'} {jacket['ratio']:.0%}"
                        jacket_note = (jacket["box"], GREEN if ok else RED, tag)
                        if JACKET_CAPTURE_ENABLED:
                            self._maybe_capture_roi(frame, jacket)

                if gallery.empty:
                    note = (box, WHITE, None, 1)
                    self._voter.reset()
                    self._turn = None
                    self._boarding.handle_no_model()
                elif self._turn is not None:
                    # 자세 검증 진행 중 — 신원 투표는 쉬고 연속성으로 같은 사람을 추적한다
                    note = self._run_turn(det, jacket, frame, now)
                else:
                    feat = engine.embed(frame, det)
                    m = engine.match(feat, gallery) if feat is not None else Match(None, 0.0)
                    uid = (m.user.get("id") or m.user.get("name", "")) if m.user else None
                    confirmed, votes = self._voter.vote(uid)
                    if confirmed is not None and confirmed in gallery.users:
                        user = gallery.users[confirmed]
                        boarded = self._boarding.is_boarded(confirmed)
                        if boarded:
                            note = (box, GREEN, "BOARDED", 2)
                            self._boarding.handle_recognition(user, jacket)
                        elif now < self._turn_hold_until:
                            # 자세 검증 실패 직후 — 안내가 읽히도록 잠시 뒤 다시 시작한다
                            note = (box, YELLOW, "RETRY SOON", 2)
                        elif (self._turn_check_applies(det, jacket)
                              and self._boarding.has_claimable_device()):
                            # 모듈 착용 신호가 있을 때만 자세 검증을 시작한다 — 없으면
                            # 아래 handle_recognition 이 "착용 신호가 없습니다" 를 바로 안내
                            self._turn = TurnVerifier(
                                user, now,
                                shoulder_check=assess_shoulders if JACKET_SHOULDER_CHECK else None,
                                side_check=assess_side_profile,
                            )
                            note = self._run_turn(det, jacket, frame, now)
                        else:
                            note = (box, GREEN, f"PASSENGER {m.label}", 2)
                            self._boarding.handle_recognition(user, jacket)
                    elif uid is not None or not self._voter.full:
                        # 임계값은 넘었지만 아직 표가 모자람 — 확정 전
                        note = (box, YELLOW, f"VERIFYING {votes}/{self._voter.need}", 2)
                    else:
                        note = (box, RED, f"UNKNOWN {m.label}".rstrip(), 2)
                        self._boarding.handle_unknown()
            self._scan_note = note
            self._jacket_note = jacket_note
            # 옆모습 단계에서는 가슴 박스 대신 샌드위치 띠와 구간을 표시한다
            self._side_note = None
            if self._turn is not None and self._turn.stage == "side" and self._turn.last_side:
                self._side_note = self._turn.last_side
                if self._side_note.get("box") is not None:
                    self._jacket_note = None

        # 검출을 건너뛰는 프레임에는 마지막 주석을 그대로 그려 박스 깜빡임을 막는다
        if self._scan_note is not None:
            (x, y, w, h), color, tag, thickness = self._scan_note
            cv2.rectangle(display, (x, y), (x + w, y + h), color, thickness)
            if tag:
                cv2.putText(display, tag, (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if self._jacket_note is not None:
            (x, y, w, h), color, tag = self._jacket_note
            cv2.rectangle(display, (x, y), (x + w, y + h), color, 1)
            cv2.putText(display, tag, (x + 4, y + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        side = getattr(self, "_side_note", None)
        if side is not None and side.get("box") is not None:
            # 띠 박스 + 열 구간 막대(조끼=주황, 몸통=회색) + 샌드위치 여부
            x, y, w, h = side["box"]
            ok = side.get("visible") is True
            color = GREEN if ok else RED
            cv2.rectangle(display, (x, y), (x + w, y + h), color, 1)
            bar_y = y + h - 6
            for x0, x1, is_jacket in side.get("segments", []):
                cv2.rectangle(display, (x0, bar_y), (max(x0, x1 - 1), bar_y + 5),
                              (0, 140, 255) if is_jacket else (120, 120, 120), -1)
            tag = f"SIDE {'J/B/J OK' if ok else 'NO J/B/J'} {side.get('ratio', 0):.0%}"
            cv2.putText(display, tag, (x + 4, y + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        self._publish(display)

    # ── 구명조끼 자세 검증 ───────────────────────────────────────────────
    def _turn_check_applies(self, det, jacket) -> bool:
        """이 검출에 자세 검증을 적용할 수 있는지 (설정 켜짐 + 시각 확인 켜짐 + 랜드마크)."""
        if not (JACKET_TURN_CHECK and JACKET_VISION_ENABLED and jacket is not None):
            return False
        if det.landmarks is None:
            if not self._turn_skip_logged:
                self._turn_skip_logged = True
                print("[camera] 얼굴 랜드마크 없음(LBPH 엔진) — 구명조끼 자세 검증 생략")
            return False
        return True

    def _run_turn(self, det, jacket, frame, now: float):
        """검증기에 이번 검출을 넣고 결과에 따라 승선/실패/안내를 처리한다. 화면 주석을 돌려준다."""
        turn = self._turn
        st = turn.update(det, jacket, frame, now)
        box = det.box
        if st.state == "passed":
            self._turn = None
            check = dict(turn.front_jacket or jacket or {})
            check["turn"] = True
            check["side"] = turn.side
            self._boarding.handle_recognition(turn.user, check)
            return (box, GREEN, "PASSENGER TURN OK", 2)
        if st.state == "failed":
            self._turn = None
            self._turn_hold_until = now + TURN_RETRY_HOLD_SEC
            self._voter.reset()
            self._boarding.guide(st.message, st.color)
            return (box, RED, st.tag, 2)
        if st.state == "lost":
            # 다른 얼굴로 바뀌었거나 한참 사라졌다 — 신원 확인부터 다시
            self._turn = None
            self._voter.reset()
            return (box, YELLOW, st.tag, 1)
        self._boarding.guide(st.message, st.color)
        return (box, YELLOW, st.tag, 2)

    def _maybe_capture_roi(self, frame, jacket: dict) -> None:
        """학습 데이터 수집: 가슴 ROI 크롭을 주기 제한으로 저장한다.

        VPASS_JACKET_CAPTURE=1 일 때만 호출된다. 파일명에 판정 점수를 넣어
        나중에 jacket/ vs no_jacket/ 으로 분류(라벨링)할 때 참고하게 한다.
        """
        now = time.time()
        if now - self._last_capture < JACKET_CAPTURE_INTERVAL:
            return
        self._last_capture = now
        x, y, w, h = jacket["box"]
        crop = frame[y:y + h, x:x + w]
        JACKET_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{int(now * 1000) % 1000:03d}"
        name = f"{stamp}_{jacket['method']}{jacket['ratio']:.2f}.jpg"
        cv2.imwrite(str(JACKET_CAPTURE_DIR / name), crop)

    def _process_register(self, frame, detect_now: bool) -> None:
        display = frame.copy()
        if detect_now:
            with self.lock:
                engine = self._engine
            det = engine.detect_largest(frame) if engine is not None else None
            self._register_box = None if det is None else det.box
            now = time.time()
            with self.lock:
                # 얼굴이 보이는 동안 일정 간격으로 원본 프레임을 모아 둔다(다중 샘플 등록)
                if det is not None and now - self._last_sample >= FACE_ENROLL_SAMPLE_INTERVAL:
                    self._last_sample = now
                    self._register_samples.append((now, frame.copy()))
                window = FACE_ENROLL_SAMPLE_INTERVAL * FACE_ENROLL_SAMPLES * 2
                self._register_samples = [
                    (t, f) for t, f in self._register_samples if now - t <= window
                ][-FACE_ENROLL_SAMPLES * 2:]
        if self._register_box is not None:
            x, y, w, h = self._register_box
            cv2.rectangle(display, (x, y), (x + w, y + h), YELLOW, 2)
        with self.lock:
            self.raw_register_frame = frame.copy()
        self._publish(display)

    def _publish(self, frame) -> None:
        with self.lock:
            self.latest_frame = frame

    @staticmethod
    def _placeholder(text: str):
        canvas = np.zeros((360, 480, 3), dtype=np.uint8)
        canvas[:] = (17, 12, 10)  # $bg 근사(BGR)
        cv2.putText(canvas, text, (70, 190), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (128, 118, 110), 2)
        return canvas

    # ── MJPEG 스트림 ────────────────────────────────────────────────────
    def mjpeg_frames(self):
        while True:
            with self.lock:
                frame = self.latest_frame
            if frame is None:
                frame = self._placeholder("STARTING...")
            ok, jpeg = cv2.imencode(".jpg", frame)
            if ok:
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + jpeg.tobytes()
                    + b"\r\n\r\n"
                )
            time.sleep(0.04)  # ~25 FPS
