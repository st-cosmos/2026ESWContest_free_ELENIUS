# V-PASS 데모 관제 서버

Smart V-PASS 시연용 **해양경찰 통합 관제 대시보드**입니다.
여러 어선의 실시간 출입항·위치를 한눈에 보고, V-PASS 단말에서 접수된 신고를
확인하며, 관할별 해양 기상을 설정해 V-PASS 로 내려보냅니다.

- **백엔드**: Python(FastAPI) — `uv` 로 관리 (V-PASS 애플리케이션과 동일 스택)
- **UI**: React + TypeScript(Vite) — 라이트/다크 모드 지원
- **디자인**: `design/demo-service-design.pen` (Pencil) 기준

## 주요 기능

1. **선박 현황** — 카드마다 선박명·식별번호·실시간 GPS·침로·속력·승조원 표시.
   출항 선박은 밝게 & 앞쪽에, 입항 선박은 어둡게(비활성) 표시. 데모용 직접 등록/수정 지원.
2. **신고 접수** — V-PASS 신고를 모달로 확인. 수동 신고 / 자동 신고(익수, 물에 빠졌을 때)를 구분.
   신규 신고가 접수되면 **해당 건만 보여주는 최초 접수 알림 모달**이 즉시 뜸.
3. **해양 기상 관제** — 화면 오른쪽 1/3에 한반도 지도 + 5개 지방해양경찰청(동해·서해·남해·중부·제주) 관할 기상.
4. **기상 → V-PASS 반영** — 관할 기상을 바꾸면(예: 흐림) 해당 관할의 V-PASS 단말에 자동 반영.
5. **출입항 자동 수집** — 선박 출입항 시 선박명·식별번호·출입항 시각을 자동 로그로 수집.
6. **운항 시뮬레이터**(`/simulator`) — 지도에서 V-PASS 단말을 드래그해 GPS 좌표를 만들고,
   항로(waypoint)를 찍어 일정 속력으로 이동시키며, 지오펜스를 그려 **자동 출입항**을 판정합니다.
7. **요구조자 예상 위치 바운더리**(`/boundary/{신고ID}`) — SOS·익수 신고가 접수되면 사고 위치를
   기준으로 해류·풍압에 따른 **표류 예측 바운더리**를 실시간으로 그립니다. 신고 접수 현황에서
   신고 선박을 누르면 열립니다.
8. **해양 벡터 필드** — 해류·풍향/풍속의 흐름을 지도 위에 입자 궤적으로 애니메이션합니다
   (국립해양조사원 실측/예측값 또는 관제사 설정값 기반).

## 요구조자 예상 위치 (생존 가능성 · 구조 효율)

`신고 접수 현황` → 신고 선박 클릭 → `/boundary/{신고ID}`

- **지도**: 익수 지점(십자) → 합성 표류 벡터 → **확률 바운더리**(50 / 75 / 95%)와
  표류 방위 ±28° **탐색 우선 부채꼴**. 미래 시간대(+30/+60/+120분) 95% 경계도 함께 표시해
  구역이 어떻게 커지고 밀려가는지 한눈에 보입니다.
- **벡터 필드**: 해류(청록)·바람(주황) 흐름을 입자로 애니메이션. 상단에서 레이어를 끄고 켭니다.
- **타임라인**: `실시간 추적`(실제 경과 시간) 또는 +30/+60/+120분을 골라 예측 시점을 바꿉니다.
- **우측 패널**: 신고 정보 · 실시간 해양 환경 · 표류 예측 계산 근거 · 시간별 탐색 구역(반경/면적).

### 표류(Leeway) 모델 — 시연용 근사

