/**
 * The six chapters' illustrated enumerations (`parts/Bento.tsx`), each after
 * its strong scene: what LIA knows, what it produces, how it anticipates,
 * where it follows you, the circle it connects, and the control you keep.
 *
 * Tile art is drawn from the product's own vocabulary: a memory's qualifiers
 * (`memories.field_*`), the routine studio's three triggers
 * (`scheduled_actions.studio.kind_*`), the Tools' mail menu with its yellow
 * assist star (`workbench.mail.*`, ADR-372), the results card
 * (`dashboard.results.*`). Names, files and figures are fictitious.
 */
import React, { type ReactNode } from 'react';
import { Img, staticFile } from 'remotion';
import { Archive, FolderInput, Sparkles, UserPlus } from 'lucide-react';
import { COPY } from '../copy';
import { BOUNCY, SNAPPY, clamp, easeInOut, easeOut, lerp, pop, ramp } from '../motion';
import { IconChip, TONES, hexA, type Tone } from '../parts/Brand';
import type { ChapterSpec, Tile } from '../parts/Bento';
import { ENUMERATIONS, type EnumerationId } from '../timing';
import { Companion, type CompanionCharacter } from '../parts/Companion';
import { Cursor, Toggle } from '../parts/Ui';

const tile = (words: readonly [string, string], rest: Omit<Tile, 'title' | 'text'>): Tile => ({ title: words[0], text: words[1], ...rest });

/** A chapter's clock comes from `timing.ts`, shared with the sound cues. */
function clock(id: EnumerationId, count: number) {
  const { first, step, tiles, exit } = ENUMERATIONS[id];
  if (tiles !== count) throw new Error(`Enumeration ${id}: ${count} tiles drawn, ${tiles} timed`);
  return { first, step, exit };
}

/** A light app card, as the product draws them, inside a marketing tile. */
function AppCard({ children, width, style }: { children: ReactNode; width: number; style?: React.CSSProperties }) {
  return (
    <div className="card" style={{ width, padding: '16px 18px', borderRadius: 20, boxShadow: '0 18px 40px rgba(0,0,0,0.35)', ...style }}>
      {children}
    </div>
  );
}

function Chip({ t, at, tone, icon, children, size = 15 }: { t: number; at: number; tone: Tone; icon?: string; children: ReactNode; size?: number }) {
  const p = pop(t, at, SNAPPY);
  return (
    <span
      className="pill"
      style={{
        fontSize: size,
        padding: '5px 12px',
        gap: 6,
        borderColor: hexA(TONES[tone][1], 0.28),
        background: hexA(TONES[tone][1], 0.1),
        color: TONES[tone][1],
        opacity: clamp(p * 1.5),
        transform: `scale(${0.6 + 0.4 * p})`,
        whiteSpace: 'nowrap',
      }}
    >
      {icon && <span className="sym" style={{ fontSize: size * 1.15 }}>{icon}</span>}
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- know -- */

const memoryArt = (t: number) => (
  <AppCard width={350}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <IconChip icon="group" tone="rose" size={42} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, letterSpacing: '0.08em', color: '#6b7480' }}>RELATIONS</div>
        <div style={{ fontSize: 20, fontWeight: 720, color: '#333c45', whiteSpace: 'nowrap' }}>Sophie aime la montagne</div>
      </div>
    </div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 12 }}>
      <Chip t={t} at={12} tone="amber" icon="priority_high">Importance · Haute</Chip>
      <Chip t={t} at={20} tone="violet" icon="tag">Sujet déclencheur · week-end</Chip>
      <Chip t={t} at={28} tone="emerald" icon="sentiment_satisfied">Terrain positif</Chip>
    </div>
  </AppCard>
);

const PERSONAS: Array<{ character: CompanionCharacter; variant: 'female' | 'male' }> = [
  { character: 'bip', variant: 'female' },
  { character: 'moss', variant: 'male' },
  { character: 'lumen', variant: 'female' },
  { character: 'oscar', variant: 'male' },
];

