"""구명조끼 착용 자세 검증 (정면 → 옆모습).

가슴 ROI 한 장만 보면 조끼를 입지 않은 채 버클만 채워 몸 앞에 들고 있어도
'착용'으로 보인다. 입은 조끼는 몸통을 감싸므로 몸을 옆으로 돌려도 가슴 ROI 에
계속 보이지만, 들고 있는 조끼는 옆에서 보면 얇아지거나 사라진다. 그래서
얼굴 인식이 확정된 뒤 두 단계를 차례로 통과해야 승선 처리한다.

  1) front — 정면 자세에서 가슴 ROI(+어깨 ROI)에 조끼가 보인다
  2) side  — 몸을 한쪽으로 돌린 자세(어느 쪽이든)에서 상체가 "조끼 / 몸통 / 조끼"
             샌드위치 모양으로 보인다(jacketvision.assess_side_profile). 입은 조끼는
             앞판·뒤판이 몸통 양쪽에 보이지만 들고 있는 조끼는 한 덩어리뿐이다.

자세는 YuNet 5점 랜드마크로 판단한다: 코끝 x 가 두 눈 사이 구간의 어디에
있는지(0 = 한쪽 눈, 1 = 다른 쪽 눈). 정면 ≈ 0.5, 옆으로 돌리면 0 또는 1 쪽으로
간다(등록 때 쓰는 정면성 검사와 같은 값). 신원은 front 진입 시점(얼굴 인식
확정)에 한 번만 확인하고, 이후에는 얼굴 박스 연속성(위치·시간)으로 같은
사람임을 유지한다 — 옆모습으로 다시 인식하지 않으므로 옆얼굴 등록은 필요 없다.

LBPH 엔진은 랜드마크가 없어 자세를 알 수 없으므로 카메라가 이 검증을 건너뛴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config

# 오버레이 색상 (boarding.py 와 동일 토큰)
COLOR_OK = "#00FFA3"
COLOR_INFO = "#0A84FF"
COLOR_WARN = "#FF9F0A"
COLOR_DANGER = "#FF375F"


def pose_of(det) -> str | None:
    """랜드마크로 머리 방향을 분류한다: "front" | "side" | "between" | None(랜드마크 없음)."""
    lm = getattr(det, "landmarks", None)
    if lm is None:
        return None
    re_x, le_x, nose_x = float(lm[0][0]), float(lm[1][0]), float(lm[2][0])
    span = abs(le_x - re_x)
    if span <= 1.0:
        return "side"  # 두 눈이 겹칠 만큼 돌아감
    rel = (nose_x - min(re_x, le_x)) / span
    if config.FACE_ENROLL_YAW_MIN <= rel <= config.FACE_ENROLL_YAW_MAX:
        return "front"
    if rel <= config.JACKET_TURN_SIDE_YAW or rel >= 1.0 - config.JACKET_TURN_SIDE_YAW:
        return "side"
    return "between"


def same_face(prev_box, box) -> bool:
    """두 얼굴 박스가 같은 사람의 연속 프레임으로 볼 수 있는지 (위치·크기 연속성)."""
    px, py, pw, ph = prev_box
    x, y, w, h = box
    pcx, pcy = px + pw / 2, py + ph / 2
    cx, cy = x + w / 2, y + h / 2
    limit = 0.8 * max(pw, w)
    if abs(cx - pcx) > limit or abs(cy - pcy) > limit:
        return False
    ratio = w / pw if pw else 0
    return 0.5 <= ratio <= 2.0


@dataclass
class TurnStatus:
    state: str          # "front" | "side" | "passed" | "failed" | "lost"
    progress: int       # 현재 단계에서 모은 연속 프레임 수
    need: int
    message: str        # 오버레이 안내(한글)
    tag: str            # 카메라 화면 주석(영문, cv2.putText 용)
    color: str = COLOR_INFO


class TurnVerifier:
    """한 사람에 대한 정면 → 옆모습 검증 상태기계. 카메라 스레드에서만 쓴다."""

    def __init__(self, user: dict, now: float, *, need: int | None = None,
                 timeout: float | None = None, face_gap: float | None = None,
                 shoulder_check=None, side_check=None):
        self.user = user
        self.user_id = user.get("id") or user.get("name", "")
        self.need = max(1, need if need is not None else config.JACKET_TURN_FRAMES)
        self.timeout = timeout if timeout is not None else config.JACKET_TURN_TIMEOUT_SEC
        self.face_gap = face_gap if face_gap is not None else config.JACKET_TURN_FACE_GAP_SEC
        # (frame, face_box) -> {"visible": True|False|None, ...}; None 이면 어깨 검사 생략
        self._shoulder_check = shoulder_check
        # (frame, face_box) -> 샌드위치 판정 dict; None 이면 옆모습도 가슴 ROI(jacket) 로 판정
        self._side_check = side_check
        self.last_side: dict | None = None      # 마지막 옆모습 판정(화면 표시용)
        self.stage = "front"
        self.count = 0           # 현재 단계 연속 통과 프레임
        self.fail_count = 0      # side 단계에서 '옆모습인데 조끼 없음' 연속 횟수
        self.started = now
        self.last_seen = now
        self.last_box = None
        self.front_jacket: dict | None = None   # 정면 통과 시점의 조끼 판정(승선 기록용)
        self.side: str | None = None            # 통과한 옆모습 방향(표시용)

    def lost(self, now: float) -> bool:
        """얼굴이 face_gap 이상 안 보였으면 추적 종료."""
        return now - self.last_seen > self.face_gap

    def update(self, det, jacket: dict | None, frame, now: float) -> TurnStatus:
        if self.timeout > 0 and now - self.started > self.timeout:
            return TurnStatus("failed", self.count, self.need,
                              "구명조끼 확인 시간 초과 · 정면을 보고 다시 인식해 주세요",
                              "TURN TIMEOUT", COLOR_DANGER)
        if self.lost(now) or (self.last_box is not None and not same_face(self.last_box, det.box)):
            return TurnStatus("lost", 0, self.need, "", "TRACK LOST", COLOR_WARN)
        self.last_seen = now
        self.last_box = det.box

        pose = pose_of(det) or "between"
        visible = None if jacket is None else jacket.get("visible")

        if self.stage == "front":
            return self._update_front(pose, visible, jacket, det, frame)
        if pose == "side" and self._side_check is not None:
            self.last_side = self._side_check(frame, det.box)
            visible = self.last_side.get("visible")
        return self._update_side(pose, visible, det)

    # ── 단계별 처리 ──────────────────────────────────────────────────────
    def _update_front(self, pose, visible, jacket, det, frame) -> TurnStatus:
        if pose != "front":
            self.count = 0
            return self._status("front", "정면을 봐 주세요", "FRONT: LOOK AHEAD")
        if visible is None:
            self.count = 0
            return self._status("front", "상체가 화면에 나오게 서 주세요", "FRONT: STEP BACK", COLOR_WARN)
        if visible is not True:
            self.count = 0
            return self._status("front", "구명조끼가 카메라에 확인되지 않습니다 · 착용 후 다시 인식해 주세요",
                                "FRONT: NO JACKET", COLOR_DANGER)
        if self._shoulder_check is not None:
            sh = self._shoulder_check(frame, det.box)
            if sh is not None and sh.get("visible") is False:
                self.count = 0
                return self._status("front", "어깨까지 구명조끼가 보이게 서 주세요",
                                    "FRONT: SHOULDERS", COLOR_WARN)
        self.count += 1
        if self.count >= self.need:
            self.stage, self.count, self.fail_count = "side", 0, 0
            self.front_jacket = dict(jacket)
            return self._status("side", "정면 확인 완료 · 몸을 한쪽 옆으로 돌려 주세요",
                                "FRONT OK -> TURN SIDE")
        return self._status("front", f"정면 확인 중 ({self.count}/{self.need}) · 그대로 계셔 주세요",
                            f"FRONT {self.count}/{self.need}")

    def _update_side(self, pose, visible, det) -> TurnStatus:
        if pose != "side":
            self.count = 0
            return self._status("side", "몸을 한쪽 옆으로 더 돌려 주세요", "TURN SIDE")
        if visible is None:
            self.count = 0
            return self._status("side", "상체가 화면에 나오게 서 주세요", "SIDE: STEP BACK", COLOR_WARN)
        if visible is not True:
            self.count = 0
            self.fail_count += 1
            if self.fail_count >= self.need:
                return TurnStatus("failed", 0, self.need,
                                  "옆에서 구명조끼 앞판·뒤판이 확인되지 않습니다 · 조끼를 입고 다시 인식해 주세요",
                                  "SIDE: NO SANDWICH", COLOR_DANGER)
            return self._status("side", f"옆모습 확인 중 · 구명조끼 앞판·뒤판이 보이지 않습니다 ({self.fail_count}/{self.need})",
                                f"SIDE: NO SANDWICH {self.fail_count}/{self.need}", COLOR_WARN)
        self.fail_count = 0
        self.count += 1
        if self.count >= self.need:
            self.side = self._side_name(det)
            return TurnStatus("passed", self.count, self.need,
                              "옆모습 확인 완료", "SIDE OK", COLOR_OK)
        return self._status("side", f"옆모습 확인 중 ({self.count}/{self.need}) · 그대로 계셔 주세요",
                            f"SIDE {self.count}/{self.need}")

    def _status(self, state, message, tag, color=COLOR_INFO) -> TurnStatus:
        return TurnStatus(state, self.count, self.need, message, tag, color)

    @staticmethod
    def _side_name(det) -> str | None:
        lm = getattr(det, "landmarks", None)
        if lm is None:
            return None
        re_x, le_x, nose_x = float(lm[0][0]), float(lm[1][0]), float(lm[2][0])
        return "left" if nose_x < (re_x + le_x) / 2 else "right"
