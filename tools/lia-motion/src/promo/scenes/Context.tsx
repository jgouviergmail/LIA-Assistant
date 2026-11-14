/**
 * Section « context » (beats 24-47, 12-24 s): « Ta journée, déjà prête. »,
 * « Elle relie tes sources. », « Elle apprend à te connaître. »
 *
 * The dashboard is the product's « Mon dashboard » (briefing card, then the
 * domain cards in their colour code) built card by card on the beats; the
 * thread then links the briefing sentence to the agenda entry, the mail and
 * the reminder it was made from. The memory part shows four remembered facts
 * in the categories the settings use (💡 Préférences, 👥 Relations,
 * 📋 Personnel), with BIP.
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { LayoutDashboard, RefreshCw, SlidersHorizontal, Volume2 } from 'lucide-react';
import { COPY } from '../copy';
import { BOUNCY, SNAPPY, SOFT, clamp, easeIn, easeInOut, easeOut, lerp, pop, ramp, typed } from '../motion';
import { IconChip, type Tone } from '../parts/Brand';
import { AppWindow, Card } from '../parts/Ui';
import { KineticBlock } from '../parts/Type';
import { Thread, makeSpline, type Point } from '../parts/Thread';
import { Companion, type CompanionCue } from '../parts/Companion';

const W = 1180;
const H = 900;
/** Section-local frame 0 is the downbeat at 12.0 s; the sequence starts 30 frames earlier. */
const LEAD = 30;

type Pose = { cx: number; cy: number; s: number; ry: number; rx: number; o: number };
const ENTER: Pose = { cx: 1290, cy: 1420, s: 0.9, ry: -24, rx: 38, o: 0 };
const POSE_A: Pose = { cx: 1250, cy: 588, s: 0.95, ry: -17, rx: 7, o: 1 };
const POSE_B: Pose = { cx: 1240, cy: 560, s: 1, ry: 0, rx: 0, o: 1 };
const EXIT: Pose = { cx: 520, cy: 640, s: 0.7, ry: 30, rx: 4, o: 0 };

const mixPose = (a: Pose, b: Pose, t: number): Pose => ({
  cx: lerp(a.cx, b.cx, t),
  cy: lerp(a.cy, b.cy, t),
  s: lerp(a.s, b.s, t),
  ry: lerp(a.ry, b.ry, t),
  rx: lerp(a.rx, b.rx, t),
  o: lerp(a.o, b.o, t),
});

/** Screen position of a window point while the window faces the camera. */
const toScreen = (p: Point, pose: Pose): Point => ({ x: pose.cx + pose.s * (p.x - W / 2), y: pose.cy + pose.s * (p.y - H / 2) });

/** Anchors (window coordinates, content area starts at y=84) the thread links. */
const ANCHORS = {
  briefing: { x: 905, y: 286 },
  agenda: { x: 220, y: 508 },
  mail: { x: 598, y: 562 },
  reminder: { x: 220, y: 770 },
};

const BRIEFING =
  'Bonjour Alex ! Ta revue de conception commence à 10 h : relis les notes de Morgan avant. Trois nouveaux messages, et un rappel pour ton carnet.';

function Row({ time, title, sub, color, glow = 0 }: { time?: string; title: string; sub?: string; color: string; glow?: number }) {
  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        gap: 14,
        padding: '5px 10px',
        borderRadius: 12,
        background: glow > 0 ? `rgba(0,97,155,${0.1 * glow})` : 'transparent',
        boxShadow: glow > 0 ? `0 0 0 ${2 * glow}px rgba(79,141,253,${0.55 * glow}), 0 0 ${26 * glow}px rgba(79,141,253,${0.45 * glow})` : undefined,
      }}
    >
      {time && <div style={{ width: 64, fontSize: 19, fontWeight: 700, color: '#2f3741', fontVariantNumeric: 'tabular-nums' }}>{time}</div>}
      <div style={{ width: 4, alignSelf: 'stretch', borderRadius: 4, background: color }} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 20, fontWeight: 600, color: '#2f3741', whiteSpace: 'nowrap' }}>{title}</div>
        {sub && <div style={{ fontSize: 16, color: '#6b7480', whiteSpace: 'nowrap' }}>{sub}</div>}
      </div>
    </div>
  );
}