| 항목 | 근거 |
| --- | --- |
| 표류 벡터 | **해류 100% + 풍속의 3%(풍압)** 벡터 합성. 사람은 수면에 잠겨 해류를 그대로 따라가고, 노출된 상체가 받는 풍압은 통상 풍속의 2~4% 로 봅니다. 풍향은 '불어오는 방향'이라 풍압은 그 반대로 작용합니다. |
| 탐색 반경 | 위치 오차가 2차원 정규분포를 따른다고 보면 거리는 Rayleigh 분포가 되고, 포함 확률 p 의 반경은 `σ·√(-2·ln(1-p))` 입니다. `σ(t) = 0.28 nm/h × 경과시간` 기본값에서 **60분 95% 반경 ≈ 1.27 km** 로 해경 초기 탐색 구역 규모와 비슷합니다. |
| 생존 한계 | 수온별 저체온 생존곡선 근사(참고용 '추정'). |

SAROPS/CANSARP 급 수치모델이 아닌 **시연용 근사**입니다. 계수는 환경변수로 조정합니다
(`DEMO_LEEWAY_RATIO`, `DEMO_DRIFT_SPREAD_NM`, `DEMO_DRIFT_SECTOR_DEG`).

## 실행 방법

### 1) UI 빌드 (최초 1회 또는 UI 수정 시)

```bash
cd demo-server/ui
npm install
npm run build        # → ui/dist 생성
```

### 2) 서버 실행

```bash
cd demo-server
uv run demo-server                 # 서버 시작 + 브라우저 자동 열기 (기본 포트 8100)
uv run demo-server --no-browser    # 서버만
uv run demo-server --lora --lora-port /dev/ttyUSB0
```

- 접속: `http://localhost:8100` (대시보드), `http://localhost:8100/simulator` (운항 시뮬레이터),
  `http://localhost:8100/docs` (API 문서)
- UI 개발 시: `cd ui && npm run dev` → `http://localhost:5273` (API 는 8100 으로 프록시)

### 3) 데이터 초기화하고 실행하기

관제 서버도 이전 실행 상태를 파일로 들고 있습니다. 특히 운항 시뮬레이터의
출입항 상태(`port_state`)가 `departed` 로 남아 있으면 다시 켜도 '출항 중'에서
이어지므로, V-PASS 단말만 초기화해서는 시연이 깨끗하게 리셋되지 않습니다.

```bash
uv run demo-server --reset       # 신고·출입항 로그·선박 목록 + 출항 상태 초기화
uv run demo-server --reset-all   # 시뮬레이터 항로·펜스, 관할 기상까지 전부 초기화
```

| 옵션 | 지우는 것 | 남기는 것 |
| --- | --- | --- |
| `--reset` | `reports.json`(신고), `portlog.json`(출입항 로그), `vessels.json`(선박 목록 → 데모 6척으로 재생성), 시뮬레이터의 출항 상태·단말 명령·이벤트 | 시뮬레이터 항로·펜스·배속, 관할 기상 |
| `--reset-all` | 위 항목 + `simulator.json`, `weather.json` | (없음 — 최초 실행 상태로 돌아감) |

- `--reset` 은 **항로와 지오펜스를 남깁니다**. 매번 다시 그리지 않고 시연을
  처음부터 반복할 수 있도록, 선박만 항로 시작점·정박 상태로 되돌립니다.
- V-PASS 단말도 함께 초기화하려면 `uv run vpass --reset` 을 같이 실행하세요.

### 환경 변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `DEMO_PORT` | `8100` | 서버 포트 |
| `DEMO_DATA_DIR` | `demo-server/data` | 선박/신고/출입항/기상 JSON 저장 위치 |
| `DEMO_LORA` | `0` | `1`이면 LoRa UART로 V-PASS 단말 메시지를 수신 |
| `DEMO_LORA_PORT` | `/dev/ttyUSB0` | LoRa 모듈 UART 장치 경로 |
| `DEMO_LORA_BAUDRATE` | `9600` | LoRa 모듈 UART baudrate |
| `DEMO_LORA_TIMEOUT` | `2.5` | LoRa write timeout/응답 처리 기준 시간(초) |
| `DEMO_KHOA_API_KEY` | (없음) | 국립해양조사원 공공데이터 인증키. 설정 시 실측·예측 해류/바람을 가져옵니다 |
| `DEMO_KHOA_BASE` | `http://www.khoa.go.kr/api/oceangrid` | KHOA OpenAPI 베이스 |
| `DEMO_KHOA_ROMS_URL` 등 | 베이스 기준 | 서비스별 경로 개별 지정 (활용 승인 후 확정된 경로로 교체) |
| `DEMO_KHOA_SYNC_SEC` | `600` | 실측값을 관할 기상에 반영하는 주기(초) |
| `DEMO_LEEWAY_RATIO` | `0.03` | 표류 계산 시 풍속에 곱하는 풍압 계수 |
| `DEMO_DRIFT_SPREAD_NM` | `0.28` | 경과 1시간당 위치 오차 반경(해리) |
| `DEMO_DRIFT_SECTOR_DEG` | `28` | 탐색 우선 부채꼴 반각(°) |

