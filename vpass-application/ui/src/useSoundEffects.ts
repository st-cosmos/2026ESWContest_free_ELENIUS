// 상태 폴링(1초) diff 로 이벤트를 감지해 사운드 효과를 트리거한다.
//
// 이벤트 → 사운드 매핑 (public/sounds/README.md 와 동일):
//   승선 인식            → boarding
//   출항 등록(수동/지오펜스) → departure
//   입항 등록(수동/지오펜스) → arrival
//   SOS 발보(자동/수동)   → sos (신고가 떠 있는 동안 루프)
//   기상특보 발효         → warning
//   하드웨어/통신 에러     → error (에러 상태 4초 지속 시 1회, 상태별 재무장)

import { useEffect, useRef } from "react";
import { play, startLoop, stopLoop } from "./sounds";
import type { AppState } from "./types";

// 카메라 오픈/재접속 중의 일시적 camera_ok=false 로 오탐하지 않도록 지속 시간 요구
const ERROR_SUSTAIN_MS = 4000;
// 서버 연결 끊김 알림 최소 간격
const DISCONNECT_COOLDOWN_MS = 30_000;

function hardwareError(s: AppState): boolean {
  return (
    (s.camera_mode !== "idle" && !s.camera_ok) ||
    !s.telemetry.comm_ok ||
    s.lifejacket.devices.some((d) => d.worn && !d.signal_ok)
  );
}

export function useSoundEffects(
  state: AppState | null,
  connected: boolean,
): void {
  const prev = useRef<AppState | null>(null);
  const errorSince = useRef<number | null>(null);
  const errorBeeped = useRef(false);
  const prevConnected = useRef(true);
  const lastDisconnectBeep = useRef(0);

  // SOS 사이렌 — 신고가 떠 있는 동안 반복 재생 (새로고침 후 재진입해도 유지)
  const sosActive = !!state?.sos;
  useEffect(() => {
    if (sosActive) startLoop("sos");
    else stopLoop("sos");
  }, [sosActive]);

  useEffect(() => {
    if (!state) return;
    const p = prev.current;
    prev.current = state;
    if (!p) return; // 최초 로드 시점에는 아무 소리도 내지 않는다

    // 승선 인식 — 승선 인원 증가
    if (state.boarding.count > p.boarding.count) play("boarding");

    // 출항 등록 — 수동 출항 신고 / 지오펜스 이탈 공통
    if (state.voyage.active && !p.voyage.active) play("departure");

    // 입항 등록(세션 초기화·재잠금) — 수동 입항 신고 / 지오펜스 진입 공통
    if (!state.voyage.active && p.voyage.active) play("arrival");

    // 기상특보 발효 (특보 내용이 바뀌는 경우 포함)
    if (state.weather.advisory && state.weather.advisory !== p.weather.advisory)
      play("warning");

    // 하드웨어/통신 에러 — 지속 확인 후 에러 상태당 1회만
    if (hardwareError(state)) {
      if (errorSince.current == null) {
        errorSince.current = Date.now();
        errorBeeped.current = false;
      }
      if (
        !errorBeeped.current &&
        Date.now() - errorSince.current >= ERROR_SUSTAIN_MS
      ) {
        errorBeeped.current = true;
        play("error");
      }
    } else {
      errorSince.current = null;
    }
  }, [state]);

  // UI-서버 통신 두절도 에러로 알린다 (연결이 끊기면 state 갱신이 멈추므로 별도 처리)
  useEffect(() => {
    if (
      !connected &&
      prevConnected.current &&
      prev.current && // 최초 연결 시도 중은 제외
      Date.now() - lastDisconnectBeep.current > DISCONNECT_COOLDOWN_MS
    ) {
      lastDisconnectBeep.current = Date.now();
      play("error");
    }
    prevConnected.current = connected;
  }, [connected]);
}
