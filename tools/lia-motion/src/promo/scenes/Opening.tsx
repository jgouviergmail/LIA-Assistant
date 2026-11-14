/**
 * Sections « hook » and « reveal » (beats 0-23, 0-12 s).
 *
 * Beats 1-10: one domain per beat slams in the centre and its tile flies out
 * to a scattered place. Beats 11-13: « Ton quotidien est éparpillé. », the
 * letters drifting apart. Beats 14-15: the thread whips through every tile
 * and lands in the centre on the drop (beat 16, 8.0 s). Beats 16-23: the
 * tiles fall into an orbit around LIA's mark, linked to it; « LIA garde le
 * fil. »; BIP arrives; the camera dives toward the mark.
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { COPY } from '../copy';
import { BOUNCY, SOFT, SNAPPY, clamp, easeIn, easeInOut, easeOut, lerp, pop, ramp, rand } from '../motion';
import { DomainTile, LiaMark, type Tone } from '../parts/Brand';
import { Kinetic } from '../parts/Type';
import { Thread, makeSpline } from '../parts/Thread';
import { Companion, type CompanionCue } from '../parts/Companion';

/** BIP lands, delighted, looks at the promise, then turns to the viewer. */
const REVEAL_CUES: CompanionCue[] = [
  { at: 0, expression: 'excited' },
  { at: 0, gaze: { x: -0.55, y: -0.1 } },
  { at: 16, gesture: 'perk' },
  { at: 44, expression: 'joy' },
  { at: 62, gaze: { x: 0, y: 0 } },
  { at: 70, nod: 0.8 },
];

type HookTile = { icon: string; tone: Tone; x: number; y: number; d: number };

const TILES: HookTile[] = [
  { icon: 'mail', tone: 'emerald', x: 290, y: 250, d: 0.95 },
  { icon: 'calendar_month', tone: 'violet', x: 1650, y: 235, d: 1.0 },
  { icon: 'contacts', tone: 'rose', x: 430, y: 855, d: 0.86 },
  { icon: 'folder', tone: 'blue', x: 1520, y: 865, d: 0.9 },
  { icon: 'task_alt', tone: 'teal', x: 880, y: 165, d: 0.78 },
  { icon: 'alarm', tone: 'orange', x: 170, y: 560, d: 1.08 },
  { icon: 'directions_car', tone: 'sky', x: 1765, y: 575, d: 0.86 },
  { icon: 'lightbulb', tone: 'amber', x: 1150, y: 950, d: 0.82 },
  { icon: 'groups', tone: 'indigo', x: 690, y: 935, d: 1.0 },
  { icon: 'description', tone: 'fuchsia', x: 1290, y: 160, d: 0.9 },
];

/** Order in which the thread visits the tiles before landing in the centre. */
const THREAD_ORDER = [5, 0, 4, 9, 1, 6, 3, 7, 8, 2];
const CENTER = { x: 960, y: 540 };
const ORBIT = { x: 960, y: 405, rx: 610, ry: 205 };
const ITEM_START = 30;
const DROP = 480;

const drift = (i: number, f: number) => ({
  dx: Math.sin(f / 85 + i * 1.7) * 12,
  dy: Math.cos(f / 105 + i * 1.3) * 9,
});

const spline = makeSpline([
  { x: -120, y: 640 },
  ...THREAD_ORDER.map((i) => {
    const d = drift(i, 450);
    return { x: TILES[i].x + d.dx, y: TILES[i].y + d.dy };
  }),
  CENTER,
]);
/** Arc-length fraction at which the thread passes each tile. */
const knot = (k: number) => spline.lengths[Math.min((k + 1) * 48, spline.lengths.length - 1)] / spline.total;

function Slam({ f, start, text }: { f: number; start: number; text: string }) {
  const p = ramp(f, start, 6, easeOut);
  const q = ramp(f, start + 24, 6, easeIn);
  if (f < start || f > start + 31) return null;
  return (
    <div
      className="kt"
      style={{
        left: CENTER.x,
        top: CENTER.y - 92,
        fontSize: 156,
        transform: `translateX(-50%) scale(${1.32 - 0.32 * p - 0.1 * q})`,
        opacity: p * (1 - q),
        filter: `blur(${((1 - p) * 12 + q * 10).toFixed(1)}px)`,
      }}
    >
      {text}
    </div>
  );
}

