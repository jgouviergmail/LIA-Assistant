import { useState, type CSSProperties, type ReactNode } from 'react';
import {
  ArrowUpRight,
  CalendarDays,
  ChartPie,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Clock3,
  FileText,
  Mail,
  MoreHorizontal,
  Pause,
  Play,
  Radio,
  Send,
  ShieldCheck,
  Sparkles,
  Square,
  Timer,
  Users,
} from 'lucide-react';
import { FilmBip, FilmCursor, NativeWindow, SceneCaption, ease, type SceneProps } from './shared';
import './work-scenes.css';

/**
 * Offline, frame-directed product demonstrations. No player, scheduler or API
 * is mounted here. Layout and wording are adapted from the current native
 * ScheduledActionsSettings/Timeline, Workboard, RadioPage/Banner/Transcript
 * and RadioArticles. All named projects and programme text are demo content.
 * The budget's markup, category colours and arithmetic come from
 * apps/web/e2e/capture/render_trip_budget.py, translated to French here.
 */

const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const money = (n: number) => `${Math.round(n).toLocaleString('fr-FR')} €`;
const flat = (opacity: number, transform?: string): CSSProperties => ({ opacity, transform });

function Tag({ children, tone = 'blue' }: { children: ReactNode; tone?: 'blue' | 'amber' | 'green' | 'neutral' }) {
  return <span className={`wf-tag wf-tag--${tone}`}>{children}</span>;
}

function SmallBip({ frame }: SceneProps) {
  return <span className="wf-small-bip"><FilmBip frame={frame} size={38} /></span>;
}

function WorkHeader({ icon, title, subtitle }: { icon: ReactNode; title: string; subtitle?: string }) {
  return <header className="wf-page-header"><div className="wf-page-title">{icon}<h1>{title}</h1></div>{subtitle && <p>{subtitle}</p>}</header>;
}

const days = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'];

function RoutineTimeline({ frame }: SceneProps) {
  const saved = frame >= 218;
  const arrived = frame >= 272;
  return <section className="wf-routine-timeline wf-panel">
    <div className="wf-panel-heading"><CalendarDays size={24} /><h2>Vue de la semaine</h2><span>Europe/Paris</span></div>
    <div className="wf-week-nav"><ChevronLeft size={19} /><b>19 — 25 octobre 2026</b><ChevronRight size={19} /></div>
    <div className="wf-calendar">
      <div className="wf-calendar-head"><span>Heure</span>{days.map((day, i) => <span key={day} className={i === 4 && saved ? 'selected' : ''}>{day}<b>{19 + i}</b></span>)}</div>
      {[8, 9, 10, 11, 12].map(hour => <div className="wf-calendar-row" key={hour}><time>{hour.toString().padStart(2, '0')}:00</time>{days.map((day, i) => <div key={day} className={i === 4 && saved ? 'wf-friday-column' : ''}>{hour === 9 && i === 4 && saved && <div className={`wf-occurrence ${arrived ? 'wf-occurrence--ready' : ''}`} style={{ opacity: ease(frame, 218, 236), transform: `scale(${mix(.7, 1, ease(frame, 218, 242))})` }}><span>1</span><b>{arrived ? 'Proposée' : '09:00'}</b></div>}</div>)}</div>)}
    </div>
    <div className="wf-calendar-legend"><i /><span>{arrived ? 'Proposée, en attente de ton accord' : 'Prochaine exécution : ven. 23 oct., 09:00'}</span></div>
  </section>;
}

