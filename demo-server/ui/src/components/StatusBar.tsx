// 상단 상태바: 로고 · 페이지 탭 · 관제 시각 · 연결 상태 · 테마 토글

import { LayoutDashboard, LifeBuoy, Moon, Radar, Route, Sun } from "lucide-react";
import { useAppState } from "../state";
import { navigate, usePath } from "../route";

function PageTabs() {
  const path = usePath();
  const sim = path.startsWith("/simulator");
  const boundary = path.startsWith("/boundary/");
  return (
    <div className="page-tabs">
      <button
        className={`page-tab${sim || boundary ? "" : " on"}`}
        onClick={() => navigate("/")}
      >
        <LayoutDashboard size={15} />
        관제 대시보드
      </button>
      <button
        className={`page-tab${sim ? " on" : ""}`}
        onClick={() => navigate("/simulator")}
      >
        <Route size={15} />
        운항 시뮬레이터
      </button>
      {/* 요구조자 예상 위치는 신고 1건에 종속된 화면이라 진입했을 때만 노출한다 */}
      {boundary && (
        <button className="page-tab on danger">
          <LifeBuoy size={15} />
          요구조자 예상 위치
        </button>
      )}
    </div>
  );
}

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

      <PageTabs />

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
