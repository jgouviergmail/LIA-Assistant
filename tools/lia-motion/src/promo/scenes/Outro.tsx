/**
 * Section « outro » (beats 152-163, 76-82 s): the soundtrack's final hit,
 * then its ring-out. The landing's own three lines — « Ton quotidien. LIA
 * garde le fil. Tu gardes la main. » — under the mark, BIP beside them, and
 * a last quiet fade to the cosmos so the loop on the landing restarts clean.
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { COPY } from '../copy';
import { BOUNCY, clamp, easeIn, easeInOut, easeOut, pop, ramp } from '../motion';
import { LiaMark } from '../parts/Brand';
import { Kinetic } from '../parts/Type';
import { Thread, makeSpline } from '../parts/Thread';
import { Companion, type CompanionCue } from '../parts/Companion';

const LEAD = 6;
const underline = makeSpline([
  { x: 690, y: 702 },
  { x: 900, y: 716 },
  { x: 1130, y: 704 },
  { x: 1268, y: 690 },
]);

/** BIP reads the closing line with the viewer, then turns to them and bows. */
const OUTRO_CUES: CompanionCue[] = [
  { at: 0, expression: 'excited' },
  { at: 0, gaze: { x: -0.65, y: -0.05 } },
  { at: 20, gesture: 'perk' },
  { at: 76, expression: 'joy' },
  { at: 76, gaze: { x: 0, y: 0 } },
  { at: 92, nod: 0.9 },
  { at: 150, scene: 'body-bow' },
];

export function Outro() {
  const s = useCurrentFrame() - LEAD;
  const flash = s >= 0 ? Math.max(0, 1 - s / 26) : 0;
  const fade = ramp(s, 296, 60, easeIn);
  const push = 1 + ramp(s, 0, 360, easeInOut) * 0.035;
  const ul = ramp(s, 48, 40, easeInOut);
  return (
    <div style={{ position: 'absolute', inset: 0, opacity: 1 - fade, transform: `scale(${push})`, transformOrigin: '50% 50%' }}>
      {flash > 0 && (
        <div style={{ position: 'absolute', left: 260, top: -220, width: 1400, height: 1400, borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(255,255,255,0.95), rgba(180,200,255,0.4) 32%, rgba(139,92,246,0.12) 60%, transparent)', opacity: flash, transform: `scale(${0.5 + (1 - flash) * 1.2})` }} />
      )}
      <LiaMark size={176} build={ramp(s, 0, 40, easeOut)} glow={0.85 + 0.15 * Math.sin(s / 10)} style={{ left: 960 - 88, top: 182 }} />
      <Kinetic frame={s} start={4} text={COPY.outro.lines[0]} x={960} y={436} size={100} align="center" slam />
      <Kinetic frame={s} start={32} text={COPY.outro.lines[1]} x={960} y={566} size={100} align="center" slam />
      <Kinetic frame={s} start={62} text={COPY.outro.lines[2]} x={960} y={720} size={100} align="center" slam />
      {ul > 0 && <Thread id="outro" spline={underline} head={ul} width={0.75} showHead={ul < 1} />}
      <Kinetic frame={s} start={122} text={COPY.outro.footer} x={960} y={912} size={30} align="center" weight={550} color="#aab3d1" stagger={2} style={{ letterSpacing: '0.01em' }} />
      {s >= 16 && (
        <div style={{ position: 'absolute', left: 1530, top: 520, transform: `translateY(${(1 - pop(s, 18, BOUNCY)) * 380}px) rotate(${Math.sin(s / 12) * 2}deg)`, opacity: clamp((s - 16) / 6) }}>
          <Companion id="outro-bip" frame={s - 16} size={300} cues={OUTRO_CUES} />
        </div>
      )}
    </div>
  );
}
