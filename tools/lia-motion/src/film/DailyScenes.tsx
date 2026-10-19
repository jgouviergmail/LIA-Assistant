import type { CSSProperties, ReactNode } from 'react';
import {
  ArrowRight,
  Calendar,
  Check,
  CheckCheck,
  Clock3,
  FileText,
  Mail,
  MapPin,
  MessageSquare,
  MoreHorizontal,
  NotebookPen,
  Pencil,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
  Volume2,
  X,
} from 'lucide-react';
import { interpolate, spring } from 'remotion';
import nativeCards from '../../public/atlas/native-source-cards.json';
import { FilmCursor, type SceneProps } from './shared';
import './daily-scenes.css';

/**
 * Offline fictional demonstrations. No account, router or transport is mounted.
 *
 * Briefing is an enlarged presentation adapter of the current TodayBriefing,
 * BriefingSynthesis, BriefingCard, AgendaEntry and MailsContent markup. Their
 * provider-bound components cannot mount independently in Remotion. In
 * particular, selecting an agenda row OPENS A PREFILLED CHAT; it never sends it.
 *
 * Email, PDF and draft are the canonical Python-rendered fixture HTML in
 * native-source-cards.json, styled by the actual application card stylesheets.
 * Approval follows HitlActionCard: edit instructions -> revised draft -> a new
 * confirmation -> resolved. Sending is a deterministic fictional film state.
 */