const personasArt = (t: number) => (
  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
    <div style={{ display: 'flex', gap: 4 }}>
      {PERSONAS.map(({ character, variant }, i) => {
        const p = pop(t, 6 + i * 7, BOUNCY);
        return (
          <div key={character} style={{ opacity: clamp(p * 2), transform: `translateY(${(1 - p) * 40}px)` }}>
            <Companion
              id={`persona-${character}`}
              character={character}
              variant={variant}
              frame={t - 6 - i * 7}
              size={86}
              cues={[
                { at: 0, expression: i % 2 ? 'joy' : 'excited' },
                { at: 0, gaze: { x: (1.5 - i) * 0.25, y: 0 } },
                { at: 34 + i * 9, gesture: 'perk' },
                { at: 90 + i * 7, gaze: { x: 0, y: 0 } },
              ]}
            />
          </div>
        );
      })}
    </div>
    <div style={{ display: 'flex', gap: 6 }}>
      {['Ami', 'Coach', 'Poète', 'Philosophe'].map((name, i) => (
        <Chip key={name} t={t} at={30 + i * 6} tone="indigo" size={14}>{name}</Chip>
      ))}
    </div>
  </div>
);

const moodArt = (t: number) => (
  <span className="pill" style={{ fontSize: 17, padding: '6px 14px', background: 'rgba(255,255,255,0.1)', borderColor: 'rgba(255,255,255,0.2)', color: '#e8ecff', opacity: clamp(ramp(t, 14, 12) * 1.2) }}>
    <span style={{ fontSize: 19 }}>😌</span> Serein
  </span>
);

export const KNOW: ChapterSpec = {
  id: 'know',
  index: 1,
  lead: COPY.know.lead,
  title: COPY.know.title,
  cols: 3,
  rows: 3,
  presenter: 'bip',
  ...clock('know', 7),
  tiles: [
    tile(COPY.know.memory, { icon: 'neurology', tone: 'violet', col: 0, row: 0, cols: 2, art: memoryArt }),
    tile(COPY.know.interests, { icon: 'interests', tone: 'sky', col: 2, row: 0 }),
    tile(COPY.know.habits, { icon: 'event_repeat', tone: 'teal', col: 0, row: 1 }),
    tile(COPY.know.commitments, { icon: 'handshake', tone: 'amber', col: 1, row: 1 }),
    tile(COPY.know.portrait, { icon: 'auto_stories', tone: 'indigo', col: 2, row: 1 }),
    tile(COPY.know.psyche, { icon: 'psychology', tone: 'fuchsia', col: 0, row: 2, art: moodArt }),
    tile(COPY.know.personas, { icon: 'face', tone: 'rose', col: 1, row: 2, cols: 2, art: personasArt }),
  ],
};

/* ----------------------------------------------------------------- act -- */

const FILES: Array<{ ext: string; color: string; name: string }> = [
  { ext: 'DOCX', color: '#2b579a', name: 'Compte-rendu' },
  { ext: 'XLSX', color: '#217346', name: 'Budget 2027' },
  { ext: 'PPTX', color: '#c43e1c', name: 'Pitch client' },
];

