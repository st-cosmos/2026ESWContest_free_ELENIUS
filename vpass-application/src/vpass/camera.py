"""카메라 매니저.

백그라운드 스레드에서 프레임을 읽어 모드별로 처리한다.
  - idle:     대기 — 카메라 장치를 닫아 절전한다 (발열 저감)
  - scan:     출항 화면 — 얼굴 인식 + 구명조끼 시각 확인 → BoardingManager 에 전달
  - register: 등록 화면 — 얼굴 가이드 박스만 표시, 원본 프레임 보관

카메라는 scan/register 모드에서만 열리고, idle 로 돌아오면 해제된다.
얼굴 검출은 DETECT_EVERY_N_FRAMES 프레임마다 1회만 수행한다.

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
    JACKET_VISION_ENABLED,
    MATCH_THRESHOLD,
)
from .facerec import (
    crop_face_roi,
    detect_largest_face,
    load_face_cascade,
    normalize_face,
    train_recognizer,
)
from .jacketvision import assess_jacket

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

        self._cascade = None  # 카메라 스레드 전용 — 다른 스레드와 공유 금지
        self._recognizer = None
        self._label_to_user: dict[int, dict] = {}

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

    # ── 수명 주기 ────────────────────────────────────────────────────────
    def start(self) -> None:
        self._cascade = load_face_cascade()
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
        users = self._users_store.load()
        recognizer, label_map = train_recognizer(users, self._base_dir)
        with self.lock:
            self._recognizer = recognizer
            self._label_to_user = label_map

    def set_mode(self, mode: str) -> None:
        with self.lock:
            self.mode = mode
            if mode == "register":
                self.raw_register_frame = None
            self._frame_no = 0
            self._scan_note = None
            self._jacket_note = None
            self._register_box = None
        if mode in ("scan", "register"):
            self._last_open_try = 0.0  # 대기에서 복귀 시 3초 스로틀 없이 즉시 오픈

    def get_register_frame(self):
        with self.lock:
            return None if self.raw_register_frame is None else self.raw_register_frame.copy()

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
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            box = detect_largest_face(self._cascade, gray)
            note = None
            jacket = None
            jacket_note = None
            if box is not None:
                # 구명조끼 시각 확인(TFLite 분류기, 없으면 HSV 폴백) — 승선 판정과 화면 표시에 사용
                if JACKET_VISION_ENABLED:
                    jacket = assess_jacket(frame, box)
                    if jacket["box"] is not None:
                        ok = jacket["visible"] is True
                        tag = f"{'JACKET' if ok else 'NO JACKET'} {jacket['ratio']:.0%}"
                        jacket_note = (jacket["box"], GREEN if ok else RED, tag)
                        if JACKET_CAPTURE_ENABLED:
                            self._maybe_capture_roi(frame, jacket)

                with self.lock:
                    recognizer = self._recognizer
                    label_map = dict(self._label_to_user)

                if recognizer is None:
                    note = (box, WHITE, None, 1)
                    self._boarding.handle_no_model()
                else:
                    face = normalize_face(crop_face_roi(gray, box))
                    label, confidence = recognizer.predict(face)
                    if confidence <= MATCH_THRESHOLD and label in label_map:
                        user = label_map[label]
                        boarded = self._boarding.is_boarded(user.get("id") or user.get("name", ""))
                        tag = "BOARDED" if boarded else f"PASSENGER ({confidence:.0f})"
                        note = (box, GREEN, tag, 2)
                        self._boarding.handle_recognition(user, jacket)
                    else:
                        note = (box, RED, "UNKNOWN", 2)
                        self._boarding.handle_unknown()
            self._scan_note = note
            self._jacket_note = jacket_note

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

        self._publish(display)

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
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            self._register_box = detect_largest_face(self._cascade, gray)
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
