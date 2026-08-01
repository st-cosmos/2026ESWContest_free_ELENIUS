// 어선운항정보 기록: 운항 목록 + 1분 간격 좌표 상세 + 더미 데이터 입력

import { Anchor, ChevronRight, Ship } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppState, VoyageDetail, VoyageSummary } from "../types";

function rangeLabel(v: VoyageSummary): string {
  const dep = v.departed_at.split(" ")[1]?.slice(0, 5) ?? "-";
  if (!v.arrived_at) return `${dep} 출항 → 운항 중`;
  const arr = v.arrived_at.split(" ")[1]?.slice(0, 5) ?? "-";
  return `${dep} 출항 → ${arr} 입항`;
}

// 더미 데이터 입력(개발용) — 연/월/일/시/분/초 + 좌표
function DummyInput({ onAdded }: { onAdded: () => void }) {
  const now = new Date();
  const [y, setY] = useState(String(now.getFullYear()));
  const [mo, setMo] = useState(String(now.getMonth() + 1).padStart(2, "0"));
  const [d, setD] = useState(String(now.getDate()).padStart(2, "0"));
  const [h, setH] = useState("06");
  const [mi, setMi] = useState("10");
  const [s, setS] = useState("00");
  const [coord, setCoord] = useState("");
  const [error, setError] = useState<string | null>(null);

  const numCell = (
    value: string,
    set: (v: string) => void,
    width: number,
    ph: string,
    max: number,
  ) => (
    <div
      className="field-box mono"
      style={{ width, padding: "8px 0", borderRadius: 8, justifyContent: "center" }}
    >
      <input
        value={value}
        onChange={(e) => set(e.target.value.replace(/\D/g, "").slice(0, max))}
        placeholder={ph}
        style={{ fontSize: 12, textAlign: "center" }}
      />
    </div>
  );

  const add = async () => {
    setError(null);
    const ts = `${y.padStart(4, "0")}-${mo.padStart(2, "0")}-${d.padStart(2, "0")} ${h.padStart(2, "0")}:${mi.padStart(2, "0")}:${s.padStart(2, "0")}`;
    const c = coord.trim() || "N34°48.125' E128°25.402'";
    try {
      await api.addManualPoint(ts, c);
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "추가 실패");
    }
  };

  return (
    <div
      style={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: "12px 14px",
        background: "var(--panel-2)",
        border: "1px solid var(--border-subtle)",
        borderRadius: 8,
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>
        운항정보 더미 데이터 입력
      </span>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        {numCell(y, setY, 56, "연", 4)}
        {numCell(mo, setMo, 44, "월", 2)}
        {numCell(d, setD, 44, "일", 2)}
        {numCell(h, setH, 44, "시", 2)}
        {numCell(mi, setMi, 44, "분", 2)}
        {numCell(s, setS, 44, "초", 2)}
        <div
          className="field-box mono"
          style={{ flex: 1, padding: "8px 12px", borderRadius: 8 }}
        >
          <input
            value={coord}
            onChange={(e) => setCoord(e.target.value)}
            placeholder="좌표 (N00°00.000' E000°00.000')"
            style={{ fontSize: 12 }}
          />
        </div>
        <button
          className="btn btn-primary btn-sm"
          style={{ padding: "8px 16px" }}
          onClick={add}
        >
          추가
        </button>
      </div>
      {error && <span style={{ fontSize: 11, color: "var(--red)" }}>{error}</span>}
    </div>
  );
}