function Scattered({ f }: { f: number }) {
  const start = ITEM_START + 10 * 30;
  const out = ramp(f, 420, 16, easeIn);
  if (f < start || f > 440) return null;
  // The phrase is read whole first; only « éparpillé. » comes apart, gently.
  const spread = ramp(f, start + 40, 70, easeInOut);
  const [lead, word] = COPY.hook.scattered[1].split(' ');
  const p2 = ramp(f, start + 10, 18, easeOut);
  return (
    <>
      <Kinetic frame={f} start={start} end={436} text={COPY.hook.scattered[0]} x={CENTER.x} y={CENTER.y - 150} size={128} align="center" slam />
      <div
        className="kt"
        style={{
          left: CENTER.x,
          top: CENTER.y - 6,
          fontSize: 128,
          transform: 'translateX(-50%)',
          opacity: p2 * (1 - out),
          filter: `blur(${((1 - p2) * 12 + out * 10).toFixed(1)}px)`,
        }}
      >
        <span className="w">{lead}</span>{' '}
        {Array.from(word).map((ch, i) => {
          const r1 = rand(i + 31) - 0.5;
          const r2 = rand(i + 77) - 0.5;
          const r3 = rand(i + 113) - 0.5;
          return (
            <span
              key={i}
              className="w"
              style={{
                transform: `translate(${(r1 * 34 * spread).toFixed(1)}px, ${(r2 * 46 * spread).toFixed(1)}px) rotate(${(r3 * 22 * spread).toFixed(1)}deg)`,
              }}
            >
              {ch}
            </span>
          );
        })}
      </div>
    </>
  );
}

