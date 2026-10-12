/** Native application filming in the isolated Docker/Playwright runtime.
 * The application DOM is never rebuilt or replaced: only fictional API data is supplied.
 * Run: node /repo/tools/lia-motion/scripts/capture-native.mjs [scene ids]
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile, execFileSync } from 'node:child_process';
import { promisify } from 'node:util';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const repo = '/repo';
const output = '/repo/output/playwright/lia-motion-native-v2';
const assetRoot = '/repo/tools/lia-motion/public/capture-v2';
const require = createRequire('/capture/package.json');
const ts = require('typescript');
const execute = promisify(execFile);
fs.mkdirSync(output, { recursive: true });
fs.mkdirSync(`${assetRoot}/fr`, { recursive: true });
const compiled = '/capture/native-fixtures';
for (const dir of ['fixtures', 'capture']) {
  fs.mkdirSync(`${compiled}/${dir}`, { recursive: true });
  for (const name of fs.readdirSync(`${repo}/apps/web/e2e/${dir}`)) {
    if (!name.endsWith('.ts')) continue;
    const source = fs.readFileSync(`${repo}/apps/web/e2e/${dir}/${name}`, 'utf8');
    const result = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
    fs.writeFileSync(`${compiled}/${dir}/${name.slice(0, -3)}.js`, result.outputText);
  }
}
const { createLandingProofCode } = require(`${compiled}/capture/landing-proof.js`);
const { createApiNetworkGuard } = require(`${compiled}/fixtures/api-network-guard.js`);
const converter = JSON.parse(execFileSync('python3', [`${repo}/data/skills/system/unit-converter/scripts/render_converter.py`], { input: JSON.stringify({ parameters: { _lang: 'fr' } }), encoding: 'utf8' })).frame;
const fontCss = fs.readFileSync(`${repo}/apps/web/e2e/fixtures/fonts/material-symbols.css`, 'utf8');
const silence = `${output}/silent.wav`;
const samples = 8000 * 120;
const header = Buffer.alloc(44);
header.write('RIFF'); header.writeUInt32LE(36 + samples, 4); header.write('WAVEfmt ', 8);
header.writeUInt32LE(16, 16); header.writeUInt16LE(1, 20); header.writeUInt16LE(1, 22);
header.writeUInt32LE(8000, 24); header.writeUInt32LE(8000, 28); header.writeUInt16LE(1, 32);
header.writeUInt16LE(8, 34); header.write('data', 36); header.writeUInt32LE(samples, 40);
fs.writeFileSync(silence, Buffer.concat([header, Buffer.alloc(samples, 128)]));
const code = createLandingProofCode('http://127.0.0.1:3134', output, converter, fontCss, `${repo}/apps/web/e2e/fixtures/fonts/MaterialSymbolsOutlined.woff2`, silence);
const json = code.slice(code.lastIndexOf(')(page, ') + 8, -1);
const input = JSON.parse(json);
const translations = new Map(Object.entries({
  'Your launch review, ready to discuss': 'Votre réunion de lancement, prête à préparer',
  'The project brief, the latest supplier email and the meeting notes agree on the scope. One delivery date still needs clarification.': 'Le dossier projet, le dernier e-mail du fournisseur et le compte rendu concordent sur le périmètre. Une date de livraison reste à clarifier.',
  'A date to resolve before the meeting': 'Une date à clarifier avant la réunion',
  'The brief says 19 October; the supplier email proposes 22 October. Ask which date can be committed to before sharing the plan.': 'Le dossier indique le 19 octobre ; le fournisseur propose le 22. Faites confirmer la date avant de partager le planning.',
  'Project brief': 'Dossier projet', 'Supplier email': 'E-mail fournisseur', 'Meeting notes': 'Compte rendu',
  'Launch plan.pdf': 'Plan de lancement.pdf', 'Launch checklist.docx': 'Checklist de lancement.docx',
  'Launch review · Minutes.md': 'Réunion de lancement · Compte rendu.md', 'Supplier · Delivery date.eml': 'Fournisseur · Date de livraison.eml',
  'target 19 October': 'objectif 19 octobre', 'proposed 22 October': 'proposition du 22 octobre',
  'Review · decision still open': 'Réunion · décision encore ouverte',
  'Three practical next steps': 'Trois prochaines étapes',
  'Clarify the delivery date with the supplier.': 'Clarifier la date de livraison avec le fournisseur.',
  "Keep the unresolved date visible in Monday's review.": 'Garder ce point ouvert dans la réunion de lundi.',
  'Prepare a message for your approval before sending it.': 'Préparer un message à valider avant envoi.',
  'Sources used in this example': 'Sources de cette démonstration',
  'Launch plan.pdf (Project Atlas space), supplier email and Review minutes. Demonstration data; no message has been sent.': 'Plan de lancement.pdf (espace Projet Atlas), e-mail fournisseur et compte rendu. Données de démonstration ; aucun message réel envoyé.',
  'A message ready for your review': 'Un message prêt à être validé',
  "The supplier's proposed date differs from your project brief. Here is a short message asking for a clear commitment.": 'La date proposée diffère du dossier projet. Voici un message pour demander une confirmation.',
  'Recipient': 'Destinataire', 'Subject': 'Objet', 'Confirm the Atlas delivery date': 'Confirmer la date de livraison Atlas',
  'You can confirm, ask for a change, or cancel below. This is a demonstration draft; nothing has been sent.': 'Vous pouvez confirmer, modifier ou annuler. Ce brouillon de démonstration n’a pas été envoyé.',
  'Would you like to send this draft?': 'Souhaitez-vous envoyer ce brouillon ?',
  'Hello,\n\nOur project brief targets 19 October, while your latest email mentions 22 October. Could you confirm the date your team can commit to?\n\nThank you,\nAlex Demo': 'Bonjour,\n\nNotre dossier prévoit le 19 octobre, tandis que votre dernier e-mail mentionne le 22. Pouvez-vous confirmer la date que votre équipe peut tenir ?\n\nMerci,\nAlex Démo',
  'Project Atlas': 'Projet Atlas', 'Demo project: a shared context for the brief, emails and meeting decisions.': 'Projet de démonstration : documents, e-mails et décisions dans un contexte partagé.',
  'Atlas · Project documents': 'Atlas · Documents du projet', 'Atlas / Suppliers': 'Atlas / Fournisseurs',
  'Convert measurements here in the conversation': 'Convertissez les mesures dans la conversation',
  'This example uses LIA’s existing unit-converter skill. Choose a value and units below; the result updates instantly.': 'Cette démonstration utilise la skill de conversion de LIA. Choisissez une valeur et ses unités : le résultat se met à jour immédiatement.',
  'Prepare Monday’s launch review using my project brief, supplier emails and meeting notes.': 'Prépare ma réunion de lancement avec le dossier projet, les e-mails du fournisseur et le compte rendu.',
  'Draft a message to clarify the supplier’s delivery date. Ask me before sending it.': 'Prépare un message pour clarifier la date de livraison. Demande-moi avant de l’envoyer.',
  'Give me a converter for the measurements in my project brief.': 'Donne-moi un convertisseur pour les mesures du dossier projet.',
  'Alex Demo': 'Alex Démo', 'Morgan Demo': 'Morgan Démo', 'Sam Demo': 'Sam Démo',
  'Confirm the supplier delivery date': 'Confirmer la date du fournisseur',
  'Morgan will send the launch checklist': 'Morgan enverra la checklist de lancement',
  'Before Monday’s review': 'Avant la réunion de lundi', '12 October': '12 octobre',
  'Align on the Atlas launch': 'Préparer le lancement Atlas',
  'Scope agreed. Supplier date still needs confirmation.': 'Périmètre validé. Date fournisseur encore à confirmer.',
  'Morgan prefers a short written recap before project reviews.': 'Morgan préfère un bref récapitulatif avant les réunions projet.',
  'I will bring the updated checklist to Monday’s review.': 'J’apporterai la checklist actualisée à la réunion de lundi.',
  'Project coordinator': 'Coordination du projet', 'Demo Studio': 'Studio Démo',
  'Atlas · Supplier proposes 22 October': 'Atlas · Le fournisseur propose le 22 octobre',
  'Monday’s review · agenda and next steps': 'Réunion de lundi · ordre du jour et étapes',
  'Can we clarify the difference with the project brief before Monday?': 'Peut-on clarifier l’écart avec le dossier avant lundi ?',
  'Let’s keep the delivery date open until the supplier confirms.': 'Gardons la date ouverte jusqu’à la confirmation du fournisseur.',
  'Atlas launch review': 'Réunion de lancement Atlas',
  'Monday’s review has one unresolved point: the supplier date.': 'Un point reste ouvert pour lundi : la date du fournisseur.',
  'The scope is agreed. Morgan is preparing the checklist; you still owe a date confirmation.': 'Le périmètre est validé. Morgan prépare la checklist ; vous devez encore confirmer la date.',
  'Clarify the date, then send Morgan a short recap before the review.': 'Clarifiez la date, puis préparez un récapitulatif pour Morgan.',
  'Atlas launch review · decisions and next steps': 'Réunion Atlas · décisions et prochaines étapes',
  'Project lead': 'Responsable projet', 'Coordinator': 'Coordination', 'Speaker 1': 'Intervenant 1', 'Speaker 2': 'Intervenant 2',
  'Summary': 'Synthèse', 'Decisions': 'Décisions', 'Actions · owner and due date': 'Actions · responsables et échéances',
  'The launch scope is agreed. The supplier’s proposed delivery date differs from the brief and remains open until written confirmation.': 'Le périmètre du lancement est validé. La date proposée diffère du dossier et reste ouverte jusqu’à confirmation écrite.',
  'Keep the agreed scope and the existing launch checklist.': 'Conserver le périmètre et la checklist de lancement.',
  'Do not circulate a delivery commitment until the supplier confirms.': 'Attendre la confirmation du fournisseur avant de communiquer une date.',
  'Ask the supplier to confirm the delivery date': 'Demander au fournisseur de confirmer la date',
  'Share the revised launch checklist before the review': 'Partager la checklist actualisée avant la réunion',
  'Meeting minutes': 'Compte rendu de réunion',
  'Your morning, with the sources beside you': 'Votre matinée, avec les sources à portée de main',
  'Good morning, Alex. This is a demonstration programme: your day, your commitments and the news you follow, in one place.': 'Bonjour Alex. Votre journée, vos engagements et les actualités que vous suivez, dans un programme de démonstration.',
  'Your Atlas review is on Monday at 10:00. One delivery date remains open; keep that question at the top of the agenda.': 'Votre réunion Atlas est prévue lundi à 10 heures. La date de livraison reste à confirmer : gardez ce point à l’ordre du jour.',
  'Your calendar · Atlas review': 'Votre agenda · Réunion Atlas', 'Your commitments · delivery confirmation': 'Vos engagements · Date de livraison',
  'From the outlets you follow: a demonstration story about repairing everyday devices. Its source is available below; no real-world news claim is made here.': 'Dans les médias que vous suivez : un sujet de démonstration sur la réparation des objets du quotidien. La source est disponible ci-dessous.',
  'Demo Daily · Repairing everyday devices': 'Le Quotidien Démo · Réparer les objets du quotidien',
  'The people and follow-ups worth remembering': 'Les personnes et les suivis à ne pas oublier',
  'Next, a short personal journal about this week’s project follow-ups.': 'À suivre : votre journal personnel et les suivis de la semaine.',
  'Alex’s demo radio': 'La radio démo d’Alex',
  'Repairing everyday devices · demonstration article': 'Réparer les objets du quotidien · article de démonstration',
  'This fictional article illustrates how the real radio page presents a cited story alongside the programme. Its contents are demonstration data, not current news.': 'Cet article fictif illustre la présentation des sources dans la vraie page Radio. Il ne s’agit pas d’une actualité réelle.',
  'Design review': 'Revue du projet', 'Project check-in': 'Point projet',
  'I prefer concise answers, with clear sources and practical examples.': 'Je préfère des réponses concises, avec des sources claires et des exemples concrets.',
  'I prefer concise answers': 'Je préfère des réponses concises',
  'Good morning, Alex. A clear plan and a little room to breathe.': 'Bonjour Alex. Une journée bien préparée, avec un peu de place pour souffler.',
  'Your design review starts at 10:00. Read the notes beforehand, then keep a short break before your afternoon check-in. You have three new messages and one reminder to bring your notebook.': 'Votre réunion commence à 10 heures. Relisez les notes et gardez une pause avant le point de l’après-midi. Vous avez trois nouveaux e-mails et un rappel pour apporter votre carnet.',
  'Clear sky': 'Ciel dégagé', 'meeting room A': 'salle A', 'Video call': 'Visio',
  'Design review — agenda and notes': 'Revue du projet — ordre du jour et notes',
  'Project update for this week': 'Avancement du projet cette semaine',
  'Bring the notebook to the design review': 'Apporter le carnet à la revue du projet',
  'Review the presentation': 'Relire la présentation',
  'Prepare next week’s ideas': 'Préparer les idées de la semaine prochaine',
}));
const phrases = [...translations].sort((a, b) => b[0].length - a[0].length);
function translate(value) {
  if (Array.isArray(value)) return value.map(translate);
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, translate(item)]));
  if (typeof value !== 'string' || value.includes('**/api/') || value.includes('<html')) return value;
  if (translations.has(value)) return translations.get(value);
  return phrases.reduce((result, [from, to]) => result.replaceAll(from, to), value);
}
Object.assign(input, translate(input));
input.selected = process.argv.slice(2);
input.mobileVideoDir = `${output}/mobile-videos`;
fs.mkdirSync(input.mobileVideoDir, { recursive: true });
input.generatedDocuments = ['synthese-atlas-demo.pdf', 'compte-rendu-demo.pdf'].map((filename, index) => ({ id: `a1b2c3d4-0000-4000-8000-00000000000${index + 1}`, title: index === 0 ? 'Synthèse Atlas · Démonstration' : 'Compte rendu · Démonstration', original_filename: filename, mime_type: 'application/pdf', file_size: fs.statSync(`${assetRoot}/demo-files/${filename}`).size, origin: 'generated_document', conversation_id: null, created_at: input.time, expires_at: '2026-10-17T07:30:00Z', shared_by_name: null, localFixtureFile: `${assetRoot}/demo-files/${filename}` }));
const userRoute = input.routes.findLast(route => route.url === '**/api/v1/auth/me');
userRoute.json.language = 'fr';
const appRoute = input.routes.findLast(route => route.url === '**/api/v1/config');
Object.assign(appRoute.json.features, { journals_enabled: true, habits_enabled: true, heartbeat_enabled: true, workboard_enabled: true });
Object.assign(appRoute.json.features, { health_metrics_enabled: true, peers_enabled: true, live_enabled: true, mcp_enabled: true, skills_enabled: true });
Object.assign(appRoute.json.features, { avatar_enabled: true, image_generation_enabled: true, generated_assets_enabled: true, plugins_enabled: true });
Object.assign(userRoute.json, { health_metrics_enabled: true, health_metrics_agents_enabled: true });
// Contract-shaped board examples: every action remains entirely inside intercepted demo APIs.
const ticketBase = { owner_user_id: '00000000-0000-4000-8000-000000000001', parent_id: null, description: 'Données de démonstration.', priority: 'medium', start_at: null, due_at: '2026-10-12T16:00:00Z', assignee_kind: 'lia', assignee_user_id: null, effective_assignee_id: '00000000-0000-4000-8000-000000000001', position: 0, follow_owner: false, follow_assignee: false, created_by: 'user', execution_mode: 'react', status_changed_at: input.time, run_count: 1, run_claimed_at: null, last_run_at: input.time, last_run_outcome: 'waiting', last_run_error: null, last_run_tokens_in: 2400, last_run_tokens_out: 600, last_run_cost_eur: .012, total_tokens_in: 2400, total_tokens_out: 600, total_tokens_cache: 0, total_google_requests: 0, total_cost_eur: .012, created_at: input.time, updated_at: input.time };
const tickets = [
  { ...ticketBase, id: '00000000-0000-4000-8000-0000000000b1', title: 'Préparer la réunion Atlas', status: 'todo', assignee_kind: 'human' },
  { ...ticketBase, id: '00000000-0000-4000-8000-0000000000b2', title: 'Comparer les propositions fournisseurs', status: 'waiting', description: 'Les documents ont été réunis. La date reste à confirmer.' },
  { ...ticketBase, id: '00000000-0000-4000-8000-0000000000b3', title: 'Relire la synthèse du projet', status: 'validating', last_run_outcome: 'success' },
];
input.routes.push({ url: '**/api/v1/workboard/tickets*', json: { tickets, total: tickets.length, counts_by_status: { idea: 0, todo: 1, in_progress: 0, waiting: 1, confirming: 0, validating: 1, done: 0 } } });
for (const ticket of tickets) input.routes.push({ url: `**/api/v1/workboard/tickets/${ticket.id}`, json: { ticket, children: [], comments: [{ id: 'demo-comment', author_kind: 'lia', author_user_id: null, body: 'Le dossier et les e-mails sont réunis. Merci de confirmer la date avant la prochaine étape.', run_id: null, created_at: input.time }], events: [] } });
input.routes.push({ url: '**/api/v1/peers/connections', json: [] });
const nativeSettingsRoutes = [];
const habitsSource = fs.readFileSync(`${repo}/apps/web/e2e/smoke/settings-habits.spec.ts`, 'utf8');
const habitsAst = ts.createSourceFile('habits.ts', habitsSource, ts.ScriptTarget.Latest, true);
const habitsDeclarations = habitsAst.statements.filter(node => ts.isVariableStatement(node) && node.declarationList.declarations.some(declaration => ['RECURRING_ID', 'MORNING_BINS', 'OVERVIEW'].includes(declaration.name.getText(habitsAst)))).map(node => node.getText(habitsAst)).join('\n');
const habitsJs = ts.transpileModule(habitsDeclarations, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
nativeSettingsRoutes.push({ url: '**/api/v1/habits', json: Function(`${habitsJs}\nreturn OVERVIEW;`)() });
const entries = [{ id: 'demo-journal', theme: 'user_observations', title: 'Des réponses concrètes, avec leurs sources', content: 'Lorsque le dossier et les échanges donnent deux dates différentes, Alex préfère garder cette incertitude visible et faire confirmer avant d’agir.', mood: 'reflective', status: 'active', source: 'conversation', personality_code: null, char_count: 182, search_hints: ['sources', 'validation'], injection_count: 2, last_injected_at: input.time, confidence: 'medium', evidence_count: 2, contradiction_count: 0, revision: 1, level: 'L1', created_at: input.time, updated_at: input.time }];
nativeSettingsRoutes.push({ url: '**/api/v1/journals', json: { entries, total: 1, by_theme: [{ theme: 'user_observations', count: 1 }], total_chars: 182, max_total_chars: 50000, usage_pct: .36 } });
nativeSettingsRoutes.push({ url: '**/api/v1/journals/themes', json: { themes: [{ code: 'self_reflection', label: 'Réflexions' }, { code: 'user_observations', label: 'Observations' }, { code: 'ideas_analyses', label: 'Idées et analyses' }, { code: 'learnings', label: 'Apprentissages' }] } });
nativeSettingsRoutes.push({ url: '**/api/v1/journals/settings', json: { journals_enabled: true, journal_consolidation_enabled: false, journal_consolidation_with_history: true, journal_max_total_chars: 50000, journal_context_max_chars: 3000, journal_max_entry_chars: 2000, journal_context_max_results: 5, size_info: { total_chars: 182, max_total_chars: 50000, usage_pct: .36 }, last_cost: { cost_eur: null, timestamp: null, source: null } } });
nativeSettingsRoutes.push({ url: '**/api/v1/health-metrics/tokens', json: { tokens: [] } });
nativeSettingsRoutes.push({ url: '**/api/v1/health-metrics/aggregate*', json: { period: 'day', from_ts: '2026-10-09T00:00:00Z', to_ts: input.time, points: Array.from({ length: 24 }, (_, hour) => ({ bucket: `2026-10-09T${String(hour).padStart(2, '0')}:00:00Z`, heart_rate_avg: 66 + Math.round(Math.sin(hour / 3) * 8), heart_rate_min: 58, heart_rate_max: 86, steps_total: hour > 7 && hour < 20 ? 350 + hour * 16 : 0, has_data: true })), averages: { heart_rate_avg: 67, steps_per_day_avg: 6840 } } });
const routine = { id: 'demo-routine', user_id: userRoute.json.id, title: 'Préparer ma journée', action_prompt: 'Fais le point sur mes rendez-vous, mes e-mails importants et les tâches à reprendre.', recurrence: { freq: 'weekly', times: { mode: 'at', at: [{ hour: 8, minute: 30 }] }, anchor_date: '2026-10-05', interval: 1, byweekday: [1, 2, 3, 4, 5], bymonthday: [], nth_weekday: null, bymonth: [], end: { kind: 'never' } }, user_timezone: 'Europe/Paris', trigger_kind: 'time', condition_config: null, requires_approval: false, execution_mode: 'pipeline', next_trigger_at: '2026-10-12T06:30:00Z', is_enabled: true, status: 'active', last_executed_at: '2026-10-09T06:30:00Z', execution_count: 5, consecutive_failures: 0, last_error: null, schedule_display: 'Du lundi au vendredi à 08:30', next_occurrences: ['2026-10-12T06:30:00Z', '2026-10-13T06:30:00Z'], times_of_day: ['08:30'], runs_per_day: 1, week_slots: [], created_at: input.time, updated_at: input.time };
nativeSettingsRoutes.push({ url: '**/api/v1/scheduled-actions', json: { scheduled_actions: [routine], total: 1, condition_check_minutes: 15, condition_max_fires_per_day: 10 } });
nativeSettingsRoutes.push({ url: '**/api/v1/scheduled-actions/week*', json: { week_start: '2026-10-05', today: 6, actions: [] } });
nativeSettingsRoutes.push({ url: '**/api/v1/peers/me', json: { discovery_enabled: true } });
nativeSettingsRoutes.push({ url: '**/api/v1/peers/requests', json: [] });
nativeSettingsRoutes.push({ url: '**/api/v1/peers/blocks', json: [] });
nativeSettingsRoutes.push({ url: '**/api/v1/peers/access-log*', json: { entries: [], total: 0 } });
nativeSettingsRoutes.push({ url: '**/api/v1/peers/connections', json: [{ id: 'demo-peer', peer_id: 'demo-morgan', peer_display_name: 'Morgan Démo', peer_email_hint: 'm…@ex…test', status: 'accepted', direction: null, requested_at: input.time, responded_at: input.time, context_message: null, my_shares: [{ domain: 'calendar', level: 'availability' }], their_shares: [{ domain: 'task', level: 'titles' }] }] });
nativeSettingsRoutes.push({ url: '**/api/v1/auth/me/voice-mode-preference', json: { voice_mode_enabled: false, voice_stt_mode: 'local', stt_remote_available: true } });
nativeSettingsRoutes.push({ url: '**/api/v1/live/connectors', json: { connectors: [], active_provider: null } });
nativeSettingsRoutes.push({ url: '**/api/v1/live/preferences', json: { interruptions: true, end_of_speech: 'normal', result_delivery: 'when_idle' } });
nativeSettingsRoutes.push({ url: '**/api/v1/radio/preferences', json: { timer_minutes: 30, public_mode: false, verification: null, voice_assignments: {}, format_frequencies: {}, excluded_formats: [], music_volume: .18 } });
nativeSettingsRoutes.push({ url: '**/api/v1/plugins', json: { plugins: [], total: 0 } });
nativeSettingsRoutes.push({ url: '**/api/v1/avatars/config', json: { available: true, enabled: false, connected: false, face_id: null, connector_version: null, session_length_seconds: 180, connect_timeout_seconds: 30 } });
nativeSettingsRoutes.push({ url: '**/api/v1/avatars/faces', json: [] });
nativeSettingsRoutes.push({ url: '**/api/v1/image-generation/options', json: { active_model: 'gpt-image-1', provider: 'openai', qualities: [{ value: 'low', min_cost_usd: 0.01, max_cost_usd: 0.02 }, { value: 'medium', min_cost_usd: 0.04, max_cost_usd: 0.06 }, { value: 'high', min_cost_usd: 0.16, max_cost_usd: 0.25 }], sizes: [{ value: '1024x1024', orientation: 'square', tier: null, label_key: 'settings.image_generation.size_square' }, { value: '1536x1024', orientation: 'landscape', tier: null, label_key: 'settings.image_generation.size_landscape' }], effective_quality: 'medium', effective_size: '1024x1024', prompt_enhancement_available: true } });
nativeSettingsRoutes.push({ url: '**/api/v1/generated-assets*', json: { items: [], total: 0, total_bytes: 0, keep: null } });
const llmRoutes = require(`${compiled}/capture/public-screenshot-data.js`).publicScreenshotRoutes().filter(route => typeof route.url === 'string' && route.url.includes('/admin/llm-config/'));
const names = { 'Query Analyzer': 'Analyse de la demande', 'Planner': 'Planification', 'ReAct Agent': 'Agent ReAct', 'Contacts Agent': 'Agent Contacts', 'Calendar Agent': 'Agent Agenda', 'Response': 'Réponse' };
for (const route of llmRoutes) if (route.json?.configs) for (const slot of route.json.configs) slot.info.display_name = names[slot.info.display_name] ?? slot.info.display_name;
nativeSettingsRoutes.push(...llmRoutes);
nativeSettingsRoutes.push({ url: '**/api/v1/telephony/calls*', json: [{ id: 'demo-call', callee_display: 'Fournisseur Démo', objective: 'Clarifier la date de livraison Atlas', status: 'completed', outcome: 'partial', summary: 'Démonstration : le fournisseur propose le 22 octobre. Aucun appel réel n’a été passé.', debrief: { key_points: ['Date proposée : le 22 octobre.'], commitments: [], follow_up_tasks: ['Confirmer la date avant de modifier le planning.'], follow_up_reminders: [], follow_up_draft: null, uncertainties: ['La date reste à valider par Alex.'] }, structured_data: { agreed: null, proposed_datetime: null, pending_user_decision: 'Choisir la date à confirmer au fournisseur.' }, call_seconds: 62, created_at: input.time, completed_at: input.time, call_kind: 'third_party', call_mode: 'direct', usage: null, relay_outcome: null }] });
nativeSettingsRoutes.push({ url: '**/api/v1/telephony/identity', json: { phone_number: null, verified: false, verified_at: null, rich_context_enabled: false, disabled_domains: [], available_domains: ['calendar', 'contacts', 'emails', 'tasks', 'context'], verification_pending: false, call_mode: 'delegated', call_mode_effective: 'delegated', live_available: true, live_unavailable_reason: null } });
nativeSettingsRoutes.push({ url: '**/api/v1/heartbeat/settings', json: { heartbeat_enabled: true, heartbeat_notify_start_hour: 8, heartbeat_notify_end_hour: 21, available_sources: ['calendar', 'emails', 'tasks', 'interests', 'departure'], disabled_sources: [], all_sources: ['calendar', 'emails', 'tasks', 'weather', 'interests', 'memories', 'journals', 'health_signals', 'birthdays', 'open_loops', 'departure', 'habits', 'workboard'], source_dependencies: { departure: ['calendar'] }, moment_kinds_disabled: [], all_moment_kinds: ['event_followup'], moment_kind_dependencies: {} } });
nativeSettingsRoutes.push({ url: '**/api/v1/mcp/servers', json: { servers: [], total: 0 } });
nativeSettingsRoutes.push({ url: '**/api/v1/skills', json: { skills: ['unit-converter', 'preparation-reunion', 'synthese-recherche', 'redaction-professionnelle', 'calendar-month', 'interactive-map'].map((name, index) => ({ name, description: ['Convertir des unités dans une interface interactive.', 'Préparer une réunion avec son contexte et ses participants.', 'Structurer une recherche avec des sources.', 'Rédiger un message professionnel adapté à la situation.', 'Afficher un calendrier mensuel interactif.', 'Explorer une carte interactive.'][index], descriptions: null, scope: 'admin', category: 'productivity', priority: 10, always_loaded: false, has_scripts: true, has_plan_template: false, enabled_for_user: true, admin_enabled: true, outputs: index === 0 || index > 3 ? ['app'] : ['text'], provenance: 'system' })), total: 6 } });
nativeSettingsRoutes.push({ url: '**/api/v1/skills/*/preview', json: { detail: 'no preview' }, status: 404 });
input.routes.push(...nativeSettingsRoutes);

async function film(entryPage, input) {
  const report = [];
  const origin = new URL(input.baseUrl).origin;
  async function captureScene(id, urlPath, readyText, interaction, exercised) {
    if (input.selected.length && !input.selected.includes(id)) return;
    const mobileContext = id === 'mobile' ? await entryPage.context().browser().newContext({ locale: 'fr-FR', timezoneId: 'Europe/Paris', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 1, recordVideo: { dir: input.mobileVideoDir, size: { width: 390, height: 844 } } }) : null;
    const page = await (mobileContext ?? entryPage.context()).newPage();
    page.setDefaultTimeout(15000);
    const unexpected = [];
    const errors = [];
    const writes = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin || url.pathname.startsWith('/api/')) {
        unexpected.push(`${route.request().method()} ${url.origin === origin ? url.pathname : url.origin}`);
        return route.abort();
      }
      return route.continue();
    });
    for (const fixture of input.routes) await page.route(typeof fixture.url === 'string' ? fixture.url : new RegExp(fixture.url.regex), route => route.fulfill(fixture.status === 204 ? { status: 204, body: '' } : { status: fixture.status ?? 200, json: fixture.json }));
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: input.fontCss, headers: { 'Access-Control-Allow-Origin': '*' } }));
    await page.route('https://fonts.gstatic.com/lia-e2e/MaterialSymbolsOutlined.woff2', route => route.fulfill({ contentType: 'font/woff2', path: input.fontPath, headers: { 'Access-Control-Allow-Origin': '*' } }));
    await page.route('**/api/v1/notifications/stream', () => undefined);
    await page.route(`**/api/v1/radio/sessions/${input.radioId}/segments/*/audio`, route => route.fulfill({ contentType: 'audio/wav', path: input.silentAudioPath }));
    await page.route(`**/api/v1/radio/sessions/${input.radioId}/stop`, route => route.fulfill({ status: 204, body: '' }));
    await page.routeWebSocket('**/*', socket => socket.close());
    await page.context().addCookies([{ name: 'lia_session', value: 'fictional-motion-capture', domain: '127.0.0.1', path: '/' }, { name: 'lia_gender', value: 'male', domain: '127.0.0.1', path: '/' }]);
    await page.addInitScript(({ time }) => {
      if (window !== window.top) return;
      if (navigator.serviceWorker) navigator.serviceWorker.register = async () => { throw new DOMException('Disabled for capture', 'NotAllowedError'); };
      const now = new Date(time).getTime();
      Object.defineProperty(window, 'Date', { value: new Proxy(Date, { construct(target, args) { return Reflect.construct(target, args.length ? args : [now]); }, get(target, key, receiver) { return key === 'now' ? () => now : Reflect.get(target, key, receiver); } }) });
      localStorage.setItem('theme', 'light');
      localStorage.setItem('lia_eyes_widget_prefs', JSON.stringify({ state: { visible: true, style: 'bip', size: 'sm', position: null, landingPosition: null }, version: 0 }));
    }, { time: input.time });
    await page.route('**/api/v1/conversations/me/messages*', route => route.fulfill({ json: id === 'approval' ? input.approvalMessages : id === 'skill' ? input.skillMessages : input.messages }));
    await page.route('**/api/v1/generated-assets?*', route => {
      const family = new URL(route.request().url()).searchParams.get('family');
      const items = family === 'documents' ? input.generatedDocuments.map(({ localFixtureFile, ...item }) => item) : [];
      return route.fulfill({ json: { items, total: items.length, total_bytes: items.reduce((total, item) => total + item.file_size, 0), limit: 24, offset: 0, max_limit: 100, keep: { kept_files: 0, kept_bytes: 0, max_files: 100, max_bytes: 100000000 } } });
    });
    if (id === 'approval') await page.route('**/api/v1/agents/hitl/pending', route => route.fulfill({ json: input.pending }));
    if (id === 'approval' || id === 'chat' || id === 'mobile') await page.route('**/api/v1/agents/chat/stream', async route => {
      writes.push({ path: '/api/v1/agents/chat/stream', body: route.request().postDataJSON() });
      const answer = id === 'approval' ? '<p>Brouillon validé dans cette démonstration. Aucun message réel n’a été envoyé.</p>' : '<h2>Votre réunion de lancement, prête à préparer</h2><p>Le dossier et les e-mails concordent sur le périmètre. Une date reste à clarifier : le dossier prévoit le 19 octobre et le fournisseur propose le 22.</p><p>Je peux préparer un message pour votre validation.</p>';
      const tokens = answer.split(/(?<=\s)/);
      const body = tokens.map(content => `data: ${JSON.stringify({ type: 'token', content, metadata: null })}\n\n`).join('') + 'data: {"type":"done","content":"","metadata":null}\n\n';
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body });
    });
    const started = Date.now();
    const video = page.video();
    try {
      await page.goto(`${input.baseUrl}${urlPath}`, { waitUntil: 'domcontentloaded' });
      await page.getByText(readyText, { exact: false }).filter({ visible: true }).first().waitFor({ timeout: 60000 });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(1000);
      const clipStartSeconds = (Date.now() - started) / 1000;
      await page.screenshot({ path: `${input.output}/${id}-before.png`, caret: 'hide' });
      await page.waitForTimeout(1200);
      await interaction(page);
      await page.mouse.move(1300, 920);
      await page.waitForTimeout(4300);
      await page.screenshot({ path: `${input.output}/${id}.png`, caret: 'hide' });
      const text = await page.locator('body').innerText();
      const emails = text.match(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g) ?? [];
      if (emails.some(email => !/@example\.(test|com|org|net)$/.test(email))) throw new Error(`Non-demo email in ${id}`);
      if (/\bsk-[\w-]{16,}|\bAIza[\w-]{20,}/.test(text)) throw new Error(`Credential-like content in ${id}`);
      if (unexpected.length || errors.length) throw new Error(JSON.stringify({ id, unexpected, errors }));
      const durationSeconds = (Date.now() - started) / 1000 - clipStartSeconds;
      await page.close();
      if (mobileContext) await mobileContext.close();
      const videoPath = await video.path();
      report.push({ id, route: urlPath, videoPath, clipStartSeconds, durationSeconds, exercised, errors, unexpected, writes });
    } catch (error) {
      await page.screenshot({ path: `${input.output}/${id}-failure.png` }).catch(() => undefined);
      const text = await page.locator('body').innerText().catch(() => '');
      const buttons = await page.getByRole('button').allTextContents().catch(() => []);
      await page.close();
      if (mobileContext) await mobileContext.close();
      report.push({ id, route: urlPath, failed: String(error), text: text.slice(0, 4000), buttons, errors, unexpected });
    }
  }
  await captureScene('relations', '/fr/dashboard/relations', 'Morgan Démo', async page => {
    await page.getByRole('button', { name: /Morgan Démo/ }).first().click();
    await page.getByText('Un point reste ouvert pour lundi', { exact: false }).waitFor();
    await page.waitForTimeout(1200);
    await page.getByRole('button', { name: /^Engagements/ }).click();
    await page.waitForTimeout(900);
    await page.getByRole('button', { name: /^Emails échangés/ }).click();
    await page.mouse.wheel(0, 320);
  }, ['native Relations overview, opening Morgan detail, commitments and exchanged emails']);
  await captureScene('radio', '/fr/dashboard/radio', 'Radio', async page => {
    await page.getByRole('button', { name: 'Lancer la radio', exact: true }).last().click();
    await page.getByRole('heading', { name: 'Votre matinée, avec les sources à portée de main', exact: true }).waitFor();
    await page.waitForTimeout(2100);
    await page.getByRole('button', { name: /^Pause/ }).click();
    await page.waitForTimeout(1000);
    const source = page.locator('summary').filter({ hasText: 'Quotidien Démo' }).first();
    await source.click();
    await page.getByRole('article').waitFor();
  }, ['native Radio start, playback of locally generated silent WAV, pause, source interaction; no generated voice']);
  await captureScene('approval', '/fr/dashboard/chat', 'Un message prêt à être validé', async page => {
    await page.getByRole('button', { name: 'Confirmer', exact: true }).click();
    await page.getByText('Brouillon validé dans cette démonstration', { exact: false }).waitFor();
  }, ['native pending HITL rehydration, confirm click, captured native chat-stream request and demo result; no email sent']);
  await captureScene('chat', '/fr/dashboard/chat', 'Votre réunion de lancement', async page => {
    const textbox = page.getByRole('textbox').last();
    await textbox.fill('Quelle date dois-je confirmer avec le fournisseur ?');
    await page.waitForTimeout(1300);
    await textbox.press('Enter');
    await page.waitForTimeout(2200);
  }, ['native chat composer, Enter submission, real streaming renderer supplied with fictional SSE tokens']);
  await captureScene('knowledge', `/fr/dashboard/spaces/${input.spaceId}`, 'Projet Atlas', async page => {
    const search = page.getByRole('textbox', { name: /Rechercher/ }).first();
    if (await search.count()) { await search.fill('lancement'); await page.waitForTimeout(1200); await search.clear(); }
    await page.mouse.wheel(0, 340);
  }, ['native knowledge-space document and connected-source lists, real scroll; no indexing']);
  await captureScene('skill', '/fr/dashboard/chat', 'Convertissez les mesures', async page => {
    await page.mouse.move(300, 450); await page.mouse.wheel(0, -2400); await page.waitForTimeout(500);
    const frame = page.frameLocator('iframe.lia-skill-app-widget__iframe');
    await frame.getByRole('button', { name: /Longueur/ }).press('Enter');
    await frame.locator('#value-in').fill('2.5');
    await frame.locator('#unit-from').selectOption('m');
    await page.waitForTimeout(900);
    await frame.locator('#unit-to').selectOption('cm');
    await frame.locator('#result').getByText(/250/).waitFor();
  }, ['native SkillAppWidget, real French system converter script, typed value/unit selection and computed 250cm result']);
  await captureScene('meetings', `/fr/dashboard/meetings/${input.meetingId}`, 'Réunion Atlas', async page => {
    await page.mouse.wheel(0, 450); await page.waitForTimeout(1600); await page.mouse.wheel(0, -280);
  }, ['native ready meeting page, participants, decisions, action items and scroll; no recording/transcription/provider']);
  await captureScene('workboard', '/fr/dashboard/workboard', 'Préparer la réunion Atlas', async page => {
    await page.getByRole('button', { name: 'Comparer les propositions fournisseurs', exact: true }).click();
    await page.getByRole('dialog').waitFor();
  }, ['native workboard columns/tickets and opening native ticket detail with demo comments/costs']);
  await captureScene('briefing', '/fr/dashboard', 'Revue du projet', async page => {
    await page.mouse.wheel(0, 660); await page.waitForTimeout(1800); await page.mouse.wheel(0, 150);
  }, ['native Today Briefing cards and scroll; handwritten fictional weather/agenda/mail/tasks']);
  await captureScene('memory', '/fr/dashboard/settings?section=memories', 'Mémoire', async page => {
    await page.getByRole('button', { name: /Préférences \(/ }).first().click();
    await page.waitForTimeout(900);
    const edit = page.getByRole('button', { name: 'Modifier', exact: true }).first();
    await edit.click(); await page.getByRole('dialog').waitFor();
  }, ['native memory list/edit dialog, no save']);
  await captureScene('routines', '/fr/dashboard/settings?section=scheduled-actions', 'Préparer ma journée', async page => {
    await page.locator('summary').filter({ hasText: 'Vue de la semaine' }).click();
    await page.getByText('Préparer ma journée', { exact: true }).waitFor();
    await page.waitForTimeout(1400);
    await page.mouse.wheel(0, 160);
  }, ['native routine cards and schedule with fictional sample recurrence; no run triggered']);
  await captureScene('habits', '/fr/dashboard/settings?section=habits', 'Habitudes', async page => {
    const rhythm = page.locator('summary').filter({ hasText: 'Rythme d’activité' }).first();
    if (await rhythm.count()) await rhythm.click();
    await page.mouse.wheel(0, 400); await page.waitForTimeout(1400); await page.mouse.wheel(0, -160);
  }, ['native habits settings, learned request/rhythm cards from existing typed E2E fixture; no mutation']);
  await captureScene('journals', '/fr/dashboard/settings?section=journals', 'Journaux personnels', async page => {
    await page.getByRole('button', { name: /Observations utilisateur/ }).click();
    await page.mouse.wheel(0, 360); await page.waitForTimeout(1400); await page.mouse.wheel(0, -140);
  }, ['native personal journals list and settings; handwritten fictional entry, no generation or consolidation']);
  await captureScene('health', '/fr/dashboard/settings?section=health-metrics', 'Données santé', async page => {
    const charts = page.getByRole('button', { name: 'Graphiques', exact: true });
    if (await charts.getAttribute('aria-expanded') === 'false') await charts.click();
    await page.mouse.wheel(0, 280);
  }, ['native health metrics charts with fictional aggregates; no medical inference or real data']);
  await captureScene('peers', '/fr/dashboard/settings?section=peer-connections', 'Connexions', async page => {
    const fold = page.locator('summary').filter({ hasText: 'Mes connexions' }).first();
    await fold.click();
    await page.getByText('Morgan Démo', { exact: true }).waitFor();
    await page.mouse.wheel(0, 320);
  }, ['native peer connection card and two sharing directions; no real person connected or access granted']);
  await captureScene('voice', '/fr/dashboard/settings?section=voice-mode', 'Mode vocal', async page => {
    await page.mouse.wheel(0, 310); await page.waitForTimeout(1200); await page.mouse.wheel(0, -150);
  }, ['native voice mode, speech engine and wake-word settings; no microphone or generated audio']);
  await captureScene('connections', '/fr/dashboard/settings?section=connectors', 'Connecteurs', async page => {
    await page.mouse.wheel(0, 420); await page.waitForTimeout(1300); await page.mouse.wheel(0, -160);
  }, ['native provider connector catalogue; no account connected or OAuth started']);
  await captureScene('avatars', '/fr/dashboard/settings?section=eyes-style', "Style de l'avatar", async page => {
    await page.getByRole('button', { name: /^Smiley/ }).click();
    await page.waitForTimeout(1800);
    await page.getByRole('button', { name: /^Bip/ }).click();
  }, ['native avatar style selector, native preview hover/focus life and local preference selection Smiley then Bip; no external avatar provider']);
  await captureScene('extensions', '/fr/dashboard/settings?section=skills', 'Compétences LIA', async page => {
    const fold = page.locator('summary').filter({ hasText: /Skills système|Skills LIA|Compétences système/ }).first();
    if (await fold.count()) await fold.click();
    await page.mouse.wheel(0, 380);
  }, ['native skills gallery, existing real system skill names and demo descriptions; no invocation or import']);
  await captureScene('mcp', '/fr/dashboard/settings?section=mcp-servers', 'Serveurs MCP', async page => {
    const add = page.getByRole('button', { name: /Ajouter/ }).last();
    await add.click(); await page.getByRole('dialog').waitFor();
  }, ['native MCP server configuration dialog, no server connected or external call']);
  await captureScene('administration', '/fr/dashboard/settings?section=admin-usage-limits', 'Limites', async page => {
    await page.getByText('morgan@example.test', { exact: true }).waitFor();
    await page.mouse.wheel(0, 280);
  }, ['native administration instance ceiling/user quota gauges; fictional values, no configuration saved']);
  await captureScene('plugins', '/fr/dashboard/settings?section=plugins', 'Plugins', async page => {
    const url = page.getByRole('textbox', { name: /Importer.*URL|depuis.*URL/i }).first();
    if (await url.count()) await url.focus();
    await page.mouse.wheel(0, 160);
  }, ['native plugin ZIP/URL import controls and empty installed-plugin list; no installation or external download']);
  await captureScene('live', '/fr/dashboard/settings?section=live-mode', 'Mode Live', async page => {
    await page.getByRole('combobox').first().click(); await page.waitForTimeout(900); await page.keyboard.press('Escape');
    await page.mouse.wheel(0, 330); await page.waitForTimeout(1200); await page.mouse.wheel(0, -150);
  }, ['native Live preference controls with no active provider connector; no microphone, WebRTC or live session']);
  await captureScene('simli', '/fr/dashboard/settings?section=avatar', 'Avatar', async page => {
    await page.mouse.wheel(0, 160);
  }, ['native speaking-avatar Simli settings, disconnected and disabled; no face image, voice or session synthesized']);
  await captureScene('images', '/fr/dashboard/settings?section=image-generation', "Génération d'images", async page => {
    await page.getByRole('combobox').first().click(); await page.waitForTimeout(1000);
    await page.keyboard.press('Escape'); await page.mouse.wheel(0, 160);
  }, ['native image-generation quality/size/prompt-enhancement preference controls with fictional model pricing; no image generated']);
  await captureScene('files', '/fr/dashboard/settings?section=generated-assets', 'Mes fichiers', async page => {
    const documents = page.getByRole('tab', { name: 'Documents', exact: true });
    await documents.click();
    await page.getByTestId('generated-asset-card').first().waitFor();
    await page.mouse.wheel(0, 160);
  }, ['native generated-files gallery, opening the Documents tab and actual local fictional PDF fixture metadata; PDFs created locally for filming, no provider generation']);
  await captureScene('phone', '/fr/dashboard/settings?section=telephony-calls', 'Fournisseur Démo', async page => {
    await page.locator('summary').filter({ hasText: 'Fournisseur Démo' }).click();
    await page.mouse.wheel(0, 260);
  }, ['native recent-calls row and structured debrief with explicitly fictional call data; no telephone call placed']);
  await captureScene('phone-identity', '/fr/dashboard/settings?section=telephony-identity', 'Téléphonie', async page => {
    await page.mouse.wheel(0, 290); await page.waitForTimeout(900);
  }, ['native phone identity/Live versus Live direct/domain-access settings, blank number and no verification call']);
  await captureScene('agents', '/fr/dashboard/settings?section=admin-llm-config', 'Configuration LLM', async page => {
    await page.getByText('Agent Contacts', { exact: true }).waitFor();
    await page.getByText('Agent Contacts', { exact: true }).scrollIntoViewIfNeeded();
  }, ['native LLM configuration list and domain-agent entries, reusing existing typed public screenshot fixtures; no orchestration run or configuration write']);
  await captureScene('heartbeat', '/fr/dashboard/settings?section=heartbeat', 'Notifications proactives', async page => {
    await page.locator('summary').first().click(); await page.mouse.wheel(0, 270);
  }, ['native proactive-notification time window and allowed-source controls; no notification generated']);
  await captureScene('mobile', '/fr/dashboard/chat', 'Votre réunion de lancement', async page => {
    const textbox = page.getByRole('textbox').last();
    await textbox.fill('Quelle date dois-je confirmer ?'); await page.waitForTimeout(1200);
    await textbox.press('Enter'); await page.waitForTimeout(2200);
  }, ['native mobile 390x844 chat and compact Bip companion, real responsive layout/composer/submission supplied fictional SSE tokens; no provider inference']);
  return report;
}

