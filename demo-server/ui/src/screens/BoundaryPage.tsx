// 요구조자 예상 위치 바운더리 — 신고 1건의 표류 예측을 지도 + 근거 패널로 보여준다.
//
// 신고 접수 현황에서 선박을 누르면 /boundary/{reportId} 로 진입한다.
// 해류·풍향/풍속은 관제 대시보드의 기상 관제 설정(또는 국립해양조사원 실측)을
// 그대로 쓰므로, 값을 바꾸면 흐름과 바운더리가 함께 움직인다.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Calculator,
  ChevronLeft,
  Info,
  Radio,
  RefreshCw,
  Ship,
  Siren,
  Target,
  Timer,
  Waves,
  Wind,
} from "lucide-react";
import { api } from "../api";
import { useAppState } from "../state";
import { navigate } from "../route";
import { StatusBar } from "../components/StatusBar";
import { BoundaryMap, type Layers } from "../components/BoundaryMap";
import type { Boundary, OceanBBox, OceanFieldData } from "../types";

const fmtDistance = (m: number) =>
  m >= 1000 ? `${(m / 1000).toFixed(m >= 10000 ? 0 : 2)} km` : `${Math.round(m)} m`;

const fmtElapsed = (minutes: number) => {
  const total = Math.max(0, Math.round(minutes * 60));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
};

const STEP_MINUTES = [30, 60, 120];