### 국립해양조사원(KHOA) 연동

`docs/api-list.md` 의 서비스 중 표류 예측에 필요한 항목만 사용합니다.

| 용도 | 서비스 | data.go.kr |
| --- | --- | --- |
| 격자 해류장 | ROMS 수치예측모델 (예측 유향/유속·수온) | 15142227 |
| 실측 해류 | 해수유동 관측소 실측 유향/유속 | 15155531 |
| 조류 예보 | 조류예보(시계열) | 15156024 |
| 실측 바람 | 조위관측소 실측 풍향/풍속 | 15142518 |
| 부이 관측 | 해양관측부이 최신 관측데이터 | 15155516 |
| 파고 | 국가해양관측망 실측 파랑 | 15155994 |

```bash
DEMO_KHOA_API_KEY=발급받은_인증키 uv run demo-server
```

- **인증키가 없으면** 관제사가 기상 관제에서 설정한 풍향·풍속·해류 값으로 벡터 필드와
  표류 예측을 계산합니다. 즉 **키 없이도 시연은 그대로 동작**합니다.
- 응답은 data.go.kr 표준(`response.body.items.item`)과 KHOA 오션그리드(`result.data`) 두 형식을
  모두 받아들이며, 실패하면 조용히 설정값 계산으로 되돌아갑니다(관제 화면은 멈추지 않습니다).
- 실제 오퍼레이션 경로는 활용 승인 후 확정되므로 `DEMO_KHOA_*_URL` 로 덮어쓸 수 있습니다.

## V-PASS 단말 연동

V-PASS 애플리케이션을 아래 환경변수와 함께 실행하면 데모 관제 서버와 연동됩니다.
**미설정 시 V-PASS 는 기존과 동일하게 독립 동작**합니다.

```bash
# 데모 서버 먼저 실행 후,
cd vpass-application
VPASS_DEMO_SERVER_URL=http://localhost:8100 uv run vpass
```

Wi-Fi/LAN 대신 E220-900T22D LoRa UART를 사용할 수도 있습니다. 이 경우 관제
서버와 V-PASS 단말 양쪽에 LoRa 모듈이 연결되어 있어야 하며, 관제 서버를 먼저
LoRa 수신 모드로 실행합니다.

```bash
# 관제 서버
cd demo-server
uv run demo-server --lora --lora-port /dev/ttyUSB0 --lora-baudrate 9600

# V-PASS 단말
cd ../vpass-application
uv run vpass --demo-transport lora --lora-port /dev/ttyUSB0 --lora-baudrate 9600
```

HTTP 연동을 명시적으로 선택하려면 `uv run vpass --demo-transport http
--demo-server-url http://관제서버:8100` 형태로 실행합니다.

연동 시 동작:

- V-PASS 텔레메트리(위치/침로/속력/승조원/출입항 상태) → 관제 대시보드에 **LIVE 선박 카드**로 표시
- V-PASS 신고(수동 SOS / 자동 익수) → 신고 접수 모달 + 최초 접수 알림
- V-PASS 출항/입항 → 출입항 자동 수집 로그
- 관제 대시보드에서 관할 기상 변경 → V-PASS 기상 표시에 자동 반영
- **운항 시뮬레이터 좌표 → V-PASS GPS** (단말 실측 GPS 가 없을 때만 사용)
- **지오펜스 통과 판정 → V-PASS 자동 출항/입항 신고**
- **킬 스위치 원격 제어** — 시뮬레이터 페이지의 `엔진 비상 차단`/`차단 해제` 버튼이
  V-PASS 단말의 엔진을 차단/복구하고, 단말이 BLE 로 킬 스위치 펌웨어(릴레이)까지 반영

