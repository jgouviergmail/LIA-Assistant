/**
 * Section « linked » (beats 196-215, 98-108 s, the soundtrack's riser and
 * build): every capability the film showed blooms around LIA's mark — « Tout
 * est relié. » — then the pairs that work together light up one per beat (the
 * weather moves the run, an e-mail becomes a task, a memory becomes a
 * reminder…). On the build every link burns at once, the constellation spins
 * up and collapses into the centre for the final hit on the closing line.
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { COPY } from '../copy';
import { SOFT, clamp, easeIn, easeOut, lerp, pop, ramp } from '../motion';
import { DomainTile, LiaMark, type Tone } from '../parts/Brand';
import { Kinetic } from '../parts/Type';

const CENTER = { x: 960, y: 520 };
/** Local frames: riser 300-360, build 360-600, the hit lands on 600. */
const BUILD = 360;
const END = 600;

type Node = { label: string; icon: string; tone: Tone };

const INNER: Node[] = [
  { label: 'Agenda', icon: 'calendar_month', tone: 'violet' },
  { label: 'E-mails', icon: 'mail', tone: 'emerald' },
  { label: 'Tâches', icon: 'task_alt', tone: 'teal' },
  { label: 'Mémoire', icon: 'neurology', tone: 'fuchsia' },
  { label: 'Rappels', icon: 'alarm', tone: 'amber' },
  { label: 'Documents', icon: 'description', tone: 'blue' },
  { label: 'Météo', icon: 'partly_cloudy_day', tone: 'sky' },
  { label: 'Trajets', icon: 'directions_car', tone: 'orange' },
  { label: 'Contacts', icon: 'contacts', tone: 'rose' },
  { label: 'Maison', icon: 'home', tone: 'amber' },
];

const OUTER: Node[] = [
  { label: 'Habitudes', icon: 'event_repeat', tone: 'teal' },
  { label: 'Engagements', icon: 'handshake', tone: 'amber' },
  { label: 'Intérêts', icon: 'interests', tone: 'sky' },
  { label: 'Psyché', icon: 'psychology', tone: 'fuchsia' },
  { label: 'Routines', icon: 'schedule', tone: 'violet' },
  { label: 'Notifications', icon: 'notifications_active', tone: 'indigo' },
  { label: 'Live', icon: 'mic', tone: 'violet' },
  { label: 'Appels', icon: 'call', tone: 'emerald' },
  { label: 'Telegram', icon: 'send', tone: 'sky' },
  { label: 'Images', icon: 'image', tone: 'fuchsia' },
  { label: 'Skills', icon: 'auto_awesome', tone: 'indigo' },
  { label: 'MCP', icon: 'extension', tone: 'cyan' },
  { label: 'Connexions', icon: 'group_add', tone: 'rose' },
  { label: 'Registres', icon: 'fact_check', tone: 'emerald' },
];

const NODES = [...INNER, ...OUTER];
const index = (label: string) => NODES.findIndex((n) => n.label === label);

/** Capabilities that work together, lit one per beat. */
const LINKS: Array<[number, number]> = [
  [index('Météo'), index('Agenda')],
  [index('E-mails'), index('Tâches')],
  [index('Mémoire'), index('Rappels')],
  [index('Habitudes'), index('Notifications')],
  [index('Agenda'), index('Trajets')],
  [index('Live'), index('Routines')],
  [index('Connexions'), index('Agenda')],
  [index('Documents'), index('E-mails')],
];
const LINKS_FROM = 120;

function nodePos(k: number, spin: number) {
  const inner = k < INNER.length;
  const count = inner ? INNER.length : OUTER.length;
  const i = inner ? k : k - INNER.length;
  const a = (-90 + (360 / count) * (i + 0.5)) * (Math.PI / 180) + spin;
  // The inner ring's height clears the mark and the two lines in the centre
  // at every angle, so the slow turn never draws a node over the words.
  const rx = inner ? 450 : 800;
  const ry = inner ? 300 : 430;
  return { x: CENTER.x + Math.cos(a) * rx, y: CENTER.y + Math.sin(a) * ry };
}

const bend = (a: { x: number; y: number }, b: { x: number; y: number }) => ({
  x: (a.x + b.x) / 2 + (CENTER.x - (a.x + b.x) / 2) * 0.4,
  y: (a.y + b.y) / 2 + (CENTER.y - (a.y + b.y) / 2) * 0.4,
});
const onCurve = (a: { x: number; y: number }, c: { x: number; y: number }, b: { x: number; y: number }, u: number) => ({
  x: (1 - u) ** 2 * a.x + 2 * (1 - u) * u * c.x + u ** 2 * b.x,
  y: (1 - u) ** 2 * a.y + 2 * (1 - u) * u * c.y + u ** 2 * b.y,
});

