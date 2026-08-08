// 해양 벡터 필드 애니메이션 — Windy 처럼 해류/바람의 흐름을 입자 궤적으로 보여준다.
//
// 서버(/api/ocean/field)가 내려준 격자를 이중선형 보간해 각 입자를 흐름 방향으로
// 흘리고, 프레임마다 화면을 완전히 지우는 대신 반투명하게 덮어 잔상(궤적)을 남긴다.
// 격자는 관제사가 풍향·풍속·해류를 바꾸지 않는 한 변하지 않으므로, 값을 수정하면
// 흐름이 즉시 바뀌는 것이 눈에 보인다.

import { useEffect, useRef } from "react";
import type { OceanFieldData } from "../types";

interface Props {
  field: OceanFieldData | null;
  /** 입자 밀도 배율 (1 = 기본) */
  density?: number;
  /** 잔상 길이 (0.06 = 길게, 0.3 = 짧게) */
  fade?: number;
  className?: string;
}

interface Particle {
  x: number; // 0~1 (좌 → 우)
  y: number; // 0~1 (상 → 하)
  age: number;
  life: number;
}

// 속도 → 색. 느린 흐름은 차분하게, 빠른 흐름은 경고색으로 올린다.
const RAMPS: Record<string, [number, string][]> = {
  current: [
    [0.0, "#1b4f9c"],
    [0.35, "#0a84ff"],
    [0.65, "#00ffa3"],
    [1.0, "#ffd60a"],
  ],
  wind: [
    [0.0, "#4a5568"],
    [0.35, "#a0aec0"],
    [0.7, "#ff9f0a"],
    [1.0, "#ff375f"],
  ],
};

function hexToRgb(hex: string): [number, number, number] {
  const v = parseInt(hex.slice(1), 16);
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

function rampColor(layer: string, t: number): string {
  const stops = RAMPS[layer] ?? RAMPS.current;
  const clamped = Math.max(0, Math.min(1, t));
  for (let i = 1; i < stops.length; i++) {
    const [p1, c1] = stops[i];
    if (clamped <= p1) {
      const [p0, c0] = stops[i - 1];
      const ratio = p1 === p0 ? 0 : (clamped - p0) / (p1 - p0);
      const a = hexToRgb(c0);
      const b = hexToRgb(c1);
      return `rgb(${a.map((v, k) => Math.round(v + (b[k] - v) * ratio)).join(",")})`;
    }
  }
  return stops[stops.length - 1][1];
}

/** 격자에서 (x, y) 위치의 방위·세기를 이중선형 보간한다. */
function sample(field: OceanFieldData, x: number, y: number) {
  const { cols, rows, points } = field;
  const fx = Math.max(0, Math.min(1, x)) * (cols - 1);
  const fy = Math.max(0, Math.min(1, y)) * (rows - 1);
  const x0 = Math.floor(fx);
  const y0 = Math.floor(fy);
  const x1 = Math.min(cols - 1, x0 + 1);
  const y1 = Math.min(rows - 1, y0 + 1);
  const tx = fx - x0;
  const ty = fy - y0;

  // 방위는 각도라서 그냥 평균하면 0°/359° 경계에서 튄다 → 벡터로 바꿔 합성한다
  let north = 0;
  let east = 0;
  let speed = 0;
  const corners: [number, number, number][] = [
    [x0, y0, (1 - tx) * (1 - ty)],
    [x1, y0, tx * (1 - ty)],
    [x0, y1, (1 - tx) * ty],
    [x1, y1, tx * ty],
  ];
  for (const [cx, cy, weight] of corners) {
    const p = points[cy * cols + cx];
    if (!p) continue;
    const rad = (p.dir * Math.PI) / 180;
    north += Math.cos(rad) * p.speed * weight;
    east += Math.sin(rad) * p.speed * weight;
    speed += p.speed * weight;
  }
  return { north, east, speed };
}

export function OceanField({ field, density = 1, fade = 0.12, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fieldRef = useRef<OceanFieldData | null>(field);
  fieldRef.current = field;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let particles: Particle[] = [];
    let raf = 0;
    let last = performance.now();
    let width = 0;
    let height = 0;

    const spawn = (): Particle => ({
      x: Math.random(),
      y: Math.random(),
      age: Math.random() * 60,
      life: 60 + Math.random() * 90,
    });

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      width = Math.max(1, Math.round(rect.width));
      height = Math.max(1, Math.round(rect.height));
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const target = Math.round(((width * height) / 9000) * density);
      particles = Array.from({ length: Math.max(40, Math.min(900, target)) }, spawn);
      ctx.clearRect(0, 0, width, height);
    };

    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const data = fieldRef.current;

      // 잔상: 지우는 대신 배경색으로 옅게 덮는다
      ctx.globalCompositeOperation = "destination-out";
      ctx.fillStyle = `rgba(0,0,0,${fade})`;
      ctx.fillRect(0, 0, width, height);
      ctx.globalCompositeOperation = "source-over";

      if (!data || data.points.length === 0) return;
      const maxSpeed = Math.max(0.05, data.range.max);
      // 화면 대각선을 60초에 한 번 건널 정도를 최고 속도로 잡는다
      const pxPerUnit = (Math.hypot(width, height) / 60) / maxSpeed;

      ctx.lineWidth = data.layer === "wind" ? 1 : 1.4;
      ctx.lineCap = "round";

      for (const p of particles) {
        const { north, east, speed } = sample(data, p.x, p.y);
        if (speed <= 0.0001) {
          p.x = Math.random();
          p.y = Math.random();
          continue;
        }
        const norm = Math.hypot(north, east) || 1;
        // 북(+)은 화면 위쪽(-y)
        const vx = (east / norm) * speed * pxPerUnit;
        const vy = (-north / norm) * speed * pxPerUnit;

        const x0 = p.x * width;
        const y0 = p.y * height;
        const x1 = x0 + vx * dt;
        const y1 = y0 + vy * dt;

        ctx.strokeStyle = rampColor(data.layer, speed / maxSpeed);
        ctx.globalAlpha = data.layer === "wind" ? 0.55 : 0.8;
        ctx.beginPath();
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
        ctx.stroke();

        p.x = x1 / width;
        p.y = y1 / height;
        p.age += 1;
        if (p.age > p.life || p.x < -0.02 || p.x > 1.02 || p.y < -0.02 || p.y > 1.02) {
          Object.assign(p, spawn(), { age: 0 });
        }
      }
      ctx.globalAlpha = 1;
    };

    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [density, fade]);

  return <canvas ref={canvasRef} className={className ?? "ocean-canvas"} />;
}

/** 범례용 색 스케일 (0~1 구간을 몇 단계로 나눠 색을 뽑는다) */
export function rampSteps(layer: "current" | "wind", steps = 5): string[] {
  return Array.from({ length: steps }, (_, i) => rampColor(layer, i / (steps - 1)));
}
