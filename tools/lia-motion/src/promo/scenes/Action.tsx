/**
 * Section « action » (beats 48-79, 24-40 s): « Une phrase suffit. »,
 * « Trois actions, en parallèle. », « Tu valides d'un clic. », « Tu gardes
 * la main. »
 *
 * The request is the landing demo's first scene (« Je vais avoir 30 min de
 * retard ce soir — préviens ma femme et décale mon rdv de 18 h 30 »). Behind
 * the scenes three specialists run side by side (contacts, agenda, e-mail),
 * then LIA answers on the right — the chat is inverted: the person on the
 * left, LIA on the right — and the draft card waits for the person's click
 * on « Confirmer », on the downbeat at 36.0 s.
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { CircleCheck, Mic, Plus, Search, Send, Trash2, User } from 'lucide-react';
import { COPY } from '../copy';
import { SNAPPY, SOFT, clamp, easeIn, easeInOut, easeOut, lerp, pop, ramp, typed } from '../motion';
import { DomainTile, IconChip, type Tone } from '../parts/Brand';
import { AppWindow, Cursor } from '../parts/Ui';
import { KineticBlock } from '../parts/Type';
import { Thread, makeSpline } from '../parts/Thread';
import { Companion, type CompanionCue } from '../parts/Companion';

const W = 1180;
const H = 900;
const LEAD = 20;
const REQUEST = 'Je vais avoir 30 min de retard ce soir — préviens ma femme et décale mon rdv de 18 h 30';
const ANSWER = 'Sophie retrouvée, ton « Point projet » de 18 h 30 aussi. J’envoie et je décale à 19 h ?';
const SEND = 180;
const CLICK = 720;

type Pose = { cx: number; cy: number; s: number; ry: number; rx: number; o: number };
const P_IN: Pose = { cx: 1560, cy: 600, s: 0.94, ry: -34, rx: 6, o: 0 };
const P_TYPE: Pose = { cx: 1270, cy: 522, s: 1.05, ry: -6, rx: 2, o: 1 };
const P_AGENTS: Pose = { cx: 1270, cy: 556, s: 1, ry: 0, rx: 0, o: 1 };
const P_HITL: Pose = { cx: 1260, cy: 512, s: 1.08, ry: 0, rx: 0, o: 1 };
const P_OUT: Pose = { cx: 1420, cy: 600, s: 0.86, ry: -24, rx: 6, o: 0 };
const mix = (a: Pose, b: Pose, t: number): Pose => ({
  cx: lerp(a.cx, b.cx, t),
  cy: lerp(a.cy, b.cy, t),
  s: lerp(a.s, b.s, t),
  ry: lerp(a.ry, b.ry, t),
  rx: lerp(a.rx, b.rx, t),
  o: lerp(a.o, b.o, t),
});
const toScreen = (x: number, y: number, p: Pose) => ({ x: p.cx + p.s * (x - W / 2), y: p.cy + p.s * (y - H / 2) });

const AGENTS: Array<{ icon: string; tone: Tone; title: string; sub: string }> = [
  { icon: 'contacts', tone: 'rose', title: 'Contacts', sub: '« ma femme » → Sophie' },
  { icon: 'calendar_month', tone: 'violet', title: 'Agenda', sub: 'Point projet · 18:30' },
  { icon: 'mail', tone: 'emerald', title: 'E-mail', sub: 'brouillon prêt' },
];

function Spinner({ t }: { t: number }) {
  return (
    <svg width="34" height="34" viewBox="0 0 34 34" style={{ transform: `rotate(${t * 14}deg)` }}>
      <circle cx="17" cy="17" r="13" fill="none" stroke="rgba(148,163,220,0.25)" strokeWidth="4" />
      <path d="M17 4 A13 13 0 0 1 30 17" fill="none" stroke="#8fb4ff" strokeWidth="4" strokeLinecap="round" />
    </svg>
  );
}

function Chat({ s }: { s: number }) {
  const text = typed(REQUEST, s, 36, 168);
  const sending = s >= SEND;
  const shown = text.length > 58 ? `…${text.slice(text.length - 57)}` : text;
  const bubble = pop(s, SEND + 2, SOFT);
  const thinking = s >= SEND + 24 && s < 486;
  const answerWords = ANSWER.split(' ');
  const nWords = Math.floor(answerWords.length * clamp((s - 486) / 52));
  const answerIn = pop(s, 480, SNAPPY);
  const hitlIn = pop(s, 540, SOFT);
  const done = ramp(s, CLICK + 6, 16, easeOut);
  const press = s >= CLICK && s < CLICK + 8 ? 1 : 0;
  return (
    <AppWindow width={W} height={H} active="chat">
      {/* top strip */}
      <div style={{ position: 'absolute', left: 0, top: 0, width: W, height: 64, display: 'flex', alignItems: 'center', padding: '0 22px', gap: 14, background: 'rgba(241,238,233,0.7)', borderBottom: '1px solid #e3dfd7' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, width: 330, height: 42, borderRadius: 999, border: '1px solid #ddd8cf', background: '#f7f5f1', padding: '0 16px', color: '#8a929c', fontSize: 17 }}>
          <Search size={18} color="#2f80c4" /> Rechercher dans l’historique…
        </div>
        <div style={{ marginLeft: 'auto', marginRight: 'auto', display: 'flex', gap: 10 }}>
          <span className="pill" style={{ borderColor: '#ddd8cf', color: '#5b6470', background: '#f7f5f1' }}>
            <Mic size={17} color="#7c6fd6" />
          </span>
          <span className="pill" style={{ borderColor: '#ddd8cf', color: '#5b6470', background: '#f7f5f1', fontSize: 16 }}>
            ◌ 8 %
          </span>
        </div>
        <span className="pill" style={{ borderColor: '#fecdd3', color: '#be123c', background: '#ffe4e6', fontSize: 16 }}>
          <Trash2 size={16} /> Supprimer
        </span>
      </div>

      {/* the person, on the left */}
      {sending && (
        <div
          style={{
            position: 'absolute',
            left: 24,
            top: lerp(720, 92, bubble),
            display: 'flex',
            gap: 14,
            alignItems: 'flex-start',
            opacity: clamp(bubble * 2),
            transform: `scale(${0.95 + 0.05 * bubble})`,
            transformOrigin: 'left top',
          }}
        >
          <div className="avatar-dot">
            <User size={26} />
          </div>
          <div>
            <div className="bubble-user" style={{ width: 760 }}>
              {REQUEST}
            </div>
            <div style={{ marginTop: 8, fontSize: 16, color: '#6b7480' }}>18:02</div>
          </div>
        </div>
      )}

      {/* LIA, on the right */}
      {s >= SEND + 20 && (
        <div style={{ position: 'absolute', right: 22, top: 232, opacity: ramp(s, SEND + 20, 14), transform: `scale(${0.6 + 0.4 * pop(s, SEND + 20, SNAPPY)})`, transformOrigin: 'right top' }}>
          <Companion id="action-bip" frame={s - SEND - 20} size={78} cues={ACTION_CUES} />
        </div>
      )}
      {thinking && (
        <div style={{ position: 'absolute', right: 116, top: 252, padding: '18px 24px', borderRadius: '22px 0 22px 22px', background: 'rgba(250,248,246,0.92)', border: '1px solid #e6e2dc', display: 'flex', gap: 9 }}>
          {[0, 1, 2].map((d) => (
            <i key={d} style={{ width: 12, height: 12, borderRadius: '50%', background: '#00619b', opacity: 0.35 + 0.65 * Math.max(0, Math.sin((s - d * 6) / 6)) }} />
          ))}
        </div>
      )}
      {s >= 480 && (
        <div style={{ position: 'absolute', right: 116, top: 236, width: 740, opacity: clamp(answerIn * 1.5), transform: `translateY(${(1 - answerIn) * 20}px) scale(${0.95 + 0.05 * answerIn})`, transformOrigin: 'right top' }}>
          <div className="bubble-lia">
            <h4>Un message prêt pour ta validation</h4>
            <p style={{ margin: 0 }}>{answerWords.slice(0, Math.max(1, nWords)).join(' ')}</p>
          </div>
          <div className="token-line" style={{ marginTop: 8 }}>
            <span>18:02</span>|<span style={{ color: '#ea7a12' }}>🟠 2 400 IN</span>
            <span style={{ color: '#15924f' }}>🟢 380 OUT</span>
            <span style={{ color: '#2563eb' }}>🔵 800 CACHE</span>
            <b style={{ color: '#2f3741' }}>• 0,0018 €</b>
          </div>
        </div>
      )}

      {/* the draft waiting for the person */}
      {s >= 540 && (
        <div
          className="card"
          style={{
            position: 'absolute',
            left: 40,
            top: 440,
            width: 1100,
            height: 256,
            padding: '20px 26px',
            opacity: clamp(hitlIn * 1.4),
            transform: `translateY(${(1 - hitlIn) * 70}px)`,
            borderColor: done > 0 ? `rgba(16,185,129,${0.6 * done})` : '#dcd8cf',
            boxShadow: done > 0 ? `0 0 0 ${3 * done}px rgba(16,185,129,0.25), 0 10px 30px rgba(0,0,0,0.08)` : undefined,
          }}
        >
          <div style={{ opacity: 1 - done }}>
            <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
              <IconChip icon="mail" tone="blue" size={46} />
              <span style={{ fontSize: 24, fontWeight: 700 }}>Brouillon à valider</span>
            </div>
            <div style={{ marginTop: 10, marginLeft: 62, fontSize: 19, lineHeight: 1.55, color: '#2f3741' }}>
              <div>
                <span className="muted">À</span>&nbsp;&nbsp;Sophie Martin
              </div>
              <div>
                <span className="muted">Objet</span>&nbsp;&nbsp;Retard ce soir (mais avec style) 😅
              </div>
              <div style={{ color: '#4b5563' }}>«&nbsp;Le trafic a décidé de tester la solidité de notre couple. Verdict à 20&nbsp;h…&nbsp;»</div>
            </div>
          </div>
          <div style={{ position: 'absolute', left: 88, bottom: 18, display: 'flex', gap: 12, opacity: 1 - done }}>
            <span className="btn btn-primary" style={{ transform: `scale(${1 - press * 0.04})`, filter: press ? 'brightness(0.9)' : undefined }}>
              Confirmer
            </span>
            <span className="btn btn-ghost">Modifier</span>
            <span className="btn btn-outline">Annuler</span>
          </div>
          {done > 0 && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', gap: 24, padding: '0 34px', opacity: done, transform: `scale(${0.96 + 0.04 * done})` }}>
              <div style={{ width: 86, height: 86, borderRadius: '50%', background: 'rgba(16,185,129,0.14)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CircleCheck size={54} color="#059669" strokeWidth={2.2} />
              </div>
              <div>
                <div style={{ fontSize: 30, fontWeight: 750, color: '#065f46' }}>E-mail envoyé à Sophie</div>
                <div style={{ fontSize: 24, color: '#2f3741', marginTop: 6 }}>📅 «&nbsp;Point projet&nbsp;» décalé à 19&nbsp;h</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* composer */}
      <div className="composer" style={{ position: 'absolute', left: 0, bottom: 0, width: W, height: 110 }}>
        <Plus size={30} color="#7c3aed" strokeWidth={2.4} />
        <div className="composer-field">
          {s < SEND ? (
            <>
              {shown || <span style={{ color: '#9aa1aa' }}>Écris ton message...</span>}
              {s >= 30 && <span className="caret" style={{ opacity: Math.floor(s / 16) % 2 === 0 || s < 170 ? 1 : 0 }} />}
            </>
          ) : (
            <span style={{ color: '#9aa1aa' }}>Écris ton message...</span>
          )}
        </div>
        <span
          className="btn btn-primary"
          style={{ padding: '18px 24px', fontSize: 21, transform: `scale(${s >= SEND - 2 && s < SEND + 6 ? 0.95 : 1})` }}
        >
          {s >= 36 && s < SEND + 4 ? (
            <>
              <Send size={22} /> Envoyer
            </>
          ) : (
            <>
              <Mic size={22} /> Maintiens pour parler
            </>
          )}
        </span>
      </div>
    </AppWindow>
  );
}

/**
 * BIP's part, from its arrival (SEND + 20): it thinks while the specialists
 * work, follows the answer being written (text streaming is attentive, never
 * speaking: the face speaks only on real audio), then rejoices on the send.
 */
const ACTION_CUES: CompanionCue[] = [
  { at: 0, expression: 'thinking' },
  { at: 0, gaze: { x: -0.45, y: -0.4 } },
  { at: 486 - SEND - 20, expression: 'attentive' },
  { at: 486 - SEND - 20, gaze: { x: -0.75, y: 0.3 } },
  { at: CLICK + 6 - SEND - 20, expression: 'joy' },
  { at: CLICK + 6 - SEND - 20, gaze: { x: 0, y: 0 } },
  { at: CLICK + 14 - SEND - 20, gesture: 'perk' },
];

export function Action() {
  const lf = useCurrentFrame();
  const s = lf - LEAD;

  let pose = mix(P_IN, P_TYPE, ramp(s, -20, 40, easeOut));
  pose = mix(pose, P_AGENTS, ramp(s, 214, 30, easeInOut));
  pose = mix(pose, P_HITL, ramp(s, 548, 60, easeInOut));
  pose = mix(pose, P_OUT, ramp(s, 922, 40, easeIn));

  // Backstage: three specialists, side by side, then the gate.
  const agentIn = (i: number) => pop(s, 240 + i * 30, SNAPPY);
  const agentDone = (i: number) => ramp(s, 330 + i * 18, 10, easeOut);
  const backstageOut = ramp(s, 452, 22, easeIn);
  const bubbleAnchor = toScreen(92, 84 + 92 + 96, P_AGENTS);
  const pts = [bubbleAnchor, { x: 600, y: 616 }, { x: 600, y: 736 }, { x: 600, y: 856 }, { x: 420, y: 944 }];
  const spline = makeSpline(pts);
  const head = ramp(s, 246, 120, easeInOut);
  const cursorT = ramp(s, CLICK - 70, 64, easeInOut);
  const confirm = { x: 847, y: 823 };
  const cursor = { x: lerp(640, confirm.x, cursorT), y: lerp(1090, confirm.y, cursorT) + Math.sin(cursorT * Math.PI) * 24 };

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <div style={{ position: 'absolute', inset: 0, perspective: 2400 }}>
        <div
          style={{
            position: 'absolute',
            left: pose.cx - W / 2,
            top: pose.cy - H / 2,
            width: W,
            height: H,
            opacity: pose.o,
            transform: `scale(${pose.s}) rotateY(${pose.ry}deg) rotateX(${pose.rx}deg)`,
          }}
        >
          <Chat s={s} />
        </div>
      </div>

      {s >= 236 && s < 480 && (
        <>
          <div style={{ position: 'absolute', left: 100, top: 520, fontSize: 18, letterSpacing: '0.16em', fontWeight: 700, color: '#8f9bc4', opacity: ramp(s, 236, 14) * (1 - backstageOut) }}>
            EN COULISSES
          </div>
          {AGENTS.map((a, i) => {
            const p = agentIn(i);
            const d = agentDone(i);
            return (
              <div
                key={a.title}
                style={{
                  position: 'absolute',
                  left: 96,
                  top: 560 + i * 120,
                  width: 504,
                  height: 104,
                  borderRadius: 22,
                  background: 'rgba(15,19,38,0.78)',
                  border: `1px solid rgba(148,163,220,${0.22 + 0.3 * d})`,
                  boxShadow: `0 22px 44px rgba(0,0,0,0.45), 0 0 ${30 * d}px rgba(79,141,253,${0.25 * d})`,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 20,
                  padding: '0 24px',
                  opacity: clamp(p * 1.4) * (1 - backstageOut),
                  transform: `translateX(${(1 - p) * -120}px) scale(${0.9 + 0.1 * p})`,
                }}
              >
                <DomainTile icon={a.icon} tone={a.tone} size={60} glow={0.3} style={{ position: 'relative' }} />
                <div>
                  <div style={{ fontSize: 25, fontWeight: 700, color: '#eef1fb' }}>{a.title}</div>
                  <div style={{ fontSize: 20, color: '#aab3d1', marginTop: 2 }}>{a.sub}</div>
                </div>
                <div style={{ marginLeft: 'auto' }}>
                  {d < 1 ? (
                    <div style={{ opacity: 1 - d }}>
                      <Spinner t={s} />
                    </div>
                  ) : null}
                  {d > 0 && (
                    <div style={{ position: d < 1 ? 'absolute' : 'static', marginTop: d < 1 ? -34 : 0, opacity: d, transform: `scale(${0.6 + 0.4 * d})` }}>
                      <CircleCheck size={34} color="#34d399" strokeWidth={2.4} />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div
            style={{
              position: 'absolute',
              left: 96,
              top: 924,
              padding: '10px 18px',
              borderRadius: 999,
              border: '1px solid rgba(251,191,36,0.55)',
              background: 'rgba(251,191,36,0.12)',
              color: '#fcd34d',
              fontSize: 21,
              fontWeight: 650,
              opacity: ramp(s, 372, 16) * (1 - backstageOut),
            }}
          >
            Ton accord — rien ne part sans toi
          </div>
        </>
      )}
      {s >= 246 && s < 476 && <Thread id="act" spline={spline} head={head} width={0.8} opacity={(1 - backstageOut) * ramp(s, 246, 8)} />}

      <KineticBlock frame={s} start={10} end={228} lines={COPY.action.sentence} x={96} y={300} size={84} slam />
      <KineticBlock frame={s} start={236} end={470} lines={COPY.action.parallel} x={96} y={300} size={84} slam />
      <KineticBlock frame={s} start={500} end={740} lines={COPY.action.click} x={96} y={300} size={84} slam />
      <KineticBlock frame={s} start={752} end={952} lines={COPY.action.control} x={96} y={300} size={84} slam />

      {s >= CLICK - 72 && s < CLICK + 40 && (
        <div style={{ opacity: 1 - ramp(s, CLICK + 20, 18) }}>
          <Cursor x={cursor.x} y={cursor.y} press={s >= CLICK && s < CLICK + 8 ? 1 : 0} ripple={clamp((s - CLICK) / 22)} />
        </div>
      )}
    </div>
  );
}
