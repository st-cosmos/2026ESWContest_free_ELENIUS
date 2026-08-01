// 데모 관제 대시보드 — 좌 2/3 선박 현황 + 우 1/3 해양 기상 지도

import { useState } from "react";
import { BellRing, Plus, Ship } from "lucide-react";
import { useAppState } from "./state";
import { api } from "./api";
import type { Vessel } from "./types";
import { StatusBar } from "./components/StatusBar";
import { VesselCard } from "./components/VesselCard";
import { PortLog } from "./components/PortLog";
import { WeatherPanel } from "./components/WeatherPanel";
import { ReportsModal } from "./components/ReportsModal";
import { ReportAlertModal } from "./components/ReportAlertModal";
import { VesselFormModal } from "./components/VesselFormModal";

export default function App() {
  const { state, refresh } = useAppState();
  const [reportsOpen, setReportsOpen] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editVessel, setEditVessel] = useState<Vessel | null>(null);

  if (!state) {
    return (
      <div className="app">
        <div className="empty" style={{ margin: "auto" }}>
          관제 서버에 연결 중…
        </div>
      </div>
    );
  }

  const openAdd = () => {
    setEditVessel(null);
    setFormOpen(true);
  };
  const openEdit = (v: Vessel) => {
    setEditVessel(v);
    setFormOpen(true);
  };
  const toggle = async (v: Vessel) => {
    try {
      await api.setVesselStatus(v.id, v.status === "departed" ? "docked" : "departed");
      refresh();
    } catch {
      /* 무시 */
    }
  };
  const remove = async (v: Vessel) => {
    if (!window.confirm(`'${v.name}' 선박을 삭제하시겠습니까?`)) return;
    try {
      await api.deleteVessel(v.id);
      refresh();
    } catch {
      /* 무시 */
    }
  };

  return (
    <div className="app">
      <StatusBar time={state.time} />

      <div className="body">
        {/* 좌측 2/3: 선박 현황 */}
        <div className="col-left">
          <div className="section-head">
            <div>
              <div className="sh-title">선박 현황</div>
              <div className="sh-desc">실시간 출입항·위치 모니터링</div>
            </div>
            <span className="count-chip">
              출항 {state.stats.departed} · 입항 {state.stats.docked}
            </span>
            <div className="spacer" />
            <button className="btn btn-danger-soft" onClick={() => setReportsOpen(true)}>
              <BellRing size={16} />
              신고 접수
              {state.unread_reports > 0 && <span className="pill-badge">{state.unread_reports}</span>}
            </button>
            <button className="btn btn-primary" onClick={openAdd}>
              <Plus size={16} />
              선박 추가
            </button>
          </div>

          <div className="vessel-grid">
            {state.vessels.length === 0 && (
              <div className="empty" style={{ gridColumn: "1 / -1" }}>
                <Ship size={22} style={{ marginBottom: 8 }} />
                <div>등록된 선박이 없습니다. '선박 추가'로 등록해 주세요.</div>
              </div>
            )}
            {state.vessels.map((v) => (
              <VesselCard
                key={v.id}
                vessel={v}
                onEdit={openEdit}
                onToggle={toggle}
                onDelete={remove}
              />
            ))}
          </div>

          <PortLog entries={state.port_log} />
        </div>

        {/* 우측 1/3: 해양 기상 관제 */}
        <div className="col-right">
          <WeatherPanel state={state} onChange={refresh} />
        </div>
      </div>

      {/* 신고 최초 접수 알림 (신규 1건) */}
      {state.report_alert && (
        <ReportAlertModal
          report={state.report_alert}
          onChange={refresh}
          onViewAll={() => setReportsOpen(true)}
        />
      )}

      {/* 신고 전체 목록 */}
      {reportsOpen && (
        <ReportsModal
          reports={state.reports}
          onClose={() => setReportsOpen(false)}
          onChange={refresh}
        />
      )}

      {/* 선박 추가/편집 */}
      {formOpen && (
        <VesselFormModal
          vessel={editVessel}
          regions={state.regions}
          onClose={() => setFormOpen(false)}
          onSaved={refresh}
        />
      )}
    </div>
  );
}
