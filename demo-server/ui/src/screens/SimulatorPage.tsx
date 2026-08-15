// 운항 시뮬레이터 — 지도에서 선박을 움직여 V-PASS 단말에 좌표를 공급하고,
// 지오펜스 통과로 출입항을 자동 등록시키는 별도 페이지(/simulator).

import { useEffect, useRef, useState } from "react";
import {
  Eraser,
  ExternalLink,
  Gauge,
  History,
  Lock,
  LogIn,
  LogOut,
  Move,
  PenTool,
  Pause,
  PersonStanding,
  Play,
  Repeat,
  RotateCcw,
  Ruler,
  SatelliteDish,
  Ship,
  Siren,
  Spline,
  Square,
  Trash2,
  Waves,
} from "lucide-react";
import { api } from "../api";
import { useAppState } from "../state";
import { navigate } from "../route";
import { StatusBar } from "../components/StatusBar";
import { SimMap, distanceNm, formatCoord, type Tool } from "../components/SimMap";
import type { SimPoint, SimState } from "../types";

const TOOLS: { id: Tool; label: string; icon: typeof Move }[] = [
  { id: "move", label: "이동", icon: Move },
  { id: "route", label: "항로 펜", icon: PenTool },
  { id: "fence", label: "지오펜스", icon: Spline },
  { id: "erase", label: "지우기", icon: Eraser },
];

