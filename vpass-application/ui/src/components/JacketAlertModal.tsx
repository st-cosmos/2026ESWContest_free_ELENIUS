// 운항 중 구명조끼 해제(버클 풀림) 경고 모달 — 어떤 화면 위에서도 표시
// 재착용(신호 수신) 시 자동으로 사라지고, [확인] 으로도 닫을 수 있다.

import { LifeBuoy } from "lucide-react";
import { api } from "../api";
import type { JacketDoffAlert } from "../types";

export function JacketAlertModal({ alert }: { alert: JacketDoffAlert }) {
  return (
    <div className="modal-backdrop" style={{ background: "#070509e6" }}>
      <div
        className="modal fade-in-up"
        style={{
          width: 460,
          alignItems: "center",
          padding: 32,
          border: "1.5px solid var(--orange)",
          boxShadow: "0 0 60px 0 #ff9f0a40, 0 20px 50px 0 #00000099",
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
            background: "#ff9f0a1f",
            border: "1px solid #ff9f0a3d",
            borderRadius: 36,
            color: "var(--orange)",
          }}
        >
          <LifeBuoy size={34} />
        </div>

        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 14,
            fontWeight: 800,
            letterSpacing: 2,
            color: "var(--orange)",
          }}
        >
          WARNING · LIFEJACKET
        </div>

        <div style={{ fontSize: 20, fontWeight: 700, textAlign: "center" }}>
          구명조끼 해제가 감지됐습니다!
          <br />
          다시 구명조끼를 착용하세요!
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
              ["대상", `${alert.who} (${alert.device})`],
              ["감지 시각", alert.time],
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
            background: "var(--orange)",
            color: "#1a1208",
            fontWeight: 700,
            borderRadius: 12,
            boxShadow: "0 0 20px 0 #ff9f0a59",
          }}
          onClick={() => api.ackJacketAlert()}
        >
          확인
        </button>
      </div>

      <div style={{ fontSize: 11, color: "var(--text-3)" }}>
        구명조끼를 다시 착용하면 이 경고는 자동으로 사라집니다
      </div>
    </div>
  );
}