const documentsArt = (t: number) => (
  <div style={{ display: 'flex', gap: 12 }}>
    {FILES.map((file, i) => {
      const p = pop(t, 8 + i * 8, BOUNCY);
      const done = ramp(t, 40 + i * 8, 10);
      return (
        <div key={file.ext} style={{ width: 104, height: 140, borderRadius: 14, background: '#f8f6f2', boxShadow: '0 14px 30px rgba(0,0,0,0.35)', overflow: 'hidden', position: 'relative', opacity: clamp(p * 1.6), transform: `translateY(${(1 - p) * 30}px) rotate(${(i - 1) * 3 * (1 - p)}deg)` }}>
          <div style={{ height: 46, background: file.color, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: 18, letterSpacing: '0.06em' }}>{file.ext}</div>
          <div style={{ padding: '10px 10px 0' }}>
            {[0.9, 0.7, 0.8].map((w, k) => (
              <div key={k} style={{ height: 6, width: `${w * 100}%`, borderRadius: 3, background: '#dcd8d1', marginBottom: 6 }} />
            ))}
            <div style={{ marginTop: 6, fontSize: 12.5, fontWeight: 700, color: '#333c45', whiteSpace: 'nowrap' }}>{file.name}</div>
          </div>
          <div style={{ position: 'absolute', right: 6, top: 52, width: 24, height: 24, borderRadius: 12, background: '#059669', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', transform: `scale(${done})` }}>
            <span className="sym" style={{ fontSize: 17 }}>check</span>
          </div>
        </div>
      );
    })}
  </div>
);

const MENU = [
  { icon: Archive, label: 'Archiver' },
  { icon: FolderInput, label: 'Déplacer vers…' },
  { icon: UserPlus, label: 'Ajouter l’expéditeur aux contacts' },
];

const menusArt = (t: number) => {
  const open = pop(t, 6, SNAPPY);
  const hover = ramp(t, 40, 8);
  const press = clamp(1 - Math.abs(t - 58) / 6);
  const cursorT = ramp(t, 24, 30, easeInOut);
  return (
    <div style={{ position: 'relative', width: 340, height: 186 }}>
      <AppCard width={322} style={{ position: 'absolute', left: 0, top: 4, padding: '8px 8px', opacity: clamp(open * 1.6), transform: `scale(${0.85 + 0.15 * open})`, transformOrigin: 'left top' }}>
        {MENU.map(({ icon: Icon, label }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', fontSize: 16, color: '#333c45', whiteSpace: 'nowrap' }}>
            <Icon size={18} strokeWidth={2} color="#5d6670" />
            {label}
          </div>
        ))}
        <div style={{ height: 1, background: '#e3dfd8', margin: '4px 6px' }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px', borderRadius: 10, fontSize: 16, fontWeight: 700, color: '#00619b', background: `rgba(0,97,155,${0.06 + hover * 0.1 + press * 0.08})` }}>
          <Sparkles size={18} strokeWidth={2.2} color="#d4a017" fill="#facc15" />
          Demander à LIA
        </div>
      </AppCard>
      <Cursor x={lerp(300, 150, cursorT)} y={lerp(30, 160, cursorT)} press={press} ripple={press} />
    </div>
  );
};

export const ACT: ChapterSpec = {
  id: 'act',
  index: 2,
  lead: COPY.act.lead,
  title: COPY.act.title,
  titleSize: 88,
  cols: 3,
  rows: 3,
  presenter: 'bip',
  ...clock('act', 7),
  tiles: [
    tile(COPY.act.documents, { icon: 'description', tone: 'blue', col: 0, row: 0, cols: 2, art: documentsArt }),
    tile(COPY.act.images, { icon: 'image', tone: 'fuchsia', col: 2, row: 0 }),
    tile(COPY.act.skills, { icon: 'auto_awesome', tone: 'indigo', col: 0, row: 1 }),
    tile(COPY.act.mcp, { icon: 'extension', tone: 'cyan', col: 1, row: 1 }),
    tile(COPY.act.spaces, { icon: 'library_books', tone: 'teal', col: 2, row: 1 }),
    tile(COPY.act.menus, { icon: 'ads_click', tone: 'amber', col: 0, row: 2, cols: 2, art: menusArt }),
    tile(COPY.act.pages, { icon: 'widgets', tone: 'orange', col: 2, row: 2 }),
  ],
};

/* ------------------------------------------------------------- foresee -- */

const TRIGGERS = [
  { icon: 'schedule', title: 'À l’heure dite', detail: 'Tous les jours · 07:30' },
  { icon: 'bolt', title: 'Quand une condition est remplie', detail: 'Un mail correspond' },
  { icon: 'webhook', title: 'Quand un autre système l’appelle', detail: 'Appel signé (webhook)' },
];

const routinesArt = (t: number) => {
  const active = t < 70 ? 0 : t < 130 ? 1 : 2;
  return (
    <AppCard width={350} style={{ padding: '16px 16px 14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <IconChip icon="event_repeat" tone="violet" size={38} />
        <div style={{ fontSize: 18, fontWeight: 760, color: '#333c45' }}>Résumé des mails clients</div>
      </div>
      <div style={{ marginTop: 12, fontSize: 12.5, fontWeight: 760, letterSpacing: '0.08em', color: '#6b7480' }}>DÉCLENCHEUR</div>
      <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {TRIGGERS.map((trigger, i) => {
          const p = pop(t, 10 + i * 8, SNAPPY);
          const on = i === active;
          return (
            <div key={trigger.icon} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 12, border: `1.5px solid ${on ? '#00619b' : '#e3dfd8'}`, background: on ? 'rgba(0,97,155,0.07)' : '#fbfaf8', opacity: clamp(p * 1.5), transform: `translateX(${(1 - p) * 24}px)` }}>
              <span className="sym" style={{ fontSize: 22, color: on ? '#00619b' : '#8a929b' }}>{trigger.icon}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14.5, fontWeight: 720, color: '#333c45', whiteSpace: 'nowrap' }}>{trigger.title}</div>
                <div style={{ fontSize: 12.5, color: '#6b7480', whiteSpace: 'nowrap' }}>{trigger.detail}</div>
              </div>
            </div>
          );
        })}
      </div>
      {[
        { label: 'Demander mon accord avant d’exécuter', at: 44 },
        { label: 'Ne me prévenir que s’il y a du nouveau', at: 52 },
      ].map(({ label, at }) => (
        <div key={label} style={{ marginTop: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, opacity: ramp(t, at - 8, 10) }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#333c45', whiteSpace: 'nowrap' }}>{label}</span>
          <div style={{ position: 'relative', width: 52, height: 30, flex: 'none' }}>
            <div style={{ position: 'absolute', left: 0, top: 0, transform: 'scale(0.7)', transformOrigin: 'left top' }}>
              <Toggle on={ramp(t, at, 10)} />
            </div>
          </div>
        </div>
      ))}
    </AppCard>
  );
};

export const FORESEE: ChapterSpec = {
  id: 'foresee',
  index: 3,
  lead: COPY.foresee.lead,
  title: COPY.foresee.title,
  cols: 3,
  rows: 3,
  presenter: 'bip',
  ...clock('foresee', 6),
  tiles: [
    tile(COPY.foresee.proactive, { icon: 'notifications_active', tone: 'violet', col: 0, row: 0 }),
    tile(COPY.foresee.discussions, { icon: 'forum', tone: 'indigo', col: 1, row: 0 }),
    tile(COPY.foresee.reminders, { icon: 'alarm', tone: 'amber', col: 2, row: 0 }),
    tile(COPY.foresee.routines, { icon: 'event_repeat', tone: 'teal', col: 0, row: 1, cols: 2, rows: 2, art: routinesArt }),
    tile(COPY.foresee.push, { icon: 'phonelink_ring', tone: 'sky', col: 2, row: 1 }),
    tile(COPY.foresee.radio, { icon: 'radio', tone: 'rose', col: 2, row: 2 }),
  ],
};

/* ------------------------------------------------------------ channels -- */

const liveArt = (t: number) => {
  const pulse = 0.5 + 0.5 * Math.sin(t / 7);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
      <div style={{ position: 'relative', width: 84, height: 84 }}>
        <div style={{ position: 'absolute', inset: -14 - pulse * 10, borderRadius: '50%', background: 'radial-gradient(closest-side, rgba(139,92,246,0.45), transparent)' }} />
        <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', background: 'linear-gradient(135deg, #4f8dfd, #8b5cf6)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 10px 30px rgba(79,141,253,0.45)' }}>
          <span className="sym" style={{ fontSize: 42, color: '#fff' }}>graphic_eq</span>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, height: 54 }}>
          {Array.from({ length: 22 }, (_, i) => {
            const v = 0.2 + 0.8 * Math.abs(Math.sin(t / 5 + i * 0.7) * Math.sin(t / 11 + i * 0.33));
            return <i key={i} style={{ width: 6, height: 54 * v, borderRadius: 4, background: i % 3 ? '#a5b4fc' : '#67e8f9', opacity: 0.9 }} />;
          })}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Chip t={t} at={10} tone="violet" icon="podcasts">Live</Chip>
          <Chip t={t} at={18} tone="cyan" icon="record_voice_over">Live direct</Chip>
        </div>
      </div>
    </div>
  );
};

