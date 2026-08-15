"""HTTP API 라우트 정의."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .runtime import Runtime

router = APIRouter()


def rt(request: Request) -> Runtime:
    return request.app.state.runtime


# ═══════════════════════════════════════════════════════════════════════
# 통합 상태 (대시보드)
# ═══════════════════════════════════════════════════════════════════════
@router.get("/api/state")
def get_state(request: Request):
    return rt(request).state_snapshot()


# ═══════════════════════════════════════════════════════════════════════
# 선박 관리 (수동 등록/수정/삭제 — 데모용 직접 입력)
# ═══════════════════════════════════════════════════════════════════════
class VesselCmd(BaseModel):
    name: str = Field(min_length=1)
    vessel_id: str = Field(min_length=1)
    region: str = "남해"
    lat: float = 34.8
    lon: float = 128.42
    course: float = 0
    speed_kn: float = 0
    crew: int = 0
    status: str = "docked"  # departed | docked


class VesselUpdateCmd(BaseModel):
    name: str | None = None
    vessel_id: str | None = None
    region: str | None = None
    lat: float | None = None
    lon: float | None = None
    course: float | None = None
    speed_kn: float | None = None
    crew: int | None = None
    status: str | None = None


class StatusCmd(BaseModel):
    status: str  # departed | docked


@router.post("/api/vessels")
def add_vessel(cmd: VesselCmd, request: Request):
    vessel = rt(request).vessels.add(cmd.model_dump())
    return {"success": True, "vessel": vessel,
            "message": f"'{vessel['name']}' 선박이 등록되었습니다."}


@router.put("/api/vessels/{vessel_id}")
def update_vessel(vessel_id: str, cmd: VesselUpdateCmd, request: Request):
    vessel = rt(request).vessels.update(vessel_id, cmd.model_dump(exclude_none=True))
    if vessel is None:
        raise HTTPException(status_code=404, detail="선박을 찾을 수 없습니다.")
    return {"success": True, "vessel": vessel, "message": "선박 정보가 수정되었습니다."}


@router.delete("/api/vessels/{vessel_id}")
def delete_vessel(vessel_id: str, request: Request):
    if not rt(request).vessels.delete(vessel_id):
        raise HTTPException(status_code=404, detail="선박을 찾을 수 없습니다.")
    return {"success": True, "message": "선박이 삭제되었습니다."}


@router.post("/api/vessels/{vessel_id}/status")
def set_vessel_status(vessel_id: str, cmd: StatusCmd, request: Request):
    result = rt(request).set_vessel_status(vessel_id, cmd.status)
    if result is None:
        raise HTTPException(status_code=404, detail="선박을 찾을 수 없거나 잘못된 상태입니다.")
    return {"success": True, "vessel": result["vessel"]}


# ═══════════════════════════════════════════════════════════════════════
# 해양 기상 (관할별) — 설정하면 V-PASS 가 조회해 반영
# ═══════════════════════════════════════════════════════════════════════
class WeatherCmd(BaseModel):
    """관할 기상 수정.

    condition 없이 수치만 보내면 기상 상태는 그대로 두고 값만 바꾼다.
    풍향(wind_dir)은 바람이 불어오는 방향, 해류(current_dir)는 흘러가는 방위다.
    """

    condition: str | None = None
    temp_c: float | None = None
    wind_dir: str | None = None          # N/NE/E/SE/S/SW/W/NW
    wind_speed_ms: float | None = None
    gust_ms: float | None = None
    current_dir: float | None = None     # 0~359
    current_kn: float | None = None
    wave_height_m: float | None = None
    water_temp_c: float | None = None


@router.get("/api/weather")
def get_all_weather(request: Request):
    return rt(request).weather.all()


@router.get("/api/weather/{region}")
def get_region_weather(region: str, request: Request):
    entry = rt(request).weather.get(region)
    if entry is None:
        raise HTTPException(status_code=404, detail="관할을 찾을 수 없습니다.")
    return entry


@router.post("/api/weather/{region}")
def set_region_weather(region: str, cmd: WeatherCmd, request: Request):
    entry = rt(request).weather.set_condition(
        region, cmd.condition,
        extras=cmd.model_dump(exclude={"condition"}, exclude_none=True),
    )
    if entry is None:
        raise HTTPException(
            status_code=400, detail="올바르지 않은 관할·기상 상태 또는 풍향입니다."
        )
    return {"success": True, "region": region, "weather": entry}


# ═══════════════════════════════════════════════════════════════════════
# 해양 벡터 필드 (해류 · 풍향/풍속 시각화) — 국립해양조사원 또는 관제 설정값
# ═══════════════════════════════════════════════════════════════════════
@router.get("/api/ocean/field")
def ocean_field(
    request: Request,
    layer: str = "current",
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
    cols: int = 26,
    rows: int = 18,
    region: str | None = None,
):
    bbox = None
    if None not in (min_lat, max_lat, min_lon, max_lon):
        bbox = {"min_lat": min_lat, "max_lat": max_lat,
                "min_lon": min_lon, "max_lon": max_lon}
    return rt(request).ocean.field(
        layer=layer, bbox=bbox, cols=cols, rows=rows, region=region
    )


# ═══════════════════════════════════════════════════════════════════════
# 요구조자 예상 위치 (표류 예측 바운더리)
# ═══════════════════════════════════════════════════════════════════════
@router.get("/api/reports/{report_id}/boundary")
def report_boundary(report_id: str, request: Request, minutes: float | None = None):
    """익수 지점 + 해류·풍압으로 계산한 예상 중심 좌표와 확률 반경.

    minutes 를 주면 해당 경과 시간(분)으로, 없으면 실제 경과 시간으로 계산한다.
    **익수(mob) 신고 전용** — 수동 SOS 는 요구조자가 없어 404 를 돌려준다.
    """
    runtime = rt(request)
    result = runtime.report_boundary(report_id, minutes)
    if result is None:
        report = runtime.reports.get(report_id)
        if report is not None:
            raise HTTPException(
                status_code=404,
                detail="수동 SOS 신고입니다. 요구조자 예상 위치는 익수 신고에만 제공됩니다.",
            )
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다.")
    return result


# ═══════════════════════════════════════════════════════════════════════
# 신고 수신함
# ═══════════════════════════════════════════════════════════════════════
@router.get("/api/reports")
def list_reports(request: Request):
    return rt(request).reports.list_public()


@router.post("/api/reports/{report_id}/seen")
def report_seen(report_id: str, request: Request):
    r = rt(request).reports.mark_alerted(report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다.")
    return {"success": True}


@router.post("/api/reports/{report_id}/dispatch")
def report_dispatch(report_id: str, request: Request):
    r = rt(request).reports.dispatch(report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다.")
    return {"success": True, "report": r}


@router.post("/api/reports/{report_id}/close")
def report_close(report_id: str, request: Request):
    """상황 종료 — 남은 신고가 없으면 시뮬레이터 위치 고정도 함께 해제된다."""
    r = rt(request).close_report(report_id)
    if r is None:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다.")
    return {"success": True, "report": r}


# ═══════════════════════════════════════════════════════════════════════
# V-PASS 단말 수신 (ingest) — V-PASS demo_bridge 가 호출
# ═══════════════════════════════════════════════════════════════════════
class IngestVesselCmd(BaseModel):
    vessel_id: str
    name: str | None = None
    region: str | None = None
    lat: float | None = None
    lon: float | None = None
    course: float | None = None
    speed_kn: float | None = None
    crew: int | None = None
    status: str | None = None
    gps_source: str | None = None  # hardware | sim | demo_sim


class IngestReportCmd(BaseModel):
    cause: str  # manual | mob
    detail: str | None = None
    time: str | None = None
    position: str | None = None
    vessel_name: str | None = None
    vessel_id: str | None = None
    region: str | None = None


class IngestPortCmd(BaseModel):
    kind: str  # departure | arrival
    vessel_name: str
    vessel_id: str
    time: str | None = None


# ═══════════════════════════════════════════════════════════════════════
# 운항 시뮬레이터 (지도에서 선박을 움직여 V-PASS 단말에 좌표를 공급)
# ═══════════════════════════════════════════════════════════════════════
class SimPositionCmd(BaseModel):
    lat: float
    lon: float


class SimPointsCmd(BaseModel):
    points: list[list[float]] = Field(default_factory=list)


class SimSpeedCmd(BaseModel):
    speed_kn: float | None = None
    time_scale: float | None = None


class SimRunCmd(BaseModel):
    action: str  # start | pause | stop


@router.get("/api/sim/state")
def sim_state(request: Request):
    return rt(request).simulator_snapshot()


@router.post("/api/sim/position")
def sim_position(cmd: SimPositionCmd, request: Request):
    rt(request).simulator.set_position(cmd.lat, cmd.lon)
    return {"success": True}


@router.post("/api/sim/route")
def sim_route(cmd: SimPointsCmd, request: Request):
    rt(request).simulator.set_route(cmd.points)
    return {"success": True}


@router.post("/api/sim/fence")
def sim_fence(cmd: SimPointsCmd, request: Request):
    rt(request).simulator.set_fence(cmd.points)
    return {"success": True}


@router.post("/api/sim/fence/flip")
def sim_fence_flip(request: Request):
    rt(request).simulator.flip_sea_side()
    return {"success": True}


@router.post("/api/sim/speed")
def sim_speed(cmd: SimSpeedCmd, request: Request):
    simulator = rt(request).simulator
    if cmd.speed_kn is not None:
        simulator.set_speed(cmd.speed_kn)
    if cmd.time_scale is not None:
        simulator.set_time_scale(cmd.time_scale)
    return {"success": True}


@router.post("/api/sim/run")
def sim_run(cmd: SimRunCmd, request: Request):
    try:
        rt(request).simulator.run(cmd.action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}


@router.post("/api/sim/reset")
def sim_reset(request: Request):
    rt(request).simulator.reset()
    return {"success": True}


@router.post("/api/sim/sos/release")
def sim_sos_release(request: Request):
    """SOS 위치 고정 해제 (시연 중 수동 복구용)."""
    rt(request).simulator.release_sos()
    return {"success": True}


@router.get("/api/sim/terminal")
def sim_terminal(request: Request):
    """V-PASS 단말이 주기적으로 받아가는 시뮬레이션 좌표 + 출입항 명령."""
    return rt(request).simulator.terminal_feed()


@router.post("/api/ingest/vessel")
def ingest_vessel(cmd: IngestVesselCmd, request: Request):
    vessel = rt(request).vessels.upsert_live(cmd.model_dump(exclude_none=True))
    return {"success": True, "vessel": vessel}


@router.post("/api/ingest/report")
def ingest_report(cmd: IngestReportCmd, request: Request):
    """V-PASS 신고 수신 → 수신함 저장 + 운항 시뮬레이터 위치 고정."""
    report = rt(request).ingest_report(cmd.model_dump())
    return {"success": True, "report": report}


@router.post("/api/ingest/port")
def ingest_port(cmd: IngestPortCmd, request: Request):
    entry = rt(request).ingest_port(cmd.kind, cmd.vessel_name, cmd.vessel_id, cmd.time)
    return {"success": True, "entry": entry}
