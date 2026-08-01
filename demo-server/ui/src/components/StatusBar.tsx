// 상단 상태바: 로고 · 관제 시각 · 연결 상태 · 테마 토글

import { Moon, Radar, Sun } from "lucide-react";
import { useAppState } from "../state";

export function StatusBar({ time }: { time: string }) {
  const { connected, theme, toggleTheme } = useAppState();

  return (
    <div className="statusbar">
      <div className="logo-area">
        <div className="logo-tile">
          <Radar size={22} />
        </div>
        <div>
          <div className="logo-title">V-PASS 관제센터</div>
          <div className="logo-sub">해양경찰 통합 관제 시스템</div>
        </div>
      </div>

      <div className="spacer" />

      <div className="clock">
        <span className="clock-label">관제 시각</span>
        <span className="clock-value">{time}</span>
      </div>

      <div className="sb-divider" />

      <div className="conn-chip">
        <span className={`glow-dot${connected ? "" : " off"}`} />
        {connected ? "실시간 연결" : "연결 끊김"}
      </div>

      <button className="icon-btn" onClick={toggleTheme} title="테마 전환">
        {theme === "dark" ? <Moon size={18} /> : <Sun size={18} />}
      </button>
    </div>
  );
}