const pictureArt = (file: string, focus = '50% 50%') => (t: number, size: { w: number; h: number }) => (
  <div style={{ width: size.w, height: size.h, borderRadius: 18, overflow: 'hidden', boxShadow: '0 16px 36px rgba(0,0,0,0.45)', border: '1px solid rgba(255,255,255,0.18)' }}>
    <Img src={staticFile(file)} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: focus, transform: `scale(${1.04 + 0.08 * ramp(t, 0, 420, easeOut)})` }} />
  </div>
);

export const CHANNELS: ChapterSpec = {
  id: 'channels',
  index: 4,
  lead: COPY.channels.lead,
  title: COPY.channels.title,
  cols: 3,
  rows: 3,
  presenter: 'bip',
  ...clock('channels', 7),
  tiles: [
    tile(COPY.channels.live, { icon: 'mic', tone: 'violet', col: 0, row: 0, cols: 2, art: liveArt }),
    tile(COPY.channels.calls, { icon: 'call', tone: 'emerald', col: 2, row: 0 }),
    tile(COPY.channels.telegram, { icon: 'send', tone: 'sky', col: 0, row: 1 }),
    tile(COPY.channels.sms, { icon: 'sms', tone: 'teal', col: 1, row: 1 }),
    tile(COPY.channels.apps, { icon: 'smartphone', tone: 'indigo', col: 2, row: 1 }),
    tile(COPY.channels.world, { icon: 'public', tone: 'emerald', col: 0, row: 2, cols: 2, art: pictureArt('promo/lia-world.jpg', '50% 45%') }),
    tile(COPY.channels.languages, { icon: 'translate', tone: 'amber', col: 2, row: 2 }),
  ],
};

