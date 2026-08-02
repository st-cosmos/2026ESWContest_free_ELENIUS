// 최소 경로 라우팅 — 관제 대시보드(/) 와 운항 시뮬레이터(/simulator) 두 화면만 있다.
// 서버(FastAPI)는 알 수 없는 경로에 index.html 을 돌려주므로 새로고침/직접 진입도 동작한다.

import { useEffect, useState } from "react";

export function usePath(): string {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const sync = () => setPath(window.location.pathname);
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  return path;
}

export function navigate(to: string): void {
  if (window.location.pathname === to) return;
  window.history.pushState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
}
