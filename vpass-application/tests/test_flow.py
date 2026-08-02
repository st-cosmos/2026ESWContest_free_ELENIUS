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

    # 착용 신호(착용 중인 장치)가 하나도 없는 상태에서 얼굴 인식 → 승선 거부
    rt.boarding.handle_recognition(user)
    check("착용 신호 없으면 승선 거부", rt.boarding.count() == 0)
    check("착용 신호 없음 경고", "착용 신호가 없습니다" in rt.overlay.get()["text"])

    # 구명조끼 착용 (시뮬레이터 = 실장치와 동일 경로)
    jacket = rt.sim_jacket("jacket-1")
    jacket.apply("wear")
    time.sleep(0.2)
    check("착용 인식", rt.devices.is_worn("jacket-1") is True)

    print("\n== 2-1) 구명조끼 시각 확인 (임시 HSV 구현) ==")
    import numpy as np  # noqa: E402
    from vpass import jacketvision  # noqa: E402

    face_box = (270, 80, 100, 100)                  # 화면 중앙 상단의 얼굴
    plain = np.full((480, 640, 3), 60, np.uint8)    # 무채색 배경/옷
    r = jacketvision.assess_jacket(plain, face_box)
    check("무채색 상체 → 미확인", r["visible"] is False and r["box"] is not None, str(r))

    orange = plain.copy()
    bx, by, bw, bh = r["box"]
    orange[by:by + bh, bx:bx + bw] = (0, 128, 255)  # 상체 ROI 를 주황(BGR)으로 채움
    r2 = jacketvision.assess_jacket(orange, face_box)
    check("주황 상체 → 착용 확인", r2["visible"] is True and r2["ratio"] > 0.9, str(r2))

    r3 = jacketvision.assess_jacket(plain, (270, 380, 100, 100))  # 얼굴이 화면 하단
    check("상체 화면 밖 → 판단 불가", r3["visible"] is None and r3["box"] is None, str(r3))

    # 모듈은 착용(치팅 가능 상태)이라도 카메라 확인을 통과해야 승선된다
    rt.boarding._notice_times.clear()
    rt.boarding.handle_recognition(user, {"visible": False, "ratio": 0.02, "box": (0, 0, 10, 10)})
    check("카메라 미확인 시 승선 거부", rt.boarding.count() == 0)
    check("카메라 미확인 경고", "카메라에 확인되지 않습니다" in rt.overlay.get()["text"])
    rt.boarding.handle_recognition(user, {"visible": None, "ratio": 0.0, "box": None})
    check("판단 불가 시 승선 보류", rt.boarding.count() == 0)
    check("판단 불가 안내", "상체가 화면에" in rt.overlay.get()["text"])

    print("\n== 3) 얼굴 인식(모듈+카메라 확인) → 승선 목록에만 추가 (시동은 잠긴 채 유지) ==")
    rt.boarding._notice_times.clear()  # 쿨다운 초기화
    rt.boarding.handle_recognition(user, {"visible": True, "ratio": 0.42, "box": (225, 205, 190, 165)})
    check("승선 처리", rt.boarding.count() == 1)
    entry = rt.boarding.session()[0]
    check("모듈+카메라 확인 기록",
          entry["lifejacket"] is True and entry["jacket_visual"] is True, str(entry))
    check("장치 동적 매칭(jacket-1)", entry["device_id"] == "jacket-1", str(entry))
    check("시동 잠금 유지", rt.engine.snapshot()["locked"])
    check("승선 로그 저장", len(rt.boarding_logs_store.load()) == 1)
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
    jacket.apply("wear")
    jacket.apply("doff")  # 입항 시 초기화 확인용으로 경고를 남겨둔다

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

    rt.stop()
    print(f"\n결과: PASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
