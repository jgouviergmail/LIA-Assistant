/**
 * Section « simple » (beats 144-151, 72-76 s, the build before the last
 * hit): the same conversation on a computer and on a phone, then four
 * settings switched on in four clicks — « Quelques clics. Aucune commande à
 * retenir. »
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { CircleCheck, Settings, User } from 'lucide-react';
import { COPY } from '../copy';
import { SNAPPY, SOFT, clamp, easeIn, easeInOut, easeOut, lerp, pop, ramp } from '../motion';
import { IconChip, type Tone } from '../parts/Brand';
import { AppWindow, Cursor, MobileBar, Phone, Toggle } from '../parts/Ui';
import { Kinetic } from '../parts/Type';
import { Thread, makeSpline } from '../parts/Thread';

const LEAD = 10;

function Conversation({ compact = false }: { compact?: boolean }) {
  const f = compact ? 0.82 : 1;
  return (
    <div style={{ padding: compact ? '18px 16px' : '26px 28px' }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div className="avatar-dot" style={{ width: 46 * f, height: 46 * f }}>
          <User size={22 * f} />
        </div>
        <div className="bubble-user" style={{ fontSize: 23 * f, padding: `${14 * f}px ${20 * f}px` }}>
          Je vais avoir 30&nbsp;min de retard ce soir — préviens ma femme et décale mon rdv de 18&nbsp;h&nbsp;30
        </div>
      </div>
      <div className="card" style={{ marginTop: 22 * f, marginLeft: compact ? 0 : 60, padding: `${18 * f}px ${22 * f}px`, display: 'flex', alignItems: 'center', gap: 18 * f, borderColor: 'rgba(16,185,129,0.5)' }}>
        <CircleCheck size={44 * f} color="#059669" />
        <div>
          <div style={{ fontSize: 26 * f, fontWeight: 750, color: '#065f46' }}>E-mail envoyé à Sophie</div>
          <div style={{ fontSize: 21 * f, color: '#2f3741' }}>📅 «&nbsp;Point projet&nbsp;» décalé à 19&nbsp;h</div>
        </div>
      </div>
    </div>
  );
}

const SETTINGS: Array<{ icon: string; tone: Tone; title: string; desc: string }> = [
  { icon: 'neurology', tone: 'indigo', title: 'Mémoire à long terme', desc: 'Ce que LIA retient de toi' },
  { icon: 'mic', tone: 'sky', title: 'Mode vocal', desc: 'Parle-lui, écoute-la' },
  { icon: 'wb_sunny', tone: 'amber', title: 'Briefing du jour', desc: 'Ta journée, chaque matin' },
  { icon: 'notifications_active', tone: 'orange', title: 'Proactivité', desc: 'Elle te prévient au bon moment' },
];
const CLICKS = [132, 162, 192, 222];

export function Simple() {
  const s = useCurrentFrame() - LEAD;
  const flash = 1 - ramp(s, -10, 22, easeOut);
  const devicesIn = pop(s, -6, SOFT);
  const recede = ramp(s, 112, 24, easeInOut);
  const panelIn = pop(s, 118, SNAPPY);
  const exit = ramp(s, 236, 14, easeIn);

  const sync = makeSpline([
    { x: 1006, y: 560 },
    { x: 1150, y: 470 },
    { x: 1290, y: 560 },
  ]);
  const syncHead = ramp(s, 24, 40, easeInOut);

  // The cursor visits each switch in turn and clicks it on a beat.
  const toggleAt = (i: number) => ({ x: 1359, y: 428 + i * 112 });
  let cursor = { x: 1580, y: 1010 };
  for (let i = 0; i < CLICKS.length; i++) {
    const t = ramp(s, CLICKS[i] - 20, 18, easeInOut);
    const target = toggleAt(i);
    cursor = { x: lerp(cursor.x, target.x, t), y: lerp(cursor.y, target.y, t) };
  }
  const lastClick = CLICKS.filter((c) => s >= c).pop();
  const ripple = lastClick === undefined ? 0 : clamp((s - lastClick) / 18);

  return (
    <div style={{ position: 'absolute', inset: 0, opacity: 1 - exit }}>
      <div style={{ position: 'absolute', inset: 0, perspective: 2200, filter: recede > 0.02 ? `blur(${(recede * 7).toFixed(1)}px)` : undefined, opacity: 1 - recede * 0.55 }}>
        <div style={{ position: 'absolute', left: 120, top: 250, transform: `translateX(${(1 - devicesIn) * -300}px) rotateY(${lerp(30, 12, devicesIn)}deg) scale(${(0.86 + 0.14 * devicesIn) * (1 - recede * 0.08)})`, opacity: clamp(devicesIn * 1.5), transformOrigin: '100% 50%' }}>
          <AppWindow width={900} height={600} active="chat" endIcons={0}>
            <Conversation />
          </AppWindow>
        </div>
        <Phone
          time="18:03"
          width={360}
          height={740}
          style={{ left: 1300, top: 190, transform: `translateX(${(1 - devicesIn) * 300}px) rotateY(${lerp(-30, -12, devicesIn)}deg) scale(${1 - recede * 0.08})`, opacity: clamp(devicesIn * 1.5) }}
        >
          <MobileBar />
          <Conversation compact />
        </Phone>
        <Thread id="sync" spline={sync} head={syncHead} tail={Math.max(0, syncHead - 0.6)} width={0.8} opacity={(1 - recede) * ramp(s, 24, 6)} />
      </div>

      <Kinetic frame={s} start={4} end={118} text={COPY.simple.devices} x={960} y={92} size={72} align="center" slam />

      {s >= 112 && (
        <div
          className="card"
          style={{
            position: 'absolute',
            left: 960 - 470,
            top: 290,
            width: 940,
            padding: '28px 34px 18px',
            opacity: clamp(panelIn * 1.5),
            transform: `translateY(${(1 - panelIn) * 80}px) scale(${0.92 + 0.08 * panelIn})`,
            boxShadow: '0 60px 120px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.12), 0 0 80px rgba(79,141,253,0.25)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontSize: 32, fontWeight: 750, color: '#2f3741' }}>
            <Settings size={34} color="#00619b" /> Réglages
          </div>
          {SETTINGS.map((row, i) => {
            const on = ramp(s, CLICKS[i], 8, easeOut);
            return (
              <div key={row.title} style={{ display: 'flex', alignItems: 'center', gap: 20, height: 112, borderTop: i ? '1px solid #e2ded6' : undefined, marginTop: i ? 0 : 14 }}>
                <IconChip icon={row.icon} tone={row.tone} size={60} />
                <div>
                  <div style={{ fontSize: 28, fontWeight: 700, color: '#2f3741' }}>{row.title}</div>
                  <div style={{ fontSize: 21, color: '#6b7480' }}>{row.desc}</div>
                </div>
                <div style={{ marginLeft: 'auto' }}>
                  <Toggle on={on} />
                </div>
              </div>
            );
          })}
        </div>
      )}
      {s >= 118 && s < 240 && <Cursor x={cursor.x} y={cursor.y} press={CLICKS.some((c) => s >= c && s < c + 6) ? 1 : 0} ripple={ripple} />}

      <Kinetic frame={s} start={124} end={244} text={COPY.simple.clicks.split('. ')[0] + '.'} x={960} y={70} size={66} align="center" slam />
      <Kinetic frame={s} start={168} end={244} text={COPY.simple.clicks.split('. ')[1]} x={960} y={160} size={52} align="center" weight={700} color="#c9d2ee" />
      {flash > 0 && <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 48%, rgba(255,255,255,0.9), rgba(170,185,255,0.25) 45%, transparent 75%)', opacity: flash }} />}
    </div>
  );
}
