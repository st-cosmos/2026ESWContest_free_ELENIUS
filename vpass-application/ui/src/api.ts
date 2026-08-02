// 백엔드 API 호출 헬퍼

import type {
  AppState,
  BoardingSummary,
  User,
  Vessel,
  VoyageDetail,
  VoyageSummary,
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

export const api = {
  state: () => request<AppState>("/api/state"),

  setCameraMode: (mode: "idle" | "scan" | "register") =>
    post("/api/camera/mode", { mode }),

  users: () => request<User[]>("/api/users"),
  registerUser: (name: string, phone: string, device_id: string | null) =>
    post<{ success: boolean; message: string }>("/api/users", { name, phone, device_id }),
  deleteUser: (id: string) =>
    request<{ success: boolean; message: string }>(`/api/users/${id}`, { method: "DELETE" }),

  boardingSession: () => request<BoardingSummary>("/api/boarding/session"),
  resetBoarding: () => post("/api/boarding/reset"),

  // 승선 확인 → 시동 허용 (출항 신고는 지오펜스 판정으로 자동 등록)
  allowEngineStart: () =>
    post<{ success: boolean; crew: number; message: string }>("/api/engine/allow"),
  confirmDeparture: () =>
    post<{ success: boolean; voyage_id: string; message: string }>("/api/departure/confirm"),
  confirmArrival: () =>
    post<{ success: boolean; voyage_id: string; message: string }>("/api/arrival/confirm"),

  vessel: () => request<Vessel | null>("/api/vessel"),
  saveVessel: (v: { region: string; vessel_id: string; name: string; home_port: string }) =>
    put<{ success: boolean; message: string }>("/api/vessel", v),

  voyages: () => request<VoyageSummary[]>("/api/voyages"),
  voyage: (id: string) => request<VoyageDetail>(`/api/voyages/${id}`),

  triggerSos: () => post<{ success: boolean }>("/api/sos"),
  ackSos: () => post<{ success: boolean }>("/api/sos/ack"),

  // 운항 중 구명조끼 해제 경고 모달 확인(닫기)
  ackJacketAlert: () => post<{ success: boolean }>("/api/jacket-alert/ack"),

  // 하드웨어 없이 익수 시나리오를 시연하기 위한 구명조끼 장치 시뮬레이터
  devJacket: (device: string, action: string) =>
    post<{ success: boolean }>("/api/dev/jacket", { device, action }),
};
