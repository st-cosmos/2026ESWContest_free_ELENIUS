# -*- coding: utf-8 -*-
"""핵심 안전 시나리오 상태 머신 검증 (카메라/하드웨어 불필요).

실행: uv run python tests/test_flow.py
"""

import os
import sys
import tempfile
import time

# 테스트용 임시 데이터 디렉터리
os.environ["VPASS_DATA_DIR"] = tempfile.mkdtemp(prefix="vpass-test-")

from vpass import config  # noqa: E402
from vpass.gps import NmeaGpsReader  # noqa: E402
from vpass.reset import reset_data  # noqa: E402
from vpass.runtime import Runtime  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = ""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def main():
    print("\n== 0) NMEA GPS 파서 검증 ==")
    gps = NmeaGpsReader("/dev/null", 9600)
    gps.update_from_nmea("$GPGGA,123519,3448.125,N,12825.402,E,1,08,0.9,12.3,M,46.9,M,,")
    fix = gps.snapshot()
    check("GGA 좌표 파싱", fix["valid"] and abs(fix["latitude"] - 34.8020833) < 0.0001)
    check("GGA 위성/고도 파싱", fix["satellites"] == 8 and fix["altitude_m"] == 12.3)

    # 판정 시간을 테스트용으로 단축 (신호 두절 판정은 ping 주기 3초보다 길어야 함)
    import vpass.lifejacket as lj
    lj.SIGNAL_LOSS_TIMEOUT = 4.5
    lj.SIGNAL_LOSS_WARNING_SEC = 3.0  # 운영값 20초 → 테스트용 단축
    lj.FALL_PING_TIMEOUT = 1.5

    rt = Runtime()
    rt.devices.start()  # 카메라 없이 감시 루프만 시작
    rt.telemetry.start()

    print("\n== 1) 초기 상태: 시동 잠금 ==")
    eng = rt.engine.snapshot()
    check("시동 잠금(locked)", eng["locked"] and eng["engaged"])

    print("\n== 2) 사용자 등록(직접 주입) + 구명조끼 착용 ==")
    user = {"id": "u1", "name": "홍길동", "phone": "010-1234-5678",
            "device_id": "jacket-1", "photo": None,
            "registered_at": "2026-08-01 09:00:00"}
    rt.users_store.save([user])

    # 착용 신호(착용 중인 장치)가 하나도 없는 상태에서 얼굴 인식 → 승선 거부
    rt.boarding.handle_recognition(user)
    check("착용 신호 없으면 승선 거부", rt.boarding.count() == 0)
    check("착용 신호 없음 경고", "착용 신호가 없습니다" in rt.overlay.get()["text"])
    check("착용 장치 없음 → 자세 검증 시작 조건 미충족", rt.boarding.has_claimable_device() is False)

    # 구명조끼 착용 (시뮬레이터 = 실장치와 동일 경로)
    jacket = rt.sim_jacket("jacket-1")
    jacket.apply("wear")
    time.sleep(0.2)
    check("착용 인식", rt.devices.is_worn("jacket-1") is True)
    check("착용 장치 있음 → 자세 검증 시작 가능", rt.boarding.has_claimable_device() is True)

    print("\n== 2-1) 구명조끼 시각 확인 (HSV 폴백 경로) ==")
    import numpy as np  # noqa: E402
    from vpass import jacketvision  # noqa: E402

    # 모델 유무와 무관하게 HSV 폴백 경로를 검증하도록 분류기를 비활성화한다
    jacketvision._CLASSIFIER = None
    jacketvision._CLASSIFIER_LOADED = True

    face_box = (270, 80, 100, 100)                  # 화면 중앙 상단의 얼굴
    plain = np.full((480, 640, 3), 60, np.uint8)    # 무채색 배경/옷
    r = jacketvision.assess_jacket(plain, face_box)
    check("무채색 상체 → 미확인",
          r["visible"] is False and r["box"] is not None and r["method"] == "hsv", str(r))

    orange = plain.copy()
    bx, by, bw, bh = r["box"]
    orange[by:by + bh, bx:bx + bw] = (0, 128, 255)  # 상체 ROI 를 주황(BGR)으로 채움
    r2 = jacketvision.assess_jacket(orange, face_box)
    check("주황 상체 → 착용 확인", r2["visible"] is True and r2["ratio"] > 0.9, str(r2))

    r3 = jacketvision.assess_jacket(plain, (270, 380, 100, 100))  # 얼굴이 화면 하단
    check("상체 화면 밖 → 판단 불가", r3["visible"] is None and r3["box"] is None, str(r3))

    print("\n== 2-2) 구명조끼 시각 확인 (ML 분류기 경로) ==")

    class _StubClassifier:
        """TFLite 분류기 대역 — 고정 착용 확률을 돌려준다."""
        def __init__(self, score):
            self.score = score

        def predict(self, roi_bgr):
            assert roi_bgr.size > 0
            return self.score

    jacketvision._CLASSIFIER = _StubClassifier(0.92)
    m1 = jacketvision.assess_jacket(plain, face_box)
    check("확률 0.92 → 착용 확인",
          m1["visible"] is True and m1["ratio"] == 0.92 and m1["method"] == "ml", str(m1))

    jacketvision._CLASSIFIER = _StubClassifier(0.08)
    m2 = jacketvision.assess_jacket(plain, face_box)
    check("확률 0.08 → 미확인", m2["visible"] is False and m2["method"] == "ml", str(m2))

    m3 = jacketvision.assess_jacket(plain, (270, 380, 100, 100))
    check("ML 이라도 상체 화면 밖 → 판단 불가", m3["visible"] is None and m3["box"] is None, str(m3))

    jacketvision._CLASSIFIER = None  # 이후 테스트는 다시 HSV 폴백

    # 모듈은 착용(치팅 가능 상태)이라도 카메라 확인을 통과해야 승선된다
    rt.boarding._notice_times.clear()
    rt.boarding.handle_recognition(user, {"visible": False, "ratio": 0.02, "box": (0, 0, 10, 10)})
    check("카메라 미확인 시 승선 거부", rt.boarding.count() == 0)
    check("카메라 미확인 경고", "카메라에 확인되지 않습니다" in rt.overlay.get()["text"])
    rt.boarding.handle_recognition(user, {"visible": None, "ratio": 0.0, "box": None})
    check("판단 불가 시 승선 보류", rt.boarding.count() == 0)
    check("판단 불가 안내", "상체가 화면에" in rt.overlay.get()["text"])

    print("\n== 2-3) 구명조끼 자세 검증 (정면 → 옆모습, 들고 있는 조끼 걸러내기) ==")
    from vpass.facerec import Detection  # noqa: E402
    from vpass.jacketturn import TurnVerifier, pose_of, same_face  # noqa: E402

    def det_at(x, y, w, h, rel):
        """코 위치 비율 rel(0=한쪽 눈, 1=다른 쪽 눈)을 갖는 가짜 검출. 눈 간격 = 0.4w."""
        re_x, le_x = x + w * 0.3, x + w * 0.7
        nose_x = re_x + (le_x - re_x) * rel
        lm = np.array([[re_x, y + h * 0.4], [le_x, y + h * 0.4], [nose_x, y + h * 0.6],
                       [x + w * 0.35, y + h * 0.8], [x + w * 0.65, y + h * 0.8]], np.float32)
        return Detection((x, y, w, h), 0.95, lm)

    FB = (270, 80, 100, 100)
    front, side_l, side_r = det_at(*FB, 0.5), det_at(*FB, 0.1), det_at(*FB, 0.95)
    between = det_at(*FB, 0.26)
    check("자세: 정면", pose_of(front) == "front")
    check("자세: 한쪽 옆모습", pose_of(side_l) == "side")
    check("자세: 반대쪽 옆모습", pose_of(side_r) == "side")
    check("자세: 돌리는 중", pose_of(between) == "between")
    check("자세: 랜드마크 없음(LBPH) → None", pose_of(Detection(FB)) is None)
    check("연속성: 같은 자리의 얼굴", same_face(FB, (280, 85, 100, 100)))
    check("연속성: 멀리 뛴 박스는 다른 사람", not same_face(FB, (30, 300, 100, 100)))

    # 어깨 패치: 무채색 → 미확인 / 어깨만 주황 → 확인 / 얼굴이 화면 하단 → 판단 불가
    sh0 = jacketvision.assess_shoulders(plain, FB)
    check("어깨 무채색 → 미확인", sh0["visible"] is False and len(sh0["boxes"]) == 2, str(sh0))
    shoulders = plain.copy()
    for (sx, sy, sw, shh) in sh0["boxes"]:
        shoulders[sy:sy + shh, sx:sx + sw] = (0, 128, 255)
    sh1 = jacketvision.assess_shoulders(shoulders, FB)
    check("어깨 주황 → 확인", sh1["visible"] is True and min(sh1["ratios"]) > 0.9, str(sh1))
    check("어깨 화면 밖 → 판단 불가",
          jacketvision.assess_shoulders(plain, (270, 420, 100, 100))["visible"] is None)

    # 옆모습 샌드위치 판정: 얼굴 아래 가로 띠에서 조끼/몸통/조끼 열 구간을 찾는다
    band = jacketvision.side_band_roi(plain.shape, FB)
    check("옆모습 띠 ROI 생성", band is not None and band[2] > 250, str(band))
    bx0, by0, bw0, bh0 = band
    sw_ok = plain.copy()
    third = bw0 // 3
    sw_ok[by0:by0 + bh0, bx0:bx0 + third] = (0, 128, 255)                 # 앞판(주황)
    sw_ok[by0:by0 + bh0, bx0 + 2 * third:bx0 + bw0] = (0, 128, 255)       # 뒤판(주황), 가운데는 몸통(회색)
    sp = jacketvision.assess_side_sandwich(sw_ok, FB)
    check("조끼/몸통/조끼 → 착용", sp["visible"] is True and sp["sandwich"] is not None, str(sp))
    check("구간 3개(조끼·몸통·조끼)",
          [f for _, _, f in sp["segments"]] == [True, False, True], str(sp["segments"]))
    one_side = plain.copy()
    one_side[by0:by0 + bh0, bx0:bx0 + bw0 // 2] = (0, 128, 255)          # 앞쪽 한 덩어리만(들고 있음)
    check("조끼 한 덩어리만 → 미착용",
          jacketvision.assess_side_sandwich(one_side, FB)["visible"] is False)
    full = plain.copy()
    full[by0:by0 + bh0, bx0:bx0 + bw0] = (0, 128, 255)                    # 띠 전체 주황(가운데 몸통 없음)
    check("몸통 구간 없음 → 미착용", jacketvision.assess_side_sandwich(full, FB)["visible"] is False)
    check("무채색 → 미착용", jacketvision.assess_side_sandwich(plain, FB)["visible"] is False)
    noisy = sw_ok.copy()
    mid = bx0 + bw0 // 2
    noisy[by0:by0 + bh0, mid:mid + 3] = (0, 128, 255)                     # 몸통 가운데 3px 잡음
    check("몸통 속 잡음 열은 무시", jacketvision.assess_side_sandwich(noisy, FB)["visible"] is True)
    check("띠 화면 밖 → 판단 불가",
          jacketvision.assess_side_sandwich(plain, (270, 420, 100, 100))["visible"] is None)
    # 구간 분할/샌드위치 탐색 단위 검사
    segs = jacketvision.column_segments([0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 0], 0.5, min_run=2)
    check("열 구간 분할", segs == [(0, 2, False), (2, 5, True), (5, 7, False), (7, 10, True), (10, 11, False)], str(segs))
    check("샌드위치 탐색", jacketvision.find_sandwich(segs, 2, 2) == ((2, 5), (5, 7), (7, 10)))

    # 옆모습 분류 모델이 있으면 색 규칙 대신 모델 점수로 판정한다
    class _StubSide:
        def __init__(self, score):
            self.score = score

        def predict(self, roi):
            return self.score

    saved = (jacketvision._SIDE_CLASSIFIER, jacketvision._SIDE_CLASSIFIER_LOADED)
    try:
        jacketvision._SIDE_CLASSIFIER_LOADED = True
        jacketvision._SIDE_CLASSIFIER = _StubSide(0.8)
        r = jacketvision.assess_side_profile(plain, FB)
        check("옆모습 모델 있으면 모델로 판정(착용)", r["method"] == "ml" and r["visible"] is True, str(r))
        jacketvision._SIDE_CLASSIFIER = _StubSide(0.2)
        r = jacketvision.assess_side_profile(sw_ok, FB)
        check("옆모습 모델이 미착용이면 샌드위치가 있어도 미착용", r["visible"] is False, str(r))
        jacketvision._SIDE_CLASSIFIER = None
        check("옆모습 모델 없으면 색 규칙으로 폴백",
              jacketvision.assess_side_profile(sw_ok, FB)["method"] == "sandwich")
    finally:
        jacketvision._SIDE_CLASSIFIER, jacketvision._SIDE_CLASSIFIER_LOADED = saved
    check("조끼 구간 하나면 없음", jacketvision.find_sandwich([(0, 5, True), (5, 9, False)], 2, 2) is None)

    JK_ON = {"visible": True, "ratio": 0.6, "box": (225, 205, 190, 165), "method": "hsv"}
    JK_OFF = {"visible": False, "ratio": 0.05, "box": (225, 205, 190, 165), "method": "hsv"}
    JK_NA = {"visible": None, "ratio": 0.0, "box": None, "method": "hsv"}

    def shoulder_ok(frame, box):
        return {"visible": True}

    def shoulder_bad(frame, box):
        return {"visible": False}

    def side_ok(frame, box):
        return {"visible": True, "box": (0, 0, 10, 10), "segments": []}

    def side_bad(frame, box):
        return {"visible": False, "box": (0, 0, 10, 10), "segments": []}

    t0 = 1000.0
    HOLD, GRACE, STEP = 3.0, 0.5, 0.2   # 3초 유지, 0.5초 끊김 허용, 검출 주기 0.2초

    def new_verifier(shoulder=None, side=side_ok):
        return TurnVerifier(user, t0, hold=HOLD, grace=GRACE, timeout=0, face_gap=1.0,
                            shoulder_check=shoulder, side_check=side)

    def feed(v, det, jacket, start, seconds):
        """start 부터 seconds 동안 STEP 간격으로 같은 입력을 넣고 마지막 상태를 돌려준다."""
        t, s = start, None
        while t <= start + seconds + 1e-9:
            s = v.update(det, jacket, plain, t)
            t += STEP
        return s, t

    # (a) 정상 착용: 정면 3초 유지 → 옆모습(얼굴 없이) 3초 유지 → 통과
    v = new_verifier()
    s, t = feed(v, front, JK_ON, t0, 1.0)
    check("정면 1초 → 아직 진행 중", s.state == "front" and 0.9 <= s.progress <= 1.1, str(s))
    s, t = feed(v, front, JK_ON, t, 2.2)
    check("정면 3초 유지 → 옆모습 단계", s.state == "side" and v.stage == "side" and v.anchor_box == FB, str(s))
    check("정면 통과 시 조끼 판정 보관", v.front_jacket == JK_ON)
    s, t = feed(v, None, None, t, 1.0)
    # 정면 단계가 3.0초에 통과한 뒤 남은 0.2초 입력도 옆모습 유지 시간으로 들어가므로 1.0~1.5초
    check("옆모습 1초 → 아직 진행 중(얼굴 없이 진행)", s.state == "side" and 0.9 <= s.progress <= 1.5, str(s))
    s, t = feed(v, None, None, t, 2.2)
    check("옆모습 3초 유지 → 통과", s.state == "passed", str(s))

    # (a-2) 잠깐 비추기만 하면 통과하지 않는다
    v = new_verifier()
    s, t = feed(v, front, JK_ON, t0, 0.6)
    check("정면 0.6초만 비춤 → 통과 안 됨", s.state == "front" and v.stage == "front")

    # (a-3) 0.5초 이내 끊김은 봐주고, 그 이상 끊기면 처음부터
    v = new_verifier()
    s, t = feed(v, front, JK_ON, t0, 2.0)
    s = v.update(front, JK_OFF, plain, t + 0.2)          # 0.4초 끊김 (grace 이내)
    s, t = feed(v, front, JK_ON, t + 0.4, 1.0)
    check("짧은 끊김은 유지 시간 보존 → 통과", v.stage == "side", str(s))
    v = new_verifier()
    s, t = feed(v, front, JK_ON, t0, 2.0)
    s, t = feed(v, front, JK_OFF, t, 1.0)                # 1초 끊김 (grace 초과)
    check("긴 끊김 → 유지 시간 초기화", s.state == "front" and s.progress == 0.0, str(s))
    s, t = feed(v, front, JK_ON, t, 1.0)
    check("초기화 후 다시 1초 → 아직 정면 단계", v.stage == "front" and 0.9 <= s.progress <= 1.1, str(s))

    # (b) 치팅: 조끼를 들고 있음 — 정면은 통과하지만 옆에서 샌드위치가 없음 → 통과하지 않음
    v = new_verifier(side=side_bad)
    feed(v, front, JK_ON, t0, 3.2)
    s, t = feed(v, side_r, JK_ON, t0 + 3.4, 8.0)         # 얼굴은 보이지만 샌드위치 없음
    check("샌드위치 없으면 통과하지 않음", s.state == "side" and s.progress == 0.0, str(s))
    check("오래 안 나오면 '조끼를 입었는지' 안내로 전환", "앞판" in s.message, s.message)
    check("마지막 옆모습 판정 보관(화면 표시용)", v.last_side is not None and v.last_side["visible"] is False)

    # (b-2) 치팅: 조끼를 들고 정면으로 서 있음 — 조끼 정면도 지퍼 쪽 안감 때문에 옆띠에
    #       샌드위치가 나온다. 얼굴이 정면이면 몸을 돌리지 않은 것이므로 통과하지 않아야 한다.
    v = new_verifier(side=side_ok)
    feed(v, front, JK_ON, t0, 3.2)
    s, t = feed(v, front, JK_ON, t0 + 3.4, 8.0)
    check("옆모습 단계에서 정면 얼굴이면 샌드위치가 나와도 통과 안 됨",
          s.state == "side" and s.progress == 0.0 and s.tag == "SIDE: FACING FRONT", str(s))
    check("정면 얼굴이면 '옆으로 돌려' 안내", "돌려" in s.message, s.message)
    s, t = feed(v, side_r, JK_ON, t, 1.0)
    check("옆 얼굴로 돌리면 유지 시간 쌓임", s.state == "side" and 0.9 <= s.progress <= 1.1, str(s))
    s = v.update(front, JK_ON, plain, t)
    check("잠깐이라도 정면 얼굴이면 유지 시간 즉시 초기화(grace 없음)", s.progress == 0.0, str(s))
    s, t = feed(v, None, None, t + 0.2, 3.2)
    check("다시 돌려 3초 유지 → 통과", s.state == "passed", str(s))

    # (b-3) 옆모습 띠는 지금 보이는 얼굴 위치를 따라간다 (돌면서 화면 안에서 움직임)
    seen_boxes = []

    def side_record(frame, box):
        seen_boxes.append(box)
        return {"visible": False, "box": (0, 0, 10, 10), "segments": []}

    v = new_verifier(side=side_record)
    feed(v, front, JK_ON, t0, 3.2)
    moved = det_at(FB[0] + 40, FB[1], FB[2], FB[3], 0.95)   # 옆 얼굴, 오른쪽으로 40px 이동
    v.update(moved, JK_ON, plain, t0 + 3.4)
    check("옆모습 띠가 지금 보이는 얼굴 위치를 따라감", seen_boxes[-1] == moved.box, str(seen_boxes[-1]))
    v.update(None, None, plain, t0 + 3.6)
    check("얼굴이 안 보이면 마지막으로 보인 위치 유지", seen_boxes[-1] == moved.box, str(seen_boxes[-1]))

    # (b-4) 몸을 돌리면서 얼굴이 얼굴폭만큼 옆으로 움직여도 추적을 유지한다
    v = new_verifier(side=side_bad)
    feed(v, front, JK_ON, t0, 3.2)
    shifted = det_at(FB[0] + int(FB[2] * 1.1), FB[1], FB[2], FB[3], 0.95)
    s = v.update(shifted, JK_ON, plain, t0 + 3.4)
    check("옆모습 단계: 얼굴폭 1.1배 이동은 같은 사람", s.state == "side", str(s))
    far = det_at(shifted.box[0] + int(FB[2] * 1.8), FB[1], FB[2], FB[3], 0.95)
    s = v.update(far, JK_ON, plain, t0 + 3.6)
    check("옆모습 단계: 얼굴폭 1.8배 이동은 추적 종료", s.state == "lost", str(s))

    # (c) 정면에서 조끼가 안 보이거나 상체가 화면 밖이면 안내
    v = new_verifier()
    s = v.update(front, JK_OFF, plain, t0)
    check("정면 조끼 미확인 안내", s.state == "front" and "확인되지 않습니다" in s.message)
    s = v.update(front, JK_NA, plain, t0 + 0.2)
    check("상체 화면 밖 → 안내", "상체가 화면에" in s.message)
    s = v.update(between, JK_ON, plain, t0 + 0.4)
    check("정면이 아니면 '정면을 봐 주세요'", "정면을" in s.message)

    # (d) 어깨 검사는 기본 꺼짐 — 명시적으로 켠 경우에만 동작
    check("어깨 검사 기본 꺼짐", config.JACKET_SHOULDER_CHECK is False)
    v = new_verifier(shoulder=shoulder_bad)
    s, t = feed(v, front, JK_ON, t0, 3.4)
    check("어깨 검사를 켠 경우 어깨 미확인이면 정면 단계 유지", v.stage == "front" and "어깨" in s.message)
    v = new_verifier(shoulder=shoulder_ok)
    s, t = feed(v, front, JK_ON, t0, 3.2)
    check("어깨 확인되면 통과", v.stage == "side")

    # (e) 시간 제한은 기본 없음 — 지정한 경우에만 초과로 실패
    v = TurnVerifier(user, t0, hold=HOLD, grace=GRACE, timeout=10, face_gap=1.0, side_check=side_bad)
    feed(v, front, JK_ON, t0, 3.2)
    s = v.update(None, None, plain, t0 + 10.5)
    check("시간 제한을 준 경우 초과 → 실패", s.state == "failed" and "시간 초과" in s.message)
    v = new_verifier(side=side_bad)
    feed(v, front, JK_ON, t0, 3.2)
    s, t = feed(v, front, JK_ON, t0 + 3.4, 120.0)        # 2분 동안 정면 유지 → 실패 없이 계속 안내
    check("기본값(제한 없음)은 오래 걸려도 계속 안내",
          s.state == "side" and "돌려" in s.message and config.JACKET_TURN_TIMEOUT_SEC == 0, str(s))

    # (f) 추적 종료 조건
    v = new_verifier()
    v.update(front, JK_ON, plain, t0 + 0.1)
    s = v.update(det_at(30, 300, 100, 100, 0.5), JK_ON, plain, t0 + 0.2)
    check("정면 단계에 다른 위치 얼굴 → 추적 종료", s.state == "lost")
    v = new_verifier()
    v.update(front, JK_ON, plain, t0 + 0.1)
    check("정면 단계에서 1초 넘게 사라짐 → 추적 종료",
          v.lost(t0 + 1.5) and v.update(front, JK_ON, plain, t0 + 1.5).state == "lost")
    v = new_verifier(side=side_bad)
    feed(v, front, JK_ON, t0, 3.2)
    s = v.update(None, None, plain, t0 + 8.0)
    check("옆모습 단계는 얼굴이 몇 초 안 보여도 유지", s.state == "side")
    s = v.update(det_at(30, 300, 100, 100, 0.5), None, plain, t0 + 8.5)
    check("옆모습 단계에 멀리 떨어진 얼굴 → 추적 종료", s.state == "lost")
    v = TurnVerifier(user, t0, hold=HOLD, grace=GRACE, timeout=0, face_gap=1.0, noface_limit=15,
                     side_check=side_bad)
    feed(v, front, JK_ON, t0, 3.2)
    s = v.update(None, None, plain, t0 + 19.0)
    check("옆모습 단계에서 15초 넘게 얼굴 없음 → 자리 떠남으로 종료", s.state == "lost")

    print("\n== 3) 얼굴 인식(모듈+카메라 확인) → 승선 목록에만 추가 (시동은 잠긴 채 유지) ==")
    rt.boarding._notice_times.clear()  # 쿨다운 초기화
    rt.boarding.handle_recognition(
        user, {"visible": True, "ratio": 0.42, "box": (225, 205, 190, 165), "turn": True, "side": "left"})
    check("승선 처리", rt.boarding.count() == 1)
    entry = rt.boarding.session()[0]
    check("자세 검증 통과 기록", entry.get("jacket_turn") is True, str(entry))
    check("환영 안내에 자세 확인 표기", "자세" in rt.overlay.get()["text"], rt.overlay.get()["text"])
    check("모듈+카메라 확인 기록",
          entry["lifejacket"] is True and entry["jacket_visual"] is True, str(entry))
    check("장치 동적 매칭(jacket-1)", entry["device_id"] == "jacket-1", str(entry))
    check("시동 잠금 유지", rt.engine.snapshot()["locked"])
    check("승선 로그 저장", len(rt.boarding_logs_store.load()) == 1)
    check("환영 인사 표시", "환영합니다" in rt.overlay.get()["text"], rt.overlay.get()["text"])

    # 카메라는 같은 얼굴을 초당 여러 번 다시 인식한다.
    # 그때마다 '이미 승선' 안내로 덮이면 환영 인사를 볼 수 없다.
    rt.boarding.handle_recognition(user, {"visible": True, "ratio": 0.42, "box": (225, 205, 190, 165)})
    check("연속 재인식에도 환영 인사 유지",
          "환영합니다" in rt.overlay.get()["text"], rt.overlay.get()["text"])
    check("중복 승선 방지", (rt.boarding.handle_recognition(user), rt.boarding.count())[1] == 1)

    print("\n== 4) 승선 확인 → 시동 허용 (출항 신고 아님) ==")
    try:
        rt.allow_engine_start()
        allowed = True
    except ValueError as e:
        allowed = False
        print(f"       allow_engine_start 실패: {e}")
    check("시동 허용 성공", allowed)
    check("시동 잠금 해제", not rt.engine.snapshot()["locked"])
    check("출항 신고는 아직 없음", rt.voyage.active_voyage() is None)

    deadline = time.time() + 30
    while time.time() < deadline and rt.telemetry.snapshot()["speed_kn"] < 3.0:
        time.sleep(0.5)
    check("순항 가속", rt.telemetry.snapshot()["speed_kn"] >= 3.0,
          f"speed={rt.telemetry.snapshot()['speed_kn']}")

    print("\n== 4-1) 지오펜스 통과 → 자동 출항 등록 ==")
    rt._handle_port_command("departure")
    v = rt.voyage.active_voyage()
    check("운항 기록 생성", v is not None)
    check("출항 신고 접수", bool(v and v["departure_reported"]))
    check("승선 명단 스냅샷", bool(v and len(v.get("crew", [])) == 1), str(v and v.get("crew")))

    rt._handle_port_command("departure")
    check("중복 출항 명령 무시", len(rt.voyage.list_voyages()) == 1)

    print("\n== 5) 익수 시나리오: 낙상 + 신호 두절 → 킬 스위치 + SOS ==")
    jacket.apply("overboard")  # 낙상 보고 후 ping 중단
    deadline = time.time() + 6
    while time.time() < deadline and not rt.devices.any_mob():
        time.sleep(0.2)
    check("익수(MOB) 감지", rt.devices.any_mob())
    eng = rt.engine.snapshot()
    check("킬 스위치 작동", eng["killed"] and eng["engaged"], str(eng))
    sos = rt.sos.active()
    check("SOS 자동 발보", sos is not None and sos["cause"] == "mob", str(sos))

    # 배가 멈추는지 (킬 스위치 → 감속)
    deadline = time.time() + 30
    while time.time() < deadline and rt.telemetry.snapshot()["speed_kn"] > 0.5:
        time.sleep(0.5)
    check("엔진 정지로 감속", rt.telemetry.snapshot()["speed_kn"] <= 0.5,
          f"speed={rt.telemetry.snapshot()['speed_kn']}")

    print("\n== 6) 상황 확인(ack) → 복구 ==")
    rt.ack_sos()
    check("SOS 해제", rt.sos.active() is None)
    check("익수 래치 해제", not rt.devices.any_mob())
    check("킬 스위치 복구", not rt.engine.snapshot()["killed"])

    def wait_warning(active: bool, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if bool(rt.devices.signal_warnings()) == active:
                return True
            time.sleep(0.1)
        return False

    print("\n== 7) 신호 두절 단독(낙상 없음) → 경고 단계 → 터치로 끄면 정상 운용 유지 ==")
    jacket.apply("resume")
    time.sleep(0.3)
    jacket.apply("silence")  # ping 만 중단 (낙상 이벤트 없음)
    check("두절 직후엔 경고 없음", not rt.devices.signal_warnings())
    check("두절 타임아웃 후 경고 시작(익수 아님)",
          wait_warning(True, 8) and not rt.devices.any_mob())
    sw = rt.state_snapshot()["lifejacket"]["signal_warning"]
    check("상태 스냅샷에 경고 노출(대상·카운트다운)",
          sw is not None and "홍길동" in sw["who"] and sw["device"] == "jacket-1"
          and 0 < sw["remaining_sec"] <= 3.0 and sw["total_sec"] == 3.0, str(sw))
    d = rt.devices.snapshot()[0]
    check("장치 스냅샷에 경고 진행 노출", d["signal_warning"] is not None, str(d))
    check("경고 중 오버레이 안내", "신호 두절" in rt.overlay.get()["text"], rt.overlay.get()["text"])
    check("모달 터치(ack) → 경고 해제", rt.ack_signal_warning("jacket-1") is True
          and not rt.devices.signal_warnings())
    time.sleep(3.5)  # 경고 시간이 지나도록 기다린다 — 끈 뒤에는 익수로 가지 않아야 한다
    check("끈 뒤 신호가 계속 없어도 익수 판정 없음(정상 운용 유지)", not rt.devices.any_mob())
    check("끈 뒤 재경고 없음", not rt.devices.signal_warnings())
    check("확인됨 상태 표시", rt.devices.snapshot()[0]["signal_warning_dismissed"] is True)
    check("킬 스위치 미작동", not rt.engine.snapshot()["killed"])
    check("빈 ack 는 False", rt.ack_signal_warning("jacket-1") is False)

    print("\n== 7-a) 신호 복귀 → 유예 해제, 다음 두절은 다시 경고 ==")
    jacket.apply("resume")
    time.sleep(0.2)
    check("신호 복귀 시 확인됨 상태 초기화",
          rt.devices.snapshot()[0]["signal_warning_dismissed"] is False)
    jacket.apply("silence")
    check("재두절 시 경고 재발생", wait_warning(True, 8) and not rt.devices.any_mob())
    jacket.apply("resume")
    check("경고 중 신호 복귀 → 경고 자동 해제", wait_warning(False, 1) and not rt.devices.any_mob())

    print("\n== 7-b) 경고 미응답 → 익수 판정 ==")
    jacket.apply("silence")
    check("경고 시작", wait_warning(True, 8))
    deadline = time.time() + 6
    while time.time() < deadline and not rt.devices.any_mob():
        time.sleep(0.2)
    check("미응답 시 익수(MOB) 판정", rt.devices.any_mob())
    d = rt.devices.snapshot()[0]
    check("원인=signal_loss", d["mob_cause"] == "signal_loss", str(d["mob_cause"]))
    check("익수 판정 시 경고는 내려감(SOS 모달로 전환)",
          d["signal_warning"] is None
          and rt.state_snapshot()["lifejacket"]["signal_warning"] is None)
    eng = rt.engine.snapshot()
    check("킬 스위치 작동", eng["killed"], str(eng))
    sos = rt.sos.active()
    check("SOS 자동 발보", sos is not None and sos["cause"] == "mob", str(sos))
    rt.ack_sos()
    check("상황 확인 후 경고 상태 초기화",
          rt.devices.snapshot()[0]["signal_warning_dismissed"] is False)
    jacket.apply("doff")

    print("\n== 7-1) 운항 중 구명조끼 해제 경고 ==")
    alert = rt.jacket_doff_alert  # 위의 doff 는 운항 중 발생
    check("해제 경고 발생", alert is not None and "홍길동" in alert["who"], str(alert))
    check("상태 스냅샷 노출", rt.state_snapshot()["lifejacket"]["doff_alert"] is not None)
    jacket.apply("wear")
    check("재착용 시 경고 자동 해제", rt.jacket_doff_alert is None)
    jacket.apply("doff")
    check("재해제 시 경고 재발생", rt.jacket_doff_alert is not None)
    rt.ack_jacket_alert()
    check("확인(ack) 시 경고 해제", rt.jacket_doff_alert is None)

    print("\n== 7-2) 배터리 교체요망 착용 경고 ==")
    jacket.apply("lowbatt")  # 미착용 상태에서 배터리 부족 주입 — 경고 없음
    check("미착용 시 경고 없음", rt.jacket_batt_alert is None)
    jacket.apply("wear")     # 교체요망 상태로 착용 → 경고
    alert = rt.jacket_batt_alert
    check("착용 시 배터리 경고 발생", alert is not None and "홍길동" in alert["who"], str(alert))
    snap_lj = rt.state_snapshot()["lifejacket"]
    check("상태 스냅샷 노출", snap_lj["batt_alert"] is not None)
    dev0 = snap_lj["devices"][0]
    check("장치 배터리 표시", dev0["battery_mv"] == 2100 and dev0["battery_low"],
          str((dev0["battery_mv"], dev0["battery_low"])))
    jacket.apply("doff")     # 탈의(배터리 교체) → 자동 해제
    check("탈의 시 배터리 경고 해제", rt.jacket_batt_alert is None)
    jacket.apply("battok")   # 배터리 교체 완료
    jacket.apply("wear")
    check("정상 배터리 재착용 시 경고 없음", rt.jacket_batt_alert is None)
    dev0 = rt.state_snapshot()["lifejacket"]["devices"][0]
    check("정상 배터리 표시", dev0["battery_mv"] == 3300 and not dev0["battery_low"],
          str((dev0["battery_mv"], dev0["battery_low"])))
    jacket.apply("doff")  # 입항 시 초기화 확인용으로 해제 경고를 남겨둔다

    print("\n== 8) 지오펜스 진입 → 자동 입항 + 세션 초기화 + 재잠금 ==")
    rt._handle_port_command("arrival")
    check("입항 시 해제 경고 초기화", rt.jacket_doff_alert is None)
    check("입항 신고 접수", rt.voyage.last_report["type"] == "arrival")
    check("승선 세션 초기화", rt.boarding.count() == 0)
    check("시동 재잠금", rt.engine.snapshot()["locked"])
    done = rt.voyage.list_voyages()[0]
    check("운항 기록 완료 처리", done["status"] == "done", str(done))
    check("기록에 승선 인원 보존", done["crew_count"] == 1, str(done))

    print("\n== 9) 승선 인원 없이 시동 허용 시 거부 ==")
    blocked = False
    try:
        rt.allow_engine_start()
    except ValueError:
        blocked = True
    check("빈 승선 목록 거부", blocked)

    print("\n== 9-1) 장치 동적 매칭 → 카메라 확인 + 착용 신호 모두 필요 ==")
    user2 = {"id": "u2", "name": "김선원", "phone": "010-2222-3333",
             "device_id": None, "photo": None,
             "registered_at": "2026-08-01 09:00:00"}
    # 착용 장치가 하나도 없는 상태(7절에서 탈의) → 카메라 확인만으로는 승선 불가
    rt.boarding.handle_recognition(user2, {"visible": True, "ratio": 0.5, "box": (0, 0, 100, 100)})
    check("착용 신호 없으면 카메라만으로 승선 불가", rt.boarding.count() == 0)
    check("착용 신호 없음 안내", "착용 신호가 없습니다" in rt.overlay.get()["text"])

    # 착용 → 스캔: 방금 착용된 장치가 그 선원에게 매칭된다
    rt.sim_jacket("jacket-2").apply("wear")
    time.sleep(0.15)
    rt.boarding.handle_recognition(user2, {"visible": True, "ratio": 0.5, "box": (0, 0, 100, 100)})
    check("카메라+착용 신호 승선", rt.boarding.count() == 1)
    e2 = rt.boarding.session()[0]
    check("장치 동적 매칭(jacket-2)",
          e2["device_id"] == "jacket-2" and e2["lifejacket"] is True, str(e2))
    resolved = rt.resolve_device_user("jacket-2")
    check("세션 매칭 기반 장치-선원 해석",
          bool(resolved and resolved["name"] == "김선원"), str(resolved))

    # 여러 장치 착용 시 가장 최근 착용 장치부터 매칭되고, 매칭된 장치는 재사용 불가
    rt.sim_jacket("jacket-3").apply("wear")
    time.sleep(0.1)
    rt.sim_jacket("jacket-4").apply("wear")
    time.sleep(0.15)
    user3 = {"id": "u3", "name": "박선원", "phone": "010-3333-4444",
             "device_id": None, "photo": None,
             "registered_at": "2026-08-01 09:00:00"}
    rt.boarding.handle_recognition(user3, {"visible": True, "ratio": 0.5, "box": (0, 0, 100, 100)})
    e3 = next(e for e in rt.boarding.session() if e["user_id"] == "u3")
    check("가장 최근 착용 장치 우선 매칭", e3["device_id"] == "jacket-4", str(e3))

    # 시각 확인이 꺼진 경우(jacket_check=None)에도 착용 신호는 필수
    user4 = {"id": "u4", "name": "이선원", "phone": "010-4444-5555",
             "device_id": None, "photo": None,
             "registered_at": "2026-08-01 09:00:00"}
    rt.boarding.handle_recognition(user4)
    e4 = next(e for e in rt.boarding.session() if e["user_id"] == "u4")
    check("시각 확인 꺼짐 → 남은 착용 장치로 승선",
          rt.boarding.count() == 3 and e4["device_id"] == "jacket-3"
          and e4["jacket_visual"] is None, str(e4))

    print("\n== 9-2) 운항 중 추가 승선 반영 + 입항 후 재출항 시 다시 환영 인사 ==")
    jacket_visual = {"visible": True, "ratio": 0.42, "box": (225, 205, 190, 165)}
    voyage = rt.confirm_departure()
    check("출항 시 승선 명단 스냅샷",
          len(rt.voyage.get_voyage(voyage["id"])["crew"]) == 3,
          str(rt.voyage.get_voyage(voyage["id"])["crew"]))

    # 운항 중 추가 승선 → 해당 운항 기록의 명단도 갱신되어야 한다(on_board 콜백)
    rt.sim_jacket("jacket-5").apply("wear")
    time.sleep(0.15)
    rt.boarding.handle_recognition(user, jacket_visual)
    check("운항 중 추가 승선 시 운항 명단 갱신",
          len(rt.voyage.get_voyage(voyage["id"])["crew"]) == 4,
          str(rt.voyage.get_voyage(voyage["id"])["crew"]))

    rt.confirm_arrival()
    check("입항 시 승선 세션 초기화", rt.boarding.count() == 0)

    rt.sim_jacket("jacket-6").apply("wear")
    time.sleep(0.15)
    rt.boarding.handle_recognition(user, jacket_visual)
    check("입항 후 같은 선원 재승선", rt.boarding.count() == 1)
    check("입항 후 환영 인사", "환영합니다" in rt.overlay.get()["text"], rt.overlay.get()["text"])

    # 입항이 세션을 비우지 못한 경우(재시작 등)에도 다음 인식에서 스스로 정리된다
    rt.boarding._session_epoch = rt.voyage.arrival_epoch() - 1
    rt.sim_jacket("jacket-7").apply("wear")
    time.sleep(0.15)
    rt.boarding.handle_recognition(user2, jacket_visual)
    session = rt.boarding.session()
    check("지난 항차 잔여 세션 자동 정리",
          len(session) == 1 and session[0]["user_id"] == "u2", str(session))
    check("자동 정리 후 환영 인사", "환영합니다" in rt.overlay.get()["text"], rt.overlay.get()["text"])

    rt.stop()

    print("\n== 10) 시작 옵션 데이터 초기화 (--reset / --reset-all) ==")
    rt.vessel_store.save({"vessel_id": "테스트-00001", "name": "테스트호"})
    face = config.FACES_DIR / "test_face.jpg"
    face.write_bytes(b"jpeg")
    check("초기화 전 운항 기록 존재", config.VOYAGES_FILE.exists())

    removed = reset_data()
    check("--reset: 운항 기록 삭제", not config.VOYAGES_FILE.exists(), str(removed))
    check("--reset: 승선 이력 삭제", not config.BOARDING_LOGS_FILE.exists())
    check("--reset: 등록 선원·어선 정보 유지",
          config.USERS_FILE.exists() and config.VESSEL_FILE.exists())
    check("--reset: 얼굴 사진 유지", face.exists())
    check("--reset 재실행 안전(멱등)", reset_data() == [])

    removed_all = reset_data(include_registry=True)
    check("--reset-all: 등록 선원 삭제", not config.USERS_FILE.exists(), str(removed_all))
    check("--reset-all: 어선 정보 삭제", not config.VESSEL_FILE.exists())
    check("--reset-all: 얼굴 사진 삭제", not face.exists())
    check("--reset-all: faces 디렉터리 유지", config.FACES_DIR.is_dir())

    # 초기화 뒤 새로 뜬 서버는 '이미 출항' 상태를 물려받지 않아야 한다
    fresh = Runtime()
    check("초기화 후 재시작: 운항 중 아님", fresh.voyage.active_voyage() is None)
    check("초기화 후 재시작: 승선 인원 없음", fresh.boarding.count() == 0)
    check("초기화 후 재시작: 시동 잠금", fresh.engine.snapshot()["locked"])
    fresh.stop()

    print(f"\n결과: PASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
