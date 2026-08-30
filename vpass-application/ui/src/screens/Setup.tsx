// 어선 최초 등록 (vessel 미등록 시 전체 화면)

import { AlertCircle, Ship } from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import { REGIONS } from "./VesselInfo";

export function Setup({ onDone }: { onDone: () => void }) {
  const [region, setRegion] = useState<string | null>(null);
  const [vesselId, setVesselId] = useState("");
  const [name, setName] = useState("");
  const [homePort, setHomePort] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!region || !vesselId.trim() || !name.trim() || !homePort.trim()) {
      setError("모든 항목을 입력해야 V-PASS를 시작할 수 있습니다");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.saveVessel({
        region,
        vessel_id: vesselId,
        name,
        home_port: homePort,
      });
      setDone(true);
      setTimeout(onDone, 1600);
    } catch (e) {
      setError(e instanceof Error ? e.message : "등록에 실패했습니다.");
      setBusy(false);
    }
  };

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background:
          "radial-gradient(ellipse 60% 60% at 85% 10%, #00ffa312 0%, #00ffa300 100%), var(--bg)",
      }}
    >
      <div
        className="fade-in-up"
        style={{
          width: 560,
          display: "flex",
          flexDirection: "column",
          gap: 16,
          padding: 32,
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: 14,
          boxShadow: "0 20px 60px 0 #00000080",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="logo-tile" style={{ width: 44, height: 44 }}>
            <Ship size={22} />
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 22, fontWeight: 700 }}>어선 최초 등록</span>
            <span style={{ fontSize: 14, color: "var(--text-2)" }}>
              모든 항목 입력 시 해양경찰청에 자동 등록됩니다
            </span>
          </div>
        </div>

        <div className="field-group" style={{ gap: 8 }}>
          <span className="field-label">지역 해양경찰청 선택</span>
          <div className="region-chips">
            {REGIONS.map((r) => (
              <button
                key={r}
                className={`region-chip${region === r ? " active" : ""}`}
                onClick={() => setRegion(r)}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div className="field-group">
          <div className="field-label-row">
            <span className="field-label">어선식별번호</span>
            <span className="field-hint">숫자만 입력 가능</span>
          </div>
          <div className="field-box mono">
            <input
              value={vesselId}
              inputMode="numeric"
              onChange={(e) => setVesselId(e.target.value)}
              placeholder="예: 2607-001-461100-3"
            />
          </div>
        </div>

        <div className="field-group">
          <div className="field-label-row">
            <span className="field-label">어선명</span>
            <span className="field-hint">한글만 입력 가능</span>
          </div>
          <div className="field-box">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 청해호"
            />
          </div>
        </div>

        <div className="field-group">
          <div className="field-label-row">
            <span className="field-label">출항지</span>
            <span className="field-hint">항구명-선석 형식</span>
          </div>
          <div className="field-box mono">
            <input
              value={homePort}
              onChange={(e) => setHomePort(e.target.value)}
              placeholder="예: 통영부두-03"
            />
          </div>
        </div>

        {error && (
          <div className="chip danger" style={{ width: "100%" }}>
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        {done ? (
          <div
            className="chip accent fade-in-up"
            style={{ width: "100%", justifyContent: "center", padding: 12 }}
          >
            해양경찰청에 자동 등록되었습니다
          </div>
        ) : (
          <button
            className="btn btn-primary"
            style={{ width: "100%" }}
            onClick={submit}
            disabled={busy}
          >
            {busy ? "등록 중…" : "등록하고 시작하기"}
          </button>
        )}

        <span style={{ fontSize: 12, color: "var(--text-3)" }}>
          등록 완료 시 '해양경찰청에 자동 등록되었습니다' 메시지가 표시된 후 메인
          화면으로 이동합니다
        </span>
      </div>
    </div>
  );
}