function CardHead({ icon, tone, title }: { icon: string; tone: Tone; title: string }) {
  return (
    <div className="card-head">
      <IconChip icon={icon} tone={tone} size={46} />
      <span className="card-title" style={{ fontSize: 23 }}>
        {title}
      </span>
      <span className="card-meta" style={{ fontSize: 15 }}>
        à l’instant
      </span>
    </div>
  );
}

function Dashboard({ s, glows }: { s: number; glows: Record<keyof typeof ANCHORS, number> }) {
  const appear = (t: number) => {
    const p = pop(s, t, SNAPPY);
    return { opacity: clamp(p * 1.3), transform: `translateY(${(1 - p) * 34}px) scale(${0.9 + 0.1 * p})` };
  };
  const text = typed(BRIEFING, s, 40, 196);
  return (
    <AppWindow width={W} height={H} active="dashboard">
      <div style={{ position: 'absolute', left: 30, top: 22, right: 30, display: 'flex', alignItems: 'center', gap: 14, ...appear(-6) }}>
        <LayoutDashboard size={34} color="#00619b" strokeWidth={2.2} />
        <span style={{ fontSize: 34, fontWeight: 750, letterSpacing: '-0.02em' }}>Mon dashboard</span>
        <span className="pill" style={{ marginLeft: 8, borderColor: 'rgba(0,97,155,0.3)', background: 'rgba(0,97,155,0.08)', color: '#00619b', fontSize: 17 }}>
          vendredi 14 novembre
        </span>
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 22, fontSize: 18, color: '#4b5563', alignItems: 'center' }}>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <SlidersHorizontal size={20} /> Personnaliser
          </span>
          <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <RefreshCw size={20} color="#00619b" /> Tout rafraîchir
          </span>
        </span>
      </div>

      <Card style={{ left: 30, top: 86, width: 1120, height: 172, padding: '18px 24px', ...appear(16) }}>
        <div className="card-head">
          <IconChip icon="auto_awesome" tone="blue" size={46} />
          <span className="card-title" style={{ fontSize: 23 }}>
            Le briefing de LIA
          </span>
          <span style={{ marginLeft: 'auto', display: 'flex', gap: 10, alignItems: 'center', color: '#00619b' }}>
            <Volume2 size={22} />
          </span>
        </div>
        <p style={{ marginTop: 12, fontSize: 23, lineHeight: 1.45, color: '#2f3741', maxWidth: 1050 }}>
          {text}
          {s >= 40 && s < 210 && <span className="caret" />}
        </p>
      </Card>

      <Card style={{ left: 30, top: 276, width: 360, height: 252, padding: '16px 18px', ...appear(60) }}>
        <CardHead icon="calendar_month" tone="violet" title="Agenda" />
        <div style={{ marginTop: 8, fontSize: 15, color: '#6b7480', paddingLeft: 10 }}>Aujourd’hui</div>
        <div style={{ marginTop: 0 }}>
          <Row time="10:00" title="Revue de conception" sub="Salle Atlas" color="#7c3aed" glow={glows.agenda} />
          <Row time="14:30" title="Point d’équipe" sub="Visio" color="#a78bfa" />
          <Row time="18:30" title="Point projet" sub="Studio Nord" color="#a78bfa" />
        </div>
      </Card>

      <Card style={{ left: 410, top: 276, width: 360, height: 252, padding: '16px 18px', ...appear(90) }}>
        <CardHead icon="mail" tone="emerald" title="Mails non lus" />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginTop: 4, paddingLeft: 6 }}>
          <span style={{ fontSize: 40, fontWeight: 750, color: '#059669', lineHeight: 1 }}>3</span>
          <span style={{ fontSize: 17, color: '#6b7480' }}>non lus aujourd’hui</span>
        </div>
        <div style={{ marginTop: 4 }}>
          <Row title="Morgan" sub="Notes de la revue" color="#10b981" glow={glows.mail} />
          <Row title="Studio Nord" sub="Livraison mise à jour" color="#6ee7b7" />
        </div>
      </Card>

      <Card style={{ left: 790, top: 276, width: 360, height: 252, padding: '16px 18px', ...appear(120) }}>
        <CardHead icon="partly_cloudy_day" tone="sky" title="Météo" />
        <div style={{ marginTop: 12, paddingLeft: 6, fontSize: 18, color: '#6b7480' }}>Lyon</div>
        <div style={{ display: 'flex', alignItems: 'center', paddingLeft: 4 }}>
          <span style={{ fontSize: 66, fontWeight: 650, color: '#1f2937', letterSpacing: '-0.03em' }}>21 °C</span>
          <span className="sym" style={{ marginLeft: 'auto', fontSize: 92, color: '#f59e0b', filter: 'drop-shadow(0 4px 8px rgba(245,158,11,0.35))' }}>
            sunny
          </span>
        </div>
        <div style={{ paddingLeft: 6, fontSize: 17, color: '#4b5563' }}>Ciel dégagé · 14° / 23°</div>
      </Card>

      <Card style={{ left: 30, top: 546, width: 360, height: 252, padding: '16px 18px', ...appear(150) }}>
        <CardHead icon="alarm" tone="amber" title="Rappels actifs" />
        <div style={{ marginTop: 12 }}>
          <Row time="09:45" title="Apporter le carnet" sub="Revue de conception" color="#f59e0b" glow={glows.reminder} />
          <Row time="17:00" title="Confirmer la livraison" sub="Studio Nord" color="#fcd34d" />
        </div>
      </Card>

      <Card style={{ left: 410, top: 546, width: 360, height: 252, padding: '16px 18px', ...appear(180) }}>
        <CardHead icon="cake" tone="rose" title="Anniversaires" />
        <div style={{ marginTop: 12 }}>
          <Row title="Sam" sub="demain · 34 ans" color="#f43f5e" />
          <Row title="Morgan" sub="dans 3 jours" color="#fda4af" />
        </div>
      </Card>

      <Card style={{ left: 790, top: 546, width: 360, height: 252, padding: '16px 18px', ...appear(210) }}>
        <CardHead icon="task_alt" tone="teal" title="Tâches" />
        <div style={{ marginTop: 12 }}>
          <Row title="Valider le devis Atlas" sub="aujourd’hui" color="#14b8a6" />
          <Row title="Préparer la revue de lundi" sub="demain" color="#5eead4" />
        </div>
      </Card>
    </AppWindow>
  );
}

