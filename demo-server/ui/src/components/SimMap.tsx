// 시뮬레이터 지도 — 위경도 ↔ 화면 비율 변환 위에서 항로/지오펜스를 편집하고
// 선박을 드래그한다. 선(항로·펜스·해안선)은 SVG, 마커/카드는 HTML 로 그린다.
// (SVG 를 preserveAspectRatio="none" 로 늘려 쓰기 때문에 원형 마커는 HTML 이 안전하다)

import { useRef, useState } from "react";
import {
  Anchor,
  ArrowRight,
  Crosshair,
  GripHorizontal,
  Navigation,
  PersonStanding,
  Ship,
  Siren,
  Waves,
} from "lucide-react";
import type { SimPoint, SimProgress, SimSos, SimVessel } from "../types";

// 데모 해역: 통영 인근 (V-PASS 홈 좌표를 포함하는 범위)
export const BOUNDS = {
  latMin: 34.55,
  latMax: 35.05,
  lonMin: 128.05,
  lonMax: 128.95,
};

export type Tool = "move" | "route" | "fence" | "erase";

const LAT_SPAN = BOUNDS.latMax - BOUNDS.latMin;
const LON_SPAN = BOUNDS.lonMax - BOUNDS.lonMin;

// 스타일화한 해안선(좌하단 육지) — 지리적 정확도보다 시연 가독성 우선
const LAND_PATH =
  "M0,49 L13,45 L27,53 L40,49 L49,60 L60,67 L57,79 L67,85 L63,100 L0,100 Z";

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export const toPct = (p: SimPoint) => ({
  x: clamp(((p.lon - BOUNDS.lonMin) / LON_SPAN) * 100, -20, 120),
  y: clamp(((BOUNDS.latMax - p.lat) / LAT_SPAN) * 100, -20, 120),
});

/** 두 지점 사이 거리(해리) — 데모 해역 규모에서는 평면 근사로 충분하다. */
export function distanceNm(a: SimPoint, b: SimPoint): number {
  const lat0 = (((a.lat + b.lat) / 2) * Math.PI) / 180;
  return Math.hypot((b.lon - a.lon) * Math.cos(lat0) * 60, (b.lat - a.lat) * 60);
}

export function formatCoord(p: SimPoint): string {
  const fmt = (v: number, ns: string) =>
    `${ns}${Math.floor(Math.abs(v))}°${((Math.abs(v) % 1) * 60).toFixed(3).padStart(6, "0")}'`;
  return `${fmt(p.lat, "N")} ${fmt(p.lon, "E")}`;
}

interface Props {
  vessel: SimVessel;
  route: SimPoint[];
  fence: SimPoint[];
  progress: SimProgress;
  tool: Tool;
  terminal: { name: string; vessel_id: string; crew: number } | null;
  /** SOS 접수 상태 — 위치 고정 + 표류만 반영 중임을 지도에 표시한다 */
  sos?: SimSos | null;
  onOpenBoundary?: () => void;
  onVesselMove: (pt: SimPoint, done: boolean) => void;
  onRouteChange: (points: SimPoint[], done: boolean) => void;
  onFenceChange: (points: SimPoint[], done: boolean) => void;
}

