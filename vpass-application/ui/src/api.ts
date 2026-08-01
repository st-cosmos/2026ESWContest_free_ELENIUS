// 백엔드 API 호출 헬퍼

import type { AppState, BoardingLogsResponse, User, VoyageDetail, VoyageSummary } from "./types";

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

export const api = {
  state: () => request<AppState>("/api/state"),

  setCameraMode: (mode: "idle" | "scan" | "register") =>
    post("/api/camera/mode", { mode }),

  users: () => request<User[]>("/api/users"),
  registerUser: (name: string, phone: string, device_id: string | null) =>
    post<{ success: boolean; message: string }>("/api/users", { name, phone, device_id }),
  deleteUser: (id: string) =>
    request<{ success: boolean; message: string }>(`/api/users/${id}`, { method: "DELETE" }),

  boardingLogs: () => request<BoardingLogsResponse>("/api/boarding/logs"),
  resetBoarding: () => post("/api/boarding/reset"),

  vessel: () => request<import("./types").Vessel | null>("/api/vessel"),
  saveVessel: (v: { region: string; vessel_id: string; name: string; home_port: string }) =>
    put<{ success: boolean; message: string }>("/api/vessel", v),

  voyages: () => request<VoyageSummary[]>("/api/voyages"),
  voyage: (id: string) => request<VoyageDetail>(`/api/voyages/${id}`),
  addManualPoint: (timestamp: string, coord: string) =>
    post<{ success: boolean }>("/api/voyages/manual_point", { timestamp, coord }),

  triggerSos: () => post<{ success: boolean }>("/api/sos"),
  ackSos: () => post<{ success: boolean }>("/api/sos/ack"),

  // 개발/시연용 시뮬레이션
  devSail: (cruising: boolean) => post<{ success: boolean }>("/api/dev/sail", { cruising }),
  devJacket: (device: string, action: string) =>
    post<{ success: boolean }>("/api/dev/jacket", { device, action }),
};