function DraftPanel({ frame }: SceneProps) {
  return <section className="wf-draft wf-panel" style={flat(ease(frame, 286, 314), `translateX(${mix(90, 0, ease(frame, 286, 318))}px)`)}>
    <div className="wf-draft-top"><div><Mail size={24} /><h2>Relance Atlas</h2></div><MoreHorizontal size={23} /></div>
    <Tag tone="amber"><Clock3 size={16} />Une action attend ton accord</Tag>
    <div className="wf-mail-fields"><div><span>À</span><b>Claire · Équipe Atlas</b></div><div><span>Objet</span><b>Atlas — point sur la proposition</b></div></div>
    <div className="wf-mail-copy"><p>Bonjour Claire,</p><p>Je reviens vers vous au sujet de la proposition Atlas. Avez-vous pu la consulter ?</p><p>Je suis disponible pour en discuter et préciser les prochaines étapes.</p><p>Bonne journée,</p></div>
    <div className="wf-draft-footer"><span><ShieldCheck size={20} />Brouillon prêt. Aucun message envoyé.</span><div><button className="wf-button wf-button--ghost">Modifier</button><button className="wf-button"><Send size={19} />Confirmer l’envoi</button></div></div>
  </section>;
}

export function RoutineScene({ frame }: SceneProps) {
  const prompt = 'Chaque vendredi, prépare la relance Atlas';
  const characters = Math.floor(ease(frame, 22, 104) * prompt.length);
  const dropdown = frame >= 133 && frame < 178;
  const dayPicked = frame >= 169;
  const saved = frame >= 218;
  const draft = frame >= 286;
  const zoom = ease(frame, 256, 319);
  let cursor = { x: 804, y: 878 };
  if (frame < 115) cursor = { x: mix(804, 687, ease(frame, 0, 23)), y: mix(878, 520, ease(frame, 0, 23)) };
  else if (frame < 154) cursor = { x: mix(687, 610, ease(frame, 115, 133)), y: mix(520, 690, ease(frame, 115, 133)) };
  else if (frame < 190) cursor = { x: mix(610, 610, ease(frame, 154, 169)), y: mix(690, 877, ease(frame, 154, 169)) };
  else if (frame < 238) cursor = { x: mix(610, 775, ease(frame, 190, 211)), y: mix(877, 823, ease(frame, 190, 211)) };
  else if (frame < 286) cursor = { x: mix(775, 1394, ease(frame, 238, 266)), y: mix(823, 514, ease(frame, 238, 266)) };
  else cursor = { x: mix(1394, 1719, ease(frame, 286, 321)), y: mix(514, 875, ease(frame, 286, 321)) };
  return <div className="wf-scene wf-routine-scene">
    <div className="wf-work-window wf-routine-window" style={{ transform: `translate(${mix(0, -26, zoom)}px, ${mix(0, -15, zoom)}px) scale(${mix(1, 1.035, zoom)})` }}>
      <NativeWindow title="LIA · Studio de routines" style={{ width: '100%', height: '100%' }}>
        <div className="wf-product-page">
          <WorkHeader icon={<CalendarDays size={31} />} title="Actions planifiées" subtitle="Tes consignes, ton calendrier, tes décisions." />
          <div className="wf-routine-content">
            <section className="wf-routine-form wf-panel" style={{ opacity: mix(1, .48, ease(frame, 286, 318)) }}>
              <div className="wf-panel-heading"><Sparkles size={24} /><h2>Ce qu’il faut faire</h2></div>
              <label className="wf-form-label">Titre</label><div className="wf-input">Relance Atlas</div>
              <label className="wf-form-label">Instruction pour l’assistant</label>
              <div className={`wf-input wf-prompt ${frame < 116 ? 'wf-input--active' : ''}`}>{prompt.slice(0, characters)}{frame >= 22 && frame < 116 && <i className="wf-caret" style={{ opacity: Math.floor(frame / 18) % 2 ? .25 : 1 }} />}</div>
              <div className="wf-panel-heading wf-trigger-heading"><Clock3 size={23} /><h2>Quand elle s’exécute</h2></div>
              <div className="wf-schedule-fields"><div><label className="wf-form-label">Fréquence</label><div className="wf-input">Chaque semaine<ChevronDown size={18} /></div></div><div className="wf-day-select"><label className="wf-form-label">Jour</label><div className={`wf-input ${dropdown ? 'wf-input--active' : ''}`}>{dayPicked ? 'Vendredi' : 'Choisir'}<ChevronDown size={18} /></div>{dropdown && <div className="wf-select-menu">{['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi'].map((day, i) => <div className={i === 4 && frame >= 160 ? 'active' : ''} key={day}>{day}{i === 4 && frame >= 169 && <Check size={18} />}</div>)}</div>}</div><div><label className="wf-form-label">Heure</label><div className="wf-input wf-time">09:00<Clock3 size={18} /></div></div></div>
              <div className="wf-schedule-note"><ShieldCheck size={21} /><span>Les actions d’envoi restent à confirmer.</span></div>
              <div className="wf-form-actions"><span>{saved ? <><Check size={19} />Routine enregistrée</> : 'Heures en Europe/Paris'}</span><button className={`wf-button ${frame >= 208 && frame <= 223 ? 'wf-button--pressed' : ''}`}>{saved ? <Check size={20} /> : null}{saved ? 'Enregistré' : 'Enregistrer'}</button></div>
            </section>
            <RoutineTimeline frame={frame} />
          </div>
        </div>
      </NativeWindow>
      {draft && <DraftPanel frame={frame} />}
      {frame >= 256 && <div className="wf-routine-timejump" style={{ opacity: ease(frame, 256, 273) }}><CalendarDays size={19} />Vendredi 23 octobre · 09:00</div>}
    </div>
    <FilmCursor x={cursor.x} y={cursor.y} pressed={(frame >= 132 && frame <= 138) || (frame >= 168 && frame <= 174) || (frame >= 211 && frame <= 217)} />
    <SceneCaption kicker="Routines" title="À l’heure choisie. Avec ton accord." detail="Prépare la suite. Garde la décision." />
  </div>;
}

