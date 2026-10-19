import React from 'react';
import { AbsoluteFill } from 'remotion';
import {
  ArrowDownToLine,
  AudioLines,
  BookUser,
  Captions,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  Clock3,
  FileText,
  Headphones,
  Lightbulb,
  Mic,
  Moon,
  MoreHorizontal,
  Pencil,
  PhoneOff,
  Pin,
  Save,
  Settings2,
  ShieldCheck,
  Square,
  Trash2,
  X,
} from 'lucide-react';
import { buttonVariants } from '@/components/ui/button-variants';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { formatElapsed } from '@/lib/meetings/format';
import type { MeetingReport, TranscriptTurn } from '@/types/meetings';
import type { Memory } from '@/hooks/useMemories';
import { FilmBip, FilmCursor, ease, uiSpring, type SceneProps } from './shared';
import './human-scenes.css';

/**
 * Three frame-directed, offline demonstrations. All names and records are
 * fictional. Native Badge/Textarea primitives, buttonVariants and meeting time
 * formatting are imported from the current application. The account-bound
 * LiveBanner, MemorySettings and meeting hooks are deliberately not mounted.
 * Their current DOM/content contracts are adapted below, enlarged for film.
 * No account, provider, microphone, storage, network or paid operation is used.
 */
export const HUMAN_SCENE_PROVENANCE = {
  kind: 'offline-scripted-demonstration',
  language: 'fr',
  genuineCapture: false,
  nativePrimitives: [
    'apps/web/src/components/ui/button-variants.ts',
    'apps/web/src/components/ui/badge.tsx',
    'apps/web/src/components/ui/textarea.tsx',
    'apps/web/src/lib/meetings/format.ts',
  ],
  adaptedSurfaces: [
    'apps/web/src/components/live/LiveBanner.tsx',
    'apps/web/src/components/live/LiveCaptions.tsx',
    'apps/web/src/components/live/LiveMeter.tsx',
    'apps/web/src/components/settings/MemorySettings.tsx',
    'apps/web/src/components/meetings/MeetingRecordingBanner.tsx',
    'apps/web/src/components/meetings/MeetingReportView.tsx',
  ],
  boundaries: 'Fictional records; condensed time; configured Live connection assumed; no live provider execution or performance claim.',
} as const;

const noop = () => undefined;

/** Native button variant contract without Radix Slot or account side effects. */
function Button({ variant, size, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'default' | 'ghost'; size?: 'default' | 'icon';
}) {
  return <button type="button" className={buttonVariants({ variant, size, className })} {...props} />;
}

const typeText = (text: string, frame: number, start: number, end: number) =>
  text.slice(0, Math.floor(text.length * Math.min(1, Math.max(0, (frame - start) / (end - start)))));

function Caret({ frame, visible = true }: { frame: number; visible?: boolean }) {
  return <span className="human-caret" style={{ opacity: visible && frame % 38 < 24 ? 1 : 0 }} />;
}

function NativePill({ children, success = false }: { children: React.ReactNode; success?: boolean }) {
  return <Badge variant={success ? 'success' : 'default'} className={`human-pill ${success ? 'human-pill--success' : ''}`}>{children}</Badge>;
}

function AppHeader({ section, children }: { section: string; children?: React.ReactNode }) {
  return <header className="human-app-header">
    <span className="human-app-wordmark">LIA<span /></span>
    <ChevronRight size={22} />
    <span className="human-app-section">{section}</span>
    <div className="human-header-end">{children}<span className="human-user-avatar">A</span></div>
  </header>;
}

function Waveform({ frame, active = true, small = false }: { frame: number; active?: boolean; small?: boolean }) {
  return <div className={`human-waveform ${small ? 'human-waveform--small' : ''}`} aria-hidden="true">
    {Array.from({ length: small ? 17 : 43 }, (_, index) => {
      const envelope = 0.22 + 0.78 * Math.sin(((index + 1) / (small ? 18 : 44)) * Math.PI);
      const wave = active ? 0.23 + 0.77 * Math.abs(Math.sin(frame * 0.105 + index * 1.27) * Math.cos(frame * 0.047 - index * 0.31)) : 0.035;
      return <i key={index} style={{ height: 5 + envelope * wave * (small ? 27 : 80), opacity: active ? 0.5 + wave * 0.5 : 0.28 }} />;
    })}
  </div>;
}

