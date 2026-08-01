// 한반도(남한) 스타일 지도 + 5개 해양경찰청 관할 기상 마커
// viewBox 좌표를 %로 환산해 마커를 배치하므로 컨테이너 크기와 무관하게 정렬된다.

import type { RegionWeather } from "../types";
import { weatherColor, weatherIcon } from "../weatherMeta";

// 남한 육지 실루엣 (viewBox 300 x 400)
const LAND_PATH =
  "M120,40 L150,32 L170,55 L185,95 L200,140 L212,185 L220,230 L214,265 " +
  "L225,290 L205,300 L190,292 L178,308 L160,298 L150,315 L132,305 L120,320 " +
  "L105,308 L95,322 L82,300 L92,278 L72,258 L88,238 L70,205 L85,175 " +
  "L62,158 L78,135 L58,110 L80,92 L70,70 L95,58 Z";

const VB_W = 300;
const VB_H = 400;

// 관할별 마커 위치 (viewBox 좌표)
const MARKER_POS: Record<string, [number, number]> = {
  동해: [248, 120],
  중부: [55, 118],
  서해: [48, 250],
  남해: [165, 352],
  제주: [85, 372],
};

interface Props {
  regions: string[];
  weather: Record<string, RegionWeather>;
  selected: string;
  onSelect: (region: string) => void;
}

export function KoreaMap({ regions, weather, selected, onSelect }: Props) {
  return (
    <div className="map-area">
      <svg
        className="map-svg"
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        preserveAspectRatio="none"
      >
        {/* 경위도 격자 */}
        {[75, 150, 225].map((x) => (
          <line key={`v${x}`} className="map-grid" x1={x} y1={0} x2={x} y2={VB_H} />
        ))}
        {[100, 200, 300].map((y) => (
          <line key={`h${y}`} className="map-grid" x1={0} y1={y} x2={VB_W} y2={y} />
        ))}
        {/* 육지 */}
        <path className="map-land" d={LAND_PATH} />
        <ellipse className="map-land" cx={85} cy={372} rx={34} ry={17} />
      </svg>

      {regions.map((region) => {
        const w = weather[region];
        if (!w) return null;
        const [vx, vy] = MARKER_POS[region] ?? [150, 200];
        const Icon = weatherIcon(w.condition);
        const color = weatherColor(w.condition);
        return (
          <button
            key={region}
            className={`region-marker${selected === region ? " selected" : ""}`}
            style={{ left: `${(vx / VB_W) * 100}%`, top: `${(vy / VB_H) * 100}%` }}
            onClick={() => onSelect(region)}
          >
            <div className="rm-top">
              <span className="rm-region">{region}</span>
              <Icon size={18} style={{ color }} />
            </div>
            <div className="rm-mid">
              <span className="rm-temp">{Math.round(w.temp_c)}°</span>
              <span className="rm-cond" style={{ color }}>
                {w.condition}
              </span>
            </div>
            <span className="rm-wave">파고 {w.wave_height_m}m</span>
          </button>
        );
      })}
    </div>
  );
}