const MEMORIES: Array<{ emoji: string; cat: string; text: string; bg: string }> = [
  { emoji: '💡', cat: 'Préférences', text: 'Des réponses courtes, avec les sources', bg: 'rgba(245,158,11,0.16)' },
  { emoji: '👥', cat: 'Relations', text: 'Sophie, ta femme', bg: 'rgba(244,63,94,0.14)' },
  { emoji: '📋', cat: 'Personnel', text: 'Footing le mardi et le jeudi, 7 h 30', bg: 'rgba(16,185,129,0.14)' },
  { emoji: '💡', cat: 'Préférences', text: 'Pas de réunion avant 9 h', bg: 'rgba(245,158,11,0.16)' },
];

function MemoryCard({ m, style }: { m: (typeof MEMORIES)[number]; style: React.CSSProperties }) {
  return (
    <div className="card" style={{ position: 'absolute', width: 680, height: 118, padding: '0 28px', display: 'flex', alignItems: 'center', gap: 22, ...style }}>
      <div style={{ width: 66, height: 66, borderRadius: 18, background: m.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 36 }}>{m.emoji}</div>
      <div>
        <div style={{ fontSize: 16, letterSpacing: '0.09em', textTransform: 'uppercase', color: '#6b7480', fontWeight: 650 }}>{m.cat}</div>
        <div style={{ fontSize: 26, fontWeight: 650, color: '#2f3741', letterSpacing: '-0.01em', marginTop: 4, whiteSpace: 'nowrap' }}>{m.text}</div>
      </div>
      <span className="sym" style={{ marginLeft: 'auto', fontSize: 30, color: '#00619b' }}>
        push_pin
      </span>
    </div>
  );
}

/** BIP watches each memory land (a nod), then turns to the viewer, pleased. */
const MEMORY_CUES: CompanionCue[] = [
  { at: 0, expression: 'attentive' },
  { at: 0, gaze: { x: -0.72, y: -0.04 } },
  { at: 44, nod: 0.6 },
  { at: 74, nod: 0.6 },
  { at: 104, nod: 0.6 },
  { at: 134, nod: 0.7 },
  { at: 176, expression: 'joy' },
  { at: 176, gaze: { x: 0, y: 0 } },
  { at: 192, gesture: 'perk' },
];

