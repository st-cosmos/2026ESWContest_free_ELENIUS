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

## V-PASS 단말 연동

V-PASS 애플리케이션을 아래 환경변수와 함께 실행하면 데모 관제 서버와 연동됩니다.
**미설정 시 V-PASS 는 기존과 동일하게 독립 동작**합니다.

```bash
# 데모 서버 먼저 실행 후,
cd vpass-application
VPASS_DEMO_SERVER_URL=http://localhost:8100 uv run vpass
```

연동 시 동작:

- V-PASS 텔레메트리(위치/침로/속력/승조원/출입항 상태) → 관제 대시보드에 **LIVE 선박 카드**로 표시
- V-PASS 신고(수동 SOS / 자동 익수) → 신고 접수 모달 + 최초 접수 알림
- V-PASS 출항/입항 → 출입항 자동 수집 로그
- 관제 대시보드에서 관할 기상 변경 → V-PASS 기상 표시에 자동 반영
- **운항 시뮬레이터 좌표 → V-PASS GPS** (단말 실측 GPS 가 없을 때만 사용)
- **지오펜스 통과 판정 → V-PASS 자동 출항/입항 신고**

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
GET  /api/sim/terminal    # (단말용) 시뮬레이션 좌표 + 출입항 명령
```

## 데모 시나리오

1. `demo-server` 실행 → 대시보드에 예시 선박 6척이 표시됨(출항 3 / 입항 3).
   출항 선박은 실시간으로 위치가 움직임.
2. 입항 선박 카드의 `출항 처리` → 카드가 밝아지고 앞으로 정렬 + 출입항 로그에 기록.
3. 우측 지도에서 관할 선택 → 기상 칩(맑음/구름조금/흐림/비/안개/뇌우) 클릭 → 해당 관할 기상 변경.
4. `VPASS_DEMO_SERVER_URL` 로 V-PASS 실행 후 SOS/익수 발생 → 대시보드에 **최초 접수 알림** 등장.
   기상을 흐림으로 바꾸면 V-PASS 화면에도 흐림으로 반영됨.

## 프로젝트 구조

```
demo-server/
├── pyproject.toml            # uv 프로젝트 (스크립트: demo-server)
├── src/demo_server/
│   ├── main.py               # 엔트리포인트 (uvicorn + 브라우저 + --reset)
│   ├── reset.py              # 시작 시 데이터 초기화(--reset / --reset-all)
│   ├── server.py             # FastAPI 앱 + 정적 서빙
│   ├── routes.py             # HTTP API 전체
│   ├── runtime.py            # 매니저 배선 + 위치 시뮬레이션 루프
│   ├── simulator.py          # 운항 시뮬레이터(항로 이동 + 지오펜스 출입항 판정)
│   ├── vessels.py            # 선박 레지스트리(수동 + V-PASS 라이브) + 이동 시뮬레이션
│   ├── weather.py            # 관할별 해양 기상
│   ├── reports.py            # 신고 수신함 (수동/자동)
│   ├── portlog.py            # 출입항 자동 수집 로그
│   ├── geo.py                # 위경도 좌표 포맷/이동
│   └── storage.py            # JSON 원자적 저장소
├── ui/                       # React + TypeScript (Vite)
│   └── src/
│       ├── App.tsx           # 대시보드 조립
│       ├── route.tsx         # 대시보드(/) ↔ 시뮬레이터(/simulator) 경로 전환
│       ├── screens/          # SimulatorPage (운항 시뮬레이터)
│       ├── components/       # 선박카드/지도/기상/신고 모달/폼/SimMap 등
│       ├── theme.css         # 라이트·다크 디자인 토큰
│       └── simulator.css     # 시뮬레이터 전용 스타일
└── data/                     # 런타임 데이터 (git 제외)
```
