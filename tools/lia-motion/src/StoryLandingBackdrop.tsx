import React, { useMemo } from 'react';
import { Easing } from 'remotion';

/** Projection of the existing LIGHT landing background, sampled from the
 * Remotion clock instead of mountLiaBackground's RAF. Source: CosmicBackdrop,
 * AttentionBackdrop, lib/landing/attention-background.ts and globals.css's
 * cosmos rules. AppCosmos applies these layers below opaque native UI too.
 * The initial unscrolled page is used: no fictional content or section marks. */
const LIGHT = { b: '43,79,201', v: '124,92,246' } as const;
const TAU = Math.PI * 2;
const opacity = (color: string, alpha: number) => `rgba(${color},${alpha})`;
type Point = { c: number; rx: number; ry: number; ph: number; x: number; y: number };

function rng(seed: number) {
  let value = seed >>> 0;
  return () => { value = (value * 1664525 + 1013904223) >>> 0; return value / 4294967296; };
}

function seedCloud(width: number, height: number): Point[] {
  const random = rng(23);
  const scale = Math.min(width, height) / 900;
  return Array.from({ length: width < 768 ? 150 : 300 }, (_, i) => {
    // Consume the exact native cluster-radius draws even on the unscrolled
    // page, where formation=0 and only random placement remains visible.
    const u = Math.max(1e-6, random());
    const angle = random() * TAU;
    const radius = Math.sqrt(-2 * Math.log(u)) * 46 * scale;
    void angle; void radius;
    return { c: i % 6, rx: 40 + random() * Math.max(1, width - 160), ry: 40 + random() * Math.max(1, height - 80), ph: random() * TAU, x: 0, y: 0 };
  });
}

function place(points: Point[], seconds: number): Point[] {
  return points.map(point => ({ ...point, x: point.rx + 6 * Math.sin(seconds * 0.5 + point.ph), y: point.ry + 6 * Math.cos(seconds * 0.4 + point.ph * 1.3) }));
}

function neighbours(points: Point[]): [number, number][] {
  return points.map((point, index) => {
    let first = -1, second = -1, d1 = 6400, d2 = 6400;
    points.forEach((other, j) => {
      if (j === index) return;
      const distance = (other.x - point.x) ** 2 + (other.y - point.y) ** 2;
      if (distance < d1) { d2 = d1; second = first; d1 = distance; first = j; }
      else if (distance < d2) { d2 = distance; second = j; }
    });
    return [first, second];
  });
}

function queryAt(frame: number, fps: number, width: number, height: number): [number, number] {
  let x = width * 0.46;
  let y = height * (0.5 + 0.38 * Math.sin(1.2));
  for (let f = 0; f <= frame; f++) {
    const seconds = f / fps;
    x += (width * (0.46 + 0.36 * Math.sin(seconds * 0.11)) - x) * 0.15;
    y += (height * (0.5 + 0.38 * Math.sin(seconds * 0.17 + 1.2)) - y) * 0.15;
  }
  return [x, y];
}