## 운항 시뮬레이터 (`/simulator`)

상단 탭에서 `운항 시뮬레이터` 로 이동합니다. V-PASS 단말이 연결되면 그 단말의
좌표를 시뮬레이터가 대신 만들어 내려보냅니다.

| 도구 | 동작 |
| --- | --- |
| 이동 | 선박 아이콘·정보 카드를 드래그 → 놓은 위치의 위경도가 V-PASS 로 전송 |
| 항로 펜 | 지도를 클릭할 때마다 항로 점 추가. `운항 시작` 을 누르면 순서대로 일정 속력 이동 |
| 지오펜스 | 지도를 클릭해 판정선을 그림. 꼭짓점을 드래그해 편집 |
| 지우기 | 항로 점·펜스 꼭짓점을 클릭해 삭제 |

- 지오펜스를 처음 그리면 **선박이 있는 쪽을 항내**로 보고 반대쪽을 바다로 잡습니다.
  방향이 반대라면 `바다 방향 뒤집기` 로 전환합니다.
- 펜스를 넘어 **바다 쪽으로 나가면 자동 출항**, 다시 **안으로 들어오면 자동 입항** 이
  V-PASS 단말에 등록되고, 그 결과가 출입항 자동 수집 로그로 돌아옵니다.
- 실제 속력(kn)으로는 시연 중 움직임이 거의 보이지 않으므로 **배속(1x/10x/30x/60x)** 을
  제공합니다. V-PASS 에 전송되는 속력은 설정한 실제 속력 그대로입니다.

```
GET  /api/sim/state       # 시뮬레이터 전체 상태(항로/펜스/선박/이벤트)
POST /api/sim/position    # 선박 위치 이동(드래그)
POST /api/sim/route       # 항로 점 전체 교체
POST /api/sim/fence       # 지오펜스 점 전체 교체
POST /api/sim/fence/flip  # 바다 방향 뒤집기
POST /api/sim/speed       # 속력(kn) / 배속
POST /api/sim/run         # start | pause | stop
POST /api/sim/reset       # 항로·펜스·이벤트 초기화
POST /api/sim/sos/release # SOS 위치 고정 해제 (시연 중 수동 복구)
GET  /api/sim/terminal    # (단말용) 시뮬레이션 좌표 + 출입항/킬 스위치 명령
POST /api/killswitch      # 킬 스위치 원격 제어 { action: "kill" | "restore" }
```

## 해양 환경 · 표류 예측 API

```
GET  /api/ocean/field?layer=current|wind&min_lat=..&max_lat=..&min_lon=..&max_lon=..&cols=..&rows=..
     # 흐름 시각화용 벡터 격자 (방위 · 세기). 출처는 KHOA 또는 관제 설정값
GET  /api/reports/{id}/boundary?minutes=12
     # 요구조자 예상 중심 좌표 + 확률 반경(50/75/95%) + 탐색 부채꼴 + 시간별 구역
POST /api/weather/{region}
     # {"wind_dir":"SW","wind_speed_ms":4.2,"current_dir":55,"current_kn":0.32}
     # condition 없이 수치만 보내면 기상 상태는 유지한 채 값만 바뀐다
```

## 데모 시나리오

1. `demo-server` 실행 → 대시보드에 예시 선박 6척이 표시됨(출항 3 / 입항 3).
   출항 선박은 실시간으로 위치가 움직임.
2. 입항 선박 카드의 `출항 처리` → 카드가 밝아지고 앞으로 정렬 + 출입항 로그에 기록.
3. 우측 지도에서 관할 선택 → 기상 칩(맑음/구름조금/흐림/비/안개/뇌우) 클릭 → 해당 관할 기상 변경.
   그 아래 **풍향 8방위 · 풍속 · 돌풍 · 해류 방위 · 유속**을 직접 조정할 수 있습니다.