/** 8 seconds / 480 frames. A configured Live session, with visible captions. */
export function VoiceScene({ frame }: SceneProps) {
  const enter = uiSpring(frame, 0);
  const live = frame >= 53;
  const reply = frame >= 198;
  const question = typeText('Quels points faut-il confirmer ?', frame, 72, 166);
  const pointOne = ease(frame, 218, 248);
  const pointTwo = ease(frame, 275, 305);
  const captionResponse = typeText('Le tarif du projet et la date de démarrage.', frame, 200, 288);
  const cursorMove = ease(frame, 13, 48);
  const cursorOut = ease(frame, 71, 92);
  const drift = ease(frame, 305, 440);
  return <AbsoluteFill className="human-scene human-voice" lang="fr" data-fictional="true">
    <div className="human-voice-title" style={{ opacity: enter, transform: `translateY(${(1 - enter) * 26}px)` }}>
      <Headphones size={31} /><h1>Parler. Se comprendre.</h1>
    </div>
    <div className="human-voice-surface" style={{ opacity: enter, transform: `perspective(2200px) translateY(${(1 - enter) * 65}px) rotateY(${-2.4 + 2.4 * drift}deg) scale(${0.985 + 0.015 * drift})` }}>
      <AppHeader section="Conversation"><NativePill><AudioLines size={17} />Live</NativePill></AppHeader>
      <div className="human-voice-context"><span className="human-project-dot" /><strong>Point projet Atlas</strong><span>Claire · vendredi</span><MoreHorizontal size={25} /></div>
      <section className={`human-live-banner ${live ? 'human-live-banner--active' : ''}`} aria-label="Session live">
        <div className="human-live-controls">
          <AudioLines size={25} />
          <span>{live ? 'Tu parles avec LIA' : 'Session live'}</span>
          <div className="human-live-actions">
            <Button variant="ghost" size="icon" className="human-icon-button human-caption-toggle" aria-label="Afficher les sous-titres"><Captions size={24} /></Button>
            <Button variant="ghost" size="icon" className="human-icon-button" aria-label="Mettre la session en veille"><Moon size={23} /></Button>
            <Button variant="ghost" size="icon" className={`human-icon-button ${live ? 'human-mic-active' : ''}`} aria-label="Couper le micro"><Mic size={25} /></Button>
            <Button variant="ghost" size="icon" className="human-icon-button human-end-call" aria-label="Terminer la session live"><PhoneOff size={24} /></Button>
          </div>
        </div>
        <ol className="human-live-captions" style={{ opacity: ease(frame, 70, 94) }}>
          <li><strong>Toi</strong><span>{question}<Caret frame={frame} visible={frame < 175} /></span></li>
          <li style={{ opacity: ease(frame, 198, 220) }}><strong>LIA</strong><span>{captionResponse}<Caret frame={frame} visible={frame >= 198 && frame < 288} /></span></li>
        </ol>
        <div className="human-live-meter" style={{ opacity: ease(frame, 86, 110) }}><Clock3 size={17} />{formatElapsed(12 + Math.floor(Math.max(0, frame - 95) / 60))}<span>·</span><span>Facturé par le fournisseur sur ta clé</span></div>
      </section>
      <div className="human-voice-chat">
        <div className="human-voice-answer-label" style={{ opacity: ease(frame, 195, 219) }}><span className="human-lia-avatar">L</span><strong>LIA</strong><span>Les deux points à confirmer</span></div>
        <div className="human-confirm-point" style={{ opacity: pointOne, transform: `translateY(${(1 - pointOne) * 26}px)` }}><span className="human-point-check"><Check size={23} /></span><div><strong>Le tarif Atlas</strong><p>240 € dans la fiche, 270 € dans le mail.</p></div><span className="human-source-chip"><FileText size={16} />Fiche + e-mail</span></div>
        <div className="human-confirm-point" style={{ opacity: pointTwo, transform: `translateY(${(1 - pointTwo) * 26}px)` }}><span className="human-point-check"><Check size={23} /></span><div><strong>La date de démarrage</strong><p>Valider le créneau avec Claire.</p></div><span className="human-source-chip"><Clock3 size={16} />Prochain échange</span></div>
      </div>
      <footer className="human-live-composer"><Mic size={24} /><span>La session live est en cours — parle, ou termine-la pour écrire.</span><Waveform frame={frame} active={live} small /></footer>
    </div>
    <div className="human-voice-companion" style={{ opacity: ease(frame, 20, 57), transform: `translateY(${Math.sin(frame / 50) * 5}px)` }}><div className="human-bip-shadow" /><FilmBip frame={frame} size={325} expression={reply && frame < 315 ? 'speaking' : reply ? 'joy' : 'attentive'} gazeX={reply ? -0.15 : -0.5} /><div className="human-companion-status"><span className={reply ? 'human-status-speaking' : ''} />{!live ? 'Prête à écouter' : reply ? 'LIA te répond' : 'LIA écoute'}</div><Waveform frame={frame} active={live && (frame < 183 || frame > 204)} /></div>
    <div style={{ opacity: (1 - cursorOut) * ease(frame, 5, 15) }}><FilmCursor x={1532 - cursorMove * 143} y={635 - cursorMove * 206} pressed={frame >= 49 && frame <= 57} /></div>
  </AbsoluteFill>;
}

