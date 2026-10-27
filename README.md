# VIFE — 구명조끼 연동 스마트 V-PASS

제24회 임베디드SW경진대회 자유공모 부문 · 팀 **ELENIUS**

> 입어야 배가 나가고, 입으면 신고가 끝나고, 빠지면 배가 멈춘다.

어선 구명조끼 착용 의무화(2026.7)와 출입항·승선원 신고 의무를 **기술적으로 강제**하면서,
익수 사고 시 **엔진 정지 → 자동 신고 → 구조 신호 → 표류 예측**까지 이어지는 안전 체계를
V-PASS 단말 위에 구현한 작품입니다.

## 시스템 구성

```
 구명조끼 모듈 ×N ──BLE 광고──▶ V-PASS 단말 (Raspberry Pi) ──BLE──▶ 킬 스위치 (ESP32-C3)
 nRF52840 · IMU · 버클 ·          얼굴인식 승선 · 착용/익수 판정           모형 배 전원 릴레이
 수분 전극 · 스트로브                 출입항 자동 신고 · 운항 기록
                                            │
                                     HTTP / LoRa (E220)
                                            ▼
                                해경 통합 관제 데모 서버
                        선박 관제 · 신고 수신 · 해양 기상 · 표류 예측
```

| 디렉터리 | 구성 요소 | 스택 |
|---|---|---|
| [`firmware/`](firmware/README.md) | 구명조끼 모듈 펌웨어 — 버클 착용 감지, IMU 자유낙하·충격, 수분 전극, 스트로브, 저전력 System OFF | nRF Connect SDK v3.4 (Zephyr) · E73-2G4M08S1C (nRF52840) · BLE 브로드캐스터 |
| [`vpass-application/`](vpass-application/README.md) | V-PASS 단말 앱 — 얼굴인식 승선 게이트, 구명조끼 착용 검사, 익수 감지, 킬 스위치 연동, 출입항 신고, 운항 기록 | Python 3.11 / FastAPI + React · TypeScript (Vite) · OpenCV |
| [`demo-server/`](demo-server/README.md) | 해경 통합 관제 데모 서버 — 선박 대시보드, 신고 수신함, 해양 기상, 운항 시뮬레이터, 요구조자 표류 예측 | Python 3.11 / FastAPI + React · TypeScript (Vite) |
| [`kill-switch/`](kill-switch/README.md) | BLE 킬 스위치 (모형 배 전원 릴레이, fail-safe 차단) | ESP32-C3 SuperMini · PlatformIO |
| `design/` | UI 디자인 원본 (`design.pen` 단말 앱, `demo-service-design.pen` 관제) | Pencil |

구명조끼 모듈 PCB(KiCad)는 별도 저장소에서 관리합니다.

## 동작 개요

1. **승선** — V-PASS 카메라가 얼굴을 인식해 승선 명부에 기록하고, 구명조끼 버클 센서 광고 +
   카메라 비전 검사를 모두 통과해야 킬 스위치가 시동을 허용합니다.
2. **출입항** — 지오펜스 통과로 출항·입항 신고가 관제 서버에 자동 전송되고, 운항 중 항적이
   1분 간격으로 기록됩니다.
3. **익수 감지** — 조끼 모듈이 500 ms 주기 BLE 광고(=생존 핑)를 보내고, 자유낙하 시 5초간
   100 ms 버스트로 전환합니다. V-PASS는 낙하 후 5초 / 착용 중 10초 무신호를 익수로 판정하고,
   낙하 + 물 접촉 플래그는 즉시 확정합니다.
4. **대응** — 킬 스위치 엔진 정지, 해경 관제에 자동 신고(시각·좌표·원인), 조끼 스트로브 점멸,
   관제 서버에서 요구조자 표류 예측·수색 범위 표시.

## 빠른 시작

각 구성 요소의 자세한 설치·실행·배포 방법은 위 표의 README를 참고하세요.

```bash
# V-PASS 단말 앱 (PC 에서도 시뮬레이터로 동작)
cd vpass-application/ui && npm install && npm run build
cd .. && uv run python tools/fetch_face_models.py   # 얼굴 인식 ONNX 모델 (최초 1회)
uv run vpass                                        # http://localhost:8000

# 해경 관제 데모 서버
cd demo-server/ui && npm install && npm run build
cd .. && uv run demo-server                         # http://localhost:8100

# 구명조끼 펌웨어 (nRF Connect SDK 환경 셸)
cd firmware && west build -b nrf52840dk/nrf52840 --sysbuild -p always .
```

하드웨어 없이 전체 시나리오를 시연하는 방법은
[`vpass-application/README.md` 의 "하드웨어 없이 시연하기"](vpass-application/README.md#하드웨어-없이-시연하기)를 참고하세요.

## 팀 ELENIUS

| 구분 | 성명 | 담당 |
|---|---|---|
| 팀장 | 정현수 | 관제 데모 서버 · 구명조끼 모듈 PCB 및 펌웨어 |
| 팀원 | 한윤평 | V-PASS 단말 앱 (승선 게이트·익수 판정·BLE 통합) |
| 팀원 | 최지섭 | 킬 스위치 · LoRa 백홀 · HW 통합 · 항법 센서 연동 |