export function Linked() {
  const m = useCurrentFrame() - 10;
  const build = ramp(m, BUILD, END - BUILD, easeIn);
  const collapse = ramp(m, END - 64, 58, easeIn);
  const spin = m * 0.0004 + collapse * collapse * 1.2;
  const scale = lerp(1.05, 1, ramp(m, 0, 150, easeOut)) * (1 + 0.035 * build) * (1 - collapse * 0.88);
  const beat = Math.exp(-((((m - 0) % 30) + 30) % 30) / 6);
  const lit = (k: number) =>
    LINKS.reduce((acc, [a, b], i) => {
      if (a !== k && b !== k) return acc;
      const d = m - (LINKS_FROM + i * 30 + (k === b ? 22 : 0));
      return Math.max(acc, d < 0 ? Math.max(0, 1 + d / 6) * 0.5 : Math.exp(-d / 28));
    }, 0) + build * 0.6;

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <div style={{ position: 'absolute', inset: 0, transform: `scale(${scale}) rotate(${collapse * 50}deg)`, transformOrigin: `${CENTER.x}px ${CENTER.y}px`, opacity: 1 - ramp(m, END - 8, 8) }}>
        <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
          <defs>
            <linearGradient id="lk-line" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#4f8dfd" />
              <stop offset="0.6" stopColor="#8b5cf6" />
              <stop offset="1" stopColor="#38d4f5" />
            </linearGradient>
            <filter id="lk-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="8" />
            </filter>
          </defs>
          {NODES.map((_, k) => {
            const p = nodePos(k, spin);
            const g = ramp(m, 8 + k * 4, 30, easeOut);
            return <line key={k} x1={CENTER.x} y1={CENTER.y} x2={lerp(CENTER.x, p.x, g)} y2={lerp(CENTER.y, p.y, g)} stroke="url(#lk-line)" strokeWidth={2 + build * 2.5} opacity={0.32 + build * 0.5} />;
          })}
          {LINKS.map(([a, b], i) => {
            const pa = nodePos(a, spin);
            const pb = nodePos(b, spin);
            const c = bend(pa, pb);
            const g = ramp(m, LINKS_FROM - 20 + i * 30, 30, easeOut);
            return <path key={i} d={`M${pa.x},${pa.y} Q${c.x},${c.y} ${pb.x},${pb.y}`} fill="none" stroke="#a5b4fc" strokeWidth={1.6 + build * 3} opacity={(0.35 + build * 0.6) * g} />;
          })}
          {LINKS.map(([a, b], i) => {
            const t0 = LINKS_FROM + i * 30;
            if (m < t0 || m > t0 + 80) return null;
            const pa = nodePos(a, spin);
            const pb = nodePos(b, spin);
            const c = bend(pa, pb);
            const head = clamp((m - t0) / 22) ** 0.8;
            const tail = Math.max(0, head - 0.5) * (m > t0 + 28 ? 1 + (m - t0 - 28) / 50 : 1);
            const fade = 1 - ramp(m, t0 + 40, 40, easeIn);
            const pts = Array.from({ length: 25 }, (_, n) => onCurve(pa, c, pb, Math.min(head, tail + ((head - tail) * n) / 24)));
            const d = pts.map((pt, n) => `${n ? 'L' : 'M'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join('');
            const tip = onCurve(pa, c, pb, head);
            return (
              <g key={`c${i}`} opacity={fade}>
                <path d={d} fill="none" stroke="url(#lk-line)" strokeWidth={14} strokeLinecap="round" opacity={0.45} filter="url(#lk-glow)" />
                <path d={d} fill="none" stroke="url(#lk-line)" strokeWidth={4.5} strokeLinecap="round" />
                <path d={d} fill="none" stroke="#ffffff" strokeWidth={1.6} strokeLinecap="round" opacity={0.9} />
                {head < 1 && <circle cx={tip.x} cy={tip.y} r={7} fill="#ffffff" />}
              </g>
            );
          })}
          {m > 40 &&
            NODES.map((_, k) => {
              const p = nodePos(k, spin);
              const period = build > 0.3 ? 15 : 30;
              const local = (((m - (k % 5) * 6) % period) + period) % period;
              const t = local / period;
              return <circle key={`p${k}`} cx={lerp(CENTER.x, p.x, t)} cy={lerp(CENTER.y, p.y, t)} r={3.5 + build * 2} fill="#e0e7ff" opacity={(0.6 + build * 0.4) * (1 - t)} />;
            })}
        </svg>
        {NODES.map((node, k) => {
          const p = nodePos(k, spin);
          const s = pop(m, 8 + k * 4, SOFT);
          const inner = k < INNER.length;
          const size = inner ? 78 : 68;
          const glow = lit(k);
          return (
            <div key={k} style={{ position: 'absolute', left: p.x - size / 2, top: p.y - size / 2, width: size, height: size, transform: `scale(${(0.2 + 0.8 * s) * (1 + beat * 0.05 * (1 + build) + Math.min(glow, 1.2) * 0.16)})`, opacity: clamp(s * 1.5) }}>
              <DomainTile icon={node.icon} tone={node.tone} size={size} glow={0.5 + glow * 0.8} />
              <div className="node-label" style={{ left: '50%', top: size + 8, transform: 'translateX(-50%)', fontSize: inner ? 22 : 20 }}>
                {node.label}
              </div>
            </div>
          );
        })}
        <LiaMark size={140} build={ramp(m, 0, 32, easeOut)} glow={0.85 + build * 0.6} style={{ left: CENTER.x - 70, top: CENTER.y - 196 }} />
        <Kinetic frame={m} start={36} text={COPY.linked.title} x={CENTER.x} y={CENTER.y - 30} size={78} align="center" slam />
        <Kinetic frame={m} start={78} text={COPY.linked.agents} x={CENTER.x} y={CENTER.y + 66} size={30} align="center" weight={560} color="#c3cbe6" stagger={2} />
      </div>
      {collapse > 0.7 && (
        <div style={{ position: 'absolute', left: CENTER.x - 700, top: CENTER.y - 700, width: 1400, height: 1400, borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(255,255,255,0.95), rgba(170,190,255,0.4) 40%, transparent)', opacity: clamp((collapse - 0.7) / 0.3) * (1 - ramp(m, END + 2, 14)), transform: `scale(${0.4 + collapse * 0.8})` }} />
      )}
    </div>
  );
}