const originalMemory: Memory = {
  id: 'film-explicit-directive',
  content: 'Fais court, avec les sources.',
  category: 'procedural',
  emotional_weight: 0,
  trigger_topic: '',
  usage_nuance: '',
  importance: 0.9,
  pinned: true,
};
const editedMemory = 'Court le matin. Détaillé sur demande.';

/** A frame-directed adapter of the native MemorySettings pinned row. */
function NativeMemoryRow({ memory, frame, updated = false }: { memory: Memory; frame: number; updated?: boolean }) {
  return <div className="human-memory-row" style={{ borderColor: updated ? '#287b905c' : undefined }}>
    <span className="human-memory-emotion">⚪</span>
    <div className="human-memory-row-content"><p><Pin size={21} />{memory.content}</p><div className="human-memory-metadata"><Clock3 size={16} /><span>{updated ? 'À l’instant' : 'Aujourd’hui'}</span><span>·</span><span>Importance : 90 %</span></div></div>
    <div className="human-row-actions"><Button variant="ghost" size="icon" className="human-icon-button human-memory-pin" aria-label="Désépingler"><Pin size={22} /></Button><Button variant="ghost" size="icon" className={`human-icon-button ${frame > 158 && frame < 200 ? 'human-edit-hover' : ''}`} aria-label="Modifier la mémoire"><Pencil size={22} /></Button><Button variant="ghost" size="icon" className="human-icon-button human-delete" aria-label="Supprimer la mémoire"><Trash2 size={21} /></Button></div>
  </div>;
}

