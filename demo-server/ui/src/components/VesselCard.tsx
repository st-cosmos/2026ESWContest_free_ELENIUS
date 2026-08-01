// 선박 카드: 선박명·식별번호·실시간 GPS·침로·속력·승조원
// 출항(departed) = 밝게, 입항(docked) = 어둡게(비활성 느낌)

import { Anchor, LogIn, Pencil, Ship, Trash2 } from "lucide-react";
import type { Vessel } from "../types";

interface Props {
  vessel: Vessel;
  onEdit: (v: Vessel) => void;
  onToggle: (v: Vessel) => void;
  onDelete: (v: Vessel) => void;
}

export function VesselCard({ vessel, onEdit, onToggle, onDelete }: Props) {
  const departed = vessel.status === "departed";
  const isVpass = vessel.source === "vpass";

  return (
    <div className={`vcard${departed ? "" : " docked"}`}>
      <div className="vcard-top">
        <div className="vcard-namecol">
          <span className="vcard-name">
            <Ship size={18} />
            {vessel.name}
            {isVpass && vessel.live && <span className="live-tag">LIVE</span>}
          </span>
          <span className="vcard-id">{vessel.vessel_id}</span>
        </div>
        <span className="status-badge">
          <span className="dot" />
          {departed ? "출항중" : "입항"}
        </span>
      </div>

      <div className="vcard-divider" />

      <div className="cell">
        <span className="cell-label">실시간 위치 · {vessel.region}</span>
        <span className="cell-value" style={{ fontSize: 14 }}>
          {vessel.position}
        </span>
      </div>

      <div className="vcard-metrics">
        <div className="cell">
          <span className="cell-label">침로</span>
          <span className="cell-value" style={{ fontSize: 16 }}>
            {departed ? `${vessel.course}°` : "—"}
          </span>
        </div>
        <div className="cell">
          <span className="cell-label">속력</span>
          <span className="cell-value" style={{ fontSize: 16 }}>
            {vessel.speed_kn} kn
          </span>
        </div>
        <div className="cell">
          <span className="cell-label">승조원</span>
          <span className="cell-value" style={{ fontSize: 16 }}>
            {vessel.crew}명
          </span>
        </div>
      </div>

      <div className="vcard-actions">
        <button
          className={`btn ${departed ? "btn-secondary" : "btn-primary"}`}
          onClick={() => onToggle(vessel)}
        >
          {departed ? (
            <>
              <LogIn size={14} /> 입항 처리
            </>
          ) : (
            <>
              <Anchor size={14} /> 출항 처리
            </>
          )}
        </button>
        <button
          className="btn btn-secondary"
          style={{ flex: "0 0 auto", padding: "8px 12px" }}
          onClick={() => onEdit(vessel)}
          title="수정"
        >
          <Pencil size={14} />
        </button>
        {!isVpass && (
          <button
            className="btn btn-danger-soft"
            style={{ flex: "0 0 auto", padding: "8px 12px" }}
            onClick={() => onDelete(vessel)}
            title="삭제"
          >
            <Trash2 size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
