// 앱 루트: 셋업 게이트 + 셸(상태바/사이드바) + 화면 전환 + SOS/구명조끼 경고 모달

import { useState } from "react";
import { JacketAlertModal } from "./components/JacketAlertModal";
import { JacketBattModal } from "./components/JacketBattModal";
import { NAV_ITEMS, Sidebar, type ScreenKey } from "./components/Sidebar";
import { SosModal } from "./components/SosModal";
import { StatusBar } from "./components/StatusBar";
import { Departure } from "./screens/Departure";
import { Home } from "./screens/Home";
import { Lifejacket } from "./screens/Lifejacket";
import { Setup } from "./screens/Setup";
import { UsersScreen } from "./screens/Users";
import { VesselInfo } from "./screens/VesselInfo";
import { VoyageRecord } from "./screens/VoyageRecord";
import { useAppState } from "./state";
import { useSoundEffects } from "./useSoundEffects";

function initialScreen(): ScreenKey {
  // ?screen=departure 형태로 초기 화면 지정 가능 (개발/키오스크용)
  const q = new URLSearchParams(window.location.search).get("screen");
  return NAV_ITEMS.some((n) => n.key === q) ? (q as ScreenKey) : "home";
}

export default function App() {
  const { state, connected, refresh } = useAppState();
  const [screen, setScreen] = useState<ScreenKey>(initialScreen);
  const [setupDone, setSetupDone] = useState(false);
  useSoundEffects(state, connected);

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
        {screen === "voyage-record" && <VoyageRecord state={state} />}
        {screen === "users" && <UsersScreen />}
        {screen === "lifejacket" && <Lifejacket state={state} />}
        {screen === "vessel-info" && <VesselInfo state={state} />}
      </div>

      {/* SOS 모달이 경고들보다 위에 오도록 나중에 렌더링.
          배터리 경고는 해제 경고와 겹치지 않게 해제 경고가 없을 때만 표시 */}
      {!state.lifejacket.doff_alert && state.lifejacket.batt_alert && (
        <JacketBattModal alert={state.lifejacket.batt_alert} />
      )}
      {state.lifejacket.doff_alert && (
        <JacketAlertModal alert={state.lifejacket.doff_alert} />
      )}
      {state.sos && <SosModal report={state.sos} />}
    </div>
  );
}
