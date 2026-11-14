/**
 * Section « anticipate » (beats 80-95, 40-48 s, the soundtrack's breakdown):
 * « Elle anticipe. » « Tu décides. »
 *
 * LIA speaks first, on the phone: the landing demo's second scene — showers
 * forecast exactly on the person's 7:30 run, a sunny slot on Thursday, « Je
 * te le décale ? ». One tap on « Oui, vas-y », the run moves, the rain
 * outside the phone gives way to a warm light.
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { COPY } from '../copy';
import { SOFT, clamp, easeIn, easeOut, lerp, pop, ramp, rand } from '../motion';
import { IconChip, LiaMark } from '../parts/Brand';
import { MobileBar, Phone, Tap } from '../parts/Ui';
import { KineticBlock } from '../parts/Type';

const LEAD = 20;
const TAP = 180;
const NOTICE =
  'Averses pile sur ton footing de 7 h 30. Jeudi 7 h : grand soleil, 14°. Je te le décale ?';

function Rain({ s, opacity }: { s: number; opacity: number }) {
  if (opacity <= 0) return null;
  return (
    <svg width={1920} height={1080} style={{ position: 'absolute', inset: 0, opacity }}>
      {Array.from({ length: 90 }, (_, i) => {
        const x0 = rand(i * 5 + 1) * 2100 - 90;
        const speed = 22 + rand(i * 5 + 2) * 18;
        const len = 34 + rand(i * 5 + 3) * 40;
        const y = ((rand(i * 5 + 4) * 1300 + s * speed) % 1300) - 120;
        const x = x0 - y * 0.2;
        return <line key={i} x1={x} y1={y} x2={x - len * 0.2} y2={y + len} stroke="#9fb6e8" strokeWidth={1.6} opacity={0.18 + rand(i) * 0.25} strokeLinecap="round" />;
      })}
    </svg>
  );
}

function Screen({ s }: { s: number }) {
  const n = pop(s, 60, SOFT);
  const moved = ramp(s, TAP + 6, 18, easeOut);
  const tapT = clamp((s - TAP) / 24);
  // While LIA's notice is on screen, the app behind it softens, as under a real banner.
  const behind = clamp(n);
  return (
    <>
      <div style={{ filter: behind > 0.02 ? `blur(${(behind * 3).toFixed(1)}px) brightness(${1 - behind * 0.1})` : undefined }}>
        <MobileBar />
        <div style={{ padding: '18px 22px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 28, fontWeight: 750, color: '#2f3741' }}>
            <span className="sym" style={{ fontSize: 30, color: '#00619b' }}>
              space_dashboard
            </span>
            Mon dashboard
          </div>
          <div className="card" style={{ marginTop: 16, padding: '16px 18px' }}>
            <div className="card-head">
              <IconChip icon="auto_awesome" tone="blue" size={40} />
              <span className="card-title" style={{ fontSize: 21 }}>
                Le briefing de LIA
              </span>
            </div>
            <p style={{ marginTop: 10, fontSize: 19, lineHeight: 1.45, color: '#2f3741' }}>
              Bonsoir Alex. Demain, footing à 7&nbsp;h&nbsp;30, puis ta revue à 10&nbsp;h.
            </p>
          </div>
          <div className="card" style={{ marginTop: 14, padding: '16px 18px' }}>
            <div className="card-head">
              <IconChip icon="calendar_month" tone="violet" size={40} />
              <span className="card-title" style={{ fontSize: 21 }}>
                Agenda
              </span>
            </div>
            <div style={{ marginTop: 10, fontSize: 19, color: '#2f3741', display: 'flex', gap: 12, alignItems: 'center', opacity: 1 - moved }}>
              <b style={{ width: 66 }}>07:30</b>
              <i style={{ width: 4, height: 30, borderRadius: 4, background: '#7c3aed' }} />
              Footing 🏃
            </div>
            <div style={{ marginTop: 8, fontSize: 19, color: '#2f3741', display: 'flex', gap: 12, alignItems: 'center' }}>
              <b style={{ width: 66 }}>10:00</b>
              <i style={{ width: 4, height: 30, borderRadius: 4, background: '#a78bfa' }} />
              Revue de conception
            </div>
          </div>
        </div>
      </div>

      {/* LIA's notification */}
      {s >= 60 && (
        <div className="notif" style={{ left: 12, right: 12, top: lerp(-300, 72, n), opacity: clamp(n * 1.5), background: 'rgba(252,252,253,0.97)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ position: 'relative', width: 40, height: 40 }}>
              <LiaMark size={40} />
            </div>
            <b style={{ fontSize: 21 }}>LIA</b>
            <span style={{ marginLeft: 'auto', fontSize: 17, color: '#6b7280' }}>maintenant</span>
          </div>
          <div style={{ position: 'relative', marginTop: 12, minHeight: 168 }}>
            <div style={{ opacity: 1 - moved }}>
              <p style={{ fontSize: 21, lineHeight: 1.4, color: '#1d2430' }}>{NOTICE}</p>
              <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
                <span className="btn btn-primary" style={{ flex: 1, fontSize: 20, padding: '14px 0', transform: `scale(${s >= TAP && s < TAP + 8 ? 0.95 : 1})` }}>
                  Oui, vas-y
                </span>
                <span className="btn btn-ghost" style={{ flex: 1, fontSize: 20, padding: '14px 0', background: 'rgba(0,0,0,0.05)' }}>
                  Non merci
                </span>
              </div>
            </div>
            {moved > 0 && (
              <div style={{ position: 'absolute', inset: 0, opacity: moved, transform: `translateY(${(1 - moved) * 12}px)` }}>
                <p style={{ fontSize: 23, lineHeight: 1.35, fontWeight: 650, color: '#1d2430' }}>C’est déplacé — tu courras au sec. ☀️</p>
                <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderRadius: 16, background: 'rgba(124,58,237,0.1)', border: '1px solid rgba(124,58,237,0.3)' }}>
                  <span className="sym" style={{ fontSize: 30, color: '#7c3aed' }}>
                    directions_run
                  </span>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: '#4c1d95' }}>Footing</div>
                    <div style={{ fontSize: 17, color: '#5b21b6' }}>jeudi · 7:00 – 8:00</div>
                  </div>
                </div>
              </div>
            )}
          </div>
          <Tap x={105} y={200} t={tapT} />
        </div>
      )}
    </>
  );
}

