// 지도 라벨 충돌 회피 배치.
//
// 표류 예측 지도는 시간이 흐르면서 마커와 원이 서로 겹친다. 특히 신고 직후에는
// 익수 지점·선박·요구조자가 모두 같은 픽셀에 모여 라벨이 포개져 읽을 수 없다.
// 각 라벨을 앵커 주변의 후보 위치에 놓아 보고, 이미 놓인 라벨·마커와 겹치지 않는
// 첫 자리를 고른다. 많이 밀려난 라벨은 호출자가 지시선을 그려 앵커와 이어 준다.

export interface LabelInput {
  key: string;
  /** 라벨이 가리키는 지점 (지도 픽셀 좌표) */
  ax: number;
  ay: number;
  /** 글자 길이 (아이콘·여백 제외) */
  text: string;
  /** 아이콘 등 글자 외 추가 너비 */
  extraWidth?: number;
  /** 선호 방향 (단위 벡터에 가까운 값). 화면 위쪽이 -y */
  prefer: [number, number];
  /** 앵커에서 라벨 중심까지 기본 거리 */
  gap: number;
  /** 낮을수록 먼저(원하는 자리에) 배치된다 */
  priority: number;
}

export interface PlacedLabel extends LabelInput {
  /** 배치된 라벨 중심 */
  x: number;
  y: number;
  width: number;
  height: number;
  /** 선호 위치에서 밀려나 지시선이 필요한지 */
  displaced: boolean;
}

export interface Obstacle {
  x: number;
  y: number;
  width: number;
  height: number;
}

interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const FONT = '700 11px "Noto Sans KR", system-ui, sans-serif';
const PADDING_X = 22; // 좌우 패딩 + 테두리
const HEIGHT = 28;
const MARGIN = 8; // 지도 가장자리 여백
const CLEARANCE = 6; // 라벨끼리 최소 간격

let measureCtx: CanvasRenderingContext2D | null | undefined;

/** 실제 폰트로 글자 너비를 잰다 (캔버스가 없으면 글자 수로 근사). */
export function measureText(text: string): number {
  if (measureCtx === undefined) {
    measureCtx = document.createElement("canvas").getContext("2d");
  }
  if (!measureCtx) {
    // 한글은 대략 전각이라 라틴보다 넓게 잡는다
    return [...text].reduce((sum, ch) => sum + (ch.charCodeAt(0) > 0x2e80 ? 11 : 6), 0);
  }
  measureCtx.font = FONT;
  return measureCtx.measureText(text).width;
}

const toRect = (x: number, y: number, w: number, h: number): Rect => ({
  left: x - w / 2,
  top: y - h / 2,
  right: x + w / 2,
  bottom: y + h / 2,
});

const overlaps = (a: Rect, b: Rect, clearance = CLEARANCE) =>
  a.left < b.right + clearance &&
  a.right > b.left - clearance &&
  a.top < b.bottom + clearance &&
  a.bottom > b.top - clearance;

/** 선호 방향을 기준으로 회전·확장하며 후보 위치를 만든다. */
function candidates(label: LabelInput): [number, number][] {
  const [px, py] = label.prefer;
  const len = Math.hypot(px, py) || 1;
  const base = Math.atan2(py / len, px / len);
  const out: [number, number][] = [];
  // 선호 방향 → 좌우로 벌리며 탐색 → 반대편까지
  const turns = [0, 30, -30, 60, -60, 90, -90, 130, -130, 180];
  for (const scale of [1, 1.5, 2.2, 3]) {
    for (const turn of turns) {
      const angle = base + (turn * Math.PI) / 180;
      const dist = label.gap * scale;
      out.push([Math.cos(angle) * dist, Math.sin(angle) * dist]);
    }
  }
  return out;
}

/**
 * 라벨들을 서로 겹치지 않게 배치한다.
 * priority 가 낮은 라벨이 먼저 자리를 잡고, 나머지가 그 주변을 피해 간다.
 */
export function layoutLabels(
  labels: LabelInput[],
  obstacles: Obstacle[],
  bounds: { width: number; height: number },
): PlacedLabel[] {
  const taken: Rect[] = obstacles.map((o) =>
    toRect(o.x, o.y, o.width, o.height),
  );
  const placed: PlacedLabel[] = [];

  for (const label of [...labels].sort((a, b) => a.priority - b.priority)) {
    const width = measureText(label.text) + PADDING_X + (label.extraWidth ?? 0);
    const half = { w: width / 2, h: HEIGHT / 2 };

    let best: { x: number; y: number; rect: Rect } | null = null;
    let fallback: { x: number; y: number; rect: Rect; hits: number } | null = null;

    for (const [dx, dy] of candidates(label)) {
      // 지도 밖으로 나가지 않게 가장자리에서 되민다
      const x = Math.min(
        bounds.width - MARGIN - half.w,
        Math.max(MARGIN + half.w, label.ax + dx),
      );
      const y = Math.min(
        bounds.height - MARGIN - half.h,
        Math.max(MARGIN + half.h, label.ay + dy),
      );
      const rect = toRect(x, y, width, HEIGHT);
      const hits = taken.filter((t) => overlaps(rect, t)).length;
      if (hits === 0) {
        best = { x, y, rect };
        break;
      }
      if (!fallback || hits < fallback.hits) fallback = { x, y, rect, hits };
    }

    const chosen = best ?? fallback;
    if (!chosen) continue;
    taken.push(chosen.rect);

    const drift = Math.hypot(chosen.x - label.ax, chosen.y - label.ay);
    placed.push({
      ...label,
      x: chosen.x,
      y: chosen.y,
      width,
      height: HEIGHT,
      // 기본 거리보다 눈에 띄게 밀려났으면 지시선을 그린다
      displaced: drift > label.gap * 1.35,
    });
  }

  return placed;
}
