// 데모 관제 서버 API 호출 헬퍼

import type {
  AppState,
  Boundary,
  OceanBBox,
  OceanFieldData,
  SimState,
  Vessel,
  VesselForm,
  WeatherPatch,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `요청 실패 (${res.status})`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* JSON 아님 */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

const put = <T,>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });

type Ok = { success: boolean; message?: string };

export const api = {
  state: () => request<AppState>("/api/state"),

  addVessel: (v: VesselForm) =>
    post<{ success: boolean; vessel: Vessel; message: string }>("/api/vessels", v),
  updateVessel: (id: string, v: Partial<VesselForm>) =>
    put<Ok>(`/api/vessels/${id}`, v),
  deleteVessel: (id: string) =>
    request<Ok>(`/api/vessels/${id}`, { method: "DELETE" }),
  setVesselStatus: (id: string, status: "departed" | "docked") =>
    post<Ok>(`/api/vessels/${id}/status`, { status }),

  /** 기상 상태(맑음/흐림…) 변경 */
  setWeather: (region: string, condition: string, extras?: WeatherPatch) =>
    post<Ok>(`/api/weather/${encodeURIComponent(region)}`, { condition, ...extras }),

  /** 풍향·풍속·해류 등 수치만 변경 (기상 상태는 유지) */
  patchWeather: (region: string, patch: WeatherPatch) =>
    post<Ok>(`/api/weather/${encodeURIComponent(region)}`, patch),

  /** 해양 벡터 필드 — 해류/바람 흐름 시각화용 격자.
   *  region 을 주면 그 관할 기상으로 계산한다(표류 예측과 같은 관할을 쓰기 위함). */
  oceanField: (
    layer: "current" | "wind",
    bbox: OceanBBox,
    cols = 26,
    rows = 18,
    region?: string,
  ) => {
    const q = new URLSearchParams({
      layer,
      min_lat: String(bbox.min_lat),
      max_lat: String(bbox.max_lat),
      min_lon: String(bbox.min_lon),
      max_lon: String(bbox.max_lon),
      cols: String(cols),
      rows: String(rows),
    });
    if (region) q.set("region", region);
    return request<OceanFieldData>(`/api/ocean/field?${q}`);
  },

  /** 요구조자 예상 위치 바운더리 (minutes 생략 시 실제 경과 시간) */
  boundary: (reportId: string, minutes?: number) =>
    request<Boundary>(
      `/api/reports/${reportId}/boundary${minutes === undefined ? "" : `?minutes=${minutes}`}`,
    ),

  simReleaseSos: () => post<Ok>("/api/sim/sos/release"),

  // 운항 시뮬레이터
  simState: () => request<SimState>("/api/sim/state"),
  simPosition: (lat: number, lon: number) => post<Ok>("/api/sim/position", { lat, lon }),
  simRoute: (points: number[][]) => post<Ok>("/api/sim/route", { points }),
  simFence: (points: number[][]) => post<Ok>("/api/sim/fence", { points }),
  simFlipFence: () => post<Ok>("/api/sim/fence/flip"),
  simSpeed: (body: { speed_kn?: number; time_scale?: number }) =>
    post<Ok>("/api/sim/speed", body),
  simRun: (action: "start" | "pause" | "stop") => post<Ok>("/api/sim/run", { action }),
  simReset: () => post<Ok>("/api/sim/reset"),

  // 킬 스위치 원격 제어 (관제 → V-PASS 단말 → BLE 릴레이)
  killswitch: (action: "kill" | "restore") => post<Ok>("/api/killswitch", { action }),

  reportSeen: (id: string) => post<Ok>(`/api/reports/${id}/seen`),
  reportDispatch: (id: string) => post<Ok>(`/api/reports/${id}/dispatch`),
  reportClose: (id: string) => post<Ok>(`/api/reports/${id}/close`),
};
