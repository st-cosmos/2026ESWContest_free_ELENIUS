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

### 3) 데이터 초기화하고 실행하기

운항 기록(`voyages.json`)의 운항은 **입항 확정 전까지 `active` 로 남습니다**.
그래서 운항 중에 프로그램을 그냥 종료하면, 다시 켰을 때도 그 운항이 살아나
'이미 출항한 상태(승선 명단 포함)'로 이어집니다. 시연을 처음부터 다시
돌리려면 초기화 옵션으로 실행합니다.

```bash
uv run vpass --reset         # 운항 기록 + 승선 이력 삭제 (선원·어선 정보는 유지)
uv run vpass --reset-all     # 등록 선원·얼굴 사진·어선 정보까지 전부 삭제
```

| 옵션 | 지우는 것 | 남기는 것 |
| --- | --- | --- |
| `--reset` | `voyages.json`(운항 기록), `boarding_logs.json`(승선 이력) | 등록 선원, 얼굴 사진, 어선 정보 |
| `--reset-all` | 위 항목 + `users.json`, `data/faces/*`, `vessel.json` | (없음 — 최초 실행 상태로 돌아감) |

- 서버가 뜨기 전에 파일을 지우므로, 재시작 즉시 정박·시동 잠금 상태로 시작합니다.
- `--reset-all` 은 어선 정보까지 지워 **어선 최초 등록 화면부터 다시 시작**합니다.
- 데모 관제 서버를 함께 쓴다면 그쪽에도 이전 출항 상태가 남아 있으므로
  `uv run demo-server --reset` 로 같이 초기화하세요.

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
| | | 관할 기상에는 풍향(`wind_dir`)·풍속(`wind_speed_ms`)·해류(`current_dir`/`current_kn`)가 포함되며, 관제 서버의 요구조자 표류 예측과 **같은 값**이 표시됩니다 |
| `VPASS_JACKET_VISION` | `1` | 승선 시 구명조끼 카메라 시각 확인 사용 여부 (`0` 비활성) |
| `VPASS_JACKET_METHOD` | `auto` | 판정 방법 — `auto`(모델 있으면 ml)/`ml`/`hsv` |
| `VPASS_JACKET_MODEL` | `models/jacket_classifier.tflite` | 가슴 ROI 이진 분류 TFLite 모델 경로 |
| `VPASS_JACKET_ML_THRESHOLD` | `0.5` | ML 착용 확률 판정 기준 |
| `VPASS_JACKET_CAPTURE` | `0` | `1` 이면 스캔 중 가슴 ROI 크롭을 학습 데이터로 저장 |
| `VPASS_JACKET_COLORS` | `orange,lime,red` | (hsv 폴백) 색상 프리셋(`orange`/`red`/`yellow`/`lime`, 쉼표 구분) |
| `VPASS_JACKET_MIN_RATIO` | `0.4` | (hsv 폴백) 상체 ROI 구명조끼 색 픽셀 비율 판정 기준 |

## 주요 동작 흐름

1. **최초 실행** → 어선 최초 등록 화면(지역 해경청/식별번호/어선명/출항지) → 해경청 자동 등록(시뮬레이션)
2. **선원 등록** — `등록 사용자 목록` → 신규 등록은 2단계로 진행합니다.
   1단계에서 이름·연락처(및 선택 항목인 구명조끼 장치 ID)를 입력하고,
   2단계에서 얼굴을 촬영해 등록합니다.
3. **승선(출석)** — `출항` 화면에서 얼굴을 인식하면 **승선 목록에만 추가**됩니다.
   구명조끼 착용은 **카메라 시각 확인**(얼굴 아래 상체에서 구명조끼 색 확인)과
   **모듈(홀센서) 착용 신호** 두 가지를 모두 만족해야 인정됩니다(버클만
   채우는 치팅 방지). 장치-선원 연결은 등록 시 고정 배정이 아니라 **스캔
   시점에 동적으로 매칭**됩니다 — 아직 매칭되지 않은 착용 장치 중 가장
   최근에 착용된 장치가 그 선원에게 연결됩니다('착용 직후 스캔' 순서 전제).
   이 단계에서는 시동이 계속 잠겨 있습니다.
   승선이 확인되면 `홍길동 님 환영합니다 · 승선 확인(구명조끼 모듈·카메라)` 안내가
   표시되고, 같은 사람이 계속 인식되면 잠시 뒤부터 `이미 승선 확인된 선원입니다`
   안내로 바뀝니다. **승선 명단은 한 항차(출항~입항) 단위**라서, 입항 이력이 있어도
   다음 출항의 얼굴 인식에서는 다시 환영 인사와 함께 승선 처리됩니다.