type BudgetValues = { travellers: number; nights: number; budget: number };
type BudgetCost = { label: string; amount: number; color: string };

/** Exact arithmetic from the existing capture fixture, with local controls. */
function tripCosts({ travellers: p, nights: n }: BudgetValues): BudgetCost[] {
  return [
    { label: 'Train', amount: 48 * p, color: '#147f9c' },
    { label: 'Hébergement', amount: 110 * n, color: '#3455b0' },
    { label: 'Repas et cafés', amount: 26 * p * (n + 1), color: '#37a58d' },
    { label: 'Musées et activités', amount: 32 * p, color: '#d6943c' },
    { label: 'Sur place', amount: 8 * p * (n + 1), color: '#9a6cb6' },
  ];
}

function BudgetRange({ name, label, value, min, max, step = 1, active, onChange }: { name: keyof BudgetValues; label: string; value: number; min: number; max: number; step?: number; active: boolean; onChange: (name: keyof BudgetValues, value: number) => void }) {
  return <div className={`wf-budget-control ${active ? 'wf-budget-control--active' : ''}`}><label htmlFor={`film-${name}`}>{label}<output>{name === 'budget' ? money(value) : value}</output></label><input id={`film-${name}`} aria-label={label} type="range" min={min} max={max} step={step} value={value} onChange={event => onChange(name, Number(event.currentTarget.value))} style={{ '--range-progress': `${(value - min) / (max - min) * 100}%` } as CSSProperties} /></div>;
}