/** 8 seconds / 480 frames. Explicit directive, edit, save, durable-looking result. */
export function MemoryScene({ frame }: SceneProps) {
  const enter = uiSpring(frame, 0);
  const saved = frame >= 334;
  const dialog = ease(frame, 192, 218) * (1 - ease(frame, 328, 344));
  const inputText = frame < 231 ? originalMemory.content : typeText(editedMemory, frame, 234, 306);
  const memory: Memory = { ...originalMemory, content: saved ? editedMemory : originalMemory.content };
  const rowIn = uiSpring(frame, 106);
  const clickEdit = ease(frame, 146, 185);
  const toField = ease(frame, 200, 231);
  const clickSave = ease(frame, 307, 325);
  const cursorX = frame < 200 ? 1432 + clickEdit * 255 : frame < 307 ? 1687 - toField * 487 : 1200 + clickSave * 322;
  const cursorY = frame < 200 ? 699 - clickEdit * 224 : frame < 307 ? 475 + toField * 60 : 535 + clickSave * 239;
  const typingCursor = 1 - ease(frame, 237, 248) + ease(frame, 299, 309);
  const question = typeText(originalMemory.content, frame, 27, 83);
  return <AbsoluteFill className="human-scene human-memory" lang="fr" data-fictional="true">
    <div className="human-memory-story" style={{ opacity: enter, transform: `translateY(${(1 - enter) * 35}px)` }}>
      <span className="human-scene-category"><BookUser size={25} />Mémoire</span>
      <h1>À ta façon.</h1>
      <p>Ce que LIA retient,<br />tu peux le corriger.</p>
      <div className="human-user-directive" style={{ opacity: ease(frame, 15, 35), transform: `translateX(${(1 - ease(frame, 15, 45)) * -55}px)` }}><span className="human-directive-author">Toi</span><strong>« {question}{frame >= 83 ? ' »' : ''}<Caret frame={frame} visible={frame < 83} /></strong></div>
      <div className="human-memory-companion"><FilmBip frame={frame} size={330} expression={saved ? 'joy' : 'attentive'} gazeX={0.5} /><div className="human-bip-shadow" /></div>
      <div className="human-memory-assurance" style={{ opacity: ease(frame, 342, 365) }}><ShieldCheck size={23} />Tu gardes la main.</div>
    </div>
    <div className="human-memory-surface" style={{ opacity: enter, transform: `perspective(2500px) translateY(${(1 - enter) * 55}px) rotateY(${-3 * (1 - ease(frame, 350, 420))}deg)` }}>
      <AppHeader section="Paramètres" />
      <div className="human-settings-body"><nav className="human-settings-rail"><span><Settings2 size={23} /></span><span className="human-settings-active"><BookUser size={25} /></span><span><Headphones size={24} /></span><span><Lightbulb size={24} /></span></nav><div className="human-memory-pane">
        <div className="human-pane-heading"><BookUser size={30} /><h2>Mémoire</h2><span className="human-enabled-pill"><Check size={16} />Activée</span></div>
        <p className="human-pane-description">Les informations que LIA garde pour mieux t’accompagner.</p>
        <div className="human-memory-section-heading"><Pin size={24} /><strong>Règles et directives</strong><span>{frame >= 106 ? '(1)' : '(0)'}</span><ChevronDown size={23} /></div>
        <p className="human-memory-policy">Tes directives ne sont jamais supprimées automatiquement.</p>
        <div style={{ opacity: Math.max(0, Math.min(1, rowIn)), transform: `translateY(${(1 - rowIn) * 46}px)` }}><NativeMemoryRow memory={memory} frame={frame} updated={saved} /></div>
        <div className="human-memory-personal-section"><span>💡</span><strong>Préférences</strong><ChevronRight size={23} /></div>
        <div className="human-memory-personal-section"><span>📋</span><strong>Personnel</strong><ChevronRight size={23} /></div>
        <div className="human-memory-save-note" style={{ opacity: ease(frame, 336, 352), transform: `translateY(${(1 - ease(frame, 336, 352)) * 12}px)` }}><span><Check size={22} /></span><div><strong>Mémoire mise à jour</strong><p>La correction est enregistrée.</p></div></div>
      </div></div>
      <div className="human-memory-dialog-scrim" style={{ opacity: dialog, pointerEvents: 'none' }} />
      <div className="human-memory-dialog" role="dialog" aria-label="Modifier la mémoire" style={{ opacity: dialog, transform: `translateY(${(1 - dialog) * 28}px) scale(${0.97 + dialog * 0.03})`, pointerEvents: 'none' }}>
        <div className="human-dialog-header"><h3>Modifier la mémoire</h3><X size={24} /></div>
        <p className="human-dialog-description">Modifie le contenu ou les nuances d’usage.</p>
        <label className="human-field-label" htmlFor="human-memory-edit">Contenu</label>
        <div className="human-memory-textarea-wrap"><Textarea id="human-memory-edit" value={inputText} readOnly rows={3} className="human-memory-textarea" /><div className="human-memory-edit-overlay" aria-hidden="true">{inputText}<Caret frame={frame} visible={frame >= 230 && frame < 310} /></div></div>
        <label className="human-field-label">Catégorie</label><div className="human-memory-select"><Pin size={20} />Règles et directives<ChevronDown size={21} /></div>
        <div className="human-dialog-footer"><Button variant="ghost" className="human-button human-button--ghost">Annuler</Button><Button className={`human-button ${frame > 320 ? 'human-button--pressed' : ''}`} onClick={noop}><Save size={21} />Enregistrer</Button></div>
      </div>
    </div>
    <div style={{ opacity: ease(frame, 137, 153) * (1 - ease(frame, 346, 366)) * typingCursor }}><FilmCursor x={cursorX} y={cursorY} pressed={(frame >= 184 && frame <= 195) || (frame >= 325 && frame <= 336)} /></div>
  </AbsoluteFill>;
}