/* -------------------------------------------------------------- circle -- */

const Person = ({ initial, color, name }: { initial: string; color: string; name: string }) => (
  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
    <div style={{ width: 66, height: 66, borderRadius: '50%', background: color, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 30, fontWeight: 800, boxShadow: `0 10px 26px ${hexA(color, 0.55)}` }}>{initial}</div>
    <div style={{ fontSize: 16, fontWeight: 700, color: '#e8ecff' }}>{name}</div>
  </div>
);

const relayArt = (t: number, size: { w: number; h: number }) => {
  const travel = ramp(t, 18, 44, easeInOut);
  const delivered = ramp(t, 64, 10);
  const pillW = 196;
  return (
    <div style={{ position: 'relative', width: size.w, height: 186 }}>
      <svg width={size.w} height={60} style={{ position: 'absolute', left: 0, top: 6 }}>
        <defs>
          <linearGradient id="relay-line" x1="0" x2="1">
            <stop offset="0" stopColor="#4f8dfd" />
            <stop offset="1" stopColor="#38d4f5" />
          </linearGradient>
        </defs>
        <path d={`M76 33 Q ${size.w / 2} ${4 - 6 * travel} ${size.w - 76} 33`} stroke="url(#relay-line)" strokeWidth={3} fill="none" strokeDasharray="6 7" strokeDashoffset={-t * 0.8} opacity={0.85} />
      </svg>
      <div style={{ position: 'absolute', left: 10, top: 6 }}>
        <Person initial="A" color="#2563eb" name="Alex" />
      </div>
      <div style={{ position: 'absolute', right: 10, top: 6 }}>
        <Person initial="L" color="#db2777" name="Léa" />
      </div>
      <div
        className="pill"
        style={{
          position: 'absolute',
          left: lerp(0, size.w - pillW, travel),
          top: 112,
          width: pillW,
          justifyContent: 'center',
          fontSize: 15,
          padding: '7px 0',
          background: 'rgba(0,97,155,0.9)',
          borderColor: 'transparent',
          color: '#fff',
          whiteSpace: 'nowrap',
          opacity: ramp(t, 12, 8),
        }}
      >
        « J’arrive dans 10 min »
      </div>
      <div style={{ position: 'absolute', right: 0, top: 154, opacity: delivered }}>
        <Chip t={t} at={66} tone="emerald" icon="done_all" size={14}>Relayé par LIA</Chip>
      </div>
    </div>
  );
};