export function TripBudgetApp({ values, active }: { values: BudgetValues; active: keyof BudgetValues | null }) {
  // These remain real, working controls in the preview; the film passes each
  // scripted drag's values as props, making every rendered frame repeatable.
  const [overrides, setOverrides] = useState<Partial<BudgetValues>>({});
  const actual = { ...values, ...overrides };
  const costs = tripCosts(actual);
  const total = costs.reduce((sum, cost) => sum + cost.amount, 0);
  const remaining = actual.budget - total;
  const circumference = 2 * Math.PI * 73;
  let offset = 0;
  const onChange = (name: keyof BudgetValues, value: number) => setOverrides(previous => ({ ...previous, [name]: value }));
  return <div className="wf-budget-app" lang="fr">
    <header><div><h1>Budget week-end</h1><p>Un week-end à Lyon, à ta mesure.</p></div><span className="wf-budget-label"><ChartPie size={18} />Skill App</span></header>
    <main className="wf-budget-layout">
      <section aria-label="Répartition du budget"><div className="wf-budget-overview"><div className="wf-budget-ring"><svg viewBox="0 0 180 180" aria-label="Dépenses estimées par catégorie" role="img">{costs.map(cost => {
        const length = cost.amount / total * circumference;
        const arc = <circle key={cost.label} cx="90" cy="90" r="73" fill="none" stroke={cost.color} strokeWidth="15" strokeDasharray={`${length - 2} ${circumference - length + 2}`} strokeDashoffset={-offset} />;
        offset += length;
        return arc;
      })}</svg><div className="wf-budget-total"><strong>{money(total)}</strong><span>séjour estimé</span></div></div><div className="wf-budget-margin"><p>{remaining >= 0 ? 'Marge disponible' : 'Budget dépassé de'}</p><strong className={remaining < 0 ? 'over' : ''}>{money(Math.abs(remaining))}</strong><p>{money(total / actual.travellers)} par personne</p><p>{actual.travellers} voyageurs · {actual.nights} nuits</p></div></div>
      <div className="wf-budget-breakdown" aria-live="polite">{costs.map(cost => <div className="wf-budget-row" key={cost.label}><div><i style={{ background: cost.color }} /><span>{cost.label}</span><b>{money(cost.amount)}</b></div><span className="wf-budget-bar"><i style={{ width: `${cost.amount / total * 100}%`, background: cost.color }} /></span></div>)}</div></section>
      <section aria-label="Ajuster ton week-end"><fieldset><legend>Compose ton week-end</legend><BudgetRange name="travellers" label="Voyageurs" value={actual.travellers} min={1} max={6} active={active === 'travellers'} onChange={onChange} /><BudgetRange name="nights" label="Nuits sur place" value={actual.nights} min={1} max={5} active={active === 'nights'} onChange={onChange} /><BudgetRange name="budget" label="Budget total" value={actual.budget} min={400} max={1800} step={20} active={active === 'budget'} onChange={onChange} /></fieldset><div className="wf-budget-plan"><div><span>01</span><p><b>Vieux Lyon et bords de Saône</b><small>Arrivée en train, balade, dîner</small></p></div><div><span>02</span><p><b>Les Halles et vue sur la ville</b><small>Marché, musée, transports locaux</small></p></div></div></section>
    </main>
    <footer><span>Estimations d’exemple · aucun prix de réservation vérifié</span><span><Check size={16} />Calcul instantané</span></footer>
  </div>;
}

export function SkillScene({ frame }: SceneProps) {
  const nights = Math.round(mix(2, 3, ease(frame, 82, 130)));
  const travellers = Math.round(mix(2, 3, ease(frame, 166, 209)));
  const budget = Math.round(mix(760, 1200, ease(frame, 246, 309)) / 20) * 20;
  const active: keyof BudgetValues | null = frame >= 66 && frame < 142 ? 'nights' : frame >= 150 && frame < 224 ? 'travellers' : frame >= 231 && frame < 314 ? 'budget' : null;
  const camera = ease(frame, 32, 72) * (1 - ease(frame, 314, 360));
  let x = 1690, y = 905;
  if (frame < 148) { x = mix(1690, 1201, ease(frame, 18, 65)) + mix(0, 167, ease(frame, 82, 130)); y = mix(905, 540, ease(frame, 18, 65)); }
  else if (frame < 230) { x = mix(1368, 1167, ease(frame, 148, 164)) + mix(0, 134, ease(frame, 166, 209)); y = mix(540, 452, ease(frame, 148, 164)); }
  else if (frame < 326) { x = mix(1301, 1205, ease(frame, 230, 245)) + mix(0, 211, ease(frame, 246, 309)); y = mix(452, 628, ease(frame, 230, 245)); }
  else { x = mix(1416, 1742, ease(frame, 326, 354)); y = mix(628, 880, ease(frame, 326, 354)); }
  return <div className="wf-scene wf-skill-scene">
    <div className="wf-skill-conversation" style={{ opacity: 1 - .58 * camera }}><SmallBip frame={frame} /><p>Voici ton budget. Tu peux l’ajuster directement.</p></div>
    <div className="wf-work-window wf-skill-window" style={{ transform: `translateY(${mix(0, -14, camera)}px) scale(${mix(1, 1.025, camera)})` }}><NativeWindow title="LIA · Budget week-end" style={{ width: '100%', height: '100%' }}><TripBudgetApp values={{ nights, travellers, budget }} active={active} /></NativeWindow></div>
    <FilmCursor x={x} y={y} pressed={(frame >= 82 && frame <= 130) || (frame >= 166 && frame <= 209) || (frame >= 246 && frame <= 309)} />
    <SceneCaption kicker="Skill Apps" title="Une réponse que tu peux manipuler." detail="Ajuste. Compare. Le résultat suit." />
  </div>;
}

