// 데모 관제 서버 API 호출 헬퍼

import type { AppState, RegionWeather, SimState, Vessel, VesselForm } from "./types";

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

  setWeather: (region: string, condition: string, extras?: Partial<RegionWeather>) =>
    post<Ok>(`/api/weather/${encodeURIComponent(region)}`, { condition, ...extras }),

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

  reportSeen: (id: string) => post<Ok>(`/api/reports/${id}/seen`),
  reportDispatch: (id: string) => post<Ok>(`/api/reports/${id}/dispatch`),
  reportClose: (id: string) => post<Ok>(`/api/reports/${id}/close`),
};
