// 좌측 사이드바: 로고 + 내비게이션 + 시스템 상태

import {
  ClipboardList,
  House,
  Info,
  LifeBuoy,
  Ship,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useAppState } from "../state";

export type ScreenKey =
  | "home"
  | "departure"
  | "voyage-record"
  | "users"
  | "lifejacket"
  | "vessel-info";

export const NAV_ITEMS: { key: ScreenKey; label: string; icon: LucideIcon }[] = [
  { key: "home", label: "홈", icon: House },
  { key: "departure", label: "출항", icon: Ship },
  { key: "voyage-record", label: "운항 기록지", icon: ClipboardList },
  { key: "users", label: "등록 사용자 목록", icon: Users },
  { key: "lifejacket", label: "구명조끼 모니터", icon: LifeBuoy },
  { key: "vessel-info", label: "어선 정보", icon: Info },
];

export function Sidebar({
  active,
  onNavigate,
}: {
  active: ScreenKey;
  onNavigate: (key: ScreenKey) => void;
}) {
  const { state, connected } = useAppState();
  const alarm = state?.lifejacket.mob_alarm ?? false;

  return (
    <aside className="sidebar">
      <div className="logo-area">
        <div className="logo-tile">
          <Ship size={20} />
        </div>
        <div>
          <div className="logo-title">Smart V-PASS</div>
          <div className="logo-subtitle">어선 안전 관리 시스템</div>
        </div>
      </div>

      <nav className="nav-menu">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            className={`nav-item${active === key ? " active" : ""}`}
            onClick={() => onNavigate(key)}
          >
            <Icon size={18} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span
          className={`glow-dot${connected && !alarm ? "" : " off"}${alarm ? " pulse" : ""}`}
        />
        <span>
          {!connected
            ? "서버 연결 대기 중"
            : alarm
              ? "익수 감지 — 비상 상황"
              : "시스템 정상 작동 중"}
        </span>
      </div>
    </aside>
  );
}
