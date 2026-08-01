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
    condition: str
    temp_c: float | None = None
    wind: str | None = None
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
        raise HTTPException(status_code=400, detail="올바르지 않은 관할 또는 기상 상태입니다.")
    return {"success": True, "region": region, "weather": entry}


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
    r = rt(request).reports.close(report_id)
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


@router.post("/api/ingest/vessel")
def ingest_vessel(cmd: IngestVesselCmd, request: Request):
    vessel = rt(request).vessels.upsert_live(cmd.model_dump(exclude_none=True))
    return {"success": True, "vessel": vessel}


@router.post("/api/ingest/report")
def ingest_report(cmd: IngestReportCmd, request: Request):
    report = rt(request).reports.add(cmd.model_dump())
    return {"success": True, "report": report}


@router.post("/api/ingest/port")
def ingest_port(cmd: IngestPortCmd, request: Request):
    entry = rt(request).ingest_port(cmd.kind, cmd.vessel_name, cmd.vessel_id, cmd.time)
    return {"success": True, "entry": entry}
