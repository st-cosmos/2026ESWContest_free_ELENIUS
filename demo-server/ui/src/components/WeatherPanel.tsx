// 우측 1/3: 해양 기상 관제 (한반도 지도 + 관할별 기상 설정 → V-PASS 반영)
//
// 풍향·풍속·해류는 관제사가 직접 수정한다. 이 값은 V-PASS 단말 기상 표시와
// 요구조자 표류 예측(바운더리), 해양 벡터 필드가 함께 사용하므로 한 곳만 바꾸면
// 모든 화면이 같이 움직인다.

import { useEffect, useRef, useState } from "react";
import { CloudSun, Minus, Plus, RefreshCw, Waves, Wind } from "lucide-react";
import { api } from "../api";
import type { AppState, WeatherPatch, WindDir } from "../types";
import { KoreaMap } from "./KoreaMap";
import { weatherColor, weatherIcon } from "../weatherMeta";

type NumField = "wind_speed_ms" | "gust_ms" | "current_dir" | "current_kn";

interface StepSpec {
  field: NumField;
  label: string;
  step: number;
  digits: number;
  tone: "orange" | "cyan";
  min: number;
  max: number;
  wrap?: boolean;
}

const STEPPERS: StepSpec[] = [
  { field: "wind_speed_ms", label: "풍속 (m/s)", step: 0.1, digits: 1, tone: "orange", min: 0, max: 60 },
  { field: "gust_ms", label: "돌풍 (m/s)", step: 0.1, digits: 1, tone: "orange", min: 0, max: 80 },
  { field: "current_dir", label: "해류 방위 (°)", step: 5, digits: 0, tone: "cyan", min: 0, max: 359, wrap: true },
  { field: "current_kn", label: "유속 (kn)", step: 0.05, digits: 2, tone: "cyan", min: 0, max: 12 },
];

export function WeatherPanel({ state, onChange }: { state: AppState; onChange: () => void }) {
  const [selected, setSelected] = useState<string>(state.regions[0] ?? "동해");
  const [busy, setBusy] = useState(false);
  /** 서버 응답을 기다리는 동안 눌린 값을 즉시 보여주기 위한 임시값 */
  const [draft, setDraft] = useState<Partial<Record<NumField, number>>>({});
  const timer = useRef<number | null>(null);
  const pending = useRef<WeatherPatch>({});

  const w = state.weather[selected];

  // 관할을 바꾸면 임시값은 버린다
  useEffect(() => {
    setDraft({});
    pending.current = {};
  }, [selected]);

  // 서버 값이 임시값을 따라잡으면 임시값을 정리한다
  useEffect(() => {
    if (!w) return;
    setDraft((d) => {
      const next = { ...d };
      let changed = false;
      for (const key of Object.keys(next) as NumField[]) {
        if (Math.abs((w[key] as number) - (next[key] as number)) < 1e-6) {
          delete next[key];
          changed = true;
        }
      }
      return changed ? next : d;
    });
  }, [w]);

  const flush = () => {
    const patch = pending.current;
    pending.current = {};
    timer.current = null;
    if (Object.keys(patch).length === 0) return;
    api
      .patchWeather(selected, patch)
      .then(onChange)
      .catch(() => setDraft({}));
  };

  const queue = (patch: WeatherPatch) => {
    pending.current = { ...pending.current, ...patch };
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(flush, 250);
  };

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

  const setWindDir = (dir: WindDir) => {
    if (!w || w.wind_dir === dir) return;
    queue({ wind_dir: dir });
    onChange();
  };

  const value = (spec: StepSpec): number =>
    draft[spec.field] ?? (w ? (w[spec.field] as number) : 0);

  const bump = (spec: StepSpec, dir: 1 | -1) => {
    if (!w) return;
    const raw = value(spec) + spec.step * dir;
    const next = spec.wrap
      ? ((raw % 360) + 360) % 360
      : Math.max(spec.min, Math.min(spec.max, raw));
    const rounded = Number(next.toFixed(spec.digits));
    setDraft((d) => ({ ...d, [spec.field]: rounded }));
    queue({ [spec.field]: rounded } as WeatherPatch);
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
            <>
              <div className="wc-flowhead">
                <Wind size={13} style={{ color: "var(--orange)" }} />
                <span className="l">풍향 · 풍속 · 해류 (실시간 편집)</span>
                <div className="spacer" />
                <span className="hint">요구조자 예측에 즉시 반영</span>
              </div>

              <div className="wc-dirs">
                {(state.wind_dirs ?? []).map((dir) => (
                  <button
                    key={dir}
                    className={`wc-dir${w.wind_dir === dir ? " on" : ""}`}
                    onClick={() => setWindDir(dir)}
                    title={`${dir} 방향에서 불어옴`}
                  >
                    {dir}
                  </button>
                ))}
              </div>

              <div className="wc-steppers">
                {STEPPERS.map((spec) => (
                  <div className="wc-stepper" key={spec.field}>
                    <span className="l">{spec.label}</span>
                    <div className="ctl">
                      <button onClick={() => bump(spec, -1)} aria-label={`${spec.label} 감소`}>
                        <Minus size={12} />
                      </button>
                      <span className={`v ${spec.tone}`}>
                        {spec.field === "current_dir"
                          ? String(Math.round(value(spec))).padStart(3, "0")
                          : value(spec).toFixed(spec.digits)}
                      </span>
                      <button onClick={() => bump(spec, 1)} aria-label={`${spec.label} 증가`}>
                        <Plus size={12} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="wc-detail">
                <Metric l="기온" v={`${Math.round(w.temp_c)}°C`} />
                <Metric l="파고" v={`${w.wave_height_m}m`} />
                <Metric l="수온" v={`${w.water_temp_c}°C`} />
                <Metric
                  l="표류 기준"
                  v={`${w.wind_dir} ${w.wind_speed_ms.toFixed(1)} · ${Math.round(w.current_dir)}°`}
                />
              </div>

              <div className="wc-source">
                <Waves size={12} />
                해류·바람 출처: {w.source ?? "관제 설정"} · {state.ocean_source}
              </div>
            </>
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