export function Opening() {
  const f = useCurrentFrame();
  // Thread: 420 -> 480 head, tail chasing; it then becomes the orbit.
  const headT = clamp((f - 420) / 60) ** 1.7;
  const tailT = f < 480 ? Math.max(0, headT - 0.42) : lerp(0.58, 1, ramp(f, 480, 18, easeOut));
  const exit = ramp(f, 668, 52, easeIn);
  const camera = 1 + exit * 1.9;
  const orbitIn = (i: number) => pop(f, DROP + 2 + i * 2, SOFT);
  const markBuild = ramp(f, DROP + 2, 44, easeOut);
  const flash = f >= DROP ? Math.max(0, 1 - (f - DROP) / 22) : 0;
  const spin = (f - DROP) * 0.0042;

  // Tile placement: hook position, then orbit position after the drop.
  const tiles = TILES.map((t, i) => {
    const appear = ITEM_START + i * 30;
    const p = pop(f, appear, SNAPPY);
    const d = drift(i, f);
    const hx = lerp(CENTER.x, t.x + d.dx, p);
    const hy = lerp(CENTER.y, t.y + d.dy, p);
    const angle = (i / TILES.length) * Math.PI * 2 + Math.PI / 2 + spin;
    const ox = ORBIT.x + Math.cos(angle) * ORBIT.rx;
    const oy = ORBIT.y + Math.sin(angle) * ORBIT.ry;
    const depth = (Math.sin(angle) + 1) / 2;
    const o = f >= DROP ? orbitIn(i) : 0;
    const k = THREAD_ORDER.indexOf(i);
    const hit = f >= 420 && f < 500 ? Math.exp(-Math.abs(headT - knot(k)) * 30) : 0;
    const lit = f >= 420 ? clamp((headT - knot(k)) * 12) : 0;
    const hookScale = (0.25 + 0.75 * p) * t.d;
    const orbitScale = 0.62 + depth * 0.42;
    return {
      t,
      i,
      x: lerp(hx, ox, o),
      y: lerp(hy, oy, o),
      s: lerp(hookScale, orbitScale, o) * (1 + hit * 0.18),
      rot: lerp((rand(i + 5) - 0.5) * 16 + Math.sin(f / 70 + i) * 3, 0, o),
      z: lerp(t.d, depth, o),
      visible: f >= appear,
      hit,
      lit,
      blur: lerp(t.d < 0.85 ? 1.6 : 0, (1 - depth) * 1.6, o),
    };
  });

  const orbitPath = (() => {
    const pts = Array.from({ length: 41 }, (_, n) => {
      const a = (n / 40) * Math.PI * 2 + spin;
      return { x: ORBIT.x + Math.cos(a) * ORBIT.rx, y: ORBIT.y + Math.sin(a) * ORBIT.ry };
    });
    return makeSpline(pts, 8);
  })();
  const orbitDraw = ramp(f, DROP + 4, 40, easeOut);

  return (
    <div style={{ position: 'absolute', inset: 0, transform: `scale(${camera})`, transformOrigin: '960px 405px', opacity: 1 - ramp(f, 678, 22) }}>
      {/* links from the mark to every tile after the drop */}
      {f >= DROP && (
        <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0 }}>
          <defs>
            <linearGradient id="op-link" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="#4f8dfd" />
              <stop offset="1" stopColor="#38d4f5" />
            </linearGradient>
          </defs>
          {tiles.map(({ x, y, i }) => {
            const g = ramp(f, DROP + 14 + i * 3, 26, easeOut);
            const pulse = 0.25 + 0.2 * Math.exp(-(((f - DROP) % 30) / 8));
            return (
              <line
                key={i}
                x1={ORBIT.x}
                y1={ORBIT.y}
                x2={lerp(ORBIT.x, x, g)}
                y2={lerp(ORBIT.y, y, g)}
                stroke="url(#op-link)"
                strokeWidth={2}
                opacity={pulse * g}
              />
            );
          })}
        </svg>
      )}
      {f >= DROP && <Thread id="orbit" spline={orbitPath} head={orbitDraw} tail={0} width={0.75} opacity={0.85} showHead={orbitDraw < 1} />}

      {tiles
        .filter((t) => t.visible)
        .sort((a, b) => a.z - b.z)
        .map(({ t, i, x, y, s, rot, hit, lit, blur }) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: x - 66,
              top: y - 66,
              width: 132,
              height: 132,
              transform: `scale(${s}) rotate(${rot}deg)`,
              filter: blur > 0.2 ? `blur(${blur.toFixed(1)}px) brightness(${1 + hit * 0.6})` : `brightness(${1 + hit * 0.6})`,
            }}
          >
            <DomainTile icon={t.icon} tone={t.tone} size={132} glow={0.35 + lit * 0.35 + hit * 0.4} />
            {lit > 0 && f < DROP + 30 && (
              <div
                style={{
                  position: 'absolute',
                  inset: -10,
                  borderRadius: 44,
                  border: '2px solid rgba(167,190,255,0.8)',
                  opacity: lit * (1 - ramp(f, DROP, 30)),
                }}
              />
            )}
          </div>
        ))}

      {Array.from({ length: 10 }, (_, i) => (
        <Slam key={i} f={f} start={ITEM_START + i * 30} text={COPY.hook.items[i]} />
      ))}
      <Scattered f={f} />

      {f >= 420 && f < 520 && <Thread id="hook" spline={spline} head={headT} tail={tailT} width={1.15} opacity={1 - ramp(f, 496, 20)} />}

      {/* the drop: flash, mark, line */}
      {flash > 0 && (
        <div
          style={{
            position: 'absolute',
            left: CENTER.x - 700,
            top: ORBIT.y - 700,
            width: 1400,
            height: 1400,
            borderRadius: '50%',
            background: 'radial-gradient(closest-side, rgba(255,255,255,0.95), rgba(180,200,255,0.45) 30%, rgba(139,92,246,0.15) 60%, transparent)',
            opacity: flash,
            transform: `scale(${0.4 + (1 - flash) * 1.4})`,
          }}
        />
      )}
      {f >= DROP && (
        <LiaMark size={210} build={markBuild} glow={markBuild * (0.85 + 0.15 * Math.sin(f / 9))} style={{ left: ORBIT.x - 105, top: ORBIT.y - 105 }} />
      )}
      <Kinetic frame={f} start={DROP + 14} text={COPY.reveal.line} x={960} y={712} size={112} align="center" stagger={5} slam />
      <Kinetic frame={f} start={600} text={COPY.reveal.sub} x={960} y={858} size={44} align="center" weight={500} color="#b7bfdc" stagger={3} />
      {f >= 596 && (
        <div
          style={{
            position: 'absolute',
            left: 1560,
            top: 640,
            transform: `translateY(${(1 - pop(f, 598, BOUNCY)) * 420}px) rotate(${Math.sin((f - 598) / 11) * 2.5}deg)`,
          }}
        >
          <Companion id="reveal-bip" frame={f - 598} size={300} cues={REVEAL_CUES} />
        </div>
      )}
    </div>
  );
}