const guard = await createApiNetworkGuard();
const chromium = fs.readdirSync('/ms-playwright').find(name => /^chromium_headless_shell-\d+$/.test(name));
const config = `${output}/cli-config.json`;
const videoDir = `${output}/videos-${Date.now()}`;
fs.writeFileSync(config, JSON.stringify({ browser: { browserName: 'chromium', isolated: true, launchOptions: { executablePath: `/ms-playwright/${chromium}/chrome-headless-shell-linux64/chrome-headless-shell`, args: ['--disable-background-networking', '--disable-component-update', '--disable-domain-reliability', '--disable-sync', '--disable-client-side-phishing-detection', '--safebrowsing-disable-auto-update', '--no-default-browser-check', '--no-first-run', '--no-pings', '--metrics-recording-only', '--disable-features=AutofillServerCommunication,CertificateTransparencyComponentUpdater,OptimizationHints,MediaRouter,Translate,NetworkTimeServiceQuerying'], proxy: guard.proxy }, contextOptions: { locale: 'fr-FR', timezoneId: 'Europe/Paris', viewport: { width: 1440, height: 960 }, reducedMotion: 'no-preference', serviceWorkers: 'allow', recordVideo: { dir: videoDir, size: { width: 1440, height: 960 } } } }, outputDir: output }, null, 2));
const program = `${output}/program.js`;
fs.writeFileSync(program, `async page => (${film.toString()})(page, ${JSON.stringify(input)})`);
const cliArgs = ['--yes', '--package', '@playwright/cli@0.1.22', 'playwright-cli', '--session', `motion-native-${process.pid}`];
async function cli(args) {
  const { stdout } = await execute('npx', [...cliArgs, ...args], { cwd: '/capture', encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
  if (stdout.includes('### Error')) throw new Error(stdout);
  return stdout;
}
let report;
try {
  await cli(['open', 'about:blank', `--config=${config}`]);
  const result = await cli(['run-code', `--filename=${program}`]);
  fs.writeFileSync(`${output}/capture-cli-${Date.now()}.log`, result);
  const match = result.match(/### Result\r?\n([\s\S]*?)\r?\n###/);
  if (!match) throw new Error('Missing native capture result');
  report = JSON.parse(match[1]);
} finally {
  guard.quarantine();
  await cli(['close']);
  await guard.close();
}
const manifestPath = `${assetRoot}/manifest.json`;
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
for (const capture of report) {
  if (capture.failed) { console.log(JSON.stringify(capture)); continue; }
  const still = `${assetRoot}/fr/${capture.id}.png`;
  fs.copyFileSync(`${output}/${capture.id}.png`, still);
  fs.copyFileSync(`${output}/${capture.id}-before.png`, `${assetRoot}/fr/${capture.id}-before.png`);
  // Raw videos remain proof artifacts; the parent encoder trims and exports 30fps MP4.
  const raw = `${assetRoot}/fr/${capture.id}-raw.webm`;
  fs.copyFileSync(capture.videoPath, raw);
  const png = fs.readFileSync(still);
  const asset = { id: capture.id, path: `capture-v2/fr/${capture.id}.png`, beforePath: `capture-v2/fr/${capture.id}-before.png`, type: 'image', width: png.readUInt32BE(16), height: png.readUInt32BE(20), sha256: sha(png), locale: 'fr', nativeFrontend: true, fictionalData: true, clipRawPath: `capture-v2/fr/${capture.id}-raw.webm`, clipStartSeconds: capture.clipStartSeconds, durationSeconds: capture.durationSeconds, route: capture.route, exercised: capture.exercised, writes: capture.writes };
  manifest.assets = manifest.assets.filter(item => item.id !== capture.id).concat(asset);
}
manifest.capture = { capturedAt: new Date().toISOString(), viewport: { width: 1440, height: 960 }, browser: 'official Playwright Chromium 1.63.0', runtime: 'existing isolated .next-e2e-landing-final standalone build in lia-web-dev, APIs disabled server-side', currentRepositoryRevision: execFileSync('git', ['-C', repo, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), exactCompiledRevisionEstablished: false, data: 'Fictional API fixtures in native frontend. No live backend/account, provider, external action, generated voice, or product DOM replacement.', transportGuardBlocked: guard.blockedRequests, fixtureSource: 'apps/web/e2e/capture/landing-proof-data.ts', results: report.map(({ videoPath, text, buttons, ...rest }) => rest) };
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
fs.writeFileSync(`${output}/capture-report-${Date.now()}.json`, JSON.stringify({ report, transportGuardBlocked: guard.blockedRequests }, null, 2) + '\n');
console.log(JSON.stringify({ captured: report.filter(item => !item.failed).map(item => item.id), failures: report.filter(item => item.failed).map(item => item.id), transportGuardBlocked: guard.blockedRequests }));
