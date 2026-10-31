// 어선 정보: 최초 등록 정보 조회/수정 → 해양경찰청 자동 보고(시뮬레이션)

import { CheckCircle2, PencilLine } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppState } from "../types";

export const REGIONS = ["동해", "서해", "남해", "중부", "제주"];

export function VesselInfo({ state }: { state: AppState }) {
  const vessel = state.vessel;
  const [region, setRegion] = useState("");
  const [vesselId, setVesselId] = useState("");
  const [name, setName] = useState("");
  const [homePort, setHomePort] = useState("");
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirtyKey, setDirtyKey] = useState(0); // 되돌리기용

  useEffect(() => {
    if (vessel) {
      setRegion(vessel.region);
      setVesselId(vessel.vessel_id);
      setName(vessel.name);
      setHomePort(vessel.home_port);
    }
    // dirtyKey 변경 시(되돌리기) 서버 값으로 재설정
  }, [vessel?.updated_at, dirtyKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setError(null);
    if (!region || !vesselId.trim() || !name.trim() || !homePort.trim()) {
      setError("모든 항목을 입력해 주세요.");
      return;
    }
    try {
      const res = await api.saveVessel({
        region,
        vessel_id: vesselId,
        name,
        home_port: homePort,
      });
      setToast(res.message);
      setTimeout(() => setToast(null), 4000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장에 실패했습니다.");
    }
  };

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">어선 정보</h1>
          <p className="page-desc">
            최초 등록한 정보를 언제든지 수정할 수 있습니다. 수정 시 해양경찰청에 자동
            보고됩니다.
          </p>
        </div>
        {toast && (
          <div className="chip accent fade-in-up">
            <CheckCircle2 size={14} />
            <span>{toast}</span>
          </div>
        )}
      </div>

      <section
        className="panel"
        style={{
          width: 640,
          display: "flex",
          flexDirection: "column",
          gap: 18,
          padding: 24,
          flexShrink: 0,
        }}
      >
        <div className="field-group" style={{ gap: 8 }}>
          <span className="field-label">지역 해양경찰청</span>
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
            <PencilLine size={14} color="var(--text-3)" />
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
            <PencilLine size={14} color="var(--text-3)" />
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
            <PencilLine size={14} color="var(--text-3)" />
          </div>
        </div>

        {error && (
          <div className="chip danger" style={{ width: "100%" }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            className="btn btn-secondary"
            onClick={() => setDirtyKey((k) => k + 1)}
          >
            되돌리기
          </button>
          <button className="btn btn-primary" onClick={save}>
            수정 사항 저장
          </button>
        </div>
      </section>
    </div>
  );
}
