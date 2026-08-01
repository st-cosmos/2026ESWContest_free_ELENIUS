# Smart V-PASS Application

라즈베리파이에서 동작하는 어선 안전 관리 시스템입니다.
얼굴 인식 승선(출석) 관리, 구명조끼 착용/익수 감지, 킬 스위치 연동,
출항·입항 자동 신고, 어선운항정보 기록 기능을 제공합니다.

- **백엔드**: Python(FastAPI) — `uv` 로 관리
- **UI**: React + TypeScript(Vite) — 백엔드가 빌드 결과물을 서빙
- **디자인**: `design/design.pen` (Pencil) 기준으로 구현

## 실행 방법

### 1) UI 빌드 (최초 1회 또는 UI 수정 시)

```bash
cd vpass-application/ui
npm install
npm run build        # → ui/dist 생성
```

### 2) 서버 실행

```bash
cd vpass-application
uv run vpass                 # 서버 시작 + 브라우저 자동 열기
uv run vpass --no-browser    # 서버만
uv run vpass --kiosk         # chromium 키오스크 모드(라즈베리파이는 자동)
```

- 접속: `http://localhost:8000` (UI), `http://localhost:8000/docs` (API 문서)
- UI 개발 시: `cd ui && npm run dev` → `http://localhost:5173` (API 는 8000 으로 프록시)

### 환경 변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `VPASS_DATA_DIR` | `vpass-application/data` | 사용자/기록 JSON·얼굴 사진 저장 위치 |
| `VPASS_CAMERA_INDEX` | `0` | OpenCV 카메라 인덱스 |
| `VPASS_KILLSWITCH_PIN` | `17` | 킬 스위치 릴레이 GPIO(BCM) 핀 |
| `VPASS_TELEMETRY_PROVIDER` | `auto` | `auto`/`hardware`/`sim` — auto는 라즈베리파이에서 GPS·지자계 사용 |
| `VPASS_GPS_PORT` | `/dev/serial0` | NEO-6M 등 NMEA GPS UART 장치 |
| `VPASS_GPS_BAUDRATE` | `9600` | GPS UART baudrate |
| `VPASS_COMPASS_I2C_BUS` | `1` | QMC5883L I2C bus 번호 |
| `VPASS_COMPASS_DECLINATION_DEG` | `0` | 지자기 편각 보정값(degree) |
| `VPASS_COMPASS_X_OFFSET`, `VPASS_COMPASS_Y_OFFSET` | `0` | 지자계 고정 offset 값 |
| `VPASS_COMPASS_X_SCALE`, `VPASS_COMPASS_Y_SCALE` | `1` | 지자계 고정 scale 값 |
| `VPASS_COMPASS_HEADING_ALPHA` | `0.25` | 침로 저역통과 필터 계수(0 < alpha <= 1) |

## 주요 동작 흐름

1. **최초 실행** → 어선 최초 등록 화면(지역 해경청/식별번호/어선명/출항지) → 해경청 자동 등록(시뮬레이션)
2. **선원 등록** — `등록 사용자 목록` → 신규 등록(이름/연락처/구명조끼 장치 ID + 얼굴 촬영)
3. **출항(출석)** — `출항` 화면에서 얼굴 인식 → 승선 처리
   - 구명조끼 장치가 배정된 선원은 **착용 상태여야** 승선 처리됨
   - 첫 승선 시 **시동 잠금 해제** → (시뮬레이션) 배가 출항해 속도가 오르면 **출항 자동 신고**
4. **운항 중** — 1분 간격으로 시간·좌표가 `어선운항정보 기록`에 저장
5. **익수 감지** — 착용 중 무선 신호 두절(10초) 또는 낙상 후 신호 두절(5초)
   → **킬 스위치 작동(엔진 정지) + SOS 자동 발보** → SOS 모달 `상황 확인`으로 해제
6. **입항** — 속도가 0에 가까워지면 **입항 자동 신고** + 승선 세션 초기화 + 시동 재잠금
7. **수동 SOS** — 상태바 SOS 버튼을 **2초 내 3회** 클릭

## 하드웨어 없이 시연하기

- **구명조끼**: `구명조끼 모니터` 하단 시뮬레이터 — 착용/탈의/낙상/익수/신호두절/재개
  (실제 ESP8266 장치와 동일한 처리 경로 사용)
- **운항**: `어선운항정보 기록` 우상단 `모의 출항`/`모의 입항`
  (모의 출항은 시동 잠금 해제 후에만 가능 — 얼굴 인식 승선 필요)
