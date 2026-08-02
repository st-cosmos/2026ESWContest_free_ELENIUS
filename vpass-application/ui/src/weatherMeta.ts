// 기상 상태별 아이콘/색상 매핑 (데모 관제 서버 UI 와 동일한 기준)

import {
  Cloud,
  CloudFog,
  CloudLightning,
  CloudRain,
  CloudSun,
  Sun,
  type LucideIcon,
} from "lucide-react";

export const WEATHER_ICON: Record<string, LucideIcon> = {
  맑음: Sun,
  구름조금: CloudSun,
  흐림: Cloud,
  비: CloudRain,
  안개: CloudFog,
  뇌우: CloudLightning,
};

export const WEATHER_COLOR: Record<string, string> = {
  맑음: "var(--orange)",
  구름조금: "var(--text-2)",
  흐림: "var(--text-2)",
  비: "var(--cyan)",
  안개: "var(--text-3)",
  뇌우: "var(--red)",
};

export function weatherIcon(condition: string): LucideIcon {
  return WEATHER_ICON[condition] ?? Cloud;
}

export function weatherColor(condition: string): string {
  return WEATHER_COLOR[condition] ?? "var(--text-2)";
}
