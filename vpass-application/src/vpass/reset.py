"""시작 시 데이터 초기화 (`--reset` / `--reset-all`).

프로그램을 껐다 켜도 `voyages.json` 의 운항이 `active` 로 남아 있으면 다시
'운항 중(이미 출항함)' 상태로 복구되고, 그 운항에 저장된 승선 명단도 그대로
보인다. 시연을 처음부터 다시 돌릴 수 있도록 서버가 뜨기 전에 저장 파일을 지운다.

  uv run vpass --reset       # 운항·승선 기록만 초기화 (선원/어선 정보 유지)
  uv run vpass --reset-all   # 등록 선원·얼굴 사진·어선 정보까지 전부 초기화
"""

from __future__ import annotations

from pathlib import Path

from . import config

# --reset: 실행할 때마다 새로 쌓이는 기록 — '이미 출항' 상태가 남는 원인
RUNTIME_FILES = (
    (config.VOYAGES_FILE, "운항 기록"),
    (config.BOARDING_LOGS_FILE, "승선 이력"),
)

# --reset-all: 미리 등록해 둔 정보까지 (얼굴 사진은 FACES_DIR 통째로)
REGISTRY_FILES = (
    (config.USERS_FILE, "등록 선원"),
    (config.VESSEL_FILE, "어선 정보"),
)


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


def _clear_faces(removed: list[str]) -> None:
    """등록 얼굴 사진을 지운다(디렉터리는 남긴다)."""
    count = 0
    for photo in config.FACES_DIR.glob("*"):
        if not photo.is_file():
            continue
        try:
            photo.unlink()
            count += 1
        except OSError as e:
            print(f"[reset] {photo.name} 삭제 실패: {e}")
    if count:
        removed.append(f"얼굴 사진 {count}장")


def reset_data(include_registry: bool = False) -> list[str]:
    """저장 데이터를 지우고, 실제로 지운 항목의 이름을 돌려준다.

    include_registry=True 이면 등록 선원·얼굴 사진·어선 정보까지 모두 지운다.
    """
    config.ensure_dirs()
    removed: list[str] = []

    for path, label in RUNTIME_FILES:
        _remove(path, label, removed)

    if include_registry:
        for path, label in REGISTRY_FILES:
            _remove(path, label, removed)
        _clear_faces(removed)

    return removed
