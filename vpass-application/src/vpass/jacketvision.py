"""구명조끼 착용 시각 확인 (임시 구현).

구명조끼 모듈(홀센서) 신호만 믿으면 조끼를 입지 않은 채 버클만 채워
착용으로 위장하는 치팅이 가능하다. 그래서 승선 등록(얼굴 인식) 시점에
카메라 프레임의 얼굴 아래 상체 ROI 를 함께 검사해, 모듈 신호와 시각
확인이 모두 통과해야 승선 처리한다(판정은 boarding.BoardingManager).

현재는 상체 ROI 의 HSV 색상 비율 검사로 판정하는 임시 구현이다.
추후 구명조끼 객체 검출 모델을 학습해 이 모듈만 교체한다.

판정(visible):
  True  — 상체 ROI 의 구명조끼 색 비율이 기준 이상 (착용으로 판단)
  False — 상체 ROI 를 검사했지만 구명조끼 색 부족 (미착용으로 판단)
  None  — 상체가 화면 밖이라 판단 불가
"""

from __future__ import annotations

import cv2
import numpy as np

from .config import JACKET_COLOR_RANGES, JACKET_MIN_COLOR_RATIO, JACKET_ROI_MIN_VISIBLE

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


def color_ratio(roi_bgr) -> float:
    """ROI 픽셀 중 구명조끼 색(HSV 범위 합집합)에 드는 비율을 반환한다."""
    hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in JACKET_COLOR_RANGES:
        mask |= cv2.inRange(hsv, np.array(lo, np.uint8), np.array(hi, np.uint8))
    return float(cv2.countNonZero(mask)) / float(mask.size)


def assess_jacket(frame_bgr, face_box) -> dict:
    """얼굴 아래 상체의 색상 비율로 구명조끼 착용 여부를 판정한다.

    반환: {"visible": True|False|None, "ratio": float, "box": (x, y, w, h)|None}
    """
    box = chest_roi(frame_bgr.shape, face_box)
    if box is None:
        return {"visible": None, "ratio": 0.0, "box": None}
    x, y, w, h = box
    ratio = color_ratio(frame_bgr[y:y + h, x:x + w])
    return {"visible": ratio >= JACKET_MIN_COLOR_RATIO, "ratio": round(ratio, 3), "box": box}
