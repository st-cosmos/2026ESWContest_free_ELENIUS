"""얼굴 위조(사진·화면) 판별 — MiniFASNet 두 개의 평균 '진짜' 확률.

SFace 는 생김새만 비교하므로 휴대폰 화면이나 인쇄 사진에 띄운 선원 얼굴도 높은 유사도
(실측 0.75~0.84)로 통과한다. Silent-Face-Anti-Spoofing(Minivision, Apache-2.0)의
MiniFASNetV2(얼굴 박스 2.7배 영역)와 MiniFASNetV1SE(4.0배 영역)를 함께 돌려,
화면·종이 질감과 테두리를 본다. 출력은 [위조(2D), 진짜, 위조(3D)] 소프트맥스이고
두 모델의 '진짜' 확률 평균을 점수로 쓴다.

모델 파일이 없으면 load_checker() 가 None 을 돌려주고 앱은 위조 판별 없이 동작한다.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config

INPUT_SIZE = 80
REAL_INDEX = 1


def crop_face(image, box, scale: float, size: int = INPUT_SIZE):
    """얼굴 박스 중심으로 scale 배 넓힌 영역을 잘라 size×size 로 줄인다 (원 구현과 동일)."""
    src_h, src_w = image.shape[:2]
    x, y, w, h = (float(v) for v in box)
    scale = min((src_h - 1) / h, (src_w - 1) / w, scale)
    new_w, new_h = w * scale, h * scale
    cx, cy = x + w / 2, y + h / 2
    x1, y1 = max(0, int(cx - new_w / 2)), max(0, int(cy - new_h / 2))
    x2, y2 = min(src_w - 1, int(cx + new_w / 2)), min(src_h - 1, int(cy + new_h / 2))
    return cv2.resize(image[y1:y2 + 1, x1:x2 + 1], (size, size))


def _softmax(z: np.ndarray) -> np.ndarray:
    e = np.exp(z - z.max())
    return e / e.sum()


class LivenessChecker:
    """nets: [(cv2.dnn 네트워크 또는 forward 가능한 객체, 확대 배율)]. 카메라 스레드 전용."""

    def __init__(self, nets, threshold: float):
        self._nets = nets
        self.threshold = threshold

    def score(self, frame_bgr, box) -> float:
        """두 모델의 '진짜' 확률 평균 (0~1). BGR 원본 값(0~255)을 그대로 넣는다."""
        probs = []
        for net, scale in self._nets:
            blob = crop_face(frame_bgr, box, scale).astype(np.float32).transpose(2, 0, 1)[None]
            net.setInput(blob)
            probs.append(_softmax(np.asarray(net.forward()).reshape(-1))[REAL_INDEX])
        return float(np.mean(probs))

    def is_live(self, frame_bgr, box) -> tuple[bool, float]:
        s = self.score(frame_bgr, box)
        return s >= self.threshold, s


def models_available() -> bool:
    return all(Path(p).is_file() for p, _ in config.FACE_LIVENESS_MODELS)


def load_checker() -> LivenessChecker | None:
    """설정이 켜져 있고 모델이 있으면 판별기를 만든다. 아니면 None (위조 판별 생략)."""
    if not config.FACE_LIVENESS_ENABLED:
        return None
    if not models_available():
        print("[liveness] MiniFASNet 모델이 없습니다 → 위조 판별 없이 동작 "
              "(uv run python tools/fetch_face_models.py 로 내려받으세요)")
        return None
    try:
        nets = [(cv2.dnn.readNetFromONNX(str(p)), s) for p, s in config.FACE_LIVENESS_MODELS]
    except Exception as e:
        print(f"[liveness] 모델 로드 실패 → 위조 판별 없이 동작: {e}")
        return None
    print(f"[liveness] MiniFASNet 위조 판별 사용 (임계값 {config.FACE_LIVENESS_THRESHOLD})")
    return LivenessChecker(nets, config.FACE_LIVENESS_THRESHOLD)