const mix = (frame: number, from: number, to: number) => {
  const t = interpolate(frame, [from, to], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return t * t * (3 - 2 * t);
};
const pop = (frame: number, start: number) =>
  spring({ frame: frame - start, fps: 60, config: { damping: 23, stiffness: 145 } });
const typed = (text: string, frame: number, start: number, end: number) =>
  text.slice(0, Math.floor(text.length * mix(frame, start, end)));

function Caption({ title, detail }: { title: string; detail: string }) {
  return (
    <header className="daily-caption">
      <h2>{title}</h2>
      <p>{detail}</p>
    </header>
  );
}

function AppWindow({
  children,
  title,
  style,
  className = '',
}: {
  children: ReactNode;
  title: string;
  style?: CSSProperties;
  className?: string;
}) {
  return (
    <section className={`daily-app-window ${className}`} style={style}>
      <div className="daily-app-toolbar">
        <div className="daily-app-brand"><span />LIA</div>
        <div className="daily-app-route">{title}</div>
        <div className="daily-app-account">A</div>
      </div>
      {children}
    </section>
  );
}

function TileHeader({
  title,
  icon,
  tone = 'violet',
}: {
  title: string;
  icon: ReactNode;
  tone?: 'violet' | 'emerald';
}) {
  return (
    <div className={`daily-tile-header daily-tone-${tone}`}>
      <span className="daily-tile-icon">{icon}</span>
      <h3>{title}</h3>
      <span className="daily-updated">À l’instant</span>
      <RefreshCw size={19} />
    </div>
  );
}

function MeetingRow({
  time,
  title,
  location,
  selected,
  dimmed,
}: {
  time: string;
  title: string;
  location: string;
  selected?: boolean;
  dimmed?: boolean;
}) {
  return (
    <li className={`daily-meeting ${selected ? 'is-selected' : ''}`} style={{ opacity: dimmed ? 0.46 : 1 }}>
      <button type="button" aria-label={`Parle-moi de ${title} à ${time}`} aria-pressed={selected}>
        <span className="daily-meeting-time"><Clock3 size={18} />{time}</span>
        <strong>{title}</strong>
        <span className="daily-meeting-place"><MapPin size={17} />{location}</span>
      </button>
      <span className="daily-row-actions"><NotebookPen size={19} /><MoreHorizontal size={19} /></span>
    </li>
  );
}

export function BriefingScene({ frame }: SceneProps) {
  const selected = frame >= 145;
  const open = pop(frame, 168);
  const start = pop(frame, 0);
  const camera = mix(frame, 190, 425);
  const cursorX = interpolate(frame, [0, 65, 138, 165, 250, 320], [1550, 1460, 526, 526, 1262, 1405], { extrapolateRight: 'clamp' });
  const cursorY = interpolate(frame, [0, 65, 138, 165, 250, 320], [790, 752, 784, 784, 773, 836], { extrapolateRight: 'clamp' });
  return (
    <div className="daily-scene daily-briefing" data-fictional="true">
      <Caption title="Une journée qui commence avec du contexte." detail="L’agenda, les messages et les points à préparer se retrouvent au même endroit." />
      <div className="daily-camera" style={{ transform: `perspective(2200px) rotateY(${-1.7 + camera * 2}deg) rotateX(${1.4 - camera * 1.1}deg) translateY(${(1 - start) * 65}px) scale(${0.96 + camera * 0.025})`, opacity: start }}>
        <AppWindow title="Mon dashboard" className="daily-briefing-window">
          <div className="daily-dashboard-content" data-source="TodayBriefing.tsx / BriefingSynthesis.tsx">
            <div className="daily-dashboard-heading"><div><p>Vendredi 16 octobre</p><h3>Bonjour Alex.</h3></div><span className="daily-day-badge"><Calendar size={20} />Aujourd’hui</span></div>
            <section className="daily-synthesis" aria-label="Le point de LIA">
              <div className="daily-synthesis-heading"><Sparkles size={22} /><strong>Le point de LIA</strong><Volume2 size={22} /><span>−</span></div>
              <p>Tu retrouves Claire à <strong>10 h</strong> pour Atlas.<br />Son dernier message signale un tarif à vérifier avant votre échange.</p>
            </section>
            <div className="daily-briefing-columns">
              <section className="daily-briefing-tile daily-agenda" data-source="AgendaCard.tsx / AgendaEntry">
                <TileHeader title="Agenda" icon={<Calendar size={25} />} />
                <div className="daily-agenda-day"><Calendar size={19} />Vendredi 16 octobre</div>
                <ul>
                  <MeetingRow time="10:00 – 10:30" title="Point Atlas avec Claire" location="Visioconférence" selected={selected} />
                  <MeetingRow time="14:00 – 15:00" title="Revue de la maquette" location="Studio" dimmed={selected} />
                </ul>
              </section>
              <section className="daily-briefing-tile daily-priority-mails" data-source="MailsCard.tsx / MailsContent">
                <TileHeader title="E-mails" icon={<Mail size={25} />} tone="emerald" />
                <div className="daily-unread"><strong>3</strong><span>non lus aujourd’hui</span></div>
                <div className="daily-briefing-mail"><span><Mail size={18} />08:42</span><strong>Atlas — tarif actualisé</strong><p>Claire</p><span className="daily-mail-priority">À lire avant le rendez-vous</span></div>
                <div className="daily-briefing-mail daily-mail-secondary"><span><Mail size={18} />08:10</span><strong>Maquette : dernière version</strong><p>Équipe design</p></div>
              </section>
            </div>
          </div>
        </AppWindow>
        <div className="daily-prefill-panel" style={{ transform: `translateX(${(1 - open) * 110}px) translateY(${(1 - open) * 25}px) scale(${0.96 + open * 0.04})`, opacity: open }}>
          <div className="daily-prefill-heading"><MessageSquare size={25} /><strong>Discussion</strong><X size={21} /></div>
          <div className="daily-prefill-context"><Calendar size={21} /><span>Point Atlas avec Claire</span><strong>10 h</strong></div>
          <div className="daily-prefill-message">Parle-moi de mon rendez-vous<br /><strong>« Point Atlas avec Claire »<br />à 10:00.</strong></div>
          <div className="daily-composer daily-prefilled"><span>Parle-moi de mon rendez-vous<br />avec Claire à 10:00.</span><button type="button" aria-label="Envoyer"><Send size={25} /></button></div>
          <p className="daily-prefill-hint"><Pencil size={17} />Message prérempli, prêt à envoyer</p>
        </div>
      </div>
      {frame > 62 && frame < 365 && <FilmCursor x={cursorX} y={cursorY} pressed={frame >= 141 && frame < 153} />}
      <div className="daily-bottom-note" style={{ opacity: mix(frame, 300, 330), transform: `translateY(${(1 - pop(frame, 300)) * 25}px)` }}><Check size={22} />Le bon rendez-vous. Le bon point de départ.</div>
    </div>
  );
}

function CanonicalSource({ kind, className = '', style }: { kind: 'email' | 'document'; className?: string; style?: CSSProperties }) {
  return (
    <div className={`daily-native-source daily-native-source--${kind} ${className}`} style={style}>
      <div className="daily-source-origin">{kind === 'email' ? <Mail size={22} /> : <FileText size={22} />}<strong>{kind === 'email' ? 'E-mail de Claire' : 'Fiche Atlas'}</strong><span>{kind === 'email' ? 'Le plus récent' : 'Document du projet'}</span></div>
      <div className="daily-native-html" dangerouslySetInnerHTML={{ __html: kind === 'email' ? nativeCards.emailHtml : nativeCards.documentHtml }} />
    </div>
  );
}

function SourceChip({ kind, style }: { kind: 'email' | 'document'; style?: CSSProperties }) {
  return <span className={`daily-source-chip daily-source-chip--${kind}`} style={style}>{kind === 'email' ? <Mail size={18} /> : <FileText size={18} />}{kind === 'email' ? 'E-mail de Claire' : 'Fiche Atlas'}</span>;
}

export function ContextScene({ frame }: SceneProps) {
  const prompt = 'Compare le dernier e-mail de Claire à la fiche Atlas.';
  const text = typed(prompt, frame, 24, 114);
  const sent = frame >= 130;
  const result = pop(frame, 257);
  const mailIn = pop(frame, 143);
  const docIn = pop(frame, 182);
  const fly = mix(frame, 220, 282);
  const camera = mix(frame, 0, 479);
  return (
    <div className="daily-scene daily-context" data-fictional="true">
      <Caption title="Relier les sources. Faire apparaître l’essentiel." detail="Un e-mail et un document peuvent raconter deux versions différentes." />
      <div className="daily-context-workspace" style={{ transform: `perspective(2500px) rotateY(${1.2 - camera * 2.2}deg) rotateX(${0.8 - camera * 0.6}deg) scale(${0.98 + camera * 0.025})` }}>
        <div className="daily-context-sources">
          <CanonicalSource kind="email" style={{ opacity: mailIn, transform: `translateX(${(1 - mailIn) * -95}px) rotate(${(1 - mailIn) * -4}deg)` }} />
          <CanonicalSource kind="document" style={{ opacity: docIn, transform: `translateX(${(1 - docIn) * -95}px) rotate(${(1 - docIn) * 3}deg)` }} />
        </div>
        <AppWindow title="Discussion · Atlas" className="daily-context-chat">
          <div className="daily-chat-inner">
            <div className="daily-user-message" style={{ opacity: sent ? 1 : 0.5 }}><span>Vous</span>{sent ? prompt : 'Préparer mon rendez-vous avec Claire'}</div>
            {frame >= 150 && frame < 272 && <div className="daily-research-status"><span className="daily-research-pulse" />Lecture des deux sources…</div>}
            <div className="daily-context-answer" style={{ opacity: result, transform: `translateY(${(1 - result) * 44}px)` }}>
              <div className="daily-assistant-label"><Sparkles size={22} /><strong>LIA</strong></div>
              <h3>Deux montants.<br />Un point à clarifier.</h3>
              <div className="daily-source-finding"><p>Claire annonce <strong>270 €</strong> dans son dernier e-mail.</p><SourceChip kind="email" /></div>
              <div className="daily-source-finding"><p>La fiche projet indique encore <strong>240 €</strong>.</p><SourceChip kind="document" /></div>
              <div className="daily-clarification" style={{ opacity: mix(frame, 320, 350), transform: `translateY(${(1 - pop(frame, 320)) * 18}px)` }}><MessageSquare size={23} /><p>Demandons à Claire<br /><strong>quel tarif s’applique.</strong></p></div>
            </div>
            <div className={`daily-composer daily-context-composer ${sent ? '' : 'is-typing'}`}>
              <span>{sent ? 'Écrivez votre message…' : <>{text}<i className="daily-caret" style={{ opacity: frame % 36 < 22 ? 1 : 0 }} /></>}</span><button type="button" aria-label="Envoyer" className={frame >= 126 && frame < 137 ? 'is-pressed' : ''}><Send size={25} /></button>
            </div>
          </div>
        </AppWindow>
        {frame >= 218 && frame < 293 && <>
          <SourceChip kind="email" style={{ position: 'absolute', left: 288 + fly * 745, top: 310 + fly * 130, opacity: Math.sin(Math.min(1, mix(frame, 218, 293)) * Math.PI), transform: `scale(${1.05 - fly * 0.05})`, zIndex: 20 }} />
          <SourceChip kind="document" style={{ position: 'absolute', left: 300 + fly * 733, top: 660 - fly * 81, opacity: Math.sin(Math.min(1, mix(frame, 218, 293)) * Math.PI), zIndex: 20 }} />
        </>}
      </div>
      {frame > 92 && frame < 158 && <FilmCursor x={interpolate(frame, [92, 124], [1540, 1736], { extrapolateRight: 'clamp' })} y={interpolate(frame, [92, 124], [870, 913], { extrapolateRight: 'clamp' })} pressed={frame >= 127 && frame < 136} />}
    </div>
  );
}

function DraftPreview({ amended }: { amended: boolean }) {
  const added = ' Merci pour ta précision avant notre rendez-vous de 10 h.';
  const html = amended
    ? nativeCards.decisionHtml.replace('Claire, quel tarif s’applique à Atlas : 240 € ou 270 € ?', `Bonjour Claire, peux-tu me confirmer quel tarif s’applique à Atlas : 240 € ou 270 € ?${added}`)
    : nativeCards.decisionHtml;
  return <div className="daily-approval-preview daily-native-html"><div className="lia-response-wrapper" data-card-version="2" dangerouslySetInnerHTML={{ __html: html }} /></div>;
}

function ApprovalButtons({ pressed, edited }: { pressed: boolean; edited: boolean }) {
  return <div className="daily-hitl-buttons"><button type="button" className={`daily-primary-button ${pressed ? 'is-pressed' : ''}`}><Check size={21} />Confirmer</button><button type="button" className={edited ? 'daily-edited-button' : ''}><Pencil size={19} />Modifier</button><button type="button">Annuler</button></div>;
}

export function ApprovalScene({ frame }: SceneProps) {
  const editOpen = frame >= 87 && frame < 220;
  const amended = frame >= 238;
  const confirmed = frame >= 368;
  const delivered = frame >= 393;
  const instruction = 'Ajoute un ton plus chaleureux et rappelle notre rendez-vous de 10 h.';
  const instructionText = typed(instruction, frame, 102, 188);
  const entrance = pop(frame, 0);
  const end = pop(frame, 395);
  const cursorX = interpolate(frame, [0, 45, 82, 100, 193, 213, 245, 325, 361, 380], [1585, 1350, 925, 925, 976, 846, 846, 740, 732, 752], { extrapolateRight: 'clamp' });
  const cursorY = interpolate(frame, [0, 45, 82, 100, 193, 213, 245, 325, 361, 380], [900, 840, 777, 777, 819, 849, 849, 813, 808, 810], { extrapolateRight: 'clamp' });
  return (
    <div className="daily-scene daily-approval" data-fictional="true">
      <Caption title="LIA prépare. Tu gardes le dernier mot." detail="Relis, demande une modification, puis confirme l’action." />
      <div className="daily-approval-camera" style={{ opacity: entrance, transform: `perspective(2400px) rotateY(${-1.4 + mix(frame, 0, 479) * 2.6}deg) rotateX(${0.8 - mix(frame, 0, 479) * 0.8}deg) translateY(${(1 - entrance) * 70}px) scale(${0.97 + mix(frame, 220, 360) * 0.025})` }}>
        <AppWindow title="Discussion · Atlas" className="daily-approval-window">
          <div className="daily-approval-main">
            <div className="daily-approval-brief"><div className="daily-assistant-label"><Sparkles size={22} /><strong>LIA</strong></div><p>Je te propose de demander à Claire<br /><strong>quel montant s’applique à Atlas.</strong></p></div>
            <DraftPreview amended={amended} />
            <section className={`daily-hitl-card ${confirmed ? 'is-confirmed' : ''}`} aria-label="Brouillon à valider" data-source="HitlActionCard.tsx / DraftEditForm">
              <div className="daily-hitl-icon">{confirmed ? <Check size={25} /> : <Mail size={25} />}</div>
              <div className="daily-hitl-content">
                <div className="daily-hitl-heading"><strong>{confirmed ? 'Confirmé' : 'Brouillon à valider'}</strong>{amended && !confirmed && <span><Check size={16} />Brouillon modifié</span>}</div>
                {editOpen ? <div className="daily-draft-edit"><div className="daily-edit-textarea">{instructionText}<i className="daily-caret" style={{ opacity: frame % 36 < 22 ? 1 : 0 }} /></div><div className="daily-edit-actions"><button type="button" className={`daily-primary-button ${frame >= 210 && frame < 220 ? 'is-pressed' : ''}`}>Envoyer les modifications</button><span>Retour</span></div></div> : confirmed ? <p className="daily-confirmed-text"><ShieldCheck size={20} />Vous avez confirmé cet envoi.</p> : <><p className="daily-hitl-recipient">À Claire &lt;claire@example.test&gt;</p><ApprovalButtons pressed={frame >= 360 && frame < 369} edited={amended} /></>}
              </div>
            </section>
          </div>
          {delivered && <div className="daily-delivered" style={{ opacity: end, transform: `translateY(${(1 - end) * 55}px) scale(${0.94 + end * 0.06})` }}><div className="daily-delivered-icon"><CheckCheck size={37} /></div><div><strong>Message envoyé à Claire</strong><p>Votre demande de précision est partie.</p></div><Mail size={35} /></div>}
        </AppWindow>
        <aside className="daily-control-note" style={{ opacity: mix(frame, 250, 286), transform: `translateX(${(1 - pop(frame, 250)) * 70}px)` }}><ShieldCheck size={39} /><h3>La confirmation<br />t’appartient.</h3><p>Le brouillon reste visible<br />jusqu’à ta décision.</p><div><Check size={20} />Relu<ArrowRight size={19} /><Check size={20} />Validé</div></aside>
      </div>
      {frame > 40 && frame < 389 && <FilmCursor x={cursorX} y={cursorY} pressed={(frame >= 82 && frame < 91) || (frame >= 210 && frame < 220) || (frame >= 360 && frame < 369)} />}
    </div>
  );
}
