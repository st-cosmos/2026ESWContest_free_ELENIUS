// 출항: 얼굴 인식으로 승선 목록을 만들고, 확인 후 시동을 허용한다.
// 출항/입항 신고는 이 화면에서 하지 않는다 — 관제 서버의 지오펜스 통과 판정으로
// 자동 등록된다(지오펜스를 쓰지 않는 환경을 위해 수동 신고 버튼만 남겨 둔다).

import {
  Anchor,
  KeyRound,
  Lock,
  Radar,
  ScanFace,
  ShieldAlert,
  ShieldCheck,
  Ship,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppState, CrewEntry } from "../types";

// 구명조끼 확인 출처(모듈/카메라) 라벨 — 없으면 빈 문자열
function jacketLabel(entry: CrewEntry): string {
  const sources = [entry.lifejacket && "모듈", entry.jacket_visual && "카메라"]
    .filter(Boolean)
    .join("·");
  return sources ? ` · 구명조끼 확인(${sources})` : "";
}

function CrewRow({ entry }: { entry: CrewEntry }) {
  return (
    <div
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
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--accent)" }}>
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
        얼굴 인식 완료 · 승선 확인
        {jacketLabel(entry)}
      </span>
    </div>
  );
}

function EngineAllowConfirm({
  crew,
  onClose,
}: {
  crew: CrewEntry[];
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wearing = crew.filter((c) => c.lifejacket || c.jacket_visual).length;

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.allowEngineStart();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "시동 허용에 실패했습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal fade-in-up">
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 18, fontWeight: 700 }}>승선 확인 · 시동 허용</span>
            <span style={{ fontSize: 12, color: "var(--text-2)" }}>
              아래 승선 인원을 확인하고 시동을 허용합니다.
            </span>
          </div>
          <button onClick={onClose} style={{ color: "var(--text-3)" }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", width: "100%" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-2)" }}>
            승선 인원
          </span>
          <span
            style={{
              marginLeft: "auto",
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              fontWeight: 600,
              color: "var(--accent)",
            }}
          >
            {crew.length}명 · 구명조끼 확인 {wearing}명
          </span>
        </div>

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 8,
            padding: 10,
            background: "var(--deep)",
            borderRadius: 8,
            maxHeight: 220,
            overflowY: "auto",
          }}
        >
          {crew.map((c) => (
            <div
              key={c.user_id}
              className="cell"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "10px 12px",
                borderRadius: 10,
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 700, color: "var(--accent)" }}>
                {c.name}
              </span>
              <span
                className={`badge ${c.lifejacket || c.jacket_visual ? "accent" : "muted"}`}
              >
                <span className="dot" />
                {c.lifejacket
                  ? "구명조끼 착용"
                  : c.jacket_visual
                    ? "구명조끼 확인(카메라)"
                    : "장치 미배정"}
              </span>
              <span style={{ flex: 1 }} />
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  color: "var(--text-3)",
                }}
              >
                {c.time}
              </span>
            </div>
          ))}
        </div>

        <div className="chip accent" style={{ width: "100%", whiteSpace: "normal" }}>
          <ShieldCheck size={16} />
          <span>
            허용 시 시동 잠금만 해제됩니다 · 출항 신고는 지오펜스를 넘어가는 시점에
            자동 접수됩니다
          </span>
        </div>

        {error && (
          <div className="chip danger" style={{ width: "100%", whiteSpace: "normal" }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10 }}>
          <button
            className="btn btn-primary"
            style={{ flex: 1 }}
            onClick={confirm}
            disabled={busy}
          >
            {busy ? "처리 중…" : "시동 허용"}
          </button>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            취소
          </button>
        </div>
      </div>
    </div>
  );
}

