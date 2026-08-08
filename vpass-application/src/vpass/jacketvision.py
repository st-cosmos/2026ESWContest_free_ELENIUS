"""구명조끼 착용 시각 확인.

구명조끼 모듈(홀센서) 신호만 믿으면 조끼를 입지 않은 채 버클만 채워
착용으로 위장하는 치팅이 가능하다. 그래서 승선 등록(얼굴 인식) 시점에
카메라 프레임의 얼굴 아래 상체 ROI 를 함께 검사해, 모듈 신호와 시각
확인이 모두 통과해야 승선 처리한다(판정은 boarding.BoardingManager).

판정 방법 (VPASS_JACKET_METHOD):
  ml   — 가슴 ROI 를 입력으로 받는 TFLite 이진 분류기.
         모델은 tools/train_jacket_classifier.py 로 학습해 models/ 에 배치.
         입력 규약: RGB 0-255 (전처리는 모델 내부에 포함), 출력: 착용 확률 1개.
  hsv  — 상체 ROI 의 구명조끼 색(HSV 범위) 픽셀 비율 검사.
  auto — 모델 파일과 tflite 런타임이 있으면 ml, 없으면 hsv (기본).

판정(visible):
  True  — 착용으로 판단 (ml: 확률 >= JACKET_ML_THRESHOLD / hsv: 색 비율 기준 이상)
  False — 상체 ROI 를 검사했지만 미착용으로 판단
  None  — 상체가 화면 밖이라 판단 불가
"""

from __future__ import annotations

import cv2
import numpy as np

from .config import (
    JACKET_COLOR_RANGES,
    JACKET_MIN_COLOR_RATIO,
    JACKET_ML_THRESHOLD,
    JACKET_MODEL_PATH,
    JACKET_ROI_MIN_VISIBLE,
    JACKET_VISION_METHOD,
)

# 얼굴 박스(w×h) 기준 상체 ROI 배치 — 목(0.25h)은 건너뛰고 가슴을 넓게 본다
CHEST_TOP = 0.25    # ROI 시작: 얼굴 아래 y+h 에서 0.25h 아래
CHEST_BOTTOM = 1.9  # ROI 끝: 얼굴 아래 y+h 에서 1.9h 아래
CHEST_SIDE = 0.45   # 얼굴 좌우로 0.45w 씩 확장 (총폭 1.9w)


def chest_roi(frame_shape, face_box):
    """얼굴 박스 아래 상체 ROI 를 프레임 좌표 (x, y, w, h) 로 반환한다.

    프레임 밖으로 잘려 남은 면적이 JACKET_ROI_MIN_VISIBLE 미만이면
    None(판단 불가)을 반환한다.
    """
    fh, fw = frame_shape[:2]
    x, y, w, h = (int(v) for v in face_box)
    x1 = x - int(w * CHEST_SIDE)
    x2 = x + w + int(w * CHEST_SIDE)
    y1 = y + h + int(h * CHEST_TOP)
    y2 = y + h + int(h * CHEST_BOTTOM)
    full_area = (x2 - x1) * (y2 - y1)
    if full_area <= 0:
        return None
    cx1, cy1 = max(0, x1), max(0, y1)
    cx2, cy2 = min(fw, x2), min(fh, y2)
    if cx2 <= cx1 or cy2 <= cy1:
        return None
    if (cx2 - cx1) * (cy2 - cy1) < full_area * JACKET_ROI_MIN_VISIBLE:
        return None
    return cx1, cy1, cx2 - cx1, cy2 - cy1


# ── HSV 폴백 ─────────────────────────────────────────────────────────────
def color_ratio(roi_bgr) -> float:
    """ROI 픽셀 중 구명조끼 색(HSV 범위 합집합)에 드는 비율을 반환한다."""
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in JACKET_COLOR_RANGES:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    return float(cv2.countNonZero(mask)) / float(mask.size)