4. **시동 허용** — 승선 인원을 확인한 뒤 `[승선 확인 · 시동 허용]` 을 눌러야
   **시동 잠금이 해제**됩니다. 이 버튼은 출항 신고를 하지 않습니다.
5. **출항** — 데모 관제 서버 `운항 시뮬레이터`에서 그린 **지오펜스를 넘어
   바다로 나가면** 자동으로 출항 신고가 접수되고 운항 기록이 시작됩니다.
   출항 시점의 승선 명단이 해당 운항 기록에 함께 저장됩니다.
   (지오펜스를 쓰지 않는 환경에서는 `[수동 출항 신고]` 버튼을 사용합니다.)
6. **운항 중** — 항해 시간 기준 1분 간격으로 시간·좌표가 `운항 기록지`에 저장됩니다.
   운항 시뮬레이터가 배속으로 돌 때는 그 배속만큼 기록 간격도 좁아집니다
   (예: 30배속 → 실제 2초마다 1건). 정박 중(속력 0)에는 1분 간격을 유지합니다.
   운항 중 구명조끼 버클을 풀면(장치 미장착 신호) **해제 경고 모달**이
   모든 화면 위에 표시되며, 다시 착용하면 자동으로 사라집니다(`확인` 으로도 닫기 가능).
7. **익수 감지** — 착용 중 무선 신호 두절(10초) 또는 낙상 후 신호 두절(5초)
   → **킬 스위치 작동(엔진 정지) + SOS 자동 발보** → SOS 모달 `상황 확인`으로 해제
8. **입항** — 지오펜스 안(항내)으로 다시 들어오면 자동으로 입항 신고가 접수됩니다.
   이후 승선 세션이 초기화되고 시동이 재잠금됩니다. (`[수동 입항 신고]` 도 가능)
9. **수동 SOS** — 상태바 SOS 버튼 → 확인 창에서 `[해양경찰청에 즉시 신고]`

> **GPS 좌표 출처**: 실측 GPS(라즈베리파이 NMEA)가 잡히면 언제나 실측값을 사용하고,
> 실측이 없을 때만 데모 관제 서버 운항 시뮬레이터의 좌표를 사용합니다.
> 시뮬레이션 좌표를 쓰는 동안에는 상태바 GPS 칩이 `GPS · 시뮬레이션` 으로 표시됩니다.

## 화면 구성

| 화면 | 설명 |
| --- | --- |
| 홈 | 해상 기상·물때, 승선 인원/구명조끼/시동 잠금/최근 운항 요약 |
| 출항 | 실시간 얼굴 인식 승선, 시동 허용 / 수동 출입항 신고 |
| 운항 기록지 | 출입항 1건 = 목록 1행. 펼치면 승선 로그 + 항해 1분 간격 운항 상세 |
| 등록 사용자 목록 | 선원 대장, 2단계 신규 등록, 삭제 |
| 구명조끼 모니터 | 장치별 착용/신호/익수 상태, 장치 시뮬레이터 |
| 어선 정보 | 최초 등록 정보 조회·수정(수정 시 해경청 자동 보고) |

## 하드웨어 없이 시연하기

- **구명조끼**: `구명조끼 모니터` 하단 시뮬레이터 — 착용/탈의/낙상/익수/신호두절/재개
  (실제 ESP8266 장치와 동일한 처리 경로 사용)
- **운항**: `출항` 화면에서 얼굴 인식 → `[승선 확인 · 시동 허용]` 로 시동을 풀고,
  데모 관제 서버의 `운항 시뮬레이터`(`/simulator`)에서 항로를 그려 배를 움직이면
  지오펜스 통과 시점에 출항/입항이 자동으로 기록됩니다.
  데모 서버 없이 시연할 때는 `[수동 출항 신고]` / `[수동 입항 신고]` 를 사용합니다.

