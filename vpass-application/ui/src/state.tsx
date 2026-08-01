// 전역 앱 상태: /api/state 1초 폴링

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

interface AppStateCtx {
  state: AppState | null;
  connected: boolean;
  refresh: () => void;
}

const Ctx = createContext<AppStateCtx>({
  state: null,
  connected: false,
  refresh: () => {},
});

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState | null>(null);
  const [connected, setConnected] = useState(false);
  const busy = useRef(false);

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

  return (
    <Ctx.Provider value={{ state, connected, refresh: poll }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAppState = () => useContext(Ctx);
