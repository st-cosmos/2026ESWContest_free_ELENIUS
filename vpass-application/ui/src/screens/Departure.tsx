// 출항: 실시간 얼굴 인식 승선 처리 + 승선 현황 + 시동 잠금 상태

import { KeyRound, Lock, ScanFace, ShieldAlert } from "lucide-react";
import { useEffect } from "react";
import { api } from "../api";
import type { AppState } from "../types";

export function Departure({ state }: { state: AppState }) {
  // 화면 진입 시 얼굴 인식 모드, 이탈 시 대기 모드
  useEffect(() => {
    api.setCameraMode("scan").catch(() => {});
    return () => {
      api.setCameraMode("idle").catch(() => {});
    };
  }, []);

  const overlay = state.overlay;
  const session = state.boarding.session;
  const engine = state.engine;
  const unlocked = !engine.locked && !engine.killed;

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">출항 · 승선 얼굴 인식</h1>
          <p className="page-desc">
            등록된 선원의 얼굴을 인식하면 승선 처리되고 시동 잠금이 해제됩니다.
          </p>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, flex: 1, minHeight: 0, width: "100%" }}>
        {/* 실시간 카메라 */}
        <section
          className="panel"
          style={{
            flex: 1,
            minWidth: 0,
            display: "flex",
            flexDirection: "column",
            gap: 12,
            padding: 16,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h2 className="panel-title">실시간 얼굴 인식</h2>
            <div style={{ flex: 1 }} />
            <div className="badge danger">
              <span className="dot pulse" />
              <span
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 10,
                  letterSpacing: 1,
                }}
              >
                LIVE
              </span>
            </div>
          </div>

          <div
            style={{
              position: "relative",
              flex: 1,
              minHeight: 0,
              background: "var(--cam-bg)",
              borderRadius: 8,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "space-between",
              padding: 18,
            }}
          >
            <img
              src="/api/video_feed"
              alt="실시간 카메라"
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "contain",
              }}
            />
            {/* 오버레이 메시지 */}
            <div style={{ position: "relative", minHeight: 41 }}>
              {overlay.text && (
                <div
                  className="fade-in-up"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    padding: "10px 20px",
                    background: "#0a0b0ee0",
                    border: `1px solid ${overlay.color}3d`,
                    borderRadius: 999,
                  }}
                >
                  <ScanFace size={16} color={overlay.color} />
                  <span
                    style={{ fontSize: 13, fontWeight: 700, color: overlay.color }}
                  >
                    {overlay.text}
                  </span>
                </div>
              )}
            </div>

            {/* 얼굴 가이드 */}
            <div
              style={{
                position: "relative",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 12,
                pointerEvents: "none",
              }}
            >
              <div
                style={{
                  width: 180,
                  height: 220,
                  border: "2px solid var(--accent)",
                  borderRadius: "50%",
                  opacity: 0.85,
                }}
              />
              <span style={{ fontSize: 12, color: "var(--text-2)" }}>
                얼굴을 안내선 안에 맞춰 주세요
              </span>
            </div>

            <span
              style={{ position: "relative", fontSize: 11, color: "var(--text-3)" }}
            >
              얼굴 영역만 인식합니다 · 미등록 선원은 등록 사용자 목록에서 등록을
              진행하세요
            </span>
          </div>
        </section>

        {/* 우측: 승선 현황 + 시동 상태 */}
        <div
          style={{
            width: 350,
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          <section
            className="panel"
            style={{
              flex: 1,
              minHeight: 0,
              display: "flex",
              flexDirection: "column",
              gap: 12,
              padding: 16,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <h2 className="panel-title">실시간 승선 완료 인원</h2>
              <div style={{ flex: 1 }} />
              <span
                style={{
                  padding: "3px 9px",
                  background: "var(--accent-soft)",
                  borderRadius: 6,
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  fontWeight: 700,
                  color: "var(--accent)",
                }}
              >
                {session.length}
              </span>
            </div>

            <div
              style={{
                flex: 1,
                minHeight: 0,
                display: "flex",
                flexDirection: "column",
                gap: 8,
                padding: 10,
                background: "var(--deep)",
                borderRadius: 8,
                overflowY: "auto",
              }}
            >
              {session.length === 0 && (
                <div
                  style={{
                    flex: 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 12,
                    color: "var(--text-3)",
                  }}
                >
                  아직 승선한 선원이 없습니다
                </div>
              )}
              {session.map((entry) => (
                <div
                  key={entry.user_id}
                  className="cell fade-in-up"
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    padding: "10px 12px",
                    borderRadius: 10,
                    flexShrink: 0,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center" }}>
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 700,
                        color: "var(--accent)",
                      }}
                    >
                      {entry.name}
                    </span>
                    <span
                      style={{
                        marginLeft: "auto",
                        fontFamily: "var(--font-mono)",
                        fontSize: 11,
                        color: "var(--text-3)",
                      }}
                    >
                      {entry.time}
                    </span>
                  </div>
                  <span style={{ fontSize: 11, color: "var(--text-2)" }}>
                    얼굴 인식 완료 · 승선 처리됨
                    {entry.lifejacket ? " · 구명조끼 착용" : ""}
                  </span>
                </div>
              ))}
            </div>
          </section>

          {/* 시동 잠금 상태 */}
          <section
            className="panel"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: 16,
              borderColor: engine.killed
                ? "var(--red-border)"
                : unlocked
                  ? "var(--accent-border)"
                  : "var(--border)",
              flexShrink: 0,
            }}
          >
            <div
              style={{
                width: 40,
                height: 40,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: engine.killed
                  ? "var(--red-soft)"
                  : unlocked
                    ? "var(--accent-soft)"
                    : "var(--panel-2)",
                borderRadius: 10,
                color: engine.killed
                  ? "var(--red)"
                  : unlocked
                    ? "var(--accent)"
                    : "var(--text-3)",
                flexShrink: 0,
              }}
            >
              {engine.killed ? (
                <ShieldAlert size={20} />
              ) : unlocked ? (
                <KeyRound size={20} />
              ) : (
                <Lock size={20} />
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ fontSize: 14, fontWeight: 700 }}>
                {engine.killed
                  ? "엔진 비상 정지됨"
                  : unlocked
                    ? "시동 잠금 해제됨"
                    : "시동 잠금 중"}
              </span>
              <span style={{ fontSize: 11, color: "var(--text-2)" }}>
                {engine.killed
                  ? (engine.kill_reason ?? "킬 스위치 작동")
                  : unlocked
                    ? "등록 선원 얼굴 인식 완료"
                    : "선원 얼굴 인식 시 자동 해제됩니다"}
              </span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
