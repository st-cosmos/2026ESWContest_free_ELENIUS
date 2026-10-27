"""얼굴 검출/인식 엔진.

두 가지 백엔드를 같은 인터페이스(FaceEngine)로 제공한다.

  sface (기본) — YuNet 검출(5점 랜드마크) + SFace 128차원 임베딩, 코사인 유사도.
                 OpenCV 내장(cv2.FaceDetectorYN / cv2.FaceRecognizerSF)이라 추가
                 의존성이 없고, models/ 의 ONNX 두 개만 있으면 된다
                 (tools/fetch_face_models.py 로 내려받음).
  lbph         — Haar cascade + LBPH(opencv-contrib). 이전 파이프라인.
                 모델 파일이 없을 때 자동 폴백.

인식 품질을 위해 세 가지 장치를 둔다.
  1) 다중 샘플 등록 — 등록 시 연속 프레임에서 여러 장을 받아 품질 게이트
     (검출 점수·크기·선명도·정면성)를 통과한 것만 저장한다(quality_check).
  2) 마진 판정 — 1등 점수가 임계값 이상이면서 2등(다른 사람)과의 차이가
     마진 이상일 때만 인정한다(cosine_match). 비슷한 얼굴 사이의 오인식 억제.
  3) 시간 투표 — 연속 검출 결과 중 과반이 같은 사람일 때만 승선 처리한다
     (RecognitionVoter). 한 프레임의 우연한 일치로 승선되는 것을 막는다.

주의: cv2 의 검출기/인식기 객체는 호출 중 내부 상태를 바꾸므로 스레드 간
공유가 안전하지 않다. 사용 주체(카메라 스레드, HTTP 요청)마다 create_engine()
으로 전용 인스턴스를 만든다.
"""

from __future__ import annotations

import os
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import config
from .config import FACE_SIZE


# ── 공통 자료형 ──────────────────────────────────────────────────────────
@dataclass
class Detection:
    box: tuple[int, int, int, int]           # (x, y, w, h) — 정수, 프레임 좌표
    score: float = 1.0                       # 검출 신뢰도 (cascade 는 1.0 고정)
    landmarks: np.ndarray | None = None      # (5, 2) 우안·좌안·코·우입·좌입 (YuNet)
    raw: np.ndarray | None = None            # YuNet 원본 행 — alignCrop 입력
    source: tuple | None = None              # (패딩 이미지, 그 위의 Detection) — 재검출용

    @property
    def area(self) -> int:
        return self.box[2] * self.box[3]


@dataclass
class Match:
    user: dict | None                        # 인정된 사용자(없으면 None)
    score: float                             # 1등 점수(SFace: 코사인, LBPH: confidence)
    second: float | None = None              # 2등(다른 사용자) 점수
    candidate: dict | None = None            # 가장 가까운 사용자(인정 여부와 무관)
    label: str = ""                          # 화면 표시용 짧은 점수 문자열


class Gallery:
    """등록 사용자 특징 집합. 한 사용자가 여러 특징(사진)을 가질 수 있다."""

    def __init__(self):
        self.entries: list[tuple[str, np.ndarray]] = []   # (user_id, feature)
        self.users: dict[str, dict] = {}

    def add(self, user: dict, feature: np.ndarray) -> None:
        uid = user.get("id") or user.get("name", "")
        self.users[uid] = user
        self.entries.append((uid, feature))

    @property
    def empty(self) -> bool:
        return not self.entries

    def __len__(self) -> int:
        return len(self.users)