const transcript: TranscriptTurn[] = [
  { speaker: 'Sophie', start: 864, end: 870, text: 'On conserve le périmètre du pilote.' },
  { speaker: 'Claire', start: 871, end: 877, text: 'Je confirme le tarif Atlas d’ici vendredi.' },
  { speaker: 'Sophie', start: 878, end: 884, text: 'Parfait. Je valide la date de démarrage.' },
];

export const HUMAN_MEETING_REPORT: MeetingReport = {
  title: 'Point projet Atlas',
  participants: [
    { label: 'Sophie', name: 'Sophie', role: null },
    { label: 'Claire', name: 'Claire', role: null },
  ],
  sections: [
    { key: 'decisions', label: 'Décisions', kind: 'bullets', paragraph: null, bullets: ['Conserver le périmètre du pilote.'], topics: [], action_items: [], transcript: [] },
    { key: 'actions', label: 'Actions à suivre', kind: 'action_items', paragraph: null, bullets: [], topics: [], action_items: [
      { description: 'Confirmer le tarif Atlas', owner: 'Claire', due_date: 'Vendredi 23 octobre' },
      { description: 'Valider la date de démarrage', owner: 'Sophie', due_date: 'Vendredi 23 octobre' },
    ], transcript: [] },
  ],
};

/** The native read-only report structure: named sections and owner/due actions. */
function NativeMeetingReport({ frame }: SceneProps) {
  const report = HUMAN_MEETING_REPORT;
  return <article className="human-meeting-report">
    <div className="human-report-toolbar"><span><FileText size={23} />Compte rendu</span><Badge className="human-pill human-pill--neutral" variant="secondary">Généré</Badge><Button variant="ghost" size="icon" className="human-icon-button" aria-label="Modifier le compte rendu"><Pencil size={21} /></Button><Button variant="ghost" size="icon" className="human-icon-button" aria-label="Télécharger le PDF"><ArrowDownToLine size={21} /></Button></div>
    <div className="human-report-page"><h2>{report.title}</h2><p className="human-report-date">21 octobre 2026 · 14 min 44 s</p>
      <section className="human-report-participants"><h3>Participants</h3><p>{report.participants.map(person => person.name ?? person.label).join(', ')}</p></section>
      <section className="human-report-decisions" style={{ opacity: ease(frame, 241, 269) }}><h3>{report.sections[0].label}</h3><ul><li>{report.sections[0].bullets[0]}</li></ul></section>
      <section className="human-report-actions"><h3>Actions à suivre</h3><ul>{report.sections[1].action_items.map((action, index) => <li key={action.owner} style={{ opacity: ease(frame, 269 + index * 29, 297 + index * 29), transform: `translateX(${(1 - ease(frame, 269 + index * 29, 297 + index * 29)) * 24}px)` }}><span className={`human-owner-avatar human-owner-avatar--${index}`}>{action.owner?.charAt(0)}</span><div><strong>{action.description}</strong><p>{action.owner}<span>·</span>{action.due_date}</p></div><Check size={20} /></li>)}</ul></section>
    </div>
  </article>;
}

