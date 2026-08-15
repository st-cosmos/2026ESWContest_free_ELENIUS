// 신고 접수 현황 모달 (전체 목록 조회) — 수동 / 자동(익수) 구분

import { useState } from "react";
import {
  ArrowRight,
  BellRing,
  LifeBuoy,
  MousePointerClick,
  PersonStanding,
  Ship,
  Siren,
  TriangleAlert,
  X,
} from "lucide-react";
import { api } from "../api";
import { navigate } from "../route";
import type { Report } from "../types";

type Tab = "all" | "manual" | "mob";

const STATUS_LABEL: Record<string, string> = {
  dispatched: "출동 지령됨",
  closed: "상황 종료",
};

export function ReportsModal({
  reports,
  onClose,
  onChange,
}: {
  reports: Report[];
  onClose: () => void;
  onChange: () => void;
}) {
  const [tab, setTab] = useState<Tab>("all");

  const filtered = reports.filter((r) =>
    tab === "all" ? true : tab === "manual" ? r.cause === "manual" : r.cause === "mob",
  );

  const act = async (fn: Promise<unknown>) => {
    try {
      await fn;
      onChange();
    } catch {
      /* 무시 */
    }
  };

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="modal pop-in" style={{ width: 600 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="mh-icon danger">
            <BellRing size={18} />
          </div>
          <div className="spacer" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="mh-title">신고 접수 현황</span>
            <span className="mh-sub">V-PASS 단말에서 접수된 신고</span>
          </div>
          <button className="icon-btn" style={{ width: 32, height: 32 }} onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="tabs">
          {(
            [
              ["all", "전체"],
              ["manual", "수동 신고"],
              ["mob", "자동 신고 · 익수"],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              className={`tab${tab === key ? " on" : ""}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="tabs-hint">
          <MousePointerClick size={12} />
          익수(자동) 신고를 누르면 요구조자 예상 위치 페이지가 열립니다
        </div>

        <div className="modal-body">
          {filtered.length === 0 && <div className="empty">접수된 신고가 없습니다.</div>}
          {filtered.map((r) => {
            // 요구조자 예상 위치는 익수 신고 전용이다. 수동 SOS 는 선내에서 버튼을
            // 누른 것이라 물에 빠진 사람이 없어 표류를 예측할 대상이 없다.
            const mob = r.cause === "mob";
            const openBoundary = () => navigate(`/boundary/${r.id}`);
            return (
              <div
                className={`report-card${mob ? " mob clickable" : ""}`}
                key={r.id}
                onClick={mob ? openBoundary : undefined}
                title={mob ? "요구조자 예상 위치 · 표류 바운더리 보기" : undefined}
              >
                <div className="rc-top">
                  <span className={`rc-kind ${mob ? "mob" : "manual"}`}>
                    {mob ? <LifeBuoy size={13} /> : <TriangleAlert size={13} />}
                    {mob ? "자동 신고 · 익수(MOB)" : "수동 신고"}
                  </span>
                  {r.status !== "new" && (
                    <span className="status-tag">{STATUS_LABEL[r.status]}</span>
                  )}
                  <span className="rc-time mono">{r.time.slice(11)}</span>
                </div>

                <div className="rc-vessel">
                  <Ship size={16} style={{ color: "var(--text-2)" }} />
                  <span className="name">{r.vessel_name}</span>
                  <span className="id">{r.vessel_id}</span>
                </div>

                <div className="rc-info">
                  <div className="box">
                    <span className="l">신고 위치</span>
                    <span className="v mono">{r.position}</span>
                  </div>
                  <div className="box">
                    <span className="l">상세</span>
                    <span className={`v${mob ? " danger" : ""}`}>{r.detail ?? "-"}</span>
                  </div>
                </div>

                {mob && (
                  <button className="rc-boundary" onClick={openBoundary}>
                    <PersonStanding size={14} />
                    요구조자 예상 위치 · 표류 바운더리 보기
                    <div className="spacer" />
                    <ArrowRight size={14} />
                  </button>
                )}

                {r.status === "new" && (
                  <div className="rc-actions">
                    <button
                      className="btn btn-danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        act(api.reportDispatch(r.id));
                      }}
                    >
                      <Siren size={15} /> 출동 지령
                    </button>
                    <button
                      className="btn btn-secondary"
                      onClick={(e) => {
                        e.stopPropagation();
                        act(api.reportClose(r.id));
                      }}
                    >
                      상황 종료
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