class RecognitionVoter:
    """연속 검출 결과에 대한 시간 투표.

    최근 window 회(그리고 seconds 초 이내)의 판정에서 같은 사용자가 need 회
    이상 나오면 그 사용자를 확정한다. 얼굴이 사라지면(reset) 투표를 비운다.
    """

    def __init__(self, window: int, need: int, seconds: float):
        self.window = max(1, window)
        self.need = max(1, min(need, self.window))
        self.seconds = seconds
        self._votes: deque[tuple[float, str | None]] = deque(maxlen=self.window)

    def reset(self) -> None:
        self._votes.clear()

    def vote(self, user_id: str | None, now: float | None = None) -> tuple[str | None, int]:
        """한 표를 넣고 (확정된 user_id 또는 None, 최다 득표 수) 를 돌려준다."""
        now = time.time() if now is None else now
        self._votes.append((now, user_id))
        counts: dict[str, int] = {}
        for t, u in self._votes:
            if u is not None and now - t <= self.seconds:
                counts[u] = counts.get(u, 0) + 1
        if not counts:
            return None, 0
        best, n = max(counts.items(), key=lambda kv: kv[1])
        return (best if n >= self.need else None), n

    @property
    def full(self) -> bool:
        return len(self._votes) >= self.window


# ── 엔진 인터페이스 ──────────────────────────────────────────────────────
class FaceEngine:
    name = "base"

    def detect_largest(self, frame_bgr) -> Detection | None:
        raise NotImplementedError

    def embed(self, frame_bgr, det: Detection) -> np.ndarray | None:
        raise NotImplementedError

    def match(self, feature: np.ndarray, gallery: Gallery) -> Match:
        raise NotImplementedError

    def quality_check(self, frame_bgr, det: Detection) -> tuple[bool, str]:
        """등록용 샘플 품질 게이트. (통과 여부, 사유) 를 돌려준다."""
        x, y, w, h = det.box
        if w < config.FACE_ENROLL_MIN_SIZE_PX or h < config.FACE_ENROLL_MIN_SIZE_PX:
            return False, "얼굴이 너무 작습니다. 카메라에 더 가까이 와 주세요."
        gray = cv2.cvtColor(frame_bgr[y:y + h, x:x + w], cv2.COLOR_BGR2GRAY)
        if gray.size == 0:
            return False, "얼굴 영역을 잘라낼 수 없습니다."
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur < config.FACE_ENROLL_BLUR_MIN:
            return False, "사진이 흐립니다. 잠시 멈춰 주세요."
        return True, "ok"

    def build_gallery(self, users: list[dict], base_dir: Path) -> Gallery:
        """등록 사용자 사진에서 특징을 뽑아 갤러리를 만든다."""
        gallery = Gallery()
        for user in users:
            for rel in user_photos(user):
                image = imread_unicode(base_dir / rel)
                if image is None:
                    continue
                image = fit_image(image)
                det = self.detect_largest(image) or self._detect_padded(image)
                if det is None:
                    continue
                feat = self.embed(image, det)
                if feat is not None:
                    gallery.add(user, feat)
        return gallery

    def _detect_padded(self, image) -> Detection | None:
        """저장된 얼굴 크롭은 여백이 적어 검출이 실패할 수 있다 — 테두리를 넓혀 재시도."""
        h, w = image.shape[:2]
        pad = int(max(h, w) * 0.3)
        padded = cv2.copyMakeBorder(image, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        det = self.detect_largest(padded)
        if det is None:
            return None
        x, y, bw, bh = det.box
        # 박스는 원본 좌표로 돌려주되, 임베딩은 패딩 이미지에서 뽑도록 source 를 남긴다
        return Detection((x - pad, y - pad, bw, bh), det.score, None, None, (padded, det))


# ── SFace 백엔드 ─────────────────────────────────────────────────────────
class SFaceEngine(FaceEngine):
    name = "sface"

    def __init__(self, det_path: Path, rec_path: Path):
        self._det = cv2.FaceDetectorYN.create(
            str(det_path), "", (320, 320),
            config.FACE_DET_SCORE_THRESHOLD, 0.3, 50,
        )
        self._rec = cv2.FaceRecognizerSF.create(str(rec_path), "")
        self._input_size = None

    def detect_largest(self, frame_bgr) -> Detection | None:
        h, w = frame_bgr.shape[:2]
        if self._input_size != (w, h):
            self._det.setInputSize((w, h))
            self._input_size = (w, h)
        _, faces = self._det.detect(frame_bgr)
        if faces is None or len(faces) == 0:
            return None
        row = max(faces, key=lambda f: f[2] * f[3])
        x, y, bw, bh = (int(round(float(v))) for v in row[:4])
        if bw < config.FACE_MIN_SIZE_PX or bh < config.FACE_MIN_SIZE_PX:
            return None
        # 프레임 밖으로 나간 박스는 안쪽으로 자른다(구명조끼 ROI 계산·표시용)
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w, x + bw), min(h, y + bh)
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            return None
        return Detection(
            (x1, y1, x2 - x1, y2 - y1),
            float(row[14]),
            row[4:14].reshape(5, 2).astype(np.float32),
            row.astype(np.float32),
        )

    def embed(self, frame_bgr, det: Detection) -> np.ndarray | None:
        if det.source is not None:
            frame_bgr, det = det.source
        if det.raw is None:
            return None
        crop = self._rec.alignCrop(frame_bgr, det.raw)
        feat = self._rec.feature(crop).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feat))
        return feat / norm if norm > 0 else None

    def match(self, feature: np.ndarray, gallery: Gallery) -> Match:
        return cosine_match(feature, gallery, config.FACE_SFACE_THRESHOLD, config.FACE_SFACE_MARGIN)

    def quality_check(self, frame_bgr, det: Detection) -> tuple[bool, str]:
        if det.score < config.FACE_ENROLL_MIN_SCORE:
            return False, "얼굴이 또렷하게 보이지 않습니다. 정면을 봐 주세요."
        ok, why = super().quality_check(frame_bgr, det)
        if not ok:
            return ok, why
        if det.landmarks is not None:
            # 정면성: 코끝이 두 눈 사이 구간의 가운데 근처에 있어야 한다
            re_x, le_x = float(det.landmarks[0][0]), float(det.landmarks[1][0])
            span = abs(le_x - re_x)
            if span > 1:
                rel = (float(det.landmarks[2][0]) - min(re_x, le_x)) / span
                if not (config.FACE_ENROLL_YAW_MIN <= rel <= config.FACE_ENROLL_YAW_MAX):
                    return False, "고개를 돌리지 말고 정면을 봐 주세요."
        return True, "ok"


