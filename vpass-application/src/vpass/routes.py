"""HTTP API 라우트 정의."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .runtime import Runtime

router = APIRouter()


def rt(request: Request) -> Runtime:
    return request.app.state.runtime


# ═══════════════════════════════════════════════════════════════════════
# 구명조끼 장치(ESP8266) 수신 — 펌웨어 경로와 호환 유지
# ═══════════════════════════════════════════════════════════════════════
class WearingCmd(BaseModel):
    device: str = "jacket-1"
    worn: bool


class PingCmd(BaseModel):
    device: str = "jacket-1"


class FallCmd(BaseModel):
    device: str = "jacket-1"
    magnitude: float = 0.0


class AckCmd(BaseModel):
    device: str | None = None


@router.post("/api/wearing")
def device_wearing(cmd: WearingCmd, request: Request):
    rt(request).devices.set_wearing(cmd.device, cmd.worn)
    return {"ok": True}


@router.post("/api/ping")
def device_ping(cmd: PingCmd, request: Request):
    rt(request).devices.ping(cmd.device)
    return {"ok": True}


@router.post("/api/fall")
def device_fall(cmd: FallCmd, request: Request):
    rt(request).devices.fall(cmd.device, cmd.magnitude)
    return {"ok": True}


@router.post("/api/ack")
def device_ack(cmd: AckCmd, request: Request):
    rt(request).devices.ack(cmd.device)
    return {"ok": True}


@router.post("/api/jacket-batt-alert/ack")
def ack_jacket_batt_alert(request: Request):
    rt(request).ack_jacket_batt_alert()
    return {"success": True}


@router.post("/api/jacket-alert/ack")
def ack_jacket_alert(request: Request):
    """운항 중 구명조끼 해제 경고 모달 확인(닫기) — UI 전용."""
    rt(request).ack_jacket_alert()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════
# 통합 상태 / 기상
# ═══════════════════════════════════════════════════════════════════════
@router.get("/api/state")
def get_state(request: Request):
    return rt(request).state_snapshot()


# ═══════════════════════════════════════════════════════════════════════
# 카메라
# ═══════════════════════════════════════════════════════════════════════
class CameraModeCmd(BaseModel):
    mode: str  # "idle" | "scan" | "register"


@router.post("/api/camera/mode")
def set_camera_mode(cmd: CameraModeCmd, request: Request):
    if cmd.mode not in ("idle", "scan", "register"):
        raise HTTPException(status_code=400, detail="올바르지 않은 카메라 모드입니다.")
    rt(request).camera.set_mode(cmd.mode)
    return {"success": True}


@router.get("/api/video_feed")
def video_feed(request: Request):
    return StreamingResponse(
        rt(request).camera.mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ═══════════════════════════════════════════════════════════════════════
# 사용자(선원) 관리
# ═══════════════════════════════════════════════════════════════════════
class UserRegisterCmd(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    device_id: str | None = None


class UserUpdateCmd(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    device_id: str | None = None


@router.get("/api/users")
def list_users(request: Request):
    return list(reversed(rt(request).users_store.load()))


@router.post("/api/users")
def register_user(cmd: UserRegisterCmd, request: Request):
    try:
        record = rt(request).register_user(cmd.name.strip(), cmd.phone.strip(), cmd.device_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "user": record,
            "message": f"'{record['name']}' 님이 등록되었습니다."}


@router.put("/api/users/{user_id}")
def update_user(user_id: str, cmd: UserUpdateCmd, request: Request):
    runtime = rt(request)
    users = runtime.users_store.load()
    if not any(u.get("id") == user_id for u in users):
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    def _update(us):
        for u in us:
            if u.get("id") == user_id:
                u["name"] = cmd.name.strip()
                u["phone"] = cmd.phone.strip()
                u["device_id"] = cmd.device_id or None
        return us

    runtime.users_store.update(_update)
    runtime.camera.train_model()
    return {"success": True, "message": f"'{cmd.name}' 님의 정보가 수정되었습니다."}


@router.delete("/api/users/{user_id}")
def delete_user(user_id: str, request: Request):
    try:
        target = rt(request).delete_user(user_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e.args[0]))
    return {"success": True, "message": f"'{target['name']}' 님의 정보가 삭제되었습니다."}


# ═══════════════════════════════════════════════════════════════════════
# 승선(출석) 세션 · 출항/입항 확정
# ═══════════════════════════════════════════════════════════════════════
@router.get("/api/boarding/session")
def boarding_session(request: Request):
    return rt(request).boarding.summary()


@router.post("/api/boarding/reset")
def boarding_reset(request: Request):
    rt(request).boarding.reset_session(relock=True)
    return {"success": True}


@router.post("/api/engine/allow")
def allow_engine_start(request: Request):
    """승선 인원 확인 → 시동 허용. 출항 신고는 지오펜스 판정으로 자동 등록된다."""
    try:
        result = rt(request).allow_engine_start()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"success": True, "crew": result["crew"],
            "message": "승선이 확인되었습니다. 시동을 켤 수 있습니다."}


@router.post("/api/departure/confirm")
def confirm_departure(request: Request):
    """수동 출항 신고 (지오펜스를 사용하지 않는 환경용)."""
    try:
        voyage = rt(request).confirm_departure()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"success": True, "voyage_id": voyage["id"],
            "message": "출항 신고가 접수되었습니다."}


@router.post("/api/arrival/confirm")
def confirm_arrival(request: Request):
    """입항 확정 — 입항 신고 + 시동 재잠금 + 승선 세션 초기화."""
    try:
        voyage = rt(request).confirm_arrival()
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"success": True, "voyage_id": voyage["id"],
            "message": "입항이 확정되었습니다."}


# ═══════════════════════════════════════════════════════════════════════
# 어선 정보 (최초 등록 + 수정)
# ═══════════════════════════════════════════════════════════════════════
class VesselCmd(BaseModel):
    region: str = Field(min_length=1)        # 동해/서해/남해/중부/제주
    vessel_id: str = Field(min_length=1)     # 어선식별번호
    name: str = Field(min_length=1)          # 어선명
    home_port: str = Field(min_length=1)     # 출항지


@router.get("/api/vessel")
def get_vessel(request: Request):
    return rt(request).vessel_store.load()


@router.put("/api/vessel")
def put_vessel(cmd: VesselCmd, request: Request):
    runtime = rt(request)
    existing = runtime.vessel_store.load()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "region": cmd.region,
        "vessel_id": cmd.vessel_id.strip(),
        "name": cmd.name.strip(),
        "home_port": cmd.home_port.strip(),
        "registered_at": (existing or {}).get("registered_at", now),
        "updated_at": now,
        "reported_at": now,  # 해양경찰청 자동 등록/보고(시뮬레이션)
    }
    runtime.vessel_store.save(record)
    verb = "보고" if existing else "등록"
    return {"success": True, "vessel": record,
            "message": f"해양경찰청에 자동 {verb}되었습니다"}


# ═══════════════════════════════════════════════════════════════════════
# 운항 기록지 (출입항 + 승선 명단 + 항해 1분 간격 좌표)
# ═══════════════════════════════════════════════════════════════════════
@router.get("/api/voyages")
def list_voyages(request: Request):
    return rt(request).voyage.list_voyages()


@router.get("/api/voyages/{voyage_id}")
def get_voyage(voyage_id: str, request: Request):
    v = rt(request).voyage.get_voyage(voyage_id)
    if v is None:
        raise HTTPException(status_code=404, detail="운항 기록을 찾을 수 없습니다.")
    return v


# ═══════════════════════════════════════════════════════════════════════
# SOS
# ═══════════════════════════════════════════════════════════════════════
@router.post("/api/sos")
def trigger_sos(request: Request):
    report = rt(request).trigger_sos_manual()
    return {"success": True, "report": report}


@router.post("/api/sos/ack")
def ack_sos(request: Request):
    rt(request).ack_sos()
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════
# 개발/시연용 시뮬레이션
# ═══════════════════════════════════════════════════════════════════════
class SimJacketCmd(BaseModel):
    device: str = "jacket-1"
    action: str  # wear | doff | fall | overboard | silence | resume | lowbatt | battok


@router.post("/api/dev/jacket")
def dev_jacket(cmd: SimJacketCmd, request: Request):
    try:
        jacket = rt(request).sim_jacket(cmd.device)
        jacket.apply(cmd.action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "jacket": jacket.snapshot()}