## 구명조끼 장치(ESP8266) 연동 API

펌웨어(`smart-vpass-example/life-jacket`)와 호환됩니다. `config.h` 의
`SERVER_URL` 을 이 서버 주소로 설정하면 됩니다.

```
POST /api/wearing {"device": "jacket-1", "worn": true}    # 홀센서 착용/해제
POST /api/ping    {"device": "jacket-1"}                  # 착용 중 3초 주기
POST /api/fall    {"device": "jacket-1", "magnitude": 3.2}
```

선원과 장치 연결은 **승선 스캔 시점에 자동(동적)으로 매칭**됩니다 — 구명조끼를
착용하면 장치가 착용 신호를 보내고, 이어서 얼굴 인식에 성공하면 미매칭 착용
장치 중 가장 최근 것이 그 선원에게 연결됩니다. 사용자 등록 1단계의
`구명조끼 장치 ID` 필드는 선택 사항이며, 승선 매칭이 없을 때 익수 알림의
이름 해석 폴백으로만 사용됩니다.

## 구명조끼 착용 시각 확인

모듈(홀센서) 신호만으로는 구명조끼를 입지 않은 채 버클만 채워 착용으로
위장할 수 있어, 승선 등록(얼굴 인식) 시 카메라 확인을 함께 요구합니다.

- 판정(`jacketvision.py`): 얼굴 아래 가슴 ROI 를 **TFLite 이진 분류기**로
  검사합니다(`models/jacket_classifier.tflite`, 착용 확률 ≥ `VPASS_JACKET_ML_THRESHOLD`).
  모델 파일이나 tflite 런타임이 없으면 기존 **HSV 색상 비율 검사**로 자동
  폴백합니다 (`VPASS_JACKET_METHOD=hsv` 로 강제 가능).
- 카메라 확인을 통과해도 **모듈 착용 신호가 함께 있어야** 승선됩니다.
  모듈 신호는 장치-선원 동적 매칭으로 확인하며, 스캔 시점에 미매칭 착용 장치 중
  가장 최근 착용된 장치를 해당 선원에게 매칭합니다(같은 세션에서 재사용 불가,
  '착용 직후 스캔' 순서 전제 — 순서가 어긋나는 경우의 예외 처리는 추후 보강)
- 상체가 화면 밖이면 "상체가 화면에 나오게 서 주세요" 안내 후 승선을 보류
  (판단 불가를 통과시키면 치팅 구멍이 되므로)
- 출항 화면 카메라에 상체 박스와 `JACKET 42%` 형태의 판정 근거가 표시됩니다
- `VPASS_JACKET_VISION=0` 으로 시각 확인 자체를 끌 수 있습니다.

### 분류 모델 학습·배포

1. **데이터 수집** — 실제 설치 환경에서 `VPASS_JACKET_CAPTURE=1 uv run vpass` 로
   앱을 켜 두면 스캔 중 가슴 ROI 크롭이 `data/jacket_dataset/unsorted/` 에
   1초 간격으로 저장됩니다. 착용/미착용(주황색 일반 옷 포함) 상황을 골고루 수집합니다.
2. **라벨링** — 크롭을 `data/jacket_dataset/jacket/` 과 `no_jacket/` 으로 분류
   (클래스당 200장 이상 권장, 파일명의 점수는 참고용)
3. **학습 (PC)** — `pip install "tensorflow>=2.16"` 후
   `python tools/train_jacket_classifier.py --data data/jacket_dataset`
   → `models/jacket_classifier.tflite` 생성 (MobileNetV3-Small 전이학습, int8 양자화)
4. **배포 (라즈베리파이)** — 모델 파일을 같은 경로에 복사하고 `uv sync --extra ml`
   로 tflite 런타임을 설치. 앱 시작 로그에 `[jacketvision] TFLite 모델 로드` 확인.

## 사운드 효과

주요 이벤트에 UI 가 사운드를 재생합니다 (`ui/src/useSoundEffects.ts`,
파일·라이선스는 `ui/public/sounds/README.md`):

