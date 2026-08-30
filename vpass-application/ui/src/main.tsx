import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// 오프라인(선상) 환경을 위해 폰트를 로컬 번들로 포함
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
import App from "./App";
import { VirtualKeyboard } from "./components/VirtualKeyboard";
import { AppStateProvider } from "./state";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppStateProvider>
      <App />
      {/* 터치 키오스크용 가상 키보드 — 셋업 화면에서도 쓰이므로 App 밖에 둔다 */}
      <VirtualKeyboard />
    </AppStateProvider>
  </StrictMode>,
);