def cosine_match(feature: np.ndarray, gallery: Gallery, threshold: float, margin: float) -> Match:
    """사용자별 최고 코사인 점수를 구해 임계값 + 마진 규칙으로 판정한다."""
    if gallery.empty:
        return Match(None, 0.0)
    best_by_user: dict[str, float] = {}
    for uid, feat in gallery.entries:
        s = float(np.dot(feature, feat))
        if s > best_by_user.get(uid, -2.0):
            best_by_user[uid] = s
    ranked = sorted(best_by_user.items(), key=lambda kv: kv[1], reverse=True)
    uid, best = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else None
    candidate = gallery.users[uid]
    label = f"{best:.2f}"
    if best < threshold:
        return Match(None, best, second, candidate, label)
    if second is not None and best - second < margin:
        return Match(None, best, second, candidate, label)
    return Match(candidate, best, second, candidate, label)


# ── LBPH 백엔드 (폴백) ───────────────────────────────────────────────────
class LbphEngine(FaceEngine):
    name = "lbph"

    def __init__(self):
        self._cascade = load_face_cascade()
        self._recognizer = None
        self._label_to_uid: dict[int, str] = {}

    def detect_largest(self, frame_bgr) -> Detection | None:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        box = detect_largest_face(self._cascade, gray)
        if box is None:
            return None
        x, y, w, h = (int(v) for v in box)
        return Detection((x, y, w, h))

    def embed(self, frame_bgr, det: Detection) -> np.ndarray | None:
        if det.source is not None:
            frame_bgr, det = det.source
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        return normalize_face(crop_face_roi(gray, det.box))

    def build_gallery(self, users: list[dict], base_dir: Path) -> Gallery:
        gallery = super().build_gallery(users, base_dir)
        self._recognizer, self._label_to_uid = None, {}
        if gallery.empty:
            return gallery
        uid_to_label = {uid: i for i, uid in enumerate(gallery.users)}
        samples = [feat for _, feat in gallery.entries]
        labels = [uid_to_label[uid] for uid, _ in gallery.entries]
        try:
            rec = cv2.face.LBPHFaceRecognizer_create()
            rec.train(samples, np.array(labels))
            self._recognizer = rec
            self._label_to_uid = {i: uid for uid, i in uid_to_label.items()}
        except Exception as e:  # cv2.face 미포함 빌드 등
            print(f"[facerec] LBPH 학습 실패: {e}")
        return gallery

    def match(self, feature: np.ndarray, gallery: Gallery) -> Match:
        if self._recognizer is None or gallery.empty:
            return Match(None, 0.0)
        label, confidence = self._recognizer.predict(feature)
        uid = self._label_to_uid.get(int(label))
        user = gallery.users.get(uid) if uid else None
        label_txt = f"{confidence:.0f}"
        if user is None or confidence > config.MATCH_THRESHOLD:
            return Match(None, float(confidence), None, user, label_txt)
        return Match(user, float(confidence), None, user, label_txt)