const transcript = [
  { role: 'LIA', text: 'Bonjour. Ta journée commence à 9 h 30 avec le point Atlas.', source: 'Agenda', sourceKind: 'personal' },
  { role: 'Présentation', text: 'À l’affiche aujourd’hui : les nouvelles expositions de Lyon.', source: 'Le Courrier lyonnais · 23 oct. 2026', sourceKind: 'article' },
  { role: 'Analyse', text: 'Le dossier revient sur les lieux, les horaires et les visites proposées ce week-end.', source: 'Le Courrier lyonnais · 23 oct. 2026', sourceKind: 'article' },
  { role: 'LIA', text: 'Tu retrouveras l’article cité sous la transcription.', source: '', sourceKind: 'none' },
];

function RadioSourceArticle({ frame }: SceneProps) {
  const opened = frame >= 274;
  return <section className={`wf-radio-source wf-panel ${opened ? 'wf-radio-source--open' : ''}`}>
    <h2><FileText size={24} />Articles cités</h2>
    <div className="wf-source-item"><div className="wf-source-heading"><span className="wf-source-logo">C</span><div><small>Le Courrier lyonnais · 23 oct. 2026</small><h3>Un week-end de découvertes à Lyon</h3></div><ChevronDown size={22} style={{ transform: `rotate(${mix(0, 180, ease(frame, 274, 294))}deg)` }} /></div>
      <div className="wf-source-body" style={{ maxHeight: mix(0, 245, ease(frame, 274, 307)), opacity: ease(frame, 278, 301) }}><p>Les musées et lieux culturels proposent plusieurs parcours pour découvrir la ville, entre nouvelles expositions et promenades de quartier.</p><p>Les lieux et les horaires sont réunis dans l’article cité à l’antenne.</p><span className="wf-source-original">Lire l’original <ArrowUpRight size={18} /></span></div>
    </div>
    <p className="wf-fixture-note">Article fictif pour la démonstration</p>
  </section>;
}