export function Context() {
  const lf = useCurrentFrame();
  const s = lf - LEAD;

  // Window choreography.
  const enter = ramp(s, -22, 40, easeOut);
  const toB = ramp(s, 226, 34, easeInOut);
  const toExit = ramp(s, 338, 40, easeIn);
  let pose = mixPose(ENTER, POSE_A, enter);
  pose = mixPose(pose, POSE_B, toB);
  pose = mixPose(pose, EXIT, toExit);
  const breathe = Math.sin(s / 70) * 0.006;

  // Thread across the window's sources (window frontal from s=260).
  const pts = [ANCHORS.briefing, ANCHORS.agenda, ANCHORS.mail, ANCHORS.reminder].map((p) => toScreen(p, POSE_B));
  const spline = makeSpline(pts);
  const head = ramp(s, 262, 70, easeInOut);
  const threadOpacity = ramp(s, 262, 8) * (1 - ramp(s, 344, 18));
  const knots = [0, 1, 2, 3].map((k) => spline.lengths[Math.min(k * 48, spline.lengths.length - 1)] / spline.total);
  const glowAt = (k: number) => clamp((head - knots[k]) * 14 + 1) * (1 - ramp(s, 344, 18)) * (s >= 262 ? 1 : 0);
  const glows = { briefing: glowAt(0), agenda: glowAt(1), mail: glowAt(2), reminder: glowAt(3) };

  const memIn = (i: number) => pop(s, 420 + i * 30, SOFT);
  const sophieFly = ramp(s, 656, 50, easeIn);

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      {/* the dashboard window */}
      {s < 382 && (
        <div style={{ position: 'absolute', inset: 0, perspective: 2400, perspectiveOrigin: '50% 45%' }}>
          <div
            style={{
              position: 'absolute',
              left: pose.cx - W / 2,
              top: pose.cy - H / 2,
              width: W,
              height: H,
              opacity: pose.o,
              transform: `scale(${pose.s + breathe}) rotateY(${pose.ry}deg) rotateX(${pose.rx}deg)`,
              transformStyle: 'preserve-3d',
            }}
          >
            <Dashboard s={s} glows={glows} />
          </div>
        </div>
      )}
      {threadOpacity > 0 && <Thread id="ctx" spline={spline} head={head} width={0.9} opacity={threadOpacity} />}

      <KineticBlock frame={s} start={6} end={228} lines={COPY.context.ready} x={96} y={390} size={84} slam />
      <KineticBlock frame={s} start={240} end={352} lines={COPY.context.links} x={96} y={390} size={84} slam />

      {/* memory */}
      {s >= 360 && (
        <>
          <div
            style={{
              position: 'absolute',
              left: 840,
              top: 214,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              fontSize: 24,
              fontWeight: 600,
              color: '#c9d2ee',
              opacity: ramp(s, 392, 20) * (1 - ramp(s, 690, 20)),
            }}
          >
            <span className="sym" style={{ fontSize: 30, color: '#a5b4fc' }}>
              neurology
            </span>
            Mémoire · ce que LIA retient de toi
          </div>
          {MEMORIES.map((m, i) => {
            const p = memIn(i);
            const fly = i === 1 ? sophieFly : 0;
            const others = i === 1 ? 0 : ramp(s, 650, 30, easeIn);
            const x = lerp(1240, 840, p);
            const y = 270 + i * 140;
            return (
              <MemoryCard
                key={i}
                m={m}
                style={{
                  left: lerp(x, 960 - 340, fly),
                  top: lerp(y, 540 - 59, fly),
                  opacity: clamp(p * 1.4) * (1 - others) * (1 - clamp(fly * 1.6 - 0.6)),
                  transform: `scale(${(0.86 + 0.14 * p) * (1 + fly * 1.8)}) rotate(${(1 - p) * 4}deg)`,
                  filter: fly > 0.05 ? `blur(${(fly * 10).toFixed(1)}px)` : undefined,
                  zIndex: i === 1 ? 5 : 1,
                }}
              />
            );
          })}
          <div
            style={{
              position: 'absolute',
              left: 1545,
              top: 330,
              opacity: ramp(s, 380, 16) * (1 - ramp(s, 660, 30)),
              transform: `translateY(${(1 - pop(s, 380, BOUNCY)) * 260 + Math.sin(s / 24) * 6}px)`,
            }}
          >
            <Companion id="context-bip" frame={s - 380} size={340} cues={MEMORY_CUES} />
          </div>
        </>
      )}
      <KineticBlock frame={s} start={388} end={652} lines={COPY.context.knows} x={96} y={390} size={84} slam />
    </div>
  );
}
