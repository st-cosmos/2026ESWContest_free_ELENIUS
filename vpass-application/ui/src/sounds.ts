// 사운드 효과 재생 관리
// 파일: public/sounds/*.mp3 — 출처·라이선스는 public/sounds/README.md 참고

export type SoundName =
  | "boarding" // 승선 인식
  | "departure" // 출항 (수동 확인 · 지오펜스 이탈)
  | "arrival" // 입항 (지오펜스 진입 · 입항 완료)
  | "sos" // SOS 사이렌 (루프)
  | "warning" // 기상특보
  | "error"; // 하드웨어/통신 에러

const VOLUME: Record<SoundName, number> = {
  boarding: 0.7,
  departure: 0.8,
  arrival: 0.8,
  sos: 1.0,
  warning: 0.9,
  error: 0.7,
};

const cache = new Map<SoundName, HTMLAudioElement>();

function get(name: SoundName): HTMLAudioElement {
  let a = cache.get(name);
  if (!a) {
    a = new Audio(`/sounds/${name}.mp3`);
    a.preload = "auto";
    a.volume = VOLUME[name];
    cache.set(name, a);
  }
  return a;
}

export function play(name: SoundName): void {
  const a = get(name);
  a.loop = false;
  a.currentTime = 0;
  // 자동재생 차단 시 조용히 무시 — 첫 사용자 입력(unlock) 후부터 재생된다.
  // 키오스크 chromium 은 --autoplay-policy=no-user-gesture-required 로 항상 허용.
  void a.play().catch(() => {});
}

export function startLoop(name: SoundName): void {
  const a = get(name);
  if (!a.paused) return; // 이미 재생 중
  a.loop = true;
  a.currentTime = 0;
  void a.play().catch(() => {});
}

export function stopLoop(name: SoundName): void {
  const a = cache.get(name);
  if (a) {
    a.pause();
    a.loop = false;
    a.currentTime = 0;
  }
}

// 브라우저 자동재생 정책 해제: 첫 사용자 입력 때 전 오디오를 무음으로 한 번
// 재생해 두면 이후 프로그램적 재생이 허용된다 (개발 PC 브라우저용).
let unlocked = false;

function unlock(): void {
  if (unlocked) return;
  unlocked = true;
  for (const name of Object.keys(VOLUME) as SoundName[]) {
    const a = get(name);
    if (!a.paused) continue; // 재생 중인 소리(예: SOS 루프)는 건드리지 않는다
    a.muted = true;
    void a
      .play()
      .then(() => {
        a.pause();
        a.currentTime = 0;
        a.muted = false;
      })
      .catch(() => {
        a.muted = false;
      });
  }
}

if (typeof window !== "undefined") {
  window.addEventListener("pointerdown", unlock, { once: true });
  window.addEventListener("keydown", unlock, { once: true });
}
