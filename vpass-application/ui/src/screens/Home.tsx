// 홈: 인사말 + 해상 기상 + 일출·일몰/물때 + 요약 카드

import {
  ChevronRight,
  Droplets,
  Eye,
  Gauge,
  LifeBuoy,
  Lock,
  LockOpen,
  Route,
  ShieldCheck,
  Sunrise,
  Sunset,
  Thermometer,
  Users,
  Waves,
  Wind,
  type LucideIcon,
} from "lucide-react";
import type { AppState } from "../types";
import { weatherColor, weatherIcon } from "../weatherMeta";

const DAYS = ["일", "월", "화", "수", "목", "금", "토"];

function todayLabel(): string {
  const d = new Date();
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 ${DAYS[d.getDay()]}요일`;
}

function WeatherCell({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div
      className="cell"
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 12px",
      }}
    >
      <Icon size={18} color="var(--text-3)" />
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: 12, color: "var(--text-3)" }}>{label}</span>
        <span
          style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 600 }}
        >
          {value}
        </span>
      </div>
    </div>
  );
}

function SideRow({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
}) {
  return (
    <div
      className="cell"
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 12px",
      }}
    >
      <Icon size={16} color="var(--text-3)" />
      <span style={{ fontSize: 14, color: "var(--text-2)" }}>{label}</span>
      <span
        style={{
          marginLeft: "auto",
          fontFamily: "var(--font-mono)",
          fontSize: 15,
          fontWeight: 600,
        }}
      >
        {value}
      </span>
    </div>
  );
}

function QuickCard({
  icon: Icon,
  label,
  value,
  valueColor,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  valueColor?: string;
  onClick?: () => void;
}) {
  return (
    <button
      className="panel"
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: 14,
        textAlign: "left",
      }}
      onClick={onClick}
    >
      <div
        style={{
          width: 36,
          height: 36,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--panel-2)",
          borderRadius: 10,
          color: "var(--text-2)",
          flexShrink: 0,
        }}
      >
        <Icon size={18} />
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: 13, color: "var(--text-3)" }}>{label}</span>
        <span style={{ fontSize: 17, fontWeight: 700, color: valueColor }}>
          {value}
        </span>
      </div>
      <ChevronRight size={16} color="var(--text-3)" />
    </button>
  );
}

export function Home({
  state,
  onNavigate,
}: {
  state: AppState;
  onNavigate: (key: "departure" | "lifejacket" | "voyage-record") => void;
}) {
  const w = state.weather;
  const vesselName = state.vessel?.name ?? "선장님";
  const engine = state.engine;
  // 기상 상태(관제 서버에서 변경 가능)에 따라 아이콘/색상도 함께 바뀐다
  const ConditionIcon = weatherIcon(w.condition);

  return (
    <div className="content">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="page-title">안녕하세요, {vesselName}</h1>
          <p className="page-desc">
            {todayLabel()} · {state.vessel?.home_port ?? "-"} · {w.source}{" "}
            {w.updated_at} 갱신
          </p>
        </div>
        {w.advisory ? (
          <div className="chip danger">
            <ShieldCheck size={14} />
            <span>{w.advisory}</span>
          </div>
        ) : (
          <div className="chip accent">
            <ShieldCheck size={14} />
            <span>현재 발효 중인 해상 특보 없음</span>
          </div>
        )}
      </div>

      <div style={{ display: "flex", gap: 16, flex: 1, minHeight: 0, width: "100%" }}>
        {/* 현재 해상 기상 */}
        <section
          className="panel"
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 16,
            padding: 20,
          }}
        >
          <h2 className="panel-title">현재 해상 기상</h2>
          <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
            <div
              style={{
                width: 84,
                height: 84,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "var(--panel-2)",
                borderRadius: 42,
                color: weatherColor(w.condition),
              }}
            >
              <ConditionIcon size={40} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
                <span
                  style={{
                    fontFamily: "var(--font-display)",
                    fontSize: 46,
                    fontWeight: 600,
                    letterSpacing: -1,
                    lineHeight: 1,
                  }}
                >
                  {w.temp_c}°C
                </span>
                <span
                  style={{ fontSize: 18, fontWeight: 600, color: "var(--text-2)" }}
                >
                  {w.condition}
                </span>
              </div>
              <span style={{ fontSize: 14, color: "var(--text-3)" }}>
                체감 {w.feels_like_c}°C · 강수확률 {w.precip_prob}%
              </span>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", gap: 10 }}>
              <WeatherCell icon={Wind} label="풍향 / 풍속" value={w.wind} />
              <WeatherCell icon={Waves} label="파고" value={`${w.wave_height_m} m`} />
              <WeatherCell
                icon={Thermometer}
                label="수온"
                value={`${w.water_temp_c}°C`}
              />
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <WeatherCell icon={Droplets} label="습도" value={`${w.humidity}%`} />
              <WeatherCell icon={Eye} label="시정" value={`${w.visibility_km} km`} />
              <WeatherCell icon={Gauge} label="기압" value={`${w.pressure_hpa} hPa`} />
            </div>
          </div>
        </section>

        {/* 일출·일몰 / 물때 */}
        <section
          className="panel"
          style={{
            width: 330,
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            gap: 10,
            padding: 20,
          }}
        >
          <h2 className="panel-title">일출·일몰 / 물때</h2>
          <SideRow icon={Sunrise} label="일출" value={w.sunrise} />
          <SideRow icon={Sunset} label="일몰" value={w.sunset} />
          <SideRow icon={Waves} label="만조" value={w.high_tide} />
          <SideRow icon={Waves} label="간조" value={w.low_tide} />
        </section>
      </div>

      {/* 요약 카드 */}
      <div style={{ display: "flex", gap: 16, width: "100%", flexShrink: 0 }}>
        <QuickCard
          icon={Users}
          label="승선 인원"
          value={`${state.boarding.count}명`}
          onClick={() => onNavigate("departure")}
        />
        <QuickCard
          icon={LifeBuoy}
          label="구명조끼 착용"
          value={`${state.lifejacket.worn_count}명`}
          onClick={() => onNavigate("lifejacket")}
        />
        <QuickCard
          icon={engine.engaged ? Lock : LockOpen}
          label="시동 잠금"
          value={engine.killed ? "비상 정지" : engine.locked ? "잠김" : "해제"}
          valueColor={
            engine.killed
              ? "var(--red)"
              : engine.locked
                ? undefined
                : "var(--accent)"
          }
          onClick={() => onNavigate("departure")}
        />
        <QuickCard
          icon={Route}
          label="최근 운항"
          value={state.voyage.latest ? state.voyage.latest.date.slice(5) : "기록 없음"}
          onClick={() => onNavigate("voyage-record")}
        />
      </div>
    </div>
  );
}
