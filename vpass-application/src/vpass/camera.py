"""카메라 매니저.

백그라운드 스레드에서 프레임을 읽어 모드별로 처리한다.
  - idle:     대기 (얼굴 인식 안 함, 화면 절전용)
  - scan:     출항 화면 — 얼굴 인식 → BoardingManager 에 결과 전달
  - register: 등록 화면 — 얼굴 가이드 박스만 표시, 원본 프레임 보관

카메라가 없는 개발 환경에서도 서버는 정상 동작하며 안내 프레임을 송출한다.
"""

from __future__ import annotations

import threading
import time

import cv2
import numpy as np

from .config import CAMERA_INDEX, MATCH_THRESHOLD
from .facerec import (
    crop_face_roi,
    detect_largest_face,
    load_face_cascade,
    normalize_face,
    train_recognizer,
)

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

    def _loop(self) -> None:
        self._open_camera()
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                self.camera_ok = False
                self._publish(self._placeholder("CAMERA CONNECTING..."))
                time.sleep(0.5)
                self._open_camera()
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

            with self.lock:
                mode = self.mode

            try:
                if mode == "scan":
                    self._process_scan(frame)
                elif mode == "register":
                    self._process_register(frame)
                else:
                    self._publish(frame)
            except Exception as e:
                # 프레임 1장의 처리 실패가 카메라 스레드 전체를 죽이지 않게 한다
                print(f"[camera] 프레임 처리 오류: {e}")

            time.sleep(0.01)

    def _process_scan(self, frame) -> None:
        display = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        box = detect_largest_face(self._cascade, gray)

        if box is not None:
            x, y, w, h = box
            with self.lock:
                recognizer = self._recognizer
                label_map = dict(self._label_to_user)

            if recognizer is None:
                cv2.rectangle(display, (x, y), (x + w, y + h), WHITE, 1)
                self._boarding.handle_no_model()
            else:
                face = normalize_face(crop_face_roi(gray, box))
                label, confidence = recognizer.predict(face)
                if confidence <= MATCH_THRESHOLD and label in label_map:
                    user = label_map[label]
                    boarded = self._boarding.is_boarded(user.get("id") or user.get("name", ""))
                    tag = "BOARDED" if boarded else f"PASSENGER ({confidence:.0f})"
                    cv2.rectangle(display, (x, y), (x + w, y + h), GREEN, 2)
                    cv2.putText(display, tag, (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, GREEN, 2)
                    self._boarding.handle_recognition(user)
                else:
                    cv2.rectangle(display, (x, y), (x + w, y + h), RED, 2)
                    cv2.putText(display, "UNKNOWN", (x, y - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, RED, 2)
                    self._boarding.handle_unknown()

        self._publish(display)

    def _process_register(self, frame) -> None:
        display = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        box = detect_largest_face(self._cascade, gray)
        if box is not None:
            x, y, w, h = box
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
