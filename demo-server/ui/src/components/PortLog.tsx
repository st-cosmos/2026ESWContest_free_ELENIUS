// 출입항 자동 수집 로그 (선박명 · 식별번호 · 출입항 시각 · 구분)

import { Anchor, ArrowLeftRight, LogIn } from "lucide-react";
import type { PortLogEntry } from "../types";

export function PortLog({ entries }: { entries: PortLogEntry[] }) {
  return (
    <div className="panel port-panel">
      <div className="panel-head">
        <ArrowLeftRight size={18} style={{ color: "var(--accent)" }} />
        <span className="panel-title">출입항 자동 수집</span>
        <div className="spacer" />
        <span className="auto-chip">
          <span className="dot" />
          자동 기록
        </span>
      </div>

      <div className="table">
        <div className="table-header">
          <span className="col-kind">구분</span>
          <span className="col-name">선박명</span>
          <span className="col-id">식별번호</span>
          <span className="col-time">출입항 시각</span>
        </div>

        {entries.length === 0 && <div className="empty">수집된 출입항 기록이 없습니다.</div>}

        {entries.map((e) => {
          const dep = e.kind === "departure";
          return (
            <div className="table-row" key={e.id}>
              <span className="col-kind">
                <span className={`kind-badge ${e.kind}`}>
                  {dep ? <Anchor size={12} /> : <LogIn size={12} />}
                  {dep ? "출항" : "입항"}
                </span>
              </span>
              <span className="col-name" style={{ fontWeight: 600 }}>
                {e.vessel_name}
              </span>
              <span className="col-id mono muted">{e.vessel_id}</span>
              <span className="col-time mono muted">{e.time}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