export function Anticipate() {
  const lf = useCurrentFrame();
  const s = lf - LEAD;
  const enter = pop(s, -16, SOFT);
  const exit = ramp(s, 440, 40, easeIn);
  const bob = Math.sin(s / 38) * 8;
  const zoom = ramp(s, 64, 70, easeOut) * (1 - ramp(s, 330, 90, easeOut) * 0.4);
  const rain = ramp(s, -10, 30) * (1 - ramp(s, TAP + 10, 50));
  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <Rain s={s} opacity={rain * (1 - exit)} />
      <div style={{ position: 'absolute', inset: 0, perspective: 2200 }}>
        <Phone
          time="21:14"
          style={{
            left: 1040,
            top: 80 + bob,
            transformOrigin: '50% 22%',
            opacity: clamp(enter * 1.4) * (1 - exit),
            transform: `translateY(${(1 - enter) * 500 - exit * 260 + zoom * 120}px) rotateY(${lerp(-34, -14, enter) + exit * 8}deg) rotateZ(${lerp(8, 2, enter)}deg) scale(${(1 + zoom * 0.38) * (1 + exit * 0.45)})`,
            filter: exit > 0.05 ? `blur(${(exit * 14).toFixed(1)}px)` : undefined,
          }}
        >
          <Screen s={s} />
        </Phone>
      </div>
      <KineticBlock frame={s} start={20} end={236} lines={COPY.anticipate.first} x={110} y={330} size={150} gap={1.0} slam />
      <KineticBlock frame={s} start={246} end={458} lines={COPY.anticipate.second} x={110} y={330} size={150} gap={1.0} slam />
    </div>
  );
}
