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
  // V-PASS 단말의 좌표 출처 (hardware = 실측 GPS → 시뮬레이터 좌표를 무시한다)
  gps_source: "hardware" | "sim" | "demo_sim" | null;
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

export type WindDir = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

export interface RegionWeather {
  condition: string;
  temp_c: number;
  /** 파생 표기("SW 4.2 m/s") — 서버가 만들며 직접 수정하지 않는다 */
  wind: string;
  /** 바람이 불어오는 방향 (기상 표준) */
  wind_dir: WindDir;
  wind_speed_ms: number;
  gust_ms: number;
  /** 해류가 흘러가는 방위 (0~359°) */
  current_dir: number;
  current_kn: number;
  wave_height_m: number;
  water_temp_c: number;
  precip_prob: number;
  advisory: string | null;
  updated_at: string;
  source?: string;
}

/** 관제사가 수정할 수 있는 기상 항목 */
export type WeatherPatch = Partial<
  Pick<
    RegionWeather,
    | "temp_c"
    | "wind_dir"
    | "wind_speed_ms"
    | "gust_ms"
    | "current_dir"
    | "current_kn"
    | "wave_height_m"
    | "water_temp_c"
  >
>;

export interface SosSummary {
  locked: boolean;
  info: {
    report_id: string;
    cause: "manual" | "mob";
    detail: string | null;
    time: string;
    vessel_name: string | null;
    vessel_id: string | null;
  } | null;
  drift_kn: number;
  active_reports: number;
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
  wind_dirs: WindDir[];
  sos: SosSummary;
  ocean_source: string;
}

// ── 해양 벡터 필드 (해류 · 풍향/풍속) ──────────────────────────────────
export interface OceanBBox {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
}

export interface OceanVector {
  lat: number;
  lon: number;
  /** 흐르는 방위 (북=0, 시계방향) */
  dir: number;
  speed: number;
}

export interface OceanFieldData {
  layer: "current" | "wind";
  region: string;
  unit: string;
  bbox: OceanBBox;
  cols: number;
  rows: number;
  base: { bearing: number; speed: number; unit: string; from_dir?: string; gust?: number };
  range: { min: number; max: number };
  source: string;
  live: boolean;
  updated_at: string;
  points: OceanVector[];
}

// ── 요구조자 예상 위치 (표류 예측) ─────────────────────────────────────
export interface DriftVector {
  current_kn: number;
  current_dir: number;
  leeway_kn: number;
  leeway_dir: number;
  leeway_ratio: number;
  speed_kn: number;
  bearing: number;
}

export interface BoundaryRing {
  probability: number;
  radius_nm: number;
  radius_m: number;
  area_km2: number;
}

export interface GeoPoint {
  lat: number;
  lon: number;
  position: string;
}

export interface BoundaryTimelineRow {
  elapsed_min: number;
  current: boolean;
  center: GeoPoint;
  distance_m: number;
  rings: BoundaryRing[];
  radius_m: number;
  area_km2: number;
}

export interface Boundary {
  incident: GeoPoint;
  center: GeoPoint;
  elapsed_min: number;
  elapsed_actual_min: number;
  drift: DriftVector;
  distance_nm: number;
  distance_m: number;
  rings: BoundaryRing[];
  sector: { bearing: number; half_angle: number; radius_m: number };
  model: { leeway_ratio: number; spread_nm_per_hour: number; note: string };
  report: Report;
  region: string;
  weather: RegionWeather;
  timeline: BoundaryTimelineRow[];
  survival_hours: number | null;
  vessel: { lat: number; lon: number; locked: boolean; drift_kn: number; drift_m: number };
}

// ── 운항 시뮬레이터 ────────────────────────────────────────────────────
export interface SimPoint {
  lat: number;
  lon: number;
}

export interface SimVessel extends SimPoint {
  course: number;
  speed_kn: number;
  position: string;
  updated_at: string;
  running: boolean;
}

export interface SimProgress {
  index: number;
  total_nm: number;
  done_nm: number;
  percent: number;
  leg: number;
  legs: number;
  eta_min: number | null;
}

export interface SimEvent {
  id: string;
  kind: "departure" | "arrival";
  time: string;
  position: string;
}

export interface SimSos {
  locked: boolean;
  info: {
    report_id: string;
    cause: "manual" | "mob";
    detail: string | null;
    time: string;
    vessel_name: string | null;
    vessel_id: string | null;
  } | null;
  drift_kn: number;
  drift_bearing: number;
  drift_m: number;
}

export interface SimState {
  time: string;
  vessel: SimVessel;
  route: SimPoint[];
  fence: SimPoint[];
  sea_side: number;
  speed_kn: number;
  time_scale: number;
  time_scales: number[];
  running: boolean;
  finished: boolean;
  port_state: "docked" | "departed";
  progress: SimProgress;
  events: SimEvent[];
  command_seq: number;
  terminal: Vessel | null;
  sos: SimSos;
  engine_command: EngineCommand | null;
}

export interface EngineCommand {
  seq: number;
  action: "kill" | "restore";
  time: string;
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
