"""시작 시 데이터 초기화 (`--reset` / `--reset-all`).

관제 서버도 이전 실행 상태를 파일로 들고 있다. 특히 운항 시뮬레이터의
`port_state` 가 `departed` 로 남아 있으면 다시 켰을 때도 '출항 중'에서
이어지므로, V-PASS 단말만 초기화해서는 시연이 깨끗하게 리셋되지 않는다.

  uv run demo-server --reset       # 신고·출입항 로그·선박 목록 + 출입항 상태 초기화
  uv run demo-server --reset-all   # 시뮬레이터 항로·펜스, 관할 기상까지 전부 초기화
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .simulator import DEFAULT_SPEED_KN, HOME_LAT, HOME_LON
from .storage import JsonStore

# --reset: 실행할 때마다 쌓이는 기록 (선박 목록은 지우면 데모 시드로 재생성된다)
RUNTIME_FILES = (
    (config.REPORTS_FILE, "신고 접수"),
    (config.PORTLOG_FILE, "출입항 로그"),
    (config.VESSELS_FILE, "선박 목록"),
)

# --reset-all: 시연자가 미리 설정해 둔 값까지
SETUP_FILES = (
    (config.SIMULATOR_FILE, "운항 시뮬레이터(항로·펜스)"),
    (config.WEATHER_FILE, "관할 기상"),
)

# 시뮬레이터에서 '이전 실행의 출항 상태'에 해당하는 항목
_SIM_PORT_STATE = {
    "port_state": "docked",
    "command": None,
    "command_seq": 0,
    "events": [],
    "target_index": 1,
    "finished": False,
}


def _remove(path: Path, label: str, removed: list[str]) -> None:
    """파일과 원자적 쓰기용 임시 파일(.tmp)을 함께 지운다."""
    for target in (path, path.with_suffix(path.suffix + ".tmp")):
        if not target.exists():
            continue
        try:
            target.unlink()
        except OSError as e:
            print(f"[reset] {target.name} 삭제 실패: {e}")
            continue
        if target == path:
            removed.append(label)


def _reset_simulator_port_state(removed: list[str]) -> None:
    """항로·펜스는 남기고 출입항 상태만 되돌린다(선박은 항로 시작점으로).

    펜스를 다시 그리게 하면 시연 준비가 번거로워지므로, `--reset` 에서는
    '출항 중' 상태와 단말로 보낼 명령만 초기화한다.
    """
    if not config.SIMULATOR_FILE.exists():
        return
    store = JsonStore(config.SIMULATOR_FILE, {})
    data = store.load()
    if not isinstance(data, dict) or not data:
        return

    route = data.get("route") or []
    start = route[0] if route and isinstance(route[0], dict) else None
    clean = dict(_SIM_PORT_STATE)
    clean["lat"] = float(start["lat"]) if start else HOME_LAT
    clean["lon"] = float(start["lon"]) if start else HOME_LON
    clean["speed_kn"] = float(data.get("speed_kn") or DEFAULT_SPEED_KN)

    if all(data.get(key) == value for key, value in clean.items()):
        return  # 이미 정박 상태 — 지울 것이 없다
    data.update(clean)
    store.save(data)
    removed.append("시뮬레이터 출입항 상태")


def reset_data(include_setup: bool = False) -> list[str]:
    """저장 데이터를 지우고, 실제로 지운 항목의 이름을 돌려준다.

    include_setup=True 이면 시뮬레이터 항로·펜스와 관할 기상까지 모두 지운다.
    """
    config.ensure_dirs()
    removed: list[str] = []

    for path, label in RUNTIME_FILES:
        _remove(path, label, removed)

    if include_setup:
        for path, label in SETUP_FILES:
            _remove(path, label, removed)
    else:
        _reset_simulator_port_state(removed)

    return removed
