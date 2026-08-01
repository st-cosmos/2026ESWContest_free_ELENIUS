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

    # 미착용 상태에서 얼굴 인식 → 승선 거부
    rt.boarding.handle_recognition(user)
    check("미착용 시 승선 거부", rt.boarding.count() == 0)
    check("미착용 경고 오버레이", "구명조끼 미착용" in rt.overlay.get()["text"])

    # 구명조끼 착용 (시뮬레이터 = 실장치와 동일 경로)
    jacket = rt.sim_jacket("jacket-1")
    jacket.apply("wear")
    time.sleep(0.2)
    check("착용 인식", rt.devices.is_worn("jacket-1") is True)

    print("\n== 3) 얼굴 인식 → 승선 + 시동 잠금 해제 ==")
    rt.boarding._notice_times.clear()  # 쿨다운 초기화
    rt.boarding.handle_recognition(user)
    check("승선 처리", rt.boarding.count() == 1)
    check("시동 잠금 해제", not rt.engine.snapshot()["locked"])
    check("승선 로그 저장", len(rt.boarding_logs_store.load()) == 1)
    check("중복 승선 방지", (rt.boarding.handle_recognition(user), rt.boarding.count())[1] == 1)

    print("\n== 4) 자동 출항 감지 ==")
    # 잠금 해제 → 자동 순항 시작 (telemetry 가속)
    deadline = time.time() + 30
    while time.time() < deadline and rt.telemetry.snapshot()["speed_kn"] < 3.0:
        time.sleep(0.5)
    check("순항 가속", rt.telemetry.snapshot()["speed_kn"] >= 3.0,
          f"speed={rt.telemetry.snapshot()['speed_kn']}")

    v = rt.voyage.start_voyage(auto=True)  # 감시 루프 대기 대신 직접 트리거
    check("운항 기록 생성", rt.voyage.active_voyage() is not None)
    check("출항 자동 신고", v["departure_reported"])

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

    print("\n== 7) 신호 두절 단독 익수 시나리오 ==")
    jacket.apply("resume")
    time.sleep(0.3)
    jacket.apply("silence")  # ping 만 중단 (낙상 이벤트 없음)
    deadline = time.time() + 10
    while time.time() < deadline and not rt.devices.any_mob():
        time.sleep(0.2)
    check("신호 두절 익수 감지", rt.devices.any_mob())
    d = rt.devices.snapshot()[0]
    check("원인=signal_loss", d["mob_cause"] == "signal_loss", str(d["mob_cause"]))
    rt.ack_sos()
    jacket.apply("doff")

    print("\n== 8) 입항 → 세션 초기화 + 재잠금 ==")
    rt.voyage.end_voyage(auto=True)
    check("입항 자동 신고", rt.voyage.last_report["type"] == "arrival")
    check("승선 세션 초기화", rt.boarding.count() == 0)
    check("시동 재잠금", rt.engine.snapshot()["locked"])

    rt.stop()
    print(f"\n결과: PASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