function ArrivalConfirm({ onClose }: { onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.confirmArrival();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "입항 확정에 실패했습니다.");
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal fade-in-up" style={{ width: 400 }}>
        <span style={{ fontSize: 18, fontWeight: 700 }}>수동 입항 신고</span>
        <span style={{ fontSize: 13, color: "var(--text-2)" }}>
          보통은 지오펜스 안으로 들어오면 자동으로 입항 처리됩니다. 지금 바로
          운항을 종료하려면 확정하세요. 시동이 다시 잠기고 승선 목록이 초기화됩니다.
        </span>

        {error && (
          <div className="chip danger" style={{ width: "100%", whiteSpace: "normal" }}>
            {error}
          </div>
        )}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-secondary" onClick={onClose} disabled={busy}>
            취소
          </button>
          <button className="btn btn-primary" onClick={confirm} disabled={busy}>
            {busy ? "확정 중…" : "입항 확정"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function Departure({ state }: { state: AppState }) {
  const [confirming, setConfirming] = useState<"allow" | "arrive" | null>(null);
  const [manualBusy, setManualBusy] = useState(false);

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
  const sailing = state.voyage.active;

  const cardState = engine.killed
    ? "killed"
    : sailing
      ? "sailing"
      : engine.locked
        ? "locked"
        : "ready";

  const manualDeparture = async () => {
    setManualBusy(true);
    try {
      await api.confirmDeparture();
    } catch {
      /* 상태 카드에 그대로 반영된다 */
    } finally {
      setManualBusy(false);
    }
  };

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">출항 · 승선 얼굴 인식</h1>
          <p className="page-desc">
            선원 얼굴을 인식해 승선 목록을 만든 뒤 시동 허용 버튼을 눌러야 시동
            잠금이 해제됩니다. 출항·입항 신고는 지오펜스 통과 시 자동 접수됩니다.
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
              justifyContent: "flex-start",
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

            {/* 얼굴 안내선 — 상체가 함께 나오도록 화면 위쪽에 배치 */}
            <div
              style={{
                position: "relative",
                marginTop: 6,
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
                구명조끼를 착용하고 얼굴을 안내선 안에 맞춰 주세요
              </span>
            </div>

            <span
              style={{
                position: "relative",
                marginTop: "auto",
                fontSize: 11,
                color: "var(--text-3)",
              }}
            >
              얼굴 인식과 구명조끼 착용을 함께 확인합니다 · 승선이 끝나면 우측에서 출항을
              확정하세요
            </span>
          </div>
        </section>

        {/* 우측: 승선 목록 + 출항 확정 */}
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
              <h2 className="panel-title">승선 인식 인원</h2>
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
                <CrewRow key={entry.user_id} entry={entry} />
              ))}
            </div>
          </section>

          {/* 시동 허용 / 운항 상태 */}
          <section
            className="panel"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 12,
              padding: 16,
              borderColor:
                cardState === "killed"
                  ? "var(--red-border)"
                  : cardState === "locked"
                    ? "var(--border)"
                    : "var(--accent-border)",
              flexShrink: 0,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  background:
                    cardState === "killed"
                      ? "var(--red-soft)"
                      : cardState === "locked"
                        ? "var(--panel-2)"
                        : "var(--accent-soft)",
                  borderRadius: 10,
                  color:
                    cardState === "killed"
                      ? "var(--red)"
                      : cardState === "locked"
                        ? "var(--text-3)"
                        : "var(--accent)",
                  flexShrink: 0,
                }}
              >
                {cardState === "killed" ? (
                  <ShieldAlert size={20} />
                ) : cardState === "sailing" ? (
                  <Ship size={20} />
                ) : cardState === "ready" ? (
                  <KeyRound size={20} />
                ) : (
                  <Lock size={20} />
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ fontSize: 14, fontWeight: 700 }}>
                  {cardState === "killed"
                    ? "엔진 비상 정지됨"
                    : cardState === "sailing"
                      ? "운항 중"
                      : cardState === "ready"
                        ? "시동 허용됨 · 출항 대기"
                        : "시동 잠금 중"}
                </span>
                <span style={{ fontSize: 11, color: "var(--text-2)" }}>
                  {cardState === "killed"
                    ? (engine.kill_reason ?? "킬 스위치 작동")
                    : cardState === "sailing"
                      ? `${state.voyage.departed_at?.split(" ")[1] ?? ""} 출항 · 지오펜스 자동 등록`
                      : cardState === "ready"
                        ? "승선 확인 완료 · 이제 시동을 켤 수 있습니다"
                        : "승선 인원 확인 후 시동을 허용하세요"}
                </span>
              </div>
            </div>

            {cardState === "locked" && (
              <>
                <button
                  className="btn btn-primary"
                  style={{ width: "100%" }}
                  onClick={() => setConfirming("allow")}
                  disabled={session.length === 0}
                >
                  승선 확인 · 시동 허용
                </button>
                <span style={{ fontSize: 10, color: "var(--text-3)" }}>
                  시동 잠금만 해제됩니다 · 출항 신고는 지오펜스 통과 시 자동 접수
                </span>
              </>
            )}

            {cardState === "ready" && (
              <>
                <div
                  className="chip accent"
                  style={{ width: "100%", whiteSpace: "normal" }}
                >
                  <Radar size={15} />
                  <span>지오펜스를 넘어 바다로 나가면 자동으로 출항 신고됩니다</span>
                </div>
                <button
                  className="btn btn-secondary"
                  style={{ width: "100%" }}
                  onClick={manualDeparture}
                  disabled={manualBusy}
                >
                  <Anchor size={15} />
                  {manualBusy ? "신고 중…" : "수동 출항 신고"}
                </button>
                <span style={{ fontSize: 10, color: "var(--text-3)" }}>
                  지오펜스를 사용하지 않을 때만 사용하세요
                </span>
              </>
            )}

            {cardState === "sailing" && (
              <>
                <button
                  className="btn btn-secondary"
                  style={{ width: "100%" }}
                  onClick={() => setConfirming("arrive")}
                >
                  <Anchor size={15} />
                  수동 입항 신고
                </button>
                <span style={{ fontSize: 10, color: "var(--text-3)" }}>
                  지오펜스 안으로 들어오면 자동으로 입항 처리됩니다
                </span>
              </>
            )}
          </section>
        </div>
      </div>

      {confirming === "allow" && (
        <EngineAllowConfirm crew={session} onClose={() => setConfirming(null)} />
      )}
      {confirming === "arrive" && (
        <ArrivalConfirm onClose={() => setConfirming(null)} />
      )}
    </div>
  );
}
