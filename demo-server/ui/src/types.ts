// 데모 관제 서버 /api/state 및 각 API 응답 타입

export type VesselStatus = "departed" | "docked";

export interface Vessel {
  id: string;
  vessel_id: string;
  name: string;
  region: string;
  lat: number;
  lon: number;
  position: string;
  course: number;
  speed_kn: number;
  crew: number;
  status: VesselStatus;
  source: "manual" | "vpass";
  live: boolean;
  updated_at: string;
}

export interface VesselStats {
  total: number;
  departed: number;
  docked: number;
}

export interface Report {
  id: string;
  cause: "manual" | "mob";
  detail: string | null;
  time: string;
  position: string;
  vessel_name: string;
  vessel_id: string;
  region: string | null;
  status: "new" | "dispatched" | "closed";
  alerted: boolean;
  created_at: string;
}

export interface PortLogEntry {
  id: string;
  kind: "departure" | "arrival";
  vessel_name: string;
  vessel_id: string;
  time: string;
}

export interface RegionWeather {
  condition: string;
  temp_c: number;
  wind: string;
  wave_height_m: number;
  water_temp_c: number;
  precip_prob: number;
  advisory: string | null;
  updated_at: string;
}

export interface AppState {
  time: string;
  vessels: Vessel[];
  stats: VesselStats;
  reports: Report[];
  report_alert: Report | null;
  unread_reports: number;
  port_log: PortLogEntry[];
  weather: Record<string, RegionWeather>;
  regions: string[];
  conditions: string[];
}

export interface VesselForm {
  name: string;
  vessel_id: string;
  region: string;
  lat: number;
  lon: number;
  course: number;
  speed_kn: number;
  crew: number;
  status: VesselStatus;
}
