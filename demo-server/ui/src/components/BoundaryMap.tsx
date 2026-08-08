// 요구조자 예상 위치 지도 — 해류·바람 벡터 필드 위에 표류 예측 바운더리를 겹친다.
//
// 지도는 미터 기준으로 투영한다(가로/세로 축척 동일). 그래서 확률 반경이 화면에서도
// 찌그러지지 않는 정확한 원으로 보이고, 축척 바의 길이도 실제 거리와 일치한다.

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Crosshair,
  Navigation,
  PersonStanding,
  Search,
  Ship,
  Waves,
  Wind,
} from "lucide-react";
import { OceanField, rampSteps } from "./OceanField";
import type { Boundary, OceanBBox, OceanFieldData } from "../types";

const M_PER_DEG_LAT = 111_320;

export interface Layers {
  current: boolean;
  wind: boolean;
}

interface Props {
  boundary: Boundary;
  currentField: OceanFieldData | null;
  windField: OceanFieldData | null;
  layers: Layers;
  onBBoxChange: (bbox: OceanBBox) => void;
}

interface Size {
  width: number;
  height: number;
}

/** 화면에 보기 좋은 축척 눈금 (1-2-5 계열) */
function niceDistance(meters: number): number {
  const pow = Math.pow(10, Math.floor(Math.log10(meters)));
  const base = meters / pow;
  const step = base >= 5 ? 5 : base >= 2 ? 2 : 1;
  return step * pow;
}

const fmtDistance = (m: number) =>
  m >= 1000 ? `${(m / 1000).toFixed(m >= 10000 ? 0 : 1)} km` : `${Math.round(m)} m`;

