// 전역 앱 상태: /api/state 1초 폴링 + 라이트/다크 테마 관리

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "./api";
import type { AppState } from "./types";

type Theme = "light" | "dark";

interface AppStateCtx {
  state: AppState | null;
  connected: boolean;
  theme: Theme;
  toggleTheme: () => void;
  refresh: () => void;
}

const Ctx = createContext<AppStateCtx>({
  state: null,
  connected: false,
  theme: "dark",
  toggleTheme: () => {},
  refresh: () => {},
});

function initialTheme(): Theme {
  const saved = localStorage.getItem("demo-theme");
  return saved === "light" ? "light" : "dark";
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState | null>(null);
  const [connected, setConnected] = useState(false);
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const busy = useRef(false);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("demo-theme", theme);
  }, [theme]);

  const poll = async () => {
    if (busy.current) return;
    busy.current = true;
    try {
      const s = await api.state();
      setState(s);
      setConnected(true);
    } catch {
      setConnected(false);
    } finally {
      busy.current = false;
    }
  };

  useEffect(() => {
    poll();
    const t = setInterval(poll, 1000);
    return () => clearInterval(t);
  }, []);

  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  return (
    <Ctx.Provider value={{ state, connected, theme, toggleTheme, refresh: poll }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAppState = () => useContext(Ctx);