export default function BoundaryPage({ reportId }: { reportId: string }) {
  const { state, refresh } = useAppState();
  const [boundary, setBoundary] = useState<Boundary | null>(null);
  const [error, setError] = useState<string | null>(null);
  /** null = 실시간 추적 (실제 경과 시간) */
  const [minutes, setMinutes] = useState<number | null>(null);
  const [layers, setLayers] = useState<Layers>({ current: true, wind: true });
  const [bbox, setBbox] = useState<OceanBBox | null>(null);
  const [currentField, setCurrentField] = useState<OceanFieldData | null>(null);
  const [windField, setWindField] = useState<OceanFieldData | null>(null);
  const busy = useRef(false);

  // ── 바운더리 폴링 ─────────────────────────────────────────────────────
  const load = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const data = await api.boundary(reportId, minutes ?? undefined);
      setBoundary(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "예측을 불러오지 못했습니다.");
    } finally {
      busy.current = false;
    }
  }, [reportId, minutes]);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  // ── 해양 벡터 필드 (지도 범위·기상 변경 시 재요청) ────────────────────
  const weatherStamp = boundary
    ? `${boundary.weather.updated_at}|${boundary.weather.current_dir}|${boundary.weather.current_kn}|${boundary.weather.wind_dir}|${boundary.weather.wind_speed_ms}`
    : "";

  // 흐름 격자는 표류 예측과 **같은 관할**로 요청한다. 좌표 기준으로 관할을 따로
  // 고르면 화면의 해류 방향과 표류 벡터가 서로 다른 방향을 가리키게 된다.
  const region = boundary?.region;

  useEffect(() => {
    if (!bbox || !region) return;
    let alive = true;
    const fetchLayer = async (layer: "current" | "wind") => {
      try {
        const data = await api.oceanField(layer, bbox, 26, 18, region);
        if (!alive) return;
        if (layer === "current") setCurrentField(data);
        else setWindField(data);
      } catch {
        /* 필드는 없어도 지도는 그린다 */
      }
    };
    if (layers.current) fetchLayer("current");
    if (layers.wind) fetchLayer("wind");
    return () => {
      alive = false;
    };
  }, [bbox, region, weatherStamp, layers.current, layers.wind]);

  const timeline = boundary?.timeline ?? [];
  const survival = useMemo(() => {
    if (!boundary?.survival_hours) return null;
    const h = Math.floor(boundary.survival_hours);
    const m = Math.round((boundary.survival_hours - h) * 60);
    return `${h}h ${String(m).padStart(2, "0")}m`;
  }, [boundary?.survival_hours]);

  if (error && !boundary) {
    return (
      <div className="app">
        <StatusBar time={state?.time ?? ""} />
        <div className="empty" style={{ margin: "auto" }}>
          <AlertTriangle size={22} style={{ marginBottom: 8 }} />
          <div>{error}</div>
          <button className="btn" style={{ marginTop: 12 }} onClick={() => navigate("/")}>
            관제 대시보드로 돌아가기
          </button>
        </div>
      </div>
    );
  }

  if (!boundary) {
    return (
      <div className="app">
        <StatusBar time={state?.time ?? ""} />
        <div className="empty" style={{ margin: "auto" }}>표류 예측을 계산 중…</div>
      </div>
    );
  }

  const { report, weather, drift } = boundary;
  const auto = minutes === null;

  const dispatch = async () => {
    await api.reportDispatch(report.id).catch(() => {});
    refresh();
    load();
  };
  const close = async () => {
    if (!window.confirm("상황을 종료하시겠습니까? 시뮬레이터 위치 고정도 해제됩니다.")) return;
    await api.reportClose(report.id).catch(() => {});
    refresh();
    navigate("/");
  };

  return (
    <div className="app">
      <StatusBar time={state?.time ?? ""} />

      <div className="body">
        <div className="bd-panel">
          <div className="bd-head">
            <button className="btn btn-ghost" onClick={() => navigate("/")}>
              <ChevronLeft size={15} />
              신고 접수 현황
            </button>
            <div className="bd-titlecol">
              <div className="bd-title">요구조자 예상 위치 · {report.vessel_name}</div>
              <div className="bd-desc">
                {report.cause === "mob" ? "자동 익수 신고" : "수동 SOS 신고"} {report.time} 접수 ·
                경과 {fmtElapsed(boundary.elapsed_actual_min)} · 축척 자동
              </div>
            </div>
            <div className="spacer" />
            <div className="bd-layers">
              <button
                className={`bd-layer${layers.current ? " on cyan" : ""}`}
                onClick={() => setLayers((l) => ({ ...l, current: !l.current }))}
              >
                <Waves size={15} />
                해류
              </button>
              <button
                className={`bd-layer${layers.wind ? " on orange" : ""}`}
                onClick={() => setLayers((l) => ({ ...l, wind: !l.wind }))}
              >
                <Wind size={15} />
                풍속·풍향
              </button>
            </div>
            <span className={`bd-source${currentField?.live ? " live" : ""}`}>
              <Radio size={13} />
              {currentField?.source ?? state?.ocean_source ?? "관제 설정값"}
            </span>
          </div>

          <BoundaryMap
            boundary={boundary}
            currentField={currentField}
            windField={windField}
            layers={layers}
            onBBoxChange={setBbox}
          />

          <div className="bd-timeline">
            <button
              className={`btn${auto ? " btn-danger" : ""}`}
              onClick={() => setMinutes(auto ? Math.round(boundary.elapsed_min) : null)}
            >
              <span className={`glow-dot${auto ? "" : " off"}`} />
              실시간 추적
            </button>
            <div className="sb-divider" />
            <div className="bd-slider">
              <Timer size={15} />
              <span className="l">경과 시간</span>
              <input
                type="range"
                min={0}
                max={120}
                step={1}
                value={Math.min(120, Math.round(boundary.elapsed_min))}
                onChange={(e) => setMinutes(Number(e.target.value))}
              />
              <span className="v">+{Math.round(boundary.elapsed_min)}분</span>
            </div>
            <div className="bd-steps">
              <button
                className={`bd-step${auto ? " on" : ""}`}
                onClick={() => setMinutes(null)}
              >
                현재
              </button>
              {STEP_MINUTES.map((m) => (
                <button
                  key={m}
                  className={`bd-step${!auto && minutes === m ? " on" : ""}`}
                  onClick={() => setMinutes(m)}
                >
                  +{m}분
                </button>
              ))}
            </div>
            <div className="spacer" />
            <span className="bd-recalc">
              <RefreshCw size={13} />
              해류·풍상 {weather.updated_at} 기준 · 2초마다 재계산
            </span>
          </div>
        </div>

        <div className="bd-side">
          {/* 신고 접수 정보 */}
          <section className="panel danger">
            <div className="panel-head">
              <Siren size={17} className="ic-red" />
              <span className="panel-title">신고 접수 정보</span>
              <div className="spacer" />
              <span className="chip red">
                {report.cause === "mob" ? "자동 익수" : "수동 SOS"}
              </span>
            </div>
            <div className="bd-vesselrow">
              <Ship size={16} />
              <span className="n">{report.vessel_name}</span>
              <div className="spacer" />
              <span className="id">{report.vessel_id}</span>
            </div>
            <div className="cells">
              <div className="cell"><span className="l">접수 시각</span><span className="v red">{report.time.slice(-8)}</span></div>
              <div className="cell"><span className="l">경과</span><span className="v red">{fmtElapsed(boundary.elapsed_actual_min)}</span></div>
              <div className="cell"><span className="l">관할</span><span className="v">{boundary.region}</span></div>
            </div>
            {report.detail && (
              <div className="cell wide">
                <span className="l">신고 내용 (V-PASS 단말)</span>
                <span className="v sm">{report.detail}</span>
              </div>
            )}
          </section>

          {/* 실시간 해양 환경 */}
          <section className="panel">
            <div className="panel-head">
              <Waves size={17} className="ic-cyan" />
              <span className="panel-title">실시간 해양 환경</span>
              <div className="spacer" />
              <span className="chip cyan">{weather.source ?? "관제 설정"}</span>
            </div>
            <div className="cells">
              <div className="cell"><span className="l">해류 (방향 · 유속)</span><span className="v cyan">{weather.current_dir}° · {weather.current_kn.toFixed(2)} kn</span></div>
              <div className="cell"><span className="l">풍향 · 풍속 (불어오는 방향)</span><span className="v orange">{weather.wind_dir} · {weather.wind_speed_ms.toFixed(1)} m/s</span></div>
            </div>
            <div className="cells">
              <div className="cell"><span className="l">파고</span><span className="v">{weather.wave_height_m} m</span></div>
              <div className="cell"><span className="l">수온</span><span className="v">{weather.water_temp_c} °C</span></div>
              <div className="cell"><span className="l">생존 한계 (추정)</span><span className="v orange">{survival ?? "-"}</span></div>
            </div>
            <div className="bd-note accent">
              <RefreshCw size={13} />
              관제 대시보드 · {boundary.region} 관할 기상 설정과 동기화 (V-PASS 단말 동시 반영)
            </div>
          </section>

          {/* 표류 예측 */}
          <section className="panel">
            <div className="panel-head">
              <Activity size={17} className="ic-orange" />
              <span className="panel-title">표류 예측 (Leeway)</span>
              <div className="spacer" />
              <span className="chip orange"><Calculator size={12} />실시간 계산</span>
            </div>
            <div className="cells">
              <div className="cell"><span className="l">합성 표류 속도</span><span className="v orange">{drift.speed_kn.toFixed(2)} kn</span></div>
              <div className="cell"><span className="l">표류 방위</span><span className="v orange">{drift.bearing}°</span></div>
              <div className="cell"><span className="l">이동 거리</span><span className="v orange">{fmtDistance(boundary.distance_m)}</span></div>
            </div>
            <div className="bd-formula">
              <div className="f"><span className="l">해류 성분 (100%)</span><span className="v cyan">{drift.current_kn.toFixed(2)} kn · {drift.current_dir}°</span></div>
              <div className="f"><span className="l">풍압 성분 (풍속의 {(drift.leeway_ratio * 100).toFixed(0)}%)</span><span className="v orange">{drift.leeway_kn.toFixed(2)} kn · {drift.leeway_dir}°</span></div>
              <div className="f total"><span className="l">벡터 합성 결과</span><span className="v red">{drift.speed_kn.toFixed(2)} kn · {drift.bearing}°</span></div>
            </div>
            <div className="cell wide">
              <span className="l">예상 중심 좌표 (경과 +{Math.round(boundary.elapsed_min)}분)</span>
              <span className="v red">{boundary.center.position}</span>
            </div>
          </section>

          {/* 시간별 탐색 구역 */}
          <section className="panel grow">
            <div className="panel-head">
              <Target size={17} className="ic-red" />
              <span className="panel-title">시간별 탐색 구역</span>
              <div className="spacer" />
              <span className="chip red">95% 기준</span>
            </div>
            <div className="bd-table">
              <div className="th">
                <span className="c-time">경과</span>
                <span className="c-num">반경</span>
                <span className="c-num">면적</span>
                <span className="c-num">이동</span>
              </div>
              {timeline.map((row) => (
                <div key={row.elapsed_min} className={`tr${row.current ? " on" : ""}`}>
                  <span className="c-time">
                    <i className="dot" />
                    {row.current ? `현재 +${Math.round(row.elapsed_min)}분` : `+${Math.round(row.elapsed_min)}분`}
                  </span>
                  <span className="c-num">{fmtDistance(row.radius_m)}</span>
                  <span className="c-num">{row.area_km2} km²</span>
                  <span className="c-num">{fmtDistance(row.distance_m)}</span>
                </div>
              ))}
            </div>
            <div className="bd-probs">
              {boundary.rings.map((ring) => (
                <div key={ring.probability} className={`prob p${ring.probability}`}>
                  <span className="l">{ring.probability}% 구역</span>
                  <span className="v">{fmtDistance(ring.radius_m)} · {ring.area_km2} km²</span>
                </div>
              ))}
            </div>
            <div className="bd-note">
              <Info size={13} />
              {boundary.model.note}
            </div>
          </section>

          <div className="bd-actions">
            <button className="btn btn-danger" onClick={dispatch}>
              <Siren size={16} />
              {report.status === "new" ? "구조세력 배정" : "배정 완료"}
            </button>
            <button className="btn" onClick={close}>상황 종료</button>
          </div>
        </div>
      </div>
    </div>
  );
}