/** 8 seconds / 480 frames. Recording stops before the condensed report appears. */
export function MeetingScene({ frame }: SceneProps) {
  const enter = uiSpring(frame, 0);
  const stopped = frame >= 164;
  const ready = frame >= 230;
  const transform = ease(frame, 186, 239);
  const transcriptWidth = 1444 - transform * 785;
  const stopHover = ease(frame, 104, 152);
  const reportIn = uiSpring(frame, 221);
  return <AbsoluteFill className="human-scene human-meeting" lang="fr" data-fictional="true">
    <div className="human-meeting-topline" style={{ opacity: enter, transform: `translateY(${(1 - enter) * 30}px)` }}><h1>De l’échange aux décisions.</h1><div><FileText size={24} />Réunions</div></div>
    <div className="human-meeting-surface" style={{ opacity: enter, transform: `perspective(2200px) translateY(${(1 - enter) * 56}px) rotateX(${1.5 * (1 - ease(frame, 230, 290))}deg)` }}>
      <AppHeader section="Réunions"><NativePill success={ready}>{ready ? <Check size={17} /> : <CircleDot size={17} />}{ready ? 'Compte rendu prêt' : stopped ? 'Préparation du compte rendu' : 'Enregistrement'}</NativePill></AppHeader>
      <div className="human-meeting-titlebar"><ChevronLeft size={23} /><div><h2>Point projet Atlas</h2><p>21 octobre 2026 · Sophie, Claire</p></div><span className="human-meeting-format">Format réunion<ChevronDown size={18} /></span></div>
      <section className={`human-recording-banner ${stopped ? 'human-recording-banner--stopped' : ''}`}>
        <span className="human-rec-dot" style={{ opacity: stopped ? 0 : 0.6 + Math.sin(frame / 10) * 0.4 }} /><strong>{ready ? 'Compte rendu prêt' : stopped ? 'Préparation du compte rendu…' : 'Enregistrement en cours'}</strong><span className="human-recording-clock">{stopped ? '14:44' : formatElapsed(882 + Math.floor(frame / 60))}</span><Waveform frame={frame} active={!stopped} small /><span className="human-recording-transfer">{stopped ? 'Enregistrement terminé' : 'Segments transmis'}</span>
        <Button className={`human-button human-recording-stop ${stopHover > 0.6 && !stopped ? 'human-button--hover' : ''}`} onClick={noop}><Square size={18} />{stopped ? 'Terminé' : 'Terminer'}</Button>
      </section>
      <div className="human-meeting-workspace">
        <section className="human-transcript-pane" style={{ width: transcriptWidth }}><div className="human-transcript-heading"><AudioLines size={24} /><h3>Transcription</h3><span>Extrait</span></div><ol>{transcript.map((line, index) => {
          const lineIn = ease(frame, 22 + index * 35, 47 + index * 35);
          return <li key={line.start} style={{ opacity: lineIn, transform: `translateY(${(1 - lineIn) * 15}px)` }}><span className="human-transcript-time">{formatElapsed(line.start)}</span><span className={`human-speaker human-speaker--${index % 2}`}>{line.speaker}</span><p>{typeText(line.text, frame, 26 + index * 34, 64 + index * 34)}<Caret frame={frame} visible={frame > 26 + index * 34 && frame < 64 + index * 34} /></p><span className="human-transcript-focus" style={{ opacity: index === 1 ? ease(frame, 165, 194) : 0 }} /></li>;
        })}</ol><div className="human-transcript-origin"><Mic size={20} />Enregistrement de la réunion<Check size={18} /></div></section>
        <div className="human-report-reveal" style={{ opacity: ease(frame, 221, 247), transform: `translateX(${(1 - reportIn) * 115}px) scale(${0.97 + reportIn * 0.03})` }}><NativeMeetingReport frame={frame} /></div>
      </div>
    </div>
    <div className="human-meeting-endnote" style={{ opacity: ease(frame, 331, 356), transform: `translateY(${(1 - ease(frame, 331, 356)) * 17}px)` }}><Check size={23} />Les décisions, les responsables et les échéances.</div>
    <div style={{ opacity: ease(frame, 93, 108) * (1 - ease(frame, 175, 196)) }}><FilmCursor x={1588 + stopHover * 98} y={672 - stopHover * 242} pressed={frame >= 154 && frame <= 167} /></div>
  </AbsoluteFill>;
}