- 더미 좌표 입력: 운항 상세 하단 `운항정보 더미 데이터 입력`

## 구명조끼 장치(ESP8266) 연동 API

펌웨어(`smart-vpass-example/life-jacket`)와 호환됩니다. `config.h` 의
`SERVER_URL` 을 이 서버 주소로 설정하면 됩니다.

```
POST /api/wearing {"device": "jacket-1", "worn": true}    # 홀센서 착용/해제
POST /api/ping    {"device": "jacket-1"}                  # 착용 중 3초 주기
POST /api/fall    {"device": "jacket-1", "magnitude": 3.2}
```

선원과 장치 연결은 사용자 등록 시 `구명조끼 장치 ID` 필드에 장치명을
입력하면 됩니다(예: `jacket-1`).

## GPS / 지자계 연동

상위 `test-gps`에서 검증한 NMEA GPS와 QMC5883L 지자계 코드를 앱 구조에 맞게
분리해 포함했습니다. 지자계 캘리브레이션 기록/저장 모드는 제외했고, 필요한 보정값은
환경변수로 주입합니다.

- GPS: NEO-6M 등 NMEA UART 수신기 (`RMC`, `GGA` 파싱)
- 지자계: QMC5883L, I2C 주소 `0x0D`
- 라즈베리파이에서는 `VPASS_TELEMETRY_PROVIDER=auto` 기본값으로 실제 하드웨어 사용
- 개발 PC에서는 같은 기본값으로 기존 통영 해상 시뮬레이터 사용
- 상태바에는 GPS 좌표, 속도, 지자계/GPS 기반 침로, 위성 수, GPS/지자계 연결 상태가 표시됩니다.

라즈베리파이 배선 예:

```
NEO-6M TX  -> GPIO15 / RXD (physical pin 10)
NEO-6M RX  -> GPIO14 / TXD (physical pin 8, optional)
QMC5883L SDA -> GPIO2 / SDA (physical pin 3)
QMC5883L SCL -> GPIO3 / SCL (physical pin 5)
```

사용 전 `sudo raspi-config`에서 Serial Port를 활성화하고, serial login shell은 비활성화해야 합니다.

## 라즈베리파이 배포 메모

- Python 3.11+ / `uv sync` 로 의존성 설치 (piwheels 바이너리 휠 사용)
- 킬 스위치: `gpiozero` 설치 시 GPIO 릴레이 구동, 미설치/미지원 환경은 자동 시뮬레이션
  ```bash
  uv add gpiozero   # 라즈베리파이에서만
  ```
- 키오스크 자동 시작(예: `~/.config/autostart` 또는 systemd):
  ```bash
  uv run vpass --kiosk
  ```
- 기상: 현재 시뮬레이션 제공자(`weather.py`)로 동작하며, 기상청 API 연동 시 해당 모듈만 교체하면 됩니다.

## 프로젝트 구조

```
vpass-application/
├── pyproject.toml          # uv 프로젝트 (스크립트: vpass)
├── src/vpass/
│   ├── main.py             # 엔트리포인트 (uvicorn + 브라우저/키오스크)
│   ├── server.py           # FastAPI 앱 + 정적 서빙
│   ├── routes.py           # HTTP API 전체
│   ├── runtime.py          # 매니저 배선 + 장치 시뮬레이터
│   ├── camera.py           # 카메라 스레드 + MJPEG 스트림
│   ├── facerec.py          # 얼굴 검출/인식(LBPH)
│   ├── gps.py              # NMEA GPS(UART) 읽기
│   ├── compass.py          # QMC5883L 지자계(I2C) 읽기
│   ├── boarding.py         # 승선(출석) 세션 + 로그
│   ├── lifejacket.py       # 디바이스 레지스트리 + 익수 감지
│   ├── killswitch.py       # 시동 잠금/비상 정지 (GPIO 추상화)
│   ├── voyage.py           # 출항/입항 자동 감지 + 1분 트랙 기록
│   ├── telemetry.py        # GPS·지자계 통합 제공자 + 개발용 시뮬레이터
│   ├── weather.py          # 해양 기상 제공자 (KMA 연동 자리)
│   └── sos.py              # SOS 신고 관리
├── tests/test_flow.py      # 핵심 안전 시나리오 테스트 (uv run python tests/test_flow.py)
├── ui/                     # React + TypeScript (Vite)
│   └── src/screens/        # 홈/출항/출항기록지/사용자/구명조끼/어선정보/운항기록/셋업
└── data/                   # 런타임 데이터 (git 제외)
```
