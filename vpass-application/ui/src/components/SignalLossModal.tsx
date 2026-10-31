// 구명조끼 신호 두절 경고 모달 — 익수 판정 전 카운트다운 (어떤 화면 위에서도 표시)
//
// 낙상(가속도) 감지 없이 BLE 신호만 SIGNAL_LOSS_TIMEOUT 동안 끊기면 서버가 이 경고를
// 올리고 SIGNAL_LOSS_WARNING_SEC(기본 20초) 카운트다운을 시작한다.
//   - 카운트다운 안에 이 모달을 터치해 끄면 → 정상 운용 유지 (익수 아님)
//   - 터치하지 않으면              → 익수 판정 → 킬 스위치 + SOS (SosModal 로 전환)
//   - 신호가 다시 수신되면          → 자동으로 사라진다
// 모달 어디를 터치해도 끈다 (키오스크 장갑 조작 고려 — 작은 버튼만 노리지 않도록).

import { RadioTower } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SignalWarning } from "../types";

export function SignalLossModal({ warning }: { warning: SignalWarning }) {
  // 서버는 1초 폴링이라 남은 시간이 뚝뚝 끊겨 보인다 — 폴링 사이를 로컬 시계로 보간
  const anchor = useRef({ at: Date.now(), remaining: warning.remaining_sec });
  const [remaining, setRemaining] = useState(warning.remaining_sec);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    anchor.current = { at: Date.now(), remaining: warning.remaining_sec };
    setRemaining(warning.remaining_sec);
  }, [warning.remaining_sec, warning.device]);

  useEffect(() => {
    const t = setInterval(() => {
      const a = anchor.current;
      setRemaining(Math.max(0, a.remaining - (Date.now() - a.at) / 1000));
    }, 100);
    return () => clearInterval(t);
  }, []);

  const dismiss = async () => {
    if (sending) return;
    setSending(true);
    try {
      await api.ackSignalWarning(warning.device);
    } catch {
      /* 다음 폴링에서 상태가 맞춰진다 */
    } finally {
      setSending(false);
    }
  };

  const total = Math.max(1, warning.total_sec);
  const ratio = Math.min(1, Math.max(0, remaining / total));
  const urgent = remaining <= 5;
  const color = urgent ? "var(--red)" : "var(--orange)";
  const glow = urgent ? "#ff375f" : "#ff9f0a";

  return (
    <div
      className="modal-backdrop"
      style={{ background: "#070509e6", cursor: "pointer" }}
      onPointerDown={dismiss}
      role="button"
      aria-label="경고 끄기 — 정상 운용 유지"
    >
      <div
        className="modal fade-in-up"
        style={{
          width: 500,
          alignItems: "center",
          padding: 32,
          border: `1.5px solid ${color}`,
          boxShadow: `0 0 60px 0 ${glow}40, 0 20px 50px 0 #00000099`,
          transition: "border-color .3s, box-shadow .3s",
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
            background: `${glow}1f`,
            border: `1px solid ${glow}3d`,
            borderRadius: 36,
            color,
          }}
        >
          <RadioTower size={34} />
        </div>

        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 16,
            fontWeight: 800,
            letterSpacing: 2,
            color,
          }}
        >
          WARNING · SIGNAL LOST
        </div>

        <div style={{ fontSize: 22, fontWeight: 700, textAlign: "center" }}>
          구명조끼 신호가 끊겼습니다!
          <br />
          {warning.who}의 안전을 확인하세요
        </div>

        {/* 카운트다운 */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 6,
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 56,
              fontWeight: 800,
              lineHeight: 1,
              color,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {Math.ceil(remaining)}
            <span style={{ fontSize: 22, marginLeft: 4 }}>초</span>
          </div>
          <div style={{ fontSize: 14, color: "var(--text-2)" }}>
            응답이 없으면 익수로 판정하고 엔진을 비상 정지합니다
          </div>
        </div>

        <div
          style={{
            width: "100%",
            height: 8,
            background: "var(--deep)",
            borderRadius: 4,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              width: `${ratio * 100}%`,
              height: "100%",
              background: color,
              transition: "width .1s linear, background .3s",
            }}
          />
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
              ["대상", `${warning.who} (${warning.device})`],
              ["경고 시작", warning.since],
              ...(warning.count > 1
                ? ([["동시 경고", `${warning.count}대 (가장 급한 장치 표시)`]] as const)
                : []),
            ] as const
          ).map(([label, value]) => (
            <div
              key={label}
              style={{ display: "flex", alignItems: "center", width: "100%" }}
            >
              <span style={{ fontSize: 13, color: "var(--text-3)" }}>{label}</span>
              <span
                style={{
                  marginLeft: "auto",
                  fontFamily: "var(--font-mono)",
                  fontSize: 14,
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
            minHeight: 64,
            fontSize: 20,
            background: color,
            color: urgent ? "#fff" : "#1a1208",
            fontWeight: 700,
            borderRadius: 12,
            boxShadow: `0 0 20px 0 ${glow}59`,
            transition: "background .3s",
          }}
        >
          이상 없음 — 경고 끄기
        </button>
      </div>

      <div style={{ fontSize: 13, color: "var(--text-3)" }}>
        화면 아무 곳이나 터치하면 경고가 꺼지고 정상 운용이 유지됩니다 · 신호가 돌아오면 자동 해제
      </div>
    </div>
  );
}