export const CIRCLE: ChapterSpec = {
  id: 'circle',
  index: 5,
  lead: COPY.circle.lead,
  title: COPY.circle.title,
  titleSize: 88,
  cols: 3,
  rows: 2,
  presenter: 'bip',
  ...clock('circle', 5),
  tiles: [
    tile(COPY.circle.relay, { icon: 'forward_to_inbox', tone: 'blue', col: 0, row: 0, cols: 2, art: relayArt }),
    tile(COPY.circle.connections, { icon: 'group_add', tone: 'rose', col: 2, row: 0 }),
    tile(COPY.circle.sharing, { icon: 'calendar_month', tone: 'violet', col: 0, row: 1 }),
    tile(COPY.circle.capabilities, { icon: 'share', tone: 'cyan', col: 1, row: 1 }),
    tile(COPY.circle.log, { icon: 'visibility', tone: 'amber', col: 2, row: 1 }),
  ],
};

/* ------------------------------------------------------------- control -- */

const RESULTS = [
  { icon: 'task_alt', label: 'Actions réussies', value: 1284, tone: 'emerald' as Tone },
  { icon: 'event_repeat', label: 'Routines réussies', value: 312, tone: 'violet' as Tone },
  { icon: 'handshake', label: 'Engagements clôturés', value: 47, tone: 'amber' as Tone },
];

const registersArt = (t: number) => (
  <AppCard width={350} style={{ padding: '12px 16px' }}>
    <div style={{ fontSize: 15, fontWeight: 760, color: '#333c45', marginBottom: 6 }}>Ce que LIA a accompli</div>
    {RESULTS.map((row, i) => {
      const n = Math.round(row.value * ramp(t, 8 + i * 6, 46, easeOut));
      return (
        <div key={row.label} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 0', borderTop: i ? '1px solid #ebe7e1' : undefined }}>
          <IconChip icon={row.icon} tone={row.tone} size={32} />
          <span style={{ flex: 1, fontSize: 15, color: '#4a535c', whiteSpace: 'nowrap' }}>{row.label}</span>
          <span style={{ fontSize: 22, fontWeight: 800, color: '#333c45', fontVariantNumeric: 'tabular-nums' }}>{n.toLocaleString('fr-FR')}</span>
        </div>
      );
    })}
  </AppCard>
);

const meterArt = (t: number) => (
  <span className="pill" style={{ fontSize: 16, padding: '6px 12px', background: 'rgba(52,211,153,0.12)', borderColor: 'rgba(52,211,153,0.35)', color: '#6ee7b7', fontVariantNumeric: 'tabular-nums', opacity: ramp(t, 10, 10) }}>
    • {(0.0018 * ramp(t, 10, 40, easeOut)).toFixed(4).replace('.', ',')} €
  </span>
);

export const CONTROL: ChapterSpec = {
  id: 'control',
  index: 6,
  lead: COPY.control.lead,
  title: COPY.control.title,
  cols: 3,
  rows: 3,
  presenter: 'bip',
  ...clock('control', 7),
  tiles: [
    tile(COPY.control.registers, { icon: 'fact_check', tone: 'emerald', col: 0, row: 0, cols: 2, art: registersArt }),
    tile(COPY.control.cost, { icon: 'payments', tone: 'teal', col: 2, row: 0, art: meterArt }),
    tile(COPY.control.approval, { icon: 'verified_user', tone: 'blue', col: 0, row: 1 }),
    tile(COPY.control.export, { icon: 'download', tone: 'sky', col: 1, row: 1 }),
    tile(COPY.control.security, { icon: 'shield_lock', tone: 'indigo', col: 2, row: 1 }),
    tile(COPY.control.dashboards, { icon: 'monitoring', tone: 'orange', col: 0, row: 2, cols: 2, art: pictureArt('promo/grafana-overview.png', '50% 20%') }),
    tile(COPY.control.openSource, { icon: 'code', tone: 'violet', col: 2, row: 2 }),
  ],
};

