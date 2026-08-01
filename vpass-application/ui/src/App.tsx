// 앱 루트: 셋업 게이트 + 셸(상태바/사이드바) + 화면 전환 + SOS 모달

import { useState } from "react";
import { Sidebar, type ScreenKey } from "./components/Sidebar";
import { SosModal } from "./components/SosModal";
import { StatusBar } from "./components/StatusBar";
import { BoardingLog } from "./screens/BoardingLog";
import { Departure } from "./screens/Departure";
import { Home } from "./screens/Home";
import { Lifejacket } from "./screens/Lifejacket";
import { Setup } from "./screens/Setup";
import { UsersScreen } from "./screens/Users";
import { VesselInfo } from "./screens/VesselInfo";
import { VoyageLog } from "./screens/VoyageLog";
import { useAppState } from "./state";

const SCREEN_KEYS: ScreenKey[] = [
  "home",
  "departure",
  "boarding-log",
  "users",
  "lifejacket",
  "vessel-info",
  "voyage-log",
];

function initialScreen(): ScreenKey {
  // ?screen=departure 형태로 초기 화면 지정 가능 (개발/키오스크용)
  const q = new URLSearchParams(window.location.search).get("screen");
  return SCREEN_KEYS.includes(q as ScreenKey) ? (q as ScreenKey) : "home";
}

export default function App() {
  const { state, connected, refresh } = useAppState();
  const [screen, setScreen] = useState<ScreenKey>(initialScreen);
  const [setupDone, setSetupDone] = useState(false);

  if (!state) {
    return (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 12,
          color: "var(--text-3)",
        }}
      >
        <div className="glow-dot pulse" style={{ width: 12, height: 12 }} />
        <span>
          {connected ? "시스템 시작 중…" : "V-PASS 서버에 연결하는 중…"}
        </span>
      </div>
    );
  }

  // 어선 최초 등록 게이트
  if (!state.vessel && !setupDone) {
    return (
      <Setup
        onDone={() => {
          setSetupDone(true);
          refresh();
        }}
      />
    );
  }

  return (
    <div className="app">
      <StatusBar />
      <div className="app-body">
        <Sidebar active={screen} onNavigate={setScreen} />
        {screen === "home" && <Home state={state} onNavigate={setScreen} />}
        {screen === "departure" && <Departure state={state} />}
        {screen === "boarding-log" && <BoardingLog state={state} />}
        {screen === "users" && <UsersScreen />}
        {screen === "lifejacket" && <Lifejacket state={state} />}
        {screen === "vessel-info" && <VesselInfo state={state} />}
        {screen === "voyage-log" && <VoyageLog state={state} />}
      </div>

      {state.sos && <SosModal report={state.sos} />}
    </div>
  );
}