# ── TFLite 분류기 ────────────────────────────────────────────────────────
class _TFLiteJacketClassifier:
    """가슴 ROI → 착용 확률(0~1). float32/int8/uint8 입력 모델 모두 지원."""

    def __init__(self, interpreter):
        interpreter.allocate_tensors()
        self._interp = interpreter
        self._in = interpreter.get_input_details()[0]
        self._out = interpreter.get_output_details()[0]
        self._h, self._w = int(self._in["shape"][1]), int(self._in["shape"][2])

    def predict(self, roi_bgr) -> float:
        img = cv2.resize(roi_bgr, (self._w, self._h), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        dtype = np.dtype(self._in["dtype"])
        if dtype == np.float32:
            x = rgb.astype(np.float32)
        else:
            # 양자화 모델: 실수값(0-255 픽셀) → q = real/scale + zero_point
            scale, zero = self._in["quantization"]
            info = np.iinfo(dtype)
            q = np.round(rgb.astype(np.float32) / (scale or 1.0)) + zero
            x = np.clip(q, info.min, info.max).astype(dtype)
        self._interp.set_tensor(self._in["index"], x[np.newaxis, ...])
        self._interp.invoke()
        raw = self._interp.get_tensor(self._out["index"]).reshape(-1)[0]
        out_dtype = np.dtype(self._out["dtype"])
        if out_dtype == np.float32:
            return float(raw)
        scale, zero = self._out["quantization"]
        return float((float(raw) - zero) * (scale or 1.0))


def _load_interpreter_cls():
    """(Interpreter, OpResolverType|None) — 가벼운 런타임 우선으로 찾는다."""
    try:
        from tflite_runtime import interpreter as m  # 라즈베리파이 (uv sync --extra ml)
        return m.Interpreter, getattr(m, "OpResolverType", None)
    except ImportError:
        pass
    try:
        from ai_edge_litert import interpreter as m
        return m.Interpreter, getattr(m, "OpResolverType", None)
    except ImportError:
        pass
    try:
        import tensorflow as tf  # 개발 PC 에 tensorflow 가 있는 경우
        return tf.lite.Interpreter, getattr(tf.lite.experimental, "OpResolverType", None)
    except (ImportError, AttributeError):
        return None, None


# 지연 로드 싱글턴 — 테스트에서 _CLASSIFIER 를 직접 주입해 교체할 수 있다
_CLASSIFIER = None
_CLASSIFIER_LOADED = False


def _get_classifier():
    global _CLASSIFIER, _CLASSIFIER_LOADED
    if _CLASSIFIER_LOADED:
        return _CLASSIFIER
    _CLASSIFIER_LOADED = True
    if JACKET_VISION_METHOD == "hsv":
        return None
    if not JACKET_MODEL_PATH.exists():
        if JACKET_VISION_METHOD == "ml":
            print(f"[jacketvision] 모델 없음: {JACKET_MODEL_PATH} — HSV 로 폴백")
        return None
    interpreter_cls, resolver_type = _load_interpreter_cls()
    if interpreter_cls is None:
        print("[jacketvision] tflite 런타임 없음 (uv sync --extra ml) — HSV 로 폴백")
        return None
    try:
        _CLASSIFIER = _TFLiteJacketClassifier(interpreter_cls(model_path=str(JACKET_MODEL_PATH)))
    except Exception as e:
        # 일부 환경은 XNNPACK 델리게이트가 양자화 모델 준비에 실패한다 — 델리게이트 없이 재시도
        first_error = e
        _CLASSIFIER = None
        if resolver_type is not None:
            try:
                _CLASSIFIER = _TFLiteJacketClassifier(interpreter_cls(
                    model_path=str(JACKET_MODEL_PATH),
                    experimental_op_resolver_type=resolver_type.BUILTIN_WITHOUT_DEFAULT_DELEGATES,
                ))
            except Exception:
                pass
        if _CLASSIFIER is None:
            print(f"[jacketvision] 모델 로드 실패({first_error}) — HSV 로 폴백")
            return None
    print(f"[jacketvision] TFLite 모델 로드: {JACKET_MODEL_PATH.name} "
          f"(입력 {_CLASSIFIER._w}x{_CLASSIFIER._h})")
    return _CLASSIFIER


def assess_jacket(frame_bgr, face_box) -> dict:
    """얼굴 아래 상체 ROI 로 구명조끼 착용 여부를 판정한다.

    반환: {"visible": True|False|None, "ratio": float, "box": (x, y, w, h)|None,
           "method": "ml"|"hsv"}
    ratio 는 ml 이면 착용 확률, hsv 면 색 픽셀 비율이다.
    """
    clf = _get_classifier()
    box = chest_roi(frame_bgr.shape, face_box)
    if box is None:
        return {"visible": None, "ratio": 0.0, "box": None,
                "method": "ml" if clf is not None else "hsv"}
    x, y, w, h = box
    roi = frame_bgr[y:y + h, x:x + w]

    if clf is not None:
        score = clf.predict(roi)
        return {"visible": score >= JACKET_ML_THRESHOLD, "ratio": round(score, 3),
                "box": box, "method": "ml"}

    ratio = color_ratio(roi)
    return {"visible": ratio >= JACKET_MIN_COLOR_RATIO, "ratio": round(ratio, 3),
            "box": box, "method": "hsv"}