export function StoryLandingBackdrop({ width, height, frame, fps = 30, beat = 0 }: {
  width: number; height: number; frame: number; fps?: number; beat?: number;
}) {
  const points = useMemo(() => seedCloud(width, height), [width, height]);
  const seconds = frame / fps;
  const current = place(points, seconds);
  const edges = neighbours(place(points, (Math.floor(frame / 3) * 3) / fps));
  const [x, y] = queryAt(frame, fps, width, height);
  const closest = current.map((point, i) => [(point.x - x) ** 2 + (point.y - y) ** 2, i] as const).sort((a, b) => a[0] - b[0]).slice(0, 8);
  const boost = 1 + 0.525 * Math.max(0, Math.min(1, beat));
  const latent = 0.5 * boost;
  const spineX = width - (width < 768 ? 22 : 56);
  const y0 = Math.min(92, height * 0.1);
  const y1 = height - 64;
  const tokenCount = Math.max(48, Math.min(120, Math.round(height / 60)));
  const reading = 1 + (0.35 * (tokenCount - 1) - 1) * (1 - 0.85 ** (frame + 1));
  const tokenY = (i: number) => y0 + (i / (tokenCount - 1)) * (y1 - y0);
  const drift = Easing.bezier(0.42, 0, 0.58, 1);
  const a = drift(Math.min(1, seconds / 46));
  const b = drift(Math.min(1, seconds / 38));
  const lines = current.flatMap((point, i) => edges[i].filter(j => j >= 0).map(j => `M${point.x},${point.y}L${current[j].x},${current[j].y}`)).join('');
  return <div className="story-landing-backdrop" aria-hidden="true" style={{ width, height }}>
    <div className="story-landing-nebula" />
    <div className="story-landing-drift-a" style={{ transform: `translate(${width * 0.09 * a}px,${height * 0.07 * a}px) scale(${1 + 0.18 * a})` }} />
    <div className="story-landing-drift-b" style={{ transform: `translate(${-width * 0.08 * b}px,${-height * 0.06 * b}px) scale(${1 + 0.12 * b})` }} />
    {/* The native sober light variant sets cosmos-stars opacity=0. */}
    <div className="story-landing-grain" />
    <svg width={width} height={height} className="story-landing-attention" viewBox={`0 0 ${width} ${height}`}>
      <path d={lines} fill="none" stroke={opacity(LIGHT.b, 0.035 * latent)} strokeWidth={0.7} />
      {current.map((point, i) => <circle key={i} cx={point.x} cy={point.y} r={1.7} fill={opacity(point.c % 2 ? LIGHT.v : LIGHT.b, 0.26 * latent)} />)}
      {closest.map(([, i], rank) => <React.Fragment key={`q${i}`}>
        <path d={`M${x},${y}L${current[i].x},${current[i].y}`} fill="none" stroke={opacity(LIGHT.v, (0.34 - 0.03 * rank) * latent)} strokeWidth={0.9} />
        <circle cx={current[i].x} cy={current[i].y} r={2.8} fill={opacity(LIGHT.v, Math.min(0.85, 0.6 * latent))} />
      </React.Fragment>)}
      <circle cx={x} cy={y} r={Math.sqrt(closest[7][0])} fill="none" stroke={opacity(LIGHT.v, 0.14 * latent)} strokeWidth={0.8} strokeDasharray="2 5" />
      <circle cx={x} cy={y} r={4} fill={opacity(LIGHT.v, Math.min(0.9, 0.75 * latent))} />
      {width >= 768 ? <>
        {Array.from({ length: tokenCount }, (_, i) => <path key={`t${i}`} d={`M${spineX - (i === 0 ? 12 : 4)},${tokenY(i)}L${spineX + 4},${tokenY(i)}`} stroke={opacity(LIGHT.b, (i <= reading ? 0.22 : 0.08) * boost)} strokeWidth={i === 0 ? 1.2 : 1} strokeLinecap="round" />)}
        <path d={`M${spineX + 10},${y0}L${spineX + 10},${y1}`} stroke={opacity(LIGHT.b, 0.07 * boost)} strokeWidth={1} />
        <text x={spineX + 16} y={y0 + 3} fontSize={10} fontWeight={500} fontFamily="ui-monospace,Consolas,monospace" fill={opacity(LIGHT.b, 0.28 * boost)}>⟨s⟩</text>
        <circle cx={spineX} cy={tokenY(reading)} r={3.4} fill={opacity(LIGHT.v, Math.min(0.9, 0.7 * boost))} />
        <circle cx={spineX} cy={tokenY(reading)} r={9} fill="none" stroke={opacity(LIGHT.v, 0.25 * boost)} strokeWidth={1} />
      </> : null}
    </svg>
  </div>;
}
