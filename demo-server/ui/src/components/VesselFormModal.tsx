// 선박 추가/편집 모달 (데모용 직접 입력)

import { useState, type ChangeEvent, type ReactNode } from "react";
import { Anchor, Check, LogIn, Ship, X } from "lucide-react";
import { api } from "../api";
import type { Vessel, VesselForm, VesselStatus } from "../types";

interface Props {
  vessel: Vessel | null; // null = 신규 추가
  regions: string[];
  onClose: () => void;
  onSaved: () => void;
}

export function VesselFormModal({ vessel, regions, onClose, onSaved }: Props) {
  const editing = vessel !== null;
  const [form, setForm] = useState<VesselForm>({
    name: vessel?.name ?? "",
    vessel_id: vessel?.vessel_id ?? "",
    region: vessel?.region ?? regions[0] ?? "남해",
    lat: vessel?.lat ?? 34.8021,
    lon: vessel?.lon ?? 128.4234,
    course: vessel?.course ?? 0,
    speed_kn: vessel?.speed_kn ?? 0,
    crew: vessel?.crew ?? 0,
    status: vessel?.status ?? "docked",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = <K extends keyof VesselForm>(key: K, value: VesselForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const num = (key: keyof VesselForm) => (e: ChangeEvent<HTMLInputElement>) =>
    set(key, (e.target.value === "" ? 0 : Number(e.target.value)) as never);

  const submit = async () => {
    if (!form.name.trim() || !form.vessel_id.trim()) {
      setError("선박명과 식별번호를 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (editing && vessel) await api.updateVessel(vessel.id, form);
      else await api.addVessel(form);
      onSaved();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장에 실패했습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="modal pop-in" style={{ width: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="mh-icon accent">
            <Ship size={18} />
          </div>
          <div className="spacer" style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span className="mh-title">{editing ? "선박 정보 수정" : "선박 추가"}</span>
            <span className="mh-sub">관제 대상 선박 정보를 입력합니다 (데모)</span>
          </div>
          <button className="icon-btn" style={{ width: 32, height: 32 }} onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="modal-body">
          <div className="form">
            <Field label="선박명">
              <div className="field-box">
                <input
                  value={form.name}
                  placeholder="예: 제3007 통영호"
                  onChange={(e) => set("name", e.target.value)}
                />
              </div>
            </Field>

            <Field label="선박식별번호">
              <div className="field-box mono">
                <input
                  value={form.vessel_id}
                  placeholder="예: 경남-통영-12345"
                  onChange={(e) => set("vessel_id", e.target.value)}
                />
              </div>
            </Field>

            <Field label="관할 해양경찰청">
              <div className="seg">
                {regions.map((r) => (
                  <button
                    key={r}
                    className={`seg-item${form.region === r ? " on" : ""}`}
                    onClick={() => set("region", r)}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </Field>

            <div className="field-row">
              <Field label="위도 (lat)">
                <div className="field-box mono">
                  <input type="number" step="0.0001" value={form.lat} onChange={num("lat")} />
                </div>
              </Field>
              <Field label="경도 (lon)">
                <div className="field-box mono">
                  <input type="number" step="0.0001" value={form.lon} onChange={num("lon")} />
                </div>
              </Field>
            </div>

            <div className="field-row">
              <Field label="침로 (°)">
                <div className="field-box mono">
                  <input type="number" value={form.course} onChange={num("course")} />
                </div>
              </Field>
              <Field label="속력 (kn)">
                <div className="field-box mono">
                  <input type="number" step="0.1" value={form.speed_kn} onChange={num("speed_kn")} />
                </div>
              </Field>
              <Field label="승조원 (명)">
                <div className="field-box mono">
                  <input type="number" value={form.crew} onChange={num("crew")} />
                </div>
              </Field>
            </div>

            <Field label="운항 상태">
              <div className="seg">
                {(
                  [
                    ["departed", "출항중", <Anchor size={15} key="a" />],
                    ["docked", "입항", <LogIn size={15} key="l" />],
                  ] as [VesselStatus, string, ReactNode][]
                ).map(([key, label, icon]) => (
                  <button
                    key={key}
                    className={`seg-item${form.status === key ? " on" : ""}`}
                    onClick={() => set("status", key)}
                  >
                    {icon}
                    {label}
                  </button>
                ))}
              </div>
            </Field>

            {error && <div className="form-error">{error}</div>}
          </div>
        </div>

        <div className="modal-foot">
          <button className="btn btn-secondary" onClick={onClose}>
            취소
          </button>
          <button className="btn btn-primary" onClick={submit} disabled={busy}>
            <Check size={16} />
            {editing ? "저장" : "등록"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      {children}
    </div>
  );
}
