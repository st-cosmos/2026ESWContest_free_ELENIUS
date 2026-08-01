// 신고 최초 접수 알림 — 신규 신고 1건만 크게 띄우는 독립 모달

import { Check, LifeBuoy, List, Siren, TriangleAlert, Zap } from "lucide-react";
import { api } from "../api";
import type { Report } from "../types";

export function ReportAlertModal({
  report,
  onChange,
  onViewAll,
}: {
  report: Report;
  onChange: () => void;
  onViewAll: () => void;
}) {
  const mob = report.cause === "mob";

  const act = async (fn: Promise<unknown>, then?: () => void) => {
    try {
      await fn;
    } catch {
      /* 무시 */
    } finally {
      onChange();
      then?.();
    }
  };

  return (
    <div className="backdrop">
      <div className={`modal alert-modal pop-in${mob ? "" : " manual"}`}>
        <div className="alert-band">
          <span className="pulse-dot pulse" />
          <span className="t">신규 신고 접수</span>
          <span className="time mono">{report.time.slice(11)}</span>
        </div>

        <div className="alert-body">
          <div className="alert-icon">
            {mob ? <LifeBuoy size={38} /> : <TriangleAlert size={38} />}
          </div>

          <span className="alert-kind">
            {mob ? <Zap size={13} /> : <TriangleAlert size={13} />}
            {mob ? "자동 신고 · 익수(MOB)" : "수동 신고"}
          </span>

          <div>
            <div className="alert-vessel">{report.vessel_name}</div>
          </div>
          <span className="alert-vid">{report.vessel_id}</span>

          <div className="alert-info">
            <div className="row">
              <span className="l">발생 위치</span>
              <span className="v mono">{report.position}</span>
            </div>
            <div className="row">
              <span className="l">발생 시각</span>
              <span className="v mono">{report.time}</span>
            </div>
            <div className="row">
              <span className="l">상세 사유</span>
              <span className={`v${mob ? " danger" : ""}`}>{report.detail ?? "-"}</span>
            </div>
          </div>
        </div>

        <div className="alert-foot">
          <button className="alert-dispatch" onClick={() => act(api.reportDispatch(report.id))}>
            <Siren size={18} /> 즉시 출동 지령
          </button>
          <div className="alert-subrow">
            <button className="btn btn-secondary" onClick={() => act(api.reportClose(report.id))}>
              <Check size={15} /> 상황 종료
            </button>
            <button
              className="btn btn-secondary"
              onClick={() => act(api.reportSeen(report.id), onViewAll)}
            >
              <List size={15} /> 전체 목록 보기
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
