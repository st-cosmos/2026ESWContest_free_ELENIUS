// 출항 기록지: 자동 출입항 시간 + 날짜별 승선 로그

import {
  Anchor,
  Archive,
  CalendarDays,
  Ship,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { AppState, BoardingLogsResponse } from "../types";

function StatCard({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div
      className="panel"
      style={{ flex: 1, display: "flex", alignItems: "center", gap: 12, padding: 16 }}
    >
      <div
        style={{
          width: 36,
          height: 36,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--panel-2)",
          borderRadius: 10,
          color: "var(--text-2)",
          flexShrink: 0,
        }}
      >
        <Icon size={18} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
        <span style={{ fontSize: 11, color: "var(--text-3)" }}>{label}</span>
        <span
          style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600 }}
        >
          {value}
        </span>
      </div>
    </div>
  );
}

export function BoardingLog({ state }: { state: AppState }) {
  const [logs, setLogs] = useState<BoardingLogsResponse | null>(null);

  useEffect(() => {
    api.boardingLogs().then(setLogs).catch(() => {});
  }, [state.boarding.count, state.voyage.active]);

  const latest = logs?.latest_voyage ?? null;
  const days = logs?.days ?? [];
  const todayCount = days[0]?.entries.length ?? 0;

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">출항 기록지</h1>
          <p className="page-desc">
            승선 완료된 선원 로그와 선박 자동 출입항 기록입니다.
          </p>
        </div>
        <div className="chip neutral">
          <Archive size={14} />
          <span>로그 보관 기간 1년</span>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, width: "100%", flexShrink: 0 }}>
        <StatCard
          icon={Ship}
          label="자동 출항 시간"
          value={latest?.departed_at ?? "기록 없음"}
        />
        <StatCard
          icon={Anchor}
          label="자동 입항 시간"
          value={
            latest ? (latest.arrived_at ?? "운항 중") : "기록 없음"
          }
        />
        <StatCard icon={Users} label="총 승선 인원" value={`${todayCount}명`} />
      </div>

      <section
        className="panel"
        style={{
          flex: 1,
          minHeight: 0,
          width: "100%",
          display: "flex",
          flexDirection: "column",
          gap: 12,
          padding: 18,
        }}
      >
        <h2 className="panel-title">승조원 승선 로그</h2>

        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: 14,
          }}
        >
          {days.length === 0 && (
            <div
              style={{
                flex: 1,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--text-3)",
                fontSize: 12,
              }}
            >
              아직 승선 기록이 없습니다 · 출항 화면에서 얼굴 인식을 진행해 주세요
            </div>
          )}

          {days.map((day) => (
            <div
              key={day.date}
              style={{ display: "flex", flexDirection: "column", gap: 8 }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <CalendarDays size={14} color="var(--accent)" />
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    fontWeight: 700,
                    color: "var(--accent)",
                  }}
                >
                  {day.date}
                </span>
              </div>

              <div className="table-box" style={{ overflow: "visible" }}>
                <div className="table-header">
                  <span style={{ width: 60 }}>No.</span>
                  <span style={{ flex: 1 }}>이름</span>
                  <span style={{ flex: 1 }}>전화번호</span>
                  <span style={{ width: 180, textAlign: "right" }}>승선 시간</span>
                </div>
                {day.entries.map((entry, i) => (
                  <div className="table-row" key={`${entry.name}-${entry.time}-${i}`}>
                    <span
                      style={{
                        width: 60,
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                        color: "var(--text-3)",
                      }}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span style={{ flex: 1, fontSize: 13, fontWeight: 700 }}>
                      {entry.name}
                    </span>
                    <span
                      style={{
                        flex: 1,
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                        color: "var(--text-2)",
                      }}
                    >
                      {entry.phone}
                    </span>
                    <span
                      style={{
                        width: 180,
                        textAlign: "right",
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                        fontWeight: 600,
                        color: "var(--accent)",
                      }}
                    >
                      {entry.time}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
