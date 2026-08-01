// 상단 상태바: 시각/위치/침로/속도 + 통신/GPS + SOS 버튼

import { Siren, X } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { useAppState } from "../state";

function Tele({ label, value }: { label: string; value: string }) {
  return (
    <div className="tele">
      <span className="tele-label">{label}</span>
      <span className="tele-value">{value}</span>
    </div>
  );
}

function ConnChip({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="conn-chip">
      <span className={`glow-dot${ok ? "" : " off"}`} />
      <span className="conn-label">{label}</span>
    </div>
  );
}

// SOS 신고 확인 창 — 버튼을 누르면 즉시 표시, 확인 시 해경청 신고
function SosConfirm({ onClose }: { onClose: () => void }) {
  const [busy, setBusy] = useState(false);

  const report = async () => {
    setBusy(true);
    try {
      await api.triggerSos();
      onClose(); // 신고 완료 → 전역 상태의 SOS 모달이 표시됨
    } catch {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" style={{ background: "#070509e6" }}>
      <div
        className="modal fade-in-up"
        style={{
          width: 420,
          alignItems: "center",
          border: "1.5px solid var(--red)",
          boxShadow: "0 0 60px 0 #ff375f40, 0 20px 50px 0 #00000099",
        }}
      >
        <div style={{ display: "flex", width: "100%", alignItems: "flex-start" }}>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={{ color: "var(--text-3)" }}>
            <X size={18} />
          </button>
        </div>

        <div
          style={{
            width: 64,
            height: 64,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--red-soft)",
            border: "1px solid var(--red-border)",
            borderRadius: 32,
            color: "var(--red)",
          }}
        >
          <Siren size={30} />
        </div>

        <div style={{ fontSize: 19, fontWeight: 700 }}>SOS 긴급 신고</div>
        <div
          style={{
            fontSize: 13,
            lineHeight: "21px",
            color: "var(--text-2)",
            textAlign: "center",
          }}
        >
          현재 위치와 어선 정보를 해양경찰청에 즉시 전송합니다.
          <br />
          실제 비상 상황에서만 사용해 주세요.
        </div>

        <button
          className="btn"
          style={{
            width: "100%",
            background: "var(--red)",
            color: "#fff",
            fontWeight: 700,
            borderRadius: 12,
            boxShadow: "0 0 20px 0 #ff375f59",
          }}
          onClick={report}
          disabled={busy}
        >
          <Siren size={16} />
          {busy ? "신고 중…" : "해양경찰청에 즉시 신고"}
        </button>

        <button
          className="btn btn-secondary"
          style={{ width: "100%" }}
          onClick={onClose}
        >
          취소
        </button>
      </div>
    </div>
  );
}

export function StatusBar() {
  const { state, connected } = useAppState();
  const [confirming, setConfirming] = useState(false);

  const tel = state?.telemetry;
  return (
    <header className="status-bar">
      <Tele label="현재 시각" value={state?.time ?? "--:--:--"} />
      <div className="tele-divider" />
      <Tele label="위치" value={tel?.position ?? "-"} />
      <Tele label="침로" value={tel ? `${tel.course}°` : "-"} />
      <Tele label="속도" value={tel ? `${tel.speed_kn.toFixed(1)} kn` : "-"} />
      <div style={{ flex: 1 }} />
      <ConnChip label="통신" ok={connected && (tel?.comm_ok ?? false)} />
      <ConnChip label="GPS" ok={connected && (tel?.gps_ok ?? false)} />
      <button
        className="sos-button"
        onClick={() => setConfirming(true)}
        title="SOS 긴급 신고"
      >
        <Siren size={18} />
        <span className="sos-label">SOS</span>
      </button>

      {confirming && <SosConfirm onClose={() => setConfirming(false)} />}
    </header>
  );
}