export function BoundaryMap({
  boundary,
  currentField,
  windField,
  layers,
  onBBoxChange,
}: Props) {
  const areaRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size>({ width: 0, height: 0 });
  const [cursor, setCursor] = useState<{ lat: number; lon: number } | null>(null);

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      const rect = el.getBoundingClientRect();
      setSize({ width: rect.width, height: rect.height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 가장 큰 링(+120분 95%)이 화면에 여유롭게 들어오도록 축척을 잡는다
  const spanM = useMemo(() => {
    const rings = boundary.timeline.flatMap((row) => row.radius_m);
    const drift = boundary.timeline.map((row) => row.distance_m);
    const reach = Math.max(...rings, ...drift, 400);
    return reach * 2.6;
  }, [boundary.timeline]);

  const center = boundary.center;
  // 세로가 0 인 순간(첫 렌더)에 축척이 무한대가 되지 않도록 하한을 둔다
  const metersPerPx = spanM / Math.max(1, Math.min(size.width, size.height));
  const mPerDegLon = M_PER_DEG_LAT * Math.cos((center.lat * Math.PI) / 180);

  const project = (lat: number, lon: number) => ({
    x: size.width / 2 + ((lon - center.lon) * mPerDegLon) / metersPerPx,
    y: size.height / 2 - ((lat - center.lat) * M_PER_DEG_LAT) / metersPerPx,
  });
  const unproject = (x: number, y: number) => ({
    lat: center.lat + ((size.height / 2 - y) * metersPerPx) / M_PER_DEG_LAT,
    lon: center.lon + ((x - size.width / 2) * metersPerPx) / mPerDegLon,
  });
  const toPx = (meters: number) => meters / metersPerPx;

  // 벡터 필드는 지도 영역과 같은 범위로 요청한다
  useEffect(() => {
    if (size.width < 10 || size.height < 10) return;
    const halfLat = ((size.height / 2) * metersPerPx) / M_PER_DEG_LAT;
    const halfLon = ((size.width / 2) * metersPerPx) / mPerDegLon;
    onBBoxChange({
      min_lat: +(center.lat - halfLat).toFixed(5),
      max_lat: +(center.lat + halfLat).toFixed(5),
      min_lon: +(center.lon - halfLon).toFixed(5),
      max_lon: +(center.lon + halfLon).toFixed(5),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.width, size.height, center.lat, center.lon, metersPerPx]);

  const incidentPt = project(boundary.incident.lat, boundary.incident.lon);
  const centerPt = project(center.lat, center.lon);
  const vesselPt = project(boundary.vessel.lat, boundary.vessel.lon);

  // 탐색 우선 부채꼴 (표류 방위 ± 반각)
  const sectorPath = useMemo(() => {
    const { bearing, half_angle, radius_m } = boundary.sector;
    const r = toPx(radius_m);
    if (!isFinite(r) || r <= 0) return "";
    const at = (deg: number) => {
      const rad = (deg * Math.PI) / 180;
      return `${incidentPt.x + r * Math.sin(rad)},${incidentPt.y - r * Math.cos(rad)}`;
    };
    const [a, b] = [bearing - half_angle, bearing + half_angle];
    return `M ${incidentPt.x},${incidentPt.y} L ${at(a)} A ${r} ${r} 0 0 1 ${at(b)} Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundary.sector, incidentPt.x, incidentPt.y, metersPerPx]);

  const scaleTarget = niceDistance(metersPerPx * 120);
  const ringTone = ["r50", "r75", "r95"];
  const stepTones = ["s30", "s60", "s120"];

  return (
    <div
      className="bd-map"
      ref={areaRef}
      onPointerMove={(e) => {
        const rect = areaRef.current?.getBoundingClientRect();
        if (!rect) return;
        setCursor(unproject(e.clientX - rect.left, e.clientY - rect.top));
      }}
      onPointerLeave={() => setCursor(null)}
    >
      {layers.current && <OceanField field={currentField} className="ocean-canvas" />}
      {layers.wind && (
        <OceanField field={windField} density={0.7} fade={0.2} className="ocean-canvas wind" />
      )}

      {size.width > 0 && (
        <>
          {/* 미래 시간대 95% 경계 — 표류 방향으로 밀려가며 커진다 */}
          {boundary.timeline
            .filter((row) => !row.current)
            .slice(0, 3)
            .map((row, i) => {
              const c = project(row.center.lat, row.center.lon);
              const r = toPx(row.radius_m);
              return (
                <div
                  key={`step-${row.elapsed_min}`}
                  className={`bd-ring step ${stepTones[i] ?? "s120"}`}
                  style={{
                    left: c.x - r,
                    top: c.y - r,
                    width: r * 2,
                    height: r * 2,
                  }}
                >
                  <span className="bd-ring-tag">
                    +{Math.round(row.elapsed_min)}분 · {fmtDistance(row.radius_m)}
                  </span>
                </div>
              );
            })}

          {/* 현재 경과 시간의 확률 경계 (50 / 75 / 95%) */}
          {[...boundary.rings].reverse().map((ring) => {
            const r = toPx(ring.radius_m);
            const tone = ringTone[boundary.rings.findIndex((x) => x === ring)] ?? "r95";
            return (
              <div
                key={ring.probability}
                className={`bd-ring live ${tone}`}
                style={{
                  left: centerPt.x - r,
                  top: centerPt.y - r,
                  width: r * 2,
                  height: r * 2,
                }}
              />
            );
          })}

          <svg className="bd-svg" viewBox={`0 0 ${size.width} ${size.height}`}>
            {sectorPath && <path className="bd-sector" d={sectorPath} />}
            <line
              className="bd-drift"
              x1={incidentPt.x}
              y1={incidentPt.y}
              x2={centerPt.x}
              y2={centerPt.y}
            />
          </svg>

          {/* 익수 지점 */}
          <div className="bd-incident" style={{ left: incidentPt.x, top: incidentPt.y }}>
            <Crosshair size={16} />
          </div>
          <div className="bd-tag incident" style={{ left: incidentPt.x, top: incidentPt.y }}>
            익수 지점 {boundary.report.time.slice(-8)}
          </div>

          {/* 정지·표류 중인 선박 */}
          <div className="bd-vessel" style={{ left: vesselPt.x, top: vesselPt.y }}>
            <Ship size={16} />
          </div>
          <div className="bd-tag vessel" style={{ left: vesselPt.x, top: vesselPt.y }}>
            {boundary.report.vessel_name} ·{" "}
            {boundary.vessel.locked ? "엔진 정지 · 표류중" : "운항중"}
          </div>

          {/* 요구조자 예상 위치 */}
          <div className="bd-survivor" style={{ left: centerPt.x, top: centerPt.y }}>
            <span className="halo" />
            <PersonStanding size={20} />
          </div>

          <div
            className="bd-tag sector"
            style={{
              left: incidentPt.x + toPx(boundary.sector.radius_m * 0.55) * Math.sin((boundary.sector.bearing * Math.PI) / 180),
              top: incidentPt.y - toPx(boundary.sector.radius_m * 0.55) * Math.cos((boundary.sector.bearing * Math.PI) / 180),
            }}
          >
            <Search size={12} />
            탐색 우선 {boundary.sector.bearing}° ±{boundary.sector.half_angle}°
          </div>
        </>
      )}

      {/* 지도 부가 정보 */}
      <div className="bd-compass">
        <Navigation size={14} />
        <span>N</span>
      </div>

      <div className="bd-legend">
        <div className="bd-legend-head">범례</div>
        <div className="bd-l"><i className="sw ring r50" />50% 구역</div>
        <div className="bd-l"><i className="sw ring r75" />75% 구역</div>
        <div className="bd-l"><i className="sw ring r95" />95% 구역</div>
        <div className="bd-l"><i className="sw line" />합성 표류 벡터</div>
        {layers.current && (
          <div className="bd-l">
            <i className="sw ramp" style={{ background: `linear-gradient(90deg, ${rampSteps("current").join(",")})` }} />
            해류 {boundary.weather.current_kn.toFixed(2)} kn
          </div>
        )}
        {layers.wind && (
          <div className="bd-l">
            <i className="sw ramp" style={{ background: `linear-gradient(90deg, ${rampSteps("wind").join(",")})` }} />
            바람 {boundary.weather.wind_speed_ms.toFixed(1)} m/s
          </div>
        )}
      </div>

      <div className="bd-flowchips">
        {layers.current && (
          <span className="bd-flowchip cyan">
            <Waves size={13} />
            해류 {boundary.weather.current_dir}° · {boundary.weather.current_kn.toFixed(2)} kn
          </span>
        )}
        {layers.wind && (
          <span className="bd-flowchip orange">
            <Wind size={13} />
            {boundary.weather.wind_dir} 풍 {boundary.weather.wind_speed_ms.toFixed(1)} m/s → 압류{" "}
            {boundary.drift.leeway_kn.toFixed(2)} kn
          </span>
        )}
      </div>

      <div className="bd-cursor">
        <Crosshair size={13} />
        {cursor
          ? `${cursor.lat.toFixed(5)}, ${cursor.lon.toFixed(5)}`
          : boundary.center.position}
      </div>

      <div className="bd-scale">
        <i style={{ width: toPx(scaleTarget) }} />
        <span>{fmtDistance(scaleTarget)}</span>
      </div>
    </div>
  );
}
