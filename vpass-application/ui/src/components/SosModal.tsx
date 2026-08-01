// SOS / 익수 비상 모달 — 어떤 화면 위에서도 표시

import { Siren } from "lucide-react";
import { api } from "../api";
import type { SosReport } from "../types";

export function SosModal({ report }: { report: SosReport }) {
  const isMob = report.cause === "mob";

  return (
    <div className="modal-backdrop" style={{ background: "#070509e6" }}>
      <div
        className="modal fade-in-up"
        style={{
          width: 480,
          alignItems: "center",
          padding: 32,
          border: "1.5px solid var(--red)",
          boxShadow: "0 0 60px 0 #ff375f40, 0 20px 50px 0 #00000099",
        }}
      >
        <div
          className="pulse"
          style={{
            width: 72,
            height: 72,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--red-soft)",
            border: "1px solid var(--red-border)",
            borderRadius: 36,
            color: "var(--red)",
          }}
        >
          <Siren size={34} />
        </div>

        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 14,
            fontWeight: 800,
            letterSpacing: 2,
            color: "var(--red)",
          }}
        >
          {isMob ? "EMERGENCY · MOB" : "EMERGENCY · SOS"}
        </div>

        <div style={{ fontSize: 20, fontWeight: 700 }}>
          해양경찰청에 신고가 완료되었습니다
        </div>

        <div
          style={{
            fontSize: 13,
            lineHeight: "21px",
            color: "var(--text-2)",
            textAlign: "center",
          }}
        >
          {isMob ? (
            <>
              {report.detail ?? "선원 익수가 감지되었습니다."}
              <br />
              킬 스위치가 작동하여 엔진이 비상 정지되었습니다.
            </>
          ) : (
            <>
              현재 위치와 어선 정보가 해양경찰청에 전송되었습니다.
              <br />
              구조대가 출동할 때까지 안전한 곳에서 대기해 주세요.
            </>
          )}
        </div>

        <div
          style={{
            width: "100%",
            display: "flex",
            flexDirection: "column",
            gap: 6,
            padding: "12px 16px",
            background: "var(--deep)",
            borderRadius: 8,
          }}
        >
          {(
            [
              ["신고 시각", report.time],
              ["신고 위치", report.position],
              ["어선명", `${report.vessel_name} (${report.vessel_id})`],
            ] as const
          ).map(([label, value]) => (
            <div
              key={label}
              style={{ display: "flex", alignItems: "center", width: "100%" }}
            >
              <span style={{ fontSize: 11, color: "var(--text-3)" }}>{label}</span>
              <span
                style={{
                  marginLeft: "auto",
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                }}
              >
                {value}
              </span>
            </div>
          ))}
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
          onClick={() => api.ackSos()}
        >
          상황 확인
        </button>
      </div>

      <div style={{ fontSize: 11, color: "var(--text-3)" }}>
        상태바의 SOS 버튼으로 어떤 페이지에서든 긴급 신고할 수 있습니다
      </div>
    </div>
  );
}