export function SimulatorPage() {
  const { state } = useAppState();
  const [sim, setSim] = useState<SimState | null>(null);
  const [tool, setTool] = useState<Tool>("move");
  const editedAt = useRef(0);
  const polling = useRef(false);
  const speedTimer = useRef<number | undefined>(undefined);

  const refresh = async () => {
    if (polling.current) return;
    polling.current = true;
    try {
      const next = await api.simState();
      setSim((prev) => {
        // 편집 중에는 내가 만지고 있는 항로/펜스/선박 위치를 서버 값으로 덮지 않는다
        if (prev && Date.now() - editedAt.current < 1200) {
          return { ...next, route: prev.route, fence: prev.fence, vessel: prev.vessel };
        }
        return next;
      });
    } catch {
      /* 폴링 실패는 무시 */
    } finally {
      polling.current = false;
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 500);
    return () => clearInterval(t);
  }, []);

  if (!sim) {
    return (
      <div className="app">
        <StatusBar time={state?.time ?? "--:--:--"} />
        <div className="empty" style={{ margin: "auto" }}>
          시뮬레이터를 불러오는 중…
        </div>
      </div>
    );
  }

  const patch = (fn: (prev: SimState) => SimState) => {
    editedAt.current = Date.now();
    setSim((prev) => (prev ? fn(prev) : prev));
  };
  const send = (p: Promise<unknown>) => p.then(refresh).catch(() => {});
  const points = (list: SimPoint[]) => list.map((p) => [p.lat, p.lon]);

  const onVesselMove = (pt: SimPoint, done: boolean) => {
    patch((prev) => ({
      ...prev,
      vessel: { ...prev.vessel, ...pt, position: formatCoord(pt) },
    }));
    if (done) send(api.simPosition(pt.lat, pt.lon));
  };
  const onRouteChange = (list: SimPoint[], done: boolean) => {
    patch((prev) => ({ ...prev, route: list }));
    if (done) send(api.simRoute(points(list)));
  };
  const onFenceChange = (list: SimPoint[], done: boolean) => {
    patch((prev) => ({ ...prev, fence: list }));
    if (done) send(api.simFence(points(list)));
  };
  const onSpeed = (value: number) => {
    patch((prev) => ({ ...prev, speed_kn: value }));
    window.clearTimeout(speedTimer.current);
    speedTimer.current = window.setTimeout(() => send(api.simSpeed({ speed_kn: value })), 200);
  };

  const terminal = sim.terminal
    ? { name: sim.terminal.name, vessel_id: sim.terminal.vessel_id, crew: sim.terminal.crew }
    : null;
  const departed = sim.port_state === "departed";
  const realGps = sim.terminal?.gps_source === "hardware";
  const legs = sim.route.slice(1).map((p, i) => distanceNm(sim.route[i], p));
  const sosLocked = Boolean(sim.sos?.locked);

  return (
    <div className="app">
      <StatusBar time={sim.time} />

      <div className="body">
        {/* 좌: 지도 */}
        <div className="panel sim-panel">
          <div className="sim-head">
            <div>
              <div className="sh-title">운항 시뮬레이션 해역</div>
              <div className="sh-desc">
                통영 인근 · 드래그와 항로 펜으로 V-PASS 단말 좌표를 만든다
              </div>
            </div>
            <div className="spacer" />
            <div className="tool-palette">
              {TOOLS.map((t) => (
                <button
                  key={t.id}
                  className={`tool-btn${tool === t.id ? " on" : ""}`}
                  onClick={() => setTool(t.id)}
                >
                  <t.icon size={15} />
                  {t.label}
                </button>
              ))}
            </div>
            <div className="sb-divider" />
            <button
              className="btn btn-secondary"
              onClick={() => {
                if (window.confirm("항로·지오펜스·이벤트를 모두 지울까요?")) {
                  editedAt.current = 0;
                  send(api.simReset());
                }
              }}
            >
              <RotateCcw size={14} />
              초기화
            </button>
          </div>

          <SimMap
            vessel={sim.vessel}
            route={sim.route}
            fence={sim.fence}
            progress={sim.progress}
            tool={tool}
            terminal={terminal}
            sos={sim.sos}
            onOpenBoundary={
              sim.sos?.info?.cause === "mob"
                ? () => navigate(`/boundary/${sim.sos.info!.report_id}`)
                : undefined
            }
            onVesselMove={onVesselMove}
            onRouteChange={onRouteChange}
            onFenceChange={onFenceChange}
          />

          <div className="sim-playback">
            <button
              className="btn btn-primary"
              onClick={() => send(api.simRun("start"))}
              disabled={sim.running || sim.route.length < 2 || sosLocked}
              title={sosLocked ? "SOS 접수로 위치가 고정되어 있습니다" : undefined}
            >
              <Play size={16} />
              운항 시작
            </button>
            {sosLocked && (
              <span className="sim-lockchip">
                <Lock size={14} />
                SOS 위치 고정 · 운항 재개 불가
              </span>
            )}
            <button
              className="btn btn-secondary"
              onClick={() => send(api.simRun("pause"))}
              disabled={!sim.running}
            >
              <Pause size={15} />
              일시정지
            </button>
            <button className="btn btn-secondary" onClick={() => send(api.simRun("stop"))}>
              <Square size={15} />
              정지
            </button>

            <div className="sb-divider" />

            <div className="speed-ctl">
              <Gauge size={15} />
              <span className="l">운항 속력</span>
              <input
                type="range"
                min={1}
                max={25}
                step={0.1}
                value={sim.speed_kn}
                onChange={(e) => onSpeed(Number(e.target.value))}
              />
              <span className="v">{sim.speed_kn.toFixed(1)} kn</span>
            </div>

            <div className="scale-ctl">
              <Repeat size={14} />
              {sim.time_scales.map((s) => (
                <button
                  key={s}
                  className={`scale-chip${sim.time_scale === s ? " on" : ""}`}
                  onClick={() => send(api.simSpeed({ time_scale: s }))}
                  title="시연용 재생 배속"
                >
                  {s}x
                </button>
              ))}
            </div>

            <div className="spacer" />

            <div className="progress-ctl">
              <span className="l">
                구간 {Math.min(sim.progress.index, Math.max(1, sim.progress.legs))} /{" "}
                {sim.progress.legs}
              </span>
              <div className="pbar">
                <i style={{ width: `${sim.progress.percent}%` }} />
              </div>
              <span className="v">{sim.progress.percent}%</span>
              {sim.progress.eta_min !== null && (
                <span className="l">· 잔여 {sim.progress.eta_min}분</span>
              )}
            </div>
          </div>
        </div>

        {/* 우: SOS / 단말 / 항로 / 지오펜스 */}
        <div className="sim-side">
          {sosLocked && (
            <section className="panel sim-card sos">
              <div className="panel-head">
                <Siren size={17} style={{ color: "var(--red)" }} />
                <div className="panel-title">SOS 접수 · 운항 정지</div>
                <div className="spacer" />
                <span className="sos-kind">
                  {sim.sos.info?.cause === "mob" ? "자동 익수" : "수동 SOS"}{" "}
                  {sim.sos.info?.time?.slice(-8) ?? ""}
                </span>
              </div>

              <div className="sos-metrics">
                <div className="sos-m">
                  <span className="l">킬 스위치</span>
                  <span className="v red">작동 · 엔진 정지</span>
                </div>
                <div className="sos-m">
                  <span className="l">시뮬레이터</span>
                  <span className="v red">위치 고정</span>
                </div>
                <div className="sos-m">
                  <span className="l">표류 (해류+풍압)</span>
                  <span className="v orange">
                    {sim.sos.drift_kn.toFixed(2)} kn · {sim.sos.drift_bearing}°
                  </span>
                </div>
              </div>

              {sim.sos.info?.detail && <div className="sos-detail">{sim.sos.info.detail}</div>}

              <div className="sos-actions">
                {/* 익수 신고에만 요구조자가 있다 (수동 SOS 는 선내 버튼) */}
                {sim.sos.info?.cause === "mob" && (
                  <button
                    className="btn btn-danger"
                    onClick={() => navigate(`/boundary/${sim.sos.info!.report_id}`)}
                  >
                    <PersonStanding size={15} />
                    요구조자 예상 위치
                  </button>
                )}
                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    if (window.confirm("위치 고정을 해제하고 운항을 재개할 수 있게 할까요?"))
                      send(api.simReleaseSos());
                  }}
                >
                  고정 해제
                </button>
              </div>
            </section>
          )}

          <section className="panel sim-card">
            <div className="panel-head">
              <SatelliteDish size={17} />
              <div className="panel-title">연결된 V-PASS 단말</div>
              <div className="spacer" />
              <span className={`auto-chip${terminal ? "" : " off"}`}>
                <span className="dot" />
                {terminal ? "LIVE" : "미연결"}
              </span>
            </div>

            <div className="sc-row">
              <Ship size={15} />
              <b>{terminal?.name ?? "단말 연결 대기"}</b>
              <div className="spacer" />
              <span className="mono muted">{terminal?.vessel_id ?? "-"}</span>
            </div>

            <div className={`gps-note${realGps ? " real" : ""}`}>
              <SatelliteDish size={15} />
              <div>
                <b>
                  {realGps
                    ? "단말이 실측 GPS 를 사용 중입니다"
                    : "단말 GPS 미수신 시 이 좌표를 사용합니다"}
                </b>
                <span>
                  {realGps
                    ? "실측 좌표가 우선이므로 시뮬레이터 좌표는 적용되지 않습니다"
                    : "실측 GPS 가 잡히면 단말이 자동으로 실제 좌표로 되돌아갑니다"}
                </span>
              </div>
            </div>

            <div className="cell">
              <span className="cell-label">V-PASS 로 전송 중인 좌표</span>
              <span className="cell-value accent">{sim.vessel.position}</span>
            </div>
            <div className="sim-metrics">
              <div className="cell">
                <span className="cell-label">침로</span>
                <span className="cell-value">{sim.vessel.course}°</span>
              </div>
              <div className="cell">
                <span className="cell-label">속력</span>
                <span className="cell-value">{sim.vessel.speed_kn.toFixed(1)} kn</span>
              </div>
              <div className="cell">
                <span className="cell-label">운항 상태</span>
                <span className={`cell-value ${departed ? "accent" : "muted"}`}>
                  {departed ? "출항" : "입항"}
                </span>
              </div>
            </div>
          </section>

          <section className="panel sim-card">
            <div className="panel-head">
              <PenTool size={17} />
              <div className="panel-title">항로 · Waypoint</div>
              <div className="spacer" />
              <span className="count-chip">{sim.route.length} 점</span>
              <button
                className="icon-btn sm"
                title="항로 지우기"
                onClick={() => onRouteChange([], true)}
              >
                <Trash2 size={14} />
              </button>
            </div>

            <div className="wp-list">
              {sim.route.length === 0 && (
                <div className="empty sm">'항로 펜'으로 지도를 클릭해 점을 찍어 주세요</div>
              )}
              {sim.route.map((p, i) => (
                <div className={`wp-row${i < sim.progress.index ? " passed" : ""}`} key={i}>
                  <span className={`wp-num${i === 0 ? " start" : ""}`}>{i + 1}</span>
                  <span className="mono wp-coord">{formatCoord(p)}</span>
                  <span className="wp-dist">
                    {i === 0 ? "출발" : `${legs[i - 1].toFixed(1)} 해리`}
                  </span>
                </div>
              ))}
            </div>

            {sim.route.length >= 2 && (
              <div className="wp-foot">
                <Ruler size={13} />총 {sim.progress.total_nm} 해리 · {sim.speed_kn.toFixed(1)}kn
                기준 예상{" "}
                {Math.round((sim.progress.total_nm / Math.max(0.1, sim.speed_kn)) * 60)}분
              </div>
            )}
          </section>

          <section className="panel sim-card grow">
            <div className="panel-head">
              <Spline size={17} />
              <div className="panel-title">지오펜스 · 자동 출입항</div>
              <div className="spacer" />
              <span className="count-chip">{sim.fence.length} 점</span>
              <button
                className="icon-btn sm"
                title="지오펜스 지우기"
                onClick={() => onFenceChange([], true)}
              >
                <Trash2 size={14} />
              </button>
            </div>

            <div className="sc-row">
              <span className="muted">선박 위치 판정</span>
              <div className="spacer" />
              <span className={`state-chip${departed ? " sea" : ""}`}>
                <Waves size={13} />
                {sim.fence.length < 2
                  ? "펜스 없음"
                  : departed
                    ? "펜스 밖 · 해상"
                    : "펜스 안 · 항내"}
              </span>
            </div>

            <div className="fence-rule">
              <div>
                <LogOut size={14} className="accent" />
                펜스를 넘어 바다로 나가면 → 자동 출항 등록
              </div>
              <div>
                <LogIn size={14} className="cyan" />
                바다에서 펜스 안으로 들어오면 → 자동 입항 등록
              </div>
            </div>

            <button
              className="btn btn-secondary"
              onClick={() => send(api.simFlipFence())}
              disabled={sim.fence.length < 2}
              title="펜스의 어느 쪽을 바다로 볼지 뒤집습니다"
            >
              <Repeat size={14} />
              바다 방향 뒤집기
            </button>

            <div className="ev-head">
              <History size={13} />
              최근 자동 등록 이벤트
            </div>
            <div className="ev-list">
              {sim.events.length === 0 && (
                <div className="empty sm">아직 기록된 출입항 이벤트가 없습니다</div>
              )}
              {sim.events.slice(0, 4).map((ev) => (
                <div className="ev-row" key={ev.id}>
                  <span className={`kind-badge ${ev.kind}`}>
                    {ev.kind === "departure" ? "출항" : "입항"}
                  </span>
                  <div className="ev-txt">
                    <b>{terminal?.name ?? "V-PASS 단말"}</b>
                    <span className="mono">{ev.position}</span>
                  </div>
                  <span className="mono ev-time">{ev.time.split(" ")[1] ?? ev.time}</span>
                </div>
              ))}
            </div>

            <div className="ev-foot">
              <ExternalLink size={12} />
              전체 기록은 관제 대시보드 · 출입항 자동 수집에서 확인
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