- 승선 인식 / 출항 등록(수동·지오펜스) / 입항 등록(수동·지오펜스)
- SOS 발보(익수 자동·수동 공통) — 신고가 떠 있는 동안 사이렌 반복 재생
- 기상특보 발효, 하드웨어·통신 에러(4초 지속 시 1회)

키오스크 chromium 은 `--autoplay-policy=no-user-gesture-required` 로 실행되어
사용자 입력 없이도 재생됩니다. 일반 브라우저에서는 첫 클릭/키 입력 이후부터
재생됩니다(자동재생 정책).

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
POST /api/engine/allow       # 승선 확인 · 시동 허용 (출항 신고 아님)
POST /api/departure/confirm  # 수동 출항 신고 (지오펜스 미사용 환경)
POST /api/arrival/confirm    # 수동 입항 신고 (입항 신고 + 재잠금)
GET  /api/voyages            # 운항 기록 목록
GET  /api/voyages/{id}       # 운항 상세 (승선 명단 + 항해 1분 간격 좌표)
GET  /api/boarding/session   # 현재 승선 목록 요약
POST /api/sos, /api/sos/ack  # SOS 신고 / 상황 확인
POST /api/jacket-alert/ack   # 운항 중 구명조끼 해제 경고 모달 닫기
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
- 한글 입력: chromium 을 `--ozone-platform=x11` 로 띄워 XWayland 에서 실행합니다.
  Wayland 네이티브로 뜨면 chromium 이 `text-input` 프로토콜만 쓰는데 fcitx4 는 이를
  제공하지 않아, `GTK_IM_MODULE=fcitx` 가 설정돼 있어도 한영 전환이 되지 않습니다.
  이미 chromium 이 떠 있으면 새 창이 기존 프로세스에 붙어 이 플래그가 무시되므로,
  전환이 안 되면 chromium 을 완전히 종료한 뒤 vpass 를 다시 실행하세요.
  (fcitx5 로 올리면 `--enable-wayland-ime` 로 Wayland 네이티브 유지도 가능합니다.)
- 기상: 현재 시뮬레이션 제공자(`weather.py`)로 동작하며, 기상청 API 연동 시 해당 모듈만 교체하면 됩니다.

## 프로젝트 구조

```
vpass-application/
├── pyproject.toml          # uv 프로젝트 (스크립트: vpass)
├── src/vpass/
│   ├── main.py             # 엔트리포인트 (uvicorn + 브라우저/키오스크 + --reset)
│   ├── reset.py            # 시작 시 데이터 초기화(--reset / --reset-all)
│   ├── server.py           # FastAPI 앱 + 정적 서빙
│   ├── routes.py           # HTTP API 전체
│   ├── runtime.py          # 매니저 배선 + 출항/입항 확정 + 장치 시뮬레이터
│   ├── camera.py           # 카메라 스레드 + MJPEG 스트림
│   ├── facerec.py          # 얼굴 검출/인식(LBPH)
│   ├── jacketvision.py     # 구명조끼 착용 시각 확인(TFLite 분류기 + HSV 폴백)
│   ├── gps.py              # NMEA GPS(UART) 읽기
│   ├── compass.py          # QMC5883L 지자계(I2C) 읽기
│   ├── boarding.py         # 승선(출석) 세션 + 로그
│   ├── lifejacket.py       # 디바이스 레지스트리 + 익수 감지
│   ├── killswitch.py       # 시동 잠금/비상 정지 (GPIO 추상화)
│   ├── voyage.py           # 운항 기록(승선 명단 + 항해 1분 트랙) · 출입항은 지오펜스/수동
│   ├── telemetry.py        # GPS·지자계 통합 제공자 + 개발용 시뮬레이터
│   ├── weather.py          # 해양 기상 제공자 (KMA 연동 자리)
│   └── sos.py              # SOS 신고 관리
├── tools/
│   └── train_jacket_classifier.py  # 구명조끼 분류기 학습 (PC, tensorflow)
├── models/                 # 배포용 TFLite 모델 (jacket_classifier.tflite)
├── tests/test_flow.py      # 핵심 안전 시나리오 테스트
├── ui/                     # React + TypeScript (Vite)
│   └── src/screens/        # 홈/출항/운항기록지/사용자/구명조끼/어선정보/셋업
└── data/                   # 런타임 데이터 (git 제외, 학습 데이터셋 포함)
```
