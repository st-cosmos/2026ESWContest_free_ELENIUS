// 구명조끼 모니터: 착용/신호/익수 상태 실시간 표시 + 개발용 시뮬레이터

import {
  Activity,
  BatteryFull,
  BatteryWarning,
  BluetoothSearching,
  FlaskConical,
  LifeBuoy,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { useState } from "react";
import { api } from "../api";
import type { AppState, DeviceState } from "../types";

function DeviceCard({ device }: { device: DeviceState }) {
  const status = device.mob
    ? { label: "익수 감지", cls: "danger" as const }
    : device.fall_pending
      ? { label: "낙상 확인 중", cls: "warn" as const }
      : device.worn
        ? { label: "착용 중", cls: "accent" as const }
        : { label: "미착용", cls: "muted" as const };

  return (
    <div
      className="cell"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        padding: 16,
        borderRadius: 10,
        borderColor: device.mob ? "var(--red-border)" : undefined,
        background: device.mob ? "var(--red-soft)" : undefined,
      }}
    >
      <div
        style={{
          width: 46,
          height: 46,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: device.mob ? "var(--red-soft)" : "var(--panel-2)",
          borderRadius: 12,
          color: device.mob
            ? "var(--red)"
            : device.worn
              ? "var(--accent)"
              : "var(--text-3)",
          flexShrink: 0,
        }}
      >
        <LifeBuoy size={22} className={device.mob ? "pulse" : undefined} />
      </div>

      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 17, fontWeight: 700 }}>
            {device.user_name ?? "미배정 장치"}
          </span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              color: "var(--text-3)",
            }}
          >
            {device.device}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 5,
              fontSize: 13,
              color: device.signal_ok ? "var(--text-2)" : "var(--red)",
            }}
          >
            <Activity size={12} />
            {device.signal_ok
              ? `신호 정상 · 마지막 수신 ${device.last_ping}`
              : device.seconds_since_ping !== null
                ? `신호 두절 ${device.seconds_since_ping.toFixed(0)}초`
                : "신호 없음"}
          </span>
          {device.battery_mv !== null && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 5,
                fontSize: 11,
                fontWeight: device.battery_low ? 700 : 400,
                color: device.battery_low ? "var(--orange)" : "var(--text-2)",
              }}
            >
              {device.battery_low ? (
                <BatteryWarning size={13} />
              ) : (
                <BatteryFull size={13} />
              )}
              {(device.battery_mv / 1000).toFixed(2)}V
              {device.battery_low ? " · 교체 필요" : ""}
            </span>
          )}
          {device.last_fall !== "-" && (
            <span style={{ fontSize: 13, color: "var(--orange)" }}>
              낙상 {device.last_fall}
              {device.fall_magnitude ? ` (${device.fall_magnitude}g)` : ""}
            </span>
          )}
          {device.mob && device.mob_at && (
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--red)" }}>
              익수 판정 {device.mob_at} ·{" "}
              {device.mob_cause === "fall" ? "낙상 후 신호 두절" : "무선 신호 두절"}
            </span>
          )}
        </div>
      </div>

      <span className={`badge ${status.cls}`}>
        <span className={`dot${device.mob ? " pulse" : ""}`} />
        {status.label}
      </span>
    </div>
  );
}

// 하드웨어 없이 시연할 수 있는 가상 구명조끼 조작 패널
function SimPanel() {
  const [device, setDevice] = useState("jacket-1");
  const [error, setError] = useState<string | null>(null);

  const act = async (action: string) => {
    setError(null);
    try {
      await api.devJacket(device.trim() || "jacket-1", action);
    } catch (e) {
      setError(e instanceof Error ? e.message : "요청 실패");
    }
  };

  const buttons: { label: string; action: string; danger?: boolean }[] = [
    { label: "착용", action: "wear" },
    { label: "탈의", action: "doff" },
    { label: "낙상(복귀)", action: "fall" },
    { label: "익수(낙상+두절)", action: "overboard", danger: true },
    { label: "신호 두절", action: "silence", danger: true },
    { label: "신호 재개", action: "resume" },
    { label: "배터리 부족", action: "lowbatt" },
    { label: "배터리 정상", action: "battok" },
  ];

  return (
    <div
      style={{
        width: "100%",
        display: "flex",
        flexDirection: "column",
        gap: 8,
        padding: "12px 14px",
        background: "var(--panel-2)",
        border: "1px solid var(--border-subtle)",
        borderRadius: 8,
        flexShrink: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <FlaskConical size={14} color="var(--text-2)" />
        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-2)" }}>
          장치 시뮬레이터 (개발·시연용) — 실제 ESP8266 장치와 동일한 신호 경로
        </span>
      </div>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <div
          className="field-box mono"
          style={{ width: 130, padding: "8px 12px", borderRadius: 8 }}
        >
          <input
            value={device}
            onChange={(e) => setDevice(e.target.value)}
            style={{ fontSize: 14 }}
          />
        </div>
        {buttons.map((b) => (
          <button
            key={b.action}
            className={`btn btn-sm ${b.danger ? "btn-danger" : "btn-secondary"}`}
            onClick={() => act(b.action)}
          >
            {b.label}
          </button>
        ))}
        {error && (
          <span style={{ fontSize: 13, color: "var(--red)" }}>{error}</span>
        )}
      </div>
    </div>
  );
}

export function Lifejacket({ state }: { state: AppState }) {
  const devices = state.lifejacket.devices;
  const mob = state.lifejacket.mob_alarm;

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">구명조끼 모니터</h1>
          <p className="page-desc">구명조끼 착용이 인식된 선원 목록이 표시됩니다.</p>
        </div>
      </div>

      <div
        className={`chip ${mob ? "danger" : "accent"}`}
        style={{ width: "100%", padding: "12px 16px", flexShrink: 0 }}
      >
        {mob ? <ShieldAlert size={16} /> : <ShieldCheck size={16} />}
        <span style={{ color: mob ? "var(--red)" : "var(--text-2)", fontWeight: 400 }}>
          {mob
            ? "익수가 감지되어 킬 스위치가 작동했습니다. SOS 모달에서 상황을 확인해 주세요."
            : "구명조끼 부착 디바이스가 착용 여부와 익수 상태를 실시간으로 감지합니다. 착용이 인식되면 선원이 목록에 자동 추가됩니다."}
        </span>
      </div>

      {devices.length === 0 ? (
        <div
          style={{
            flex: 1,
            width: "100%",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            background: "#ffffff03",
            border: "1px solid var(--border)",
            borderRadius: 10,
          }}
        >
          <div
            style={{
              width: 64,
              height: 64,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--panel)",
              borderRadius: 32,
              color: "var(--text-3)",
            }}
          >
            <BluetoothSearching size={28} />
          </div>
          <span style={{ fontSize: 17, fontWeight: 600 }}>
            착용이 감지된 선원이 없습니다
          </span>
          <span style={{ fontSize: 14, color: "var(--text-3)" }}>
            구명조끼 노드 디바이스가 연결되면 자동으로 표시됩니다
          </span>
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            minHeight: 0,
            width: "100%",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 10,
          }}
        >
          {devices.map((d) => (
            <DeviceCard key={d.device} device={d} />
          ))}
        </div>
      )}

      <SimPanel />
    </div>
  );
}
