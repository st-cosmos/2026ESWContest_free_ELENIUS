// 우측 1/3: 해양 기상 관제 (한반도 지도 + 관할별 기상 설정 → V-PASS 반영)

import { useState } from "react";
import { CloudSun, RefreshCw } from "lucide-react";
import { api } from "../api";
import type { AppState } from "../types";
import { KoreaMap } from "./KoreaMap";
import { weatherColor, weatherIcon } from "../weatherMeta";

export function WeatherPanel({ state, onChange }: { state: AppState; onChange: () => void }) {
  const [selected, setSelected] = useState<string>(state.regions[0] ?? "동해");
  const [busy, setBusy] = useState(false);

  const w = state.weather[selected];

  const setCondition = async (condition: string) => {
    if (busy || !w || condition === w.condition) return;
    setBusy(true);
    try {
      await api.setWeather(selected, condition);
      onChange();
    } catch {
      /* 무시 */
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="weather-head">
        <CloudSun size={20} style={{ color: "var(--cyan)" }} />
        <div className="spacer" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <span className="panel-title">해양 기상 관제</span>
          <span className="sh-desc">5개 지방해양경찰청 관할 · 실시간</span>
        </div>
        <div className="clock">
          <span className="clock-label">갱신</span>
          <span className="clock-value">{w?.updated_at ?? "--:--"}</span>
        </div>
      </div>

      <div className="panel map-panel">
        <KoreaMap
          regions={state.regions}
          weather={state.weather}
          selected={selected}
          onSelect={setSelected}
        />

        <div className="weather-control">
          <div className="wc-head">
            <span className="wc-title">{selected} 관할 · 기상 설정</span>
            <span className="sync-chip">
              <RefreshCw size={12} />
              V-PASS 자동 반영
            </span>
          </div>

          <div className="cond-grid">
            {state.conditions.map((cond) => {
              const Icon = weatherIcon(cond);
              const on = w?.condition === cond;
              return (
                <button
                  key={cond}
                  className={`cond-chip${on ? " on" : ""}`}
                  onClick={() => setCondition(cond)}
                  disabled={busy}
                >
                  <Icon size={15} style={{ color: on ? "var(--accent)" : weatherColor(cond) }} />
                  {cond}
                </button>
              );
            })}
          </div>

          {w && (
            <div className="wc-detail">
              <Metric l="기온" v={`${Math.round(w.temp_c)}°C`} />
              <Metric l="풍향/풍속" v={w.wind} />
              <Metric l="파고" v={`${w.wave_height_m}m`} />
              <Metric l="수온" v={`${w.water_temp_c}°C`} />
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function Metric({ l, v }: { l: string; v: string }) {
  return (
    <div className="wc-metric">
      <span className="l">{l}</span>
      <span className="v">{v}</span>
    </div>
  );
}