export function VoyageLog({ state }: { state: AppState }) {
  const [voyages, setVoyages] = useState<VoyageSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<VoyageDetail | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    api
      .voyages()
      .then((vs) => {
        setVoyages(vs);
        if (vs.length > 0 && !selected) setSelected(vs[0].id);
      })
      .catch(() => {});
  }, [reloadKey, state.voyage.active, state.voyage.current_id]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    api.voyage(selected).then(setDetail).catch(() => setDetail(null));
  }, [selected, reloadKey, state.voyage.active]);

  // 운항 중이면 최신 좌표 반영을 위해 12초마다 상세 갱신
  useEffect(() => {
    if (!state.voyage.active) return;
    const t = setInterval(() => setReloadKey((k) => k + 1), 12000);
    return () => clearInterval(t);
  }, [state.voyage.active]);

  const sim = async (cruising: boolean) => {
    try {
      await api.devSail(cruising);
    } catch (e) {
      alert(e instanceof Error ? e.message : "요청 실패");
    }
  };

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">어선운항정보 기록</h1>
          <p className="page-desc">
            출항부터 입항까지를 하나의 기록으로 관리하며, 1분 간격으로 시간과 좌표가
            저장됩니다.
          </p>
        </div>
        {/* 모의 운항 제어 (개발·시연용) */}
        <button className="btn btn-secondary btn-sm" onClick={() => sim(true)}>
          <Ship size={13} /> 모의 출항
        </button>
        <button className="btn btn-secondary btn-sm" onClick={() => sim(false)}>
          <Anchor size={13} /> 모의 입항
        </button>
      </div>

      <div style={{ display: "flex", gap: 16, flex: 1, minHeight: 0, width: "100%" }}>
        {/* 운항 기록 목록 */}
        <section
          className="panel"
          style={{
            width: 330,
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            padding: 16,
          }}
        >
          <h2 className="panel-title">운항 기록</h2>
          <div
            style={{
              flex: 1,
              minHeight: 0,
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {voyages.length === 0 && (
              <span style={{ fontSize: 12, color: "var(--text-3)" }}>
                운항 기록이 없습니다 · 출항하면 자동으로 생성됩니다
              </span>
            )}
            {voyages.map((v) => {
              const active = v.id === selected;
              return (
                <button
                  key={v.id}
                  onClick={() => setSelected(v.id)}
                  style={{
                    width: "100%",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    padding: "11px 13px",
                    background: active ? "var(--accent-soft)" : "var(--cell-bg)",
                    border: `1px solid ${active ? "var(--accent-border)" : "var(--cell-border)"}`,
                    borderRadius: 10,
                    textAlign: "left",
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      fontFamily: "var(--font-mono)",
                      fontSize: 13,
                      fontWeight: 700,
                      color: active ? "var(--accent)" : "var(--text-1)",
                    }}
                  >
                    {v.date}
                    {v.status === "active" && (
                      <span
                        className="badge accent"
                        style={{ marginLeft: 8, fontSize: 9, padding: "2px 7px" }}
                      >
                        운항 중
                      </span>
                    )}
                    <ChevronRight
                      size={14}
                      style={{ marginLeft: "auto" }}
                      color="var(--text-3)"
                    />
                  </span>
                  <span style={{ fontSize: 11, color: "var(--text-2)" }}>
                    {rangeLabel(v)}
                  </span>
                </button>
              );
            })}
          </div>
          <span style={{ fontSize: 10, color: "var(--text-3)" }}>
            기록을 선택하면 상세 운항 정보를 볼 수 있습니다
          </span>
        </section>

        {/* 운항 상세 */}
        <section
          className="panel"
          style={{
            flex: 1,
            minWidth: 0,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            padding: 18,
          }}
        >
          {detail ? (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
                  <h2 className="panel-title">운항 상세 · {detail.date}</h2>
                  <span style={{ fontSize: 11, color: "var(--text-3)" }}>
                    1분 간격 시간·좌표 기록
                  </span>
                </div>
                <span
                  className={`badge ${detail.status === "active" ? "warn" : "accent"}`}
                >
                  <span className="dot" />
                  {detail.status === "active" ? "운항 중" : "운항 완료"}
                </span>
              </div>

              <div className="table-box" style={{ flex: 1, minHeight: 0 }}>
                <div className="table-header" style={{ padding: "7px 12px" }}>
                  <span style={{ width: 220 }}>시간</span>
                  <span style={{ flex: 1 }}>좌표</span>
                </div>
                {detail.points.map((p, i) => (
                  <div
                    className="table-row"
                    key={`${p.ts}-${i}`}
                    style={{ padding: "9px 12px", borderRadius: 8 }}
                  >
                    <span
                      style={{
                        width: 220,
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                        color: "var(--text-2)",
                      }}
                    >
                      {p.ts}
                    </span>
                    <span style={{ flex: 1, fontFamily: "var(--font-mono)", fontSize: 12 }}>
                      {p.coord}
                    </span>
                  </div>
                ))}
              </div>

              <DummyInput onAdded={() => setReloadKey((k) => k + 1)} />
            </>
          ) : (
            <div
              style={{
                flex: 1,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                color: "var(--text-3)",
                fontSize: 12,
              }}
            >
              좌측에서 운항 기록을 선택해 주세요
              <DummyInput onAdded={() => setReloadKey((k) => k + 1)} />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
