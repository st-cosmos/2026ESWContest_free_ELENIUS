# Smart V-PASS Application

라즈베리파이에서 동작하는 어선 안전 관리 시스템입니다.
얼굴 인식 승선(출석) 관리, 구명조끼 착용/익수 감지, 킬 스위치 연동,
출항·입항 신고, 운항 기록 관리 기능을 제공합니다.

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
| `VPASS_DEMO_SERVER_URL` | (없음) | 설정 시 데모 관제 서버와 연동(텔레메트리/신고/출입항 전송·관할 기상 수신). 미설정 시 독립 동작 |
| `VPASS_JACKET_VISION` | `1` | 승선 시 구명조끼 카메라 시각 확인 사용 여부 (`0` 비활성) |
| `VPASS_JACKET_COLORS` | `orange,lime,red` | 구명조끼 색상 프리셋(`orange`/`red`/`yellow`/`lime`, 쉼표 구분) |
| `VPASS_JACKET_MIN_RATIO` | `0.4` | 상체 ROI 에서 구명조끼 색 픽셀 비율 판정 기준 |

## 주요 동작 흐름

1. **최초 실행** → 어선 최초 등록 화면(지역 해경청/식별번호/어선명/출항지) → 해경청 자동 등록(시뮬레이션)
2. **선원 등록** — `등록 사용자 목록` → 신규 등록은 2단계로 진행합니다.
   1단계에서 이름·연락처(및 선택 항목인 구명조끼 장치 ID)를 입력하고,
   2단계에서 얼굴을 촬영해 등록합니다.
3. **승선(출석)** — `출항` 화면에서 얼굴을 인식하면 **승선 목록에만 추가**됩니다.
   구명조끼 착용은 두 신호로 함께 확인합니다(버클만 채우는 치팅 방지).
   장치가 배정된 선원은 **모듈(홀센서) 착용 신호**가 있어야 하고, 추가로
   **카메라 시각 확인**(얼굴 아래 상체에서 구명조끼 색 확인)을 통과해야
   승선 처리됩니다. 이 단계에서는 시동이 계속 잠겨 있습니다.
4. **출항 확정** — 승선 인원을 확인한 뒤 `[승선 확인 · 출항 확정]` 을 눌러야
   **시동 잠금이 해제**되고 해양경찰청 **출항 신고**가 접수됩니다.
   확정 시점의 승선 명단이 해당 운항 기록에 함께 저장됩니다.
5. **운항 중** — 1분 간격으로 시간·좌표가 `운항 기록지`에 저장됩니다.
6. **익수 감지** — 착용 중 무선 신호 두절(10초) 또는 낙상 후 신호 두절(5초)
   → **킬 스위치 작동(엔진 정지) + SOS 자동 발보** → SOS 모달 `상황 확인`으로 해제
7. **입항** — `출항` 화면의 `[입항 확정]` 을 누르거나, 속도가 0에 가까워지면
   자동으로 입항 신고가 접수됩니다. 이후 승선 세션이 초기화되고 시동이 재잠금됩니다.
8. **수동 SOS** — 상태바 SOS 버튼 → 확인 창에서 `[해양경찰청에 즉시 신고]`

## 화면 구성

| 화면 | 설명 |
| --- | --- |
| 홈 | 해상 기상·물때, 승선 인원/구명조끼/시동 잠금/최근 운항 요약 |
| 출항 | 실시간 얼굴 인식 승선, 출항 확정 / 입항 확정 |
| 운항 기록지 | 출입항 1건 = 목록 1행. 펼치면 승선 로그 + 1분 간격 운항 상세 |
| 등록 사용자 목록 | 선원 대장, 2단계 신규 등록, 삭제 |
| 구명조끼 모니터 | 장치별 착용/신호/익수 상태, 장치 시뮬레이터 |
| 어선 정보 | 최초 등록 정보 조회·수정(수정 시 해경청 자동 보고) |

## 하드웨어 없이 시연하기

- **구명조끼**: `구명조끼 모니터` 하단 시뮬레이터 — 착용/탈의/낙상/익수/신호두절/재개
  (실제 ESP8266 장치와 동일한 처리 경로 사용)
- **운항**: `출항` 화면에서 얼굴 인식 → `[승선 확인 · 출항 확정]` 을 누르면
  (시뮬레이터 환경에서) 배가 순항 속도까지 가속하며 운항 기록이 시작됩니다.
  `[입항 확정]` 으로 종료합니다.

## 구명조끼 장치(ESP8266) 연동 API

펌웨어(`smart-vpass-example/life-jacket`)와 호환됩니다. `config.h` 의
`SERVER_URL` 을 이 서버 주소로 설정하면 됩니다.

```
POST /api/wearing {"device": "jacket-1", "worn": true}    # 홀센서 착용/해제
POST /api/ping    {"device": "jacket-1"}                  # 착용 중 3초 주기
POST /api/fall    {"device": "jacket-1", "magnitude": 3.2}
```

선원과 장치 연결은 사용자 등록 1단계의 `구명조끼 장치 ID` 필드에 장치명을
입력하면 됩니다(예: `jacket-1`).

## 구명조끼 착용 시각 확인 (임시 구현)

