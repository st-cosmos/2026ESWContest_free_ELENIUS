"""구명조끼 착용 자세 검증 (정면 → 옆모습).

가슴 ROI 한 장만 보면 조끼를 입지 않은 채 버클만 채워 몸 앞에 들고 있어도
'착용'으로 보인다. 입은 조끼는 몸통을 감싸므로 몸을 옆으로 돌리면 "조끼(앞판) /
몸통·팔 / 조끼(뒤판)" 샌드위치 모양이 되지만, 들고 있는 조끼는 앞쪽 한 덩어리만
보인다. 그래서 얼굴 인식이 확정된 뒤 두 단계를 차례로 통과해야 승선 처리한다.

  1) front — 정면 자세(YuNet 랜드마크: 코가 두 눈 사이 30~70%)에서 가슴 ROI 에
             조끼가 보인다. 통과 시점의 얼굴 박스를 '기준 위치(anchor)'로 저장한다.
  2) side  — 기준 위치 아래 넓은 가로 띠에서 샌드위치 패턴이 나온다.
  각 단계는 조건이 JACKET_TURN_HOLD_SEC(기본 3초) 동안 끊기지 않고 유지돼야 통과한다 —
  잠깐 비추고 지나가는 것으로는 승선되지 않는다. JACKET_TURN_GRACE_SEC 이내의 순간
  끊김(검출 흔들림)은 봐준다.
             (jacketvision.assess_side_profile). **이 단계는 얼굴 검출이 필요 없다** —
             옆으로 돌린 얼굴은 검출기가 자주 놓치므로, 사람이 그 자리에서 몸만
             돌린다고 보고 정면 때의 위치를 그대로 쓴다. 정면 자세에서는 조끼가 한
             덩어리로 보여 샌드위치가 나오지 않으므로 '돌렸는지' 를 따로 판단하지 않아도 된다.

신원은 front 진입 시점(얼굴 인식 확정)에 한 번만 확인한다. side 단계에서 얼굴이
다시 검출되면 기준 위치와의 연속성(위치·크기)으로 같은 사람인지 보고, 멀리 떨어진
얼굴이면 추적을 끊는다(카메라는 정면 얼굴이 다른 사용자로 인식되면 추가로 끊는다).
얼굴이 전혀 안 보이는 상태가 JACKET_TURN_NOFACE_SEC 넘게 이어지면 자리를 떠난
것으로 보고 끊는다. 그 외에는 시간 제한 없이 기다린다(JACKET_TURN_TIMEOUT_SEC > 0 이면 제한).

LBPH 엔진은 랜드마크가 없어 정면 자세를 알 수 없으므로 카메라가 이 검증을 건너뛴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config

# 오버레이 색상 (boarding.py 와 동일 토큰)
COLOR_OK = "#00FFA3"
COLOR_INFO = "#0A84FF"
COLOR_WARN = "#FF9F0A"
COLOR_DANGER = "#FF375F"

# side 단계가 이만큼 지나도 샌드위치가 안 나오면 안내 문구를 '조끼를 입었는지 확인' 으로 바꾼다
SIDE_HINT_AFTER_SEC = 6.0


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
    progress: float     # 현재 단계에서 조건이 유지된 시간(초)
    need: float         # 통과에 필요한 유지 시간(초)
    message: str        # 오버레이 안내(한글)
    tag: str            # 카메라 화면 주석(영문, cv2.putText 용)
    color: str = COLOR_INFO


class TurnVerifier:
    """한 사람에 대한 정면 → 옆모습 검증 상태기계. 카메라 스레드에서만 쓴다."""

    def __init__(self, user: dict, now: float, *, hold: float | None = None,
                 grace: float | None = None, timeout: float | None = None,
                 face_gap: float | None = None, noface_limit: float | None = None,
                 shoulder_check=None, side_check=None):
        self.user = user
        self.user_id = user.get("id") or user.get("name", "")
        # 단계 통과에 필요한 조건 유지 시간과, 그 사이 허용하는 순간 끊김
        self.hold = max(0.0, hold if hold is not None else config.JACKET_TURN_HOLD_SEC)
        self.grace = max(0.0, grace if grace is not None else config.JACKET_TURN_GRACE_SEC)
        self.timeout = timeout if timeout is not None else config.JACKET_TURN_TIMEOUT_SEC
        self.face_gap = face_gap if face_gap is not None else config.JACKET_TURN_FACE_GAP_SEC
        self.noface_limit = (noface_limit if noface_limit is not None
                             else config.JACKET_TURN_NOFACE_SEC)
        # (frame, face_box) -> {"visible": True|False|None, ...}; None 이면 어깨 검사 생략(기본)
        self._shoulder_check = shoulder_check
        # (frame, anchor_box) -> 샌드위치 판정 dict; None 이면 옆모습 단계를 가슴 ROI(jacket) 로 판정
        self._side_check = side_check
        self.stage = "front"
        self.hold_since: float | None = None   # 현재 단계 조건이 이어지기 시작한 시각
        self.last_ok: float | None = None      # 조건이 마지막으로 만족된 시각(grace 판정용)
        self.started = now
        self.side_started: float | None = None
        self.last_seen = now     # 마지막으로 얼굴이 검출된 시각
        self.last_box = None     # 마지막 얼굴 박스 (front 단계 연속성용)
        self.anchor_box = None   # front 통과 시점의 얼굴 박스 — side 단계 띠 위치 기준
        self.front_jacket: dict | None = None   # 정면 통과 시점의 조끼 판정(승선 기록용)
        self.last_side: dict | None = None      # 마지막 옆모습 판정(화면 표시용)

    def lost(self, now: float) -> bool:
        """front 단계에서 얼굴이 face_gap 이상 안 보였으면 추적 종료."""
        return now - self.last_seen > self.face_gap

    def update(self, det, jacket: dict | None, frame, now: float) -> TurnStatus:
        """검출 결과 한 번을 반영한다. side 단계에서는 det 가 None 이어도 된다."""
        if self.timeout > 0 and now - self.started > self.timeout:
            return TurnStatus("failed", self.held(now), self.hold,
                              "구명조끼 확인 시간 초과 · 정면을 보고 다시 인식해 주세요",
                              "TURN TIMEOUT", COLOR_DANGER)
        if self.stage == "front":
            return self._update_front(det, jacket, frame, now)
        return self._update_side(det, jacket, frame, now)

    # ── 1) 정면 ──────────────────────────────────────────────────────────
    def _update_front(self, det, jacket, frame, now) -> TurnStatus:
        if det is None:
            if self.lost(now):
                return TurnStatus("lost", 0.0, self.hold, "", "TRACK LOST", COLOR_WARN)
            self._miss(now)
            return self._status("front", "정면을 봐 주세요", "FRONT: FACE?", now=now)
        if self.lost(now) or (self.last_box is not None and not same_face(self.last_box, det.box)):
            return TurnStatus("lost", 0.0, self.hold, "", "TRACK LOST", COLOR_WARN)
        self.last_seen = now
        self.last_box = det.box

        pose = pose_of(det) or "between"
        visible = None if jacket is None else jacket.get("visible")
        if pose != "front":
            self._miss(now)
            return self._status("front", "정면을 봐 주세요", "FRONT: LOOK AHEAD", now=now)
        if visible is None:
            self._miss(now)
            return self._status("front", "상체가 화면에 나오게 서 주세요", "FRONT: STEP BACK",
                                COLOR_WARN, now=now)
        if visible is not True:
            self._miss(now)
            return self._status("front", "구명조끼가 카메라에 확인되지 않습니다 · 착용 후 다시 인식해 주세요",
                                "FRONT: NO JACKET", COLOR_DANGER, now=now)
        if self._shoulder_check is not None:
            sh = self._shoulder_check(frame, det.box)
            if sh is not None and sh.get("visible") is False:
                self._miss(now)
                return self._status("front", "어깨까지 구명조끼가 보이게 서 주세요",
                                    "FRONT: SHOULDERS", COLOR_WARN, now=now)
        if self._hit(now):
            self.stage = "side"
            self.hold_since = self.last_ok = None
            self.side_started = now
            self.anchor_box = det.box
            self.front_jacket = dict(jacket)
            return self._status("side", "정면 확인 완료 · 몸을 한쪽 옆으로 돌려 주세요",
                                "FRONT OK -> TURN SIDE", now=now)
        held = self.held(now)
        return self._status("front", f"정면 확인 중 ({held:.0f}/{self.hold:.0f}초) · 그대로 계셔 주세요",
                            f"FRONT {held:.1f}/{self.hold:.0f}s", now=now)

    # ── 2) 옆모습 (얼굴 검출 불필요) ──────────────────────────────────────
    def _update_side(self, det, jacket, frame, now) -> TurnStatus:
        if det is not None:
            # 얼굴이 보이면 기준 위치와의 연속성만 확인한다 (멀리 떨어진 얼굴 = 다른 사람/이동)
            if not same_face(self.anchor_box, det.box):
                return TurnStatus("lost", 0.0, self.hold, "", "TRACK LOST", COLOR_WARN)
            self.last_seen = now
        elif self.noface_limit > 0 and now - self.last_seen > self.noface_limit:
            # 얼굴이 한참 안 보임 — 자리를 떠난 것으로 보고 처음부터
            return TurnStatus("lost", 0.0, self.hold, "", "TRACK LOST", COLOR_WARN)

        if self._side_check is not None:
            self.last_side = self._side_check(frame, self.anchor_box)
            visible = self.last_side.get("visible")
        else:
            visible = None if jacket is None else jacket.get("visible")

        if visible is None:
            self._miss(now)
            return self._status("side", "상체가 화면에 나오게 서 주세요", "SIDE: STEP BACK", COLOR_WARN, now=now)
        if visible is not True:
            self._miss(now)
            if self.hold_since is not None:
                # 유예 중(잠깐 끊김) — 유지 시간은 그대로 보여 준다
                held = self.held(now)
                return self._status("side", f"옆모습 확인 중 ({held:.0f}/{self.hold:.0f}초) · 그대로 계셔 주세요",
                                    f"SIDE {held:.1f}/{self.hold:.0f}s", now=now)
            waited = now - (self.side_started or now)
            if waited >= SIDE_HINT_AFTER_SEC:
                return self._status("side",
                                    "옆에서 구명조끼 앞판·뒤판이 함께 보여야 합니다 · 조끼를 입고 몸을 옆으로 돌려 주세요",
                                    "TURN SIDE: NO J/B/J", COLOR_WARN, now=now)
            return self._status("side", "몸을 한쪽 옆으로 돌려 주세요", "TURN SIDE", now=now)
        if self._hit(now):
            return TurnStatus("passed", self.held(now), self.hold, "옆모습 확인 완료", "SIDE OK", COLOR_OK)
        held = self.held(now)
        return self._status("side", f"옆모습 확인 중 ({held:.0f}/{self.hold:.0f}초) · 그대로 계셔 주세요",
                            f"SIDE {held:.1f}/{self.hold:.0f}s", now=now)

    # ── 유지 시간 관리 ───────────────────────────────────────────────────
    def _hit(self, now: float) -> bool:
        """조건 만족 1회. 유지 시간이 hold 를 채웠으면 True."""
        if self.hold_since is None:
            self.hold_since = now
        self.last_ok = now
        return now - self.hold_since >= self.hold

    def _miss(self, now: float) -> None:
        """조건 불만족 1회. grace 를 넘겨 끊겼으면 유지 시간을 처음부터 다시 센다."""
        if self.hold_since is not None and (self.last_ok is None or now - self.last_ok > self.grace):
            self.hold_since = self.last_ok = None

    def held(self, now: float) -> float:
        """현재 단계에서 조건이 유지된 시간(초)."""
        return 0.0 if self.hold_since is None else max(0.0, now - self.hold_since)

    def _status(self, state, message, tag, color=COLOR_INFO, *, now: float) -> TurnStatus:
        return TurnStatus(state, self.held(now), self.hold, message, tag, color)
