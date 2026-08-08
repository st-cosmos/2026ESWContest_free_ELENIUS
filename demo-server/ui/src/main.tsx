import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// 오프라인 환경을 위해 폰트를 로컬 번들로 포함
import "@fontsource/noto-sans-kr/400.css";
import "@fontsource/noto-sans-kr/500.css";
import "@fontsource/noto-sans-kr/600.css";
import "@fontsource/noto-sans-kr/700.css";
import "@fontsource/outfit/600.css";
import "@fontsource/outfit/700.css";
import "@fontsource/outfit/800.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "@fontsource/jetbrains-mono/700.css";

import "./theme.css";
import "./simulator.css";
import "./boundary.css";
import App from "./App";
import { SimulatorPage } from "./screens/SimulatorPage";
import BoundaryPage from "./screens/BoundaryPage";
import { AppStateProvider } from "./state";
import { usePath } from "./route";

function Root() {
  const path = usePath();
  if (path.startsWith("/simulator")) return <SimulatorPage />;
  // /boundary/{reportId} — 신고 접수 현황에서 선박을 누르면 진입
  if (path.startsWith("/boundary/")) {
    const reportId = path.split("/")[2] ?? "";
    return <BoundaryPage key={reportId} reportId={reportId} />;
  }
  return <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppStateProvider>
      <Root />
    </AppStateProvider>
  </StrictMode>,
);