모듈(홀센서) 신호만으로는 구명조끼를 입지 않은 채 버클만 채워 착용으로
위장할 수 있어, 승선 등록(얼굴 인식) 시 카메라 확인을 함께 요구합니다.

- 현재 구현: 얼굴 아래 상체 ROI 의 **HSV 색상 비율 검사**(`jacketvision.py`).
  구명조끼 색 픽셀이 기준 비율(`VPASS_JACKET_MIN_RATIO`) 이상이면 착용으로 판정
- 상체가 화면 밖이면 "상체가 화면에 나오게 서 주세요" 안내 후 승선을 보류
  (판단 불가를 통과시키면 치팅 구멍이 되므로)
- 출항 화면 카메라에 상체 박스와 `JACKET 42%` 형태의 판정 근거가 표시됩니다
- **임시 구현입니다** — 추후 구명조끼 객체 검출 모델을 학습해
  `jacketvision.py` 만 교체할 예정입니다. `VPASS_JACKET_VISION=0` 으로 끌 수 있습니다.

## GPS / 지자계 연동

상위 `test-gps`에서 검증한 NMEA GPS와 QMC5883L 지자계 코드를 앱 구조에 맞게
분리해 포함했습니다. 지자계 캘리브레이션 기록/저장 모드는 제외했고, 필요한 보정값은
환경변수로 주입합니다.

- GPS: NEO-6M 등 NMEA UART 수신기 (`RMC`, `GGA` 파싱)
- 지자계: QMC5883L, I2C 주소 `0x0D`
- 라즈베리파이에서는 `VPASS_TELEMETRY_PROVIDER=auto` 기본값으로 실제 하드웨어 사용
- 개발 PC에서는 같은 기본값으로 기존 통영 해상 시뮬레이터 사용
- 상태바에는 GPS 좌표, 속도, 지자계/GPS 기반 침로, 위성 수, GPS 연결 상태가 표시됩니다.

라즈베리파이 배선 예:

```
NEO-6M TX  -> GPIO15 / RXD (physical pin 10)
NEO-6M RX  -> GPIO14 / TXD (physical pin 8, optional)
QMC5883L SDA -> GPIO2 / SDA (physical pin 3)
QMC5883L SCL -> GPIO3 / SCL (physical pin 5)
```

사용 전 `sudo raspi-config`에서 Serial Port를 활성화하고, serial login shell은 비활성화해야 합니다.

## 주요 애플리케이션 API

```
GET  /api/state              # UI 폴링용 통합 상태
POST /api/departure/confirm  # 출항 확정 (시동 해제 + 출항 신고)
POST /api/arrival/confirm    # 입항 확정 (입항 신고 + 재잠금)
GET  /api/voyages            # 운항 기록 목록
GET  /api/voyages/{id}       # 운항 상세 (승선 명단 + 1분 간격 좌표)
GET  /api/boarding/session   # 현재 승선 목록 요약
POST /api/sos, /api/sos/ack  # SOS 신고 / 상황 확인
```

## 테스트

```bash
uv run python tests/test_flow.py
```

카메라·GPIO 없이 NMEA 파서와 핵심 안전 시나리오(승선 → 출항 확정 → 익수 감지
→ 킬 스위치 → 상황 확인 → 입항 확정)를 검증합니다.

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
  chromium 은 `--password-store=basic` 으로 실행되어 키링 비밀번호 창이 뜨지 않습니다.
- 기상: 현재 시뮬레이션 제공자(`weather.py`)로 동작하며, 기상청 API 연동 시 해당 모듈만 교체하면 됩니다.

## 프로젝트 구조

```
vpass-application/
├── pyproject.toml          # uv 프로젝트 (스크립트: vpass)
├── src/vpass/
│   ├── main.py             # 엔트리포인트 (uvicorn + 브라우저/키오스크)
│   ├── server.py           # FastAPI 앱 + 정적 서빙
│   ├── routes.py           # HTTP API 전체
│   ├── runtime.py          # 매니저 배선 + 출항/입항 확정 + 장치 시뮬레이터
│   ├── camera.py           # 카메라 스레드 + MJPEG 스트림
│   ├── facerec.py          # 얼굴 검출/인식(LBPH)
│   ├── jacketvision.py     # 구명조끼 착용 시각 확인(임시 HSV, 모델 교체 예정)
│   ├── gps.py              # NMEA GPS(UART) 읽기
│   ├── compass.py          # QMC5883L 지자계(I2C) 읽기
│   ├── boarding.py         # 승선(출석) 세션 + 로그
│   ├── lifejacket.py       # 디바이스 레지스트리 + 익수 감지
│   ├── killswitch.py       # 시동 잠금/비상 정지 (GPIO 추상화)
│   ├── voyage.py           # 운항 기록(승선 명단 + 1분 트랙) + 입항 자동 감지
│   ├── telemetry.py        # GPS·지자계 통합 제공자 + 개발용 시뮬레이터
│   ├── weather.py          # 해양 기상 제공자 (KMA 연동 자리)
│   └── sos.py              # SOS 신고 관리
├── tests/test_flow.py      # 핵심 안전 시나리오 테스트
├── ui/                     # React + TypeScript (Vite)
│   └── src/screens/        # 홈/출항/운항기록지/사용자/구명조끼/어선정보/셋업
└── data/                   # 런타임 데이터 (git 제외)
```