export function RadioScene({ frame }: SceneProps) {
  const onAir = frame >= 91 && frame < 431;
  const ended = frame >= 431;
  const programmeReady = frame >= 112;
  const scroll = ease(frame, 189, 243);
  const currentLine = frame < 156 ? 0 : frame < 207 ? 1 : frame < 323 ? 2 : 3;
  let cursor = { x: 1715, y: 891 };
  if (frame < 117) cursor = { x: mix(1715, 440, ease(frame, 14, 76)), y: mix(891, 639, ease(frame, 14, 76)) };
  else if (frame < 250) cursor = { x: mix(440, 1645, ease(frame, 137, 176)), y: mix(639, 705, ease(frame, 137, 176)) };
  else if (frame < 334) cursor = { x: mix(1645, 1690, ease(frame, 250, 270)), y: mix(705, 513, ease(frame, 250, 270)) };
  else cursor = { x: mix(1690, 1646, ease(frame, 375, 419)), y: mix(513, 336, ease(frame, 375, 419)) };
  return <div className="wf-scene wf-radio-scene">
    <div className="wf-radio-side-label"><Radio size={27} /><span>Ta radio.<br />Tes sources.</span></div>
    <div className="wf-work-window wf-radio-window"><NativeWindow title="LIA · Radio" style={{ width: '100%', height: '100%' }}>
      <div className="wf-product-page wf-radio-page">
        <WorkHeader icon={<Radio size={31} />} title="Radio" subtitle="Ta journée et l’actualité du monde, écrites et dites pour toi pendant que tu écoutes." />
        {frame < 112 && <section className="wf-radio-start wf-panel" style={{ opacity: 1 - ease(frame, 91, 112) }}><p>LIA ouvre avec ta journée, puis fait entrer l’actualité des médias que tu suis — chaque phrase montre sa source.</p><div className="wf-radio-start-options"><div><label><Timer size={22} />Arrêt automatique</label><div className="wf-input">Après 15 minutes<ChevronDown size={19} /></div></div><div><label><Users size={22} />Écoute en compagnie</label><div className="wf-company"><i /><span>Si activée : aucune information personnelle à l’antenne.</span></div></div></div><p className="wf-radio-cost-note">Le coût s’affiche sous l’en-tête et compte dans ta consommation.</p><button className={`wf-button ${frame >= 84 && frame <= 93 ? 'wf-button--pressed' : ''}`}><Play size={23} fill="currentColor" />Lancer la radio</button></section>}
        {programmeReady && <div className="wf-radio-session" style={{ opacity: ease(frame, 112, 135) }}>
          <div className={`wf-radio-banner ${ended ? 'wf-radio-banner--ended' : ''}`}><div className="wf-station-icon"><Radio size={30} /></div><div className="wf-station-title"><h2>Radio LIA <span>· {ended ? 'Éteinte' : 'À l’antenne'}</span></h2><p>{ended ? 'Tu as arrêté la radio.' : 'Le journal — Ta journée et les nouvelles de Lyon'}</p></div><div className="wf-radio-meters"><span><Timer size={17} />15 min restantes</span><b>0,0042 € <small>· ≈ 0,08 € pour 15 min</small></b></div><button className="wf-button wf-button--ghost"><Pause size={20} />Pause</button><button className={`wf-button wf-button--stop ${frame >= 423 && frame <= 433 ? 'wf-button--pressed' : ''}`}><Square size={18} fill="currentColor" />{ended ? 'Arrêtée' : 'Arrêter'}</button></div>
          <div className="wf-radio-columns"><section className="wf-radio-programme wf-panel"><div className="wf-radio-programme-heading"><span>Le journal</span><h2>Ta journée et les nouvelles de Lyon</h2><p>Transcription et sources</p></div><div className="wf-transcript-viewport"><ol style={{ transform: `translateY(${-scroll * 106}px)` }}>{transcript.map((line, index) => <li key={line.text} className={index === currentLine && onAir ? 'current' : ''}><b>{line.role}</b><p>{line.text}</p>{line.source && <span className={line.sourceKind === 'article' ? 'wf-transcript-link' : ''}>{line.source}{line.sourceKind === 'article' && <ArrowUpRight size={16} />}</span>}</li>)}</ol><div className="wf-scroll-track"><i style={{ transform: `translateY(${scroll * 48}px)` }} /></div></div><p className="wf-radio-next">Ensuite : Le dossier — Un week-end à Lyon</p></section><RadioSourceArticle frame={frame} /></div>
        </div>}
      </div>
    </NativeWindow></div>
    <FilmCursor x={cursor.x} y={cursor.y} pressed={(frame >= 85 && frame <= 91) || (frame >= 271 && frame <= 277) || (frame >= 425 && frame <= 431)} />
    <SceneCaption kicker="Radio LIA" title="Ta journée s’écoute. Ses sources se lisent." detail="Une radio personnelle, que tu lances et arrêtes." />
  </div>;
}