4. `VPASS_DEMO_SERVER_URL` 로 V-PASS 실행 후 SOS/익수 발생 → 대시보드에 **최초 접수 알림** 등장.
   기상을 흐림으로 바꾸면 V-PASS 화면에도 흐림으로 반영됨.
5. **SOS 접수 시** 운항 시뮬레이터가 자동으로 **위치 고정**되고(킬 스위치로 배가 멈추므로),
   이후에는 해류·풍압에 따른 **표류만** 반영됩니다. 지도 상단에 SOS 배너, 하단에 `운항 재개 불가`
   표시가 뜨고, `고정 해제` 또는 신고 `상황 종료` 로 풀립니다.
6. **신고 접수 현황에서 신고 선박 클릭** → 요구조자 예상 위치 바운더리 페이지.
   기상 관제에서 풍향·해류를 바꾸면 지도의 흐름과 바운더리가 **즉시** 따라 움직입니다.

## 풍향·풍속·해류 편집 (한 곳만 바꾸면 전부 반영)

`weather.json` 은 수치를 개별 필드로 보관합니다. `wind` 문자열은 기존 화면 호환용 파생 값입니다.

| 필드 | 의미 |
| --- | --- |
| `wind_dir` | 바람이 **불어오는** 8방위 (기상 표준) |
| `wind_speed_ms`, `gust_ms` | 풍속 · 순간최대풍속 (m/s) |
| `current_dir` | 해류가 **흘러가는** 방위 (0~359°) |
| `current_kn` | 유속 (kn) |

수정하면 ① 관제 대시보드 표시 ② 해양 벡터 필드(흐름 애니메이션) ③ 요구조자 표류 예측
④ V-PASS 단말 기상 표시가 **모두 같은 값**으로 갱신됩니다.

## 프로젝트 구조

```
demo-server/
├── pyproject.toml            # uv 프로젝트 (스크립트: demo-server)
├── src/demo_server/
│   ├── main.py               # 엔트리포인트 (uvicorn + 브라우저 + --reset)
│   ├── reset.py              # 시작 시 데이터 초기화(--reset / --reset-all)
│   ├── server.py             # FastAPI 앱 + 정적 서빙
│   ├── routes.py             # HTTP API 전체
│   ├── runtime.py            # 매니저 배선 + 위치 시뮬레이션 루프 + SOS 위치 고정
│   ├── khoa.py               # 국립해양조사원 공공데이터 연동 (해류·바람·파고)
│   ├── ocean.py              # 해양 벡터 필드 격자 생성 (흐름 시각화)
│   ├── drift.py              # 요구조자 표류 예측(Leeway) + 확률 바운더리
│   ├── simulator.py          # 운항 시뮬레이터(항로 이동 + 지오펜스 + SOS 표류)
│   ├── vessels.py            # 선박 레지스트리(수동 + V-PASS 라이브) + 이동 시뮬레이션
│   ├── weather.py            # 관할별 해양 기상
│   ├── reports.py            # 신고 수신함 (수동/자동)
│   ├── portlog.py            # 출입항 자동 수집 로그
│   ├── geo.py                # 위경도 좌표 포맷/이동
│   └── storage.py            # JSON 원자적 저장소
├── ui/                       # React + TypeScript (Vite)
│   └── src/
│       ├── App.tsx           # 대시보드 조립
│       ├── route.tsx         # 대시보드(/) ↔ 시뮬레이터(/simulator) ↔ 바운더리(/boundary/:id)
│       ├── screens/          # SimulatorPage, BoundaryPage(요구조자 예상 위치)
│       ├── components/       # 선박카드/지도/기상/신고 모달/SimMap
│       │                     # OceanField(흐름 애니메이션), BoundaryMap(확률 바운더리)
│       ├── theme.css         # 라이트·다크 디자인 토큰
│       ├── simulator.css     # 시뮬레이터 전용 스타일
│       └── boundary.css      # 요구조자 예상 위치 전용 스타일
└── data/                     # 런타임 데이터 (git 제외)
```
