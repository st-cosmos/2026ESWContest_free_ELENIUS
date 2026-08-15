// 백엔드 /api/state 및 각 API 응답 타입

export interface Telemetry {
  // demo_sim = 실측 GPS 미수신 → 데모 관제 서버 운항 시뮬레이터 좌표 사용
  source: "sim" | "hardware" | "demo_sim";
  lat: number | null;
  lon: number | null;
  position: string;
  position_compact: string;
  course: number | null;
  speed_kn: number;
  altitude_m: number | null;
  satellites: number | null;
  gps_updated_at: string | null;
  gps_ok: boolean;
  comm_ok: boolean;
  gps_error?: string | null;
  compass_error?: string | null;
  // 시뮬레이터 좌표를 쓰는 동안의 배속 (운항 기록 간격 보정에 사용)
  time_scale?: number;
}

export interface Vessel {
  region: string;
  vessel_id: string;
  name: string;
  home_port: string;
  registered_at: string;
  updated_at: string;
  reported_at: string;
}

export interface EngineState {
  locked: boolean;
  killed: boolean;
  kill_reason: string | null;
  engaged: boolean;
  gpio: boolean;
  ble?: boolean;
  ble_last_command?: string | null;
  ble_error?: string | null;
}

export interface CrewEntry {
  user_id: string;
  name: string;
  phone: string;
  time: string;
  device_id?: string | null; // 승선 스캔 시 동적 매칭된 구명조끼 장치 (구 기록에는 없음)
  lifejacket: boolean | null; // 모듈(홀센서) 확인 · null = 구버전 기록(장치 미배정)
  jacket_visual?: boolean | null; // 카메라 시각 확인 · null = 시각 확인 꺼짐 (구 기록에는 없음)
}

export interface BoardingSummary {
  total: number;
  lifejacket_confirmed: number;
  crew: CrewEntry[];
}

export interface DeviceState {
  device: string;
  user_name: string | null;
  worn: boolean;
  last_ping: string;
  seconds_since_ping: number | null;
  signal_ok: boolean;
  last_fall: string;
  fall_magnitude: number | null;
  fall_pending: boolean;
  mob: boolean;
  mob_cause: "fall" | "signal_loss" | null;
  mob_at: string | null;
}

// 운항 중 구명조끼 해제(버클 풀림) 경고 — 재착용 또는 확인 시 사라짐
export interface JacketDoffAlert {
  device: string;
  who: string;
  time: string;
}

export interface SosReport {
  cause: "manual" | "mob";
  detail: string | null;
  time: string;
  position: string;
  vessel_name: string;
  vessel_id: string;
}

export interface Weather {
  temp_c: number;
  condition: string;
  feels_like_c: number;
  precip_prob: number;
  wind: string;
  wave_height_m: number;
  water_temp_c: number;
  humidity: number;
  visibility_km: number;
  pressure_hpa: number;
  advisory: string | null;
  sunrise: string;
  sunset: string;
  high_tide: string;
  low_tide: string;
  updated_at: string;
  source: string;
}

export interface VoyageSummary {
  id: string;
  date: string;
  departed_at: string;
  arrived_at: string | null;
  status: "active" | "done";
  crew_count: number;
  point_count: number;
}

export interface VoyageDetail {
  id: string;
  date: string;
  departed_at: string;
  arrived_at: string | null;
  status: "active" | "done";
  departure_reported: boolean;
  arrival_reported: boolean;
  crew: CrewEntry[];
  points: { ts: string; coord: string }[];
}

export interface AppState {
  time: string;
  telemetry: Telemetry;
  vessel: Vessel | null;
  engine: EngineState;
  camera_ok: boolean;
  camera_mode: string;
  overlay: { text: string; color: string };
  boarding: { count: number; session: CrewEntry[] };
  lifejacket: {
    devices: DeviceState[];
    worn_count: number;
    mob_alarm: boolean;
    doff_alert: JacketDoffAlert | null;
  };
  voyage: {
    active: boolean;
    current_id: string | null;
    departed_at: string | null;
    latest: { id: string; date: string; departed_at: string; arrived_at: string | null; status: string } | null;
    last_report: { type: string; time: string; message: string } | null;
  };
  sos: SosReport | null;
  weather: Weather;
  platform: { raspberry_pi: boolean };
}

export interface User {
  id: string;
  name: string;
  phone: string;
  device_id: string | null;
  photo: string | null;
  registered_at: string;
}