# ── 엔진 선택 ───────────────────────────────────────────────────────────
def sface_models_available() -> bool:
    return (config.FACE_DET_MODEL_PATH.is_file() and config.FACE_REC_MODEL_PATH.is_file()
            and hasattr(cv2, "FaceDetectorYN") and hasattr(cv2, "FaceRecognizerSF"))


_announced: set[str] = set()


def create_engine(method: str | None = None) -> FaceEngine:
    """설정(VPASS_FACE_METHOD)에 따라 엔진 인스턴스를 만든다 — 호출자 전용 인스턴스."""
    method = (method or config.FACE_METHOD).lower()
    if method in ("auto", "sface") and sface_models_available():
        try:
            engine = SFaceEngine(config.FACE_DET_MODEL_PATH, config.FACE_REC_MODEL_PATH)
            _announce("sface", f"[facerec] SFace 모델 로드 (YuNet 검출, 임계값 {config.FACE_SFACE_THRESHOLD})")
            return engine
        except Exception as e:
            print(f"[facerec] SFace 로드 실패 → LBPH 폴백: {e}")
    elif method == "sface":
        print("[facerec] SFace 모델 파일이 없습니다 → LBPH 폴백 "
              "(uv run python tools/fetch_face_models.py 로 내려받으세요)")
    _announce("lbph", "[facerec] LBPH(Haar cascade) 사용")
    return LbphEngine()


def _announce(key: str, msg: str) -> None:
    if key not in _announced:
        _announced.add(key)
        print(msg)


def fit_image(image, max_side: int = 1280):
    """긴 변이 max_side 를 넘는 사진(휴대폰 원본 등)은 줄인다 — YuNet 은 아주 큰 입력에서 검출이 떨어진다."""
    h, w = image.shape[:2]
    if max(h, w) <= max_side:
        return image
    scale = max_side / max(h, w)
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def user_photos(user: dict) -> list[str]:
    """사용자 레코드의 사진 경로 목록 (photos 가 없으면 photo 하나)."""
    photos = user.get("photos")
    if isinstance(photos, list) and photos:
        return [p for p in photos if p]
    return [user["photo"]] if user.get("photo") else []


# ── Haar/LBPH 보조 함수 (이전 API 유지) ─────────────────────────────────
def load_face_cascade() -> cv2.CascadeClassifier | None:
    """CascadeClassifier 는 detectMultiScale 중 내부 상태를 바꾸므로 호출자마다 따로 로드한다."""
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