export function SimMap({
  vessel,
  route,
  fence,
  progress,
  tool,
  terminal,
  sos,
  onOpenBoundary,
  onVesselMove,
  onRouteChange,
  onFenceChange,
}: Props) {
  const areaRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const [cursor, setCursor] = useState<SimPoint | null>(null);

  const fromClient = (clientX: number, clientY: number): SimPoint => {
    const rect = areaRef.current?.getBoundingClientRect();
    if (!rect) return { lat: vessel.lat, lon: vessel.lon };
    const fx = clamp((clientX - rect.left) / rect.width, 0, 1);
    const fy = clamp((clientY - rect.top) / rect.height, 0, 1);
    return {
      lat: BOUNDS.latMax - fy * LAT_SPAN,
      lon: BOUNDS.lonMin + fx * LON_SPAN,
    };
  };

  /** 마커 드래그: 잡은 지점과의 간격을 유지하고, 놓을 때만 서버로 보낸다. */
  const beginDrag = (
    e: React.PointerEvent,
    origin: SimPoint,
    apply: (pt: SimPoint, done: boolean) => void,
  ) => {
    e.stopPropagation();
    e.preventDefault();
    draggingRef.current = true;
    const start = fromClient(e.clientX, e.clientY);
    const shifted = (ev: PointerEvent): SimPoint => {
      const now = fromClient(ev.clientX, ev.clientY);
      return {
        lat: clamp(origin.lat + (now.lat - start.lat), BOUNDS.latMin, BOUNDS.latMax),
        lon: clamp(origin.lon + (now.lon - start.lon), BOUNDS.lonMin, BOUNDS.lonMax),
      };
    };
    const move = (ev: PointerEvent) => apply(shifted(ev), false);
    const up = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      apply(shifted(ev), true);
      // 클릭 핸들러가 뒤이어 점을 추가하지 않도록 한 틱 늦게 해제
      setTimeout(() => (draggingRef.current = false), 0);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const handleBackgroundClick = (e: React.MouseEvent) => {
    if (draggingRef.current) return;
    const pt = fromClient(e.clientX, e.clientY);
    if (tool === "route") onRouteChange([...route, pt], true);
    else if (tool === "fence") onFenceChange([...fence, pt], true);
  };

  const vesselPct = toPct(vessel);
  const traveled =
    progress.done_nm > 0 && route.length >= 2
      ? [...route.slice(0, Math.max(1, progress.index)), { lat: vessel.lat, lon: vessel.lon }]
      : [];

  const line = (pts: SimPoint[]) =>
    pts.map((p) => { const c = toPct(p); return `${c.x},${c.y}`; }).join(" ");

  // 정보 카드가 지도 밖으로 나가지 않도록 방향을 뒤집는다
  const cardRight = vesselPct.x > 62;
  const cardBottom = vesselPct.y > 62;

  return (
    <div
      className={`sim-map tool-${tool}`}
      ref={areaRef}
      onClick={handleBackgroundClick}
      onPointerMove={(e) => setCursor(fromClient(e.clientX, e.clientY))}
      onPointerLeave={() => setCursor(null)}
    >
      <svg className="sim-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
        {[20, 40, 60, 80].map((v) => (
          <line key={`v${v}`} className="sim-grid" x1={v} y1={0} x2={v} y2={100} />
        ))}
        {[20, 40, 60, 80].map((v) => (
          <line key={`h${v}`} className="sim-grid" x1={0} y1={v} x2={100} y2={v} />
        ))}
        <path className="sim-land" d={LAND_PATH} />
        <ellipse className="sim-land" cx={78} cy={22} rx={4} ry={3} />
        <ellipse className="sim-land" cx={86} cy={62} rx={3} ry={2.2} />

        {fence.length >= 2 && (
          <polyline className="sim-fence" points={line(fence)} fill="none" />
        )}
        {route.length >= 2 && (
          <polyline className="sim-route" points={line(route)} fill="none" />
        )}
        {traveled.length >= 2 && (
          <polyline className="sim-route done" points={line(traveled)} fill="none" />
        )}
      </svg>

      {/* 지오펜스 꼭짓점 */}
      {fence.map((p, i) => {
        const c = toPct(p);
        return (
          <button
            key={`f${i}`}
            className="sim-handle fence"
            style={{ left: `${c.x}%`, top: `${c.y}%` }}
            title={`지오펜스 ${i + 1} · ${formatCoord(p)}`}
            onClick={(e) => {
              e.stopPropagation();
              if (tool === "erase") onFenceChange(fence.filter((_, k) => k !== i), true);
            }}
            onPointerDown={(e) => {
              if (tool === "erase") return;
              beginDrag(e, p, (pt, done) =>
                onFenceChange(fence.map((q, k) => (k === i ? pt : q)), done),
              );
            }}
          />
        );
      })}

      {/* 항로 웨이포인트 */}
      {route.map((p, i) => {
        const c = toPct(p);
        return (
          <button
            key={`w${i}`}
            className={`sim-wp${i === 0 ? " start" : ""}${i < progress.index ? " passed" : ""}`}
            style={{ left: `${c.x}%`, top: `${c.y}%` }}
            title={`${i + 1}번 · ${formatCoord(p)}`}
            onClick={(e) => {
              e.stopPropagation();
              if (tool === "erase") onRouteChange(route.filter((_, k) => k !== i), true);
            }}
            onPointerDown={(e) => {
              if (tool === "erase") return;
              beginDrag(e, p, (pt, done) =>
                onRouteChange(route.map((q, k) => (k === i ? pt : q)), done),
              );
            }}
          >
            {i + 1}
          </button>
        );
      })}

      {/* SOS 접수 — 엔진 정지 + 위치 고정, 표류만 반영 */}
      {sos?.locked && (
        <>
          <div className="sim-sosbanner">
            <Siren size={16} />
            SOS 접수 · 킬 스위치 작동 · 선박 위치 고정 (표류만 반영)
          </div>
          <div
            className="sim-drifttag"
            style={{ left: `${vesselPct.x}%`, top: `${vesselPct.y}%` }}
          >
            <Waves size={13} />
            표류 {sos.drift_kn.toFixed(2)} kn · {sos.drift_bearing}° · 누적 {sos.drift_m} m
          </div>
          {/* 요구조자 예상 위치는 익수 신고 전용 (수동 SOS 는 요구조자가 없다) */}
          {sos.info?.cause === "mob" && onOpenBoundary && (
            <button className="sim-boundarylink" onClick={onOpenBoundary}>
              <PersonStanding size={15} />
              요구조자 예상 위치 바운더리 열기
              <ArrowRight size={14} />
            </button>
          )}
        </>
      )}

      {/* 선박 마커 + 정보 카드 (둘 다 드래그하면 좌표가 이동한다) */}
      <div
        className={`sim-vessel${sos?.locked ? " sos" : ""}`}
        style={{ left: `${vesselPct.x}%`, top: `${vesselPct.y}%` }}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => beginDrag(e, { lat: vessel.lat, lon: vessel.lon }, onVesselMove)}
        title="드래그하면 V-PASS 로 전송되는 좌표가 바뀝니다"
      >
        <Ship size={19} />
        <span
          className="sim-heading"
          style={{ transform: `rotate(${vessel.course}deg) translateY(-19px)` }}
        >
          <Navigation size={11} />
        </span>
      </div>

      <div
        className={`sim-callout${cardRight ? " to-left" : ""}${cardBottom ? " to-top" : ""}`}
        style={{ left: `${vesselPct.x}%`, top: `${vesselPct.y}%` }}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => beginDrag(e, { lat: vessel.lat, lon: vessel.lon }, onVesselMove)}
      >
        <div className="sc-head">
          <Ship size={15} />
          <span className="sc-name">{terminal?.name ?? "단말 연결 대기"}</span>
          <span className={`sc-live${terminal ? "" : " off"}`}>
            <span className="dot" />
            {terminal ? "LIVE" : "OFF"}
          </span>
        </div>
        <div className="sc-id">
          {terminal ? `${terminal.vessel_id} · V-PASS 단말` : "V-PASS 단말이 연결되면 표시됩니다"}
        </div>
        <div className="sc-cell">
          <span className="l">시뮬레이션 GPS 좌표</span>
          <span className="v">{vessel.position}</span>
        </div>
        <div className="sc-metrics">
          <div className="sc-m">
            <span className="l">침로</span>
            <span className="v">{vessel.course}°</span>
          </div>
          <div className="sc-m">
            <span className="l">속력</span>
            <span className="v">{vessel.speed_kn.toFixed(1)} kn</span>
          </div>
          <div className="sc-m">
            <span className="l">승선</span>
            <span className="v">{terminal ? `${terminal.crew}명` : "-"}</span>
          </div>
        </div>
        <div className="sc-hint">
          <GripHorizontal size={13} />
          카드·아이콘을 드래그하면 해당 좌표가 V-PASS 로 전송됩니다
        </div>
      </div>

      {/* 지도 부가 정보 */}
      <div className="sim-compass">
        <Navigation size={14} />
        <span>N</span>
      </div>
      <div className="sim-legend">
        <div><i className="sw accent" />운항 완료 구간</div>
        <div><i className="sw cyan" />예정 항로</div>
        <div><i className="sw orange" />지오펜스</div>
      </div>
      <div className="sim-hintchip">
        {tool === "route" && "지도를 클릭해 항로 점을 추가하세요"}
        {tool === "fence" && "지도를 클릭해 지오펜스 선을 그리세요"}
        {tool === "erase" && "점을 클릭하면 삭제됩니다"}
        {tool === "move" && "선박·정보 카드를 드래그해 위치를 옮기세요"}
      </div>
      <div className="sim-cursor">
        <Crosshair size={13} />
        {cursor ? formatCoord(cursor) : formatCoord(vessel)}
      </div>
      <div className="sim-scale">
        <i />
        <span>{((LON_SPAN * Math.cos((BOUNDS.latMin * Math.PI) / 180) * 60) / 5).toFixed(1)} 해리</span>
      </div>
      {route.length === 0 && (
        <div className="sim-empty">
          <Anchor size={18} />
          항로 펜으로 지도를 클릭해 항로를 그려 주세요
        </div>
      )}
    </div>
  );
}
