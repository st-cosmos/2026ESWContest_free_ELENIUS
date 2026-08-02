"""OpenCV 기반 얼굴 검출/인식 유틸.

smart-vpass-example 의 검증된 파이프라인(LBPH + Haar cascade)을 그대로 사용한다.
- 얼굴 검출: haarcascade_frontalface_default
- 인식: LBPHFaceRecognizer (opencv-contrib)
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import cv2
import numpy as np

from .config import FACE_SIZE


def load_face_cascade() -> cv2.CascadeClassifier | None:
    """얼굴 검출기를 로드한다.

    CascadeClassifier 는 detectMultiScale 호출 중 내부 상태(scaleData)를
    변경하므로 스레드 간 공유가 안전하지 않다. 사용 주체(스레드/요청)마다
    이 함수로 전용 인스턴스를 로드해야 한다.
    """
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    return None if cascade.empty() else cascade


def detect_largest_face(cascade, gray):
    """회색조 이미지에서 가장 큰 얼굴 하나의 (x, y, w, h)를 반환한다."""
    if cascade is None:
        return None
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=6, minSize=(100, 100)
    )
    if len(faces) == 0:
        return None
    return max(faces, key=lambda f: f[2] * f[3])


def crop_face_roi(gray, box, margin_ratio: float = 0.08):
    """검출 박스에서 margin 비율만큼 안쪽을 잘라낸 얼굴 ROI를 반환한다."""
    x, y, w, h = box
    mw = int(w * margin_ratio)
    mh = int(h * margin_ratio)
    y1 = max(0, y + mh)
    y2 = min(gray.shape[0], y + h - mh)
    x1 = max(0, x + mw)
    x2 = min(gray.shape[1], x + w - mw)
    roi = gray[y1:y2, x1:x2]
    return roi if roi.size > 0 else gray


def normalize_face(roi):
    """조도 평활화 후 학습/예측용 크기로 변환한다."""
    return cv2.resize(cv2.equalizeHist(roi), FACE_SIZE)


def extract_face(cascade, image_bgr):
    """BGR 이미지에서 학습용 얼굴 패치를 추출한다(검출 실패 시 전체 사용)."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    box = detect_largest_face(cascade, gray)
    if box is None:
        h, w = gray.shape[:2]
        box = (0, 0, w, h)
    return normalize_face(crop_face_roi(gray, box))


def train_recognizer(users: list[dict], base_dir: Path):
    """등록 사용자 사진으로 LBPH 인식기를 학습한다.

    cascade 는 공유 인스턴스 경합을 피하기 위해 호출 시마다 새로 로드한다.
    반환: (recognizer, {label: user}) — 학습 샘플이 없으면 (None, {}).
    """
    cascade = load_face_cascade()
    samples, labels, label_to_user = [], [], {}

    for user in users:
        photo_rel = user.get("photo")
        if not photo_rel:
            continue
        image = imread_unicode(base_dir / photo_rel)
        if image is None:
            continue
        face = extract_face(cascade, image)
        if face is None:
            continue
        label = len(label_to_user)
        samples.append(face)
        labels.append(label)
        label_to_user[label] = user

    if not samples:
        return None, {}

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(samples, np.array(labels))
        return recognizer, label_to_user
    except Exception as e:  # cv2.face 미포함 빌드 등
        print(f"[facerec] 인식기 학습 실패: {e}")
        return None, {}


# ── 유니코드 경로 이미지 IO (윈도우 한글 경로 대응) ──────────────────────
def imwrite_unicode(path: Path, image, ext: str = ".jpg") -> bool:
    ok, buf = cv2.imencode(ext, image)
    if not ok:
        return False
    try:
        buf.tofile(str(path))
        return True
    except Exception:
        return False


def imread_unicode(path: Path):
    if not os.path.exists(path):
        return None
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def safe_filename(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text.strip())
