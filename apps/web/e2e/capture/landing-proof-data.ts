/** Fictional scenarios rendered by the real app, never by a live backend. */
import type { RAGSpaceDetail } from '../../src/types/rag-spaces';
import type { AdminUserUsageLimitResponse } from '../../src/types/usage-limits';
import type { MeetingDetail } from '../../src/types/meetings';
import type { RadioArticle, RadioSessionState } from '../../src/lib/radio/types';
import { appConfig } from '../fixtures/dashboard-shell';
import { messages, publicScreenshotRoutes } from './public-screenshot-data';

export const PROOF_TIME = '2026-10-10T07:30:00Z';
export const SPACE_ID = '00000000-0000-4000-8000-000000000ad1';
export const MEETING_ID = '00000000-0000-4000-8000-000000000ad2';
export const RADIO_ID = '00000000-0000-4000-8000-000000000ad3';
export const PROOF_NAMES = [
  'dossier', 'approval', 'knowledge', 'skill', 'memory', 'administration', 'relations', 'meetings', 'radio',
] as const;
export type ProofName = (typeof PROOF_NAMES)[number];

/** Same HTML vocabulary as showroom/response-html.ts, through MarkdownContent. */
export const MULTI_SOURCE_RESPONSE = `<div class="lia-response">
<h2>Your launch review, ready to discuss</h2>
<p>The project brief, the latest supplier email and the meeting notes agree on the scope. One delivery date still needs clarification.</p>
<div class="lia-callout lia-callout-warning"><p class="lia-callout__title">A date to resolve before the meeting</p><p>The brief says 19 October; the supplier email proposes 22 October. Ask which date can be committed to before sharing the plan.</p></div>
<dl class="lia-kv"><dt>Project brief</dt><dd><strong>Launch plan.pdf · target 19 October</strong></dd><dt>Supplier email</dt><dd><strong>supplier@example.test · proposed 22 October</strong></dd><dt>Meeting notes</dt><dd><strong>Review · decision still open</strong></dd></dl>
<h3>Three practical next steps</h3><ol class="lia-steps"><li>Clarify the delivery date with the supplier.</li><li>Keep the unresolved date visible in Monday's review.</li><li>Prepare a message for your approval before sending it.</li></ol>
<div class="lia-callout lia-callout-info"><p class="lia-callout__title">Sources used in this example</p><p>Launch plan.pdf (Project Atlas space), supplier email and Review minutes. Demonstration data; no message has been sent.</p></div></div>`;

export const APPROVAL_RESPONSE = `<div class="lia-response"><h2>A message ready for your review</h2><p>The supplier's proposed date differs from your project brief. Here is a short message asking for a clear commitment.</p><dl class="lia-kv"><dt>Recipient</dt><dd><strong>supplier@example.test</strong></dd><dt>Subject</dt><dd><strong>Confirm the Atlas delivery date</strong></dd></dl><p>You can confirm, ask for a change, or cancel below. This is a demonstration draft; nothing has been sent.</p></div>`;

export const PENDING_APPROVAL = {
  message_id: 'landing-proof-approval',
  draft_id: 'landing-proof-email-draft',
  interrupt_ts: PROOF_TIME,
  generated_question: 'Would you like to send this draft?',
  action_requests: [{
    type: 'draft_critique', draft_type: 'email', draft_id: 'landing-proof-email-draft',
    draft_content: {
      to: 'supplier@example.test', subject: 'Confirm the Atlas delivery date',
      body: 'Hello,\n\nOur project brief targets 19 October, while your latest email mentions 22 October. Could you confirm the date your team can commit to?\n\nThank you,\nAlex Demo',
    },
    available_actions: [
      { action: 'confirm', label: 'confirm', style: 'primary' },
      { action: 'edit', label: 'edit', style: 'ghost' },
      { action: 'cancel', label: 'cancel', style: 'secondary' },
    ], registry_ids: ['landing-proof-email-draft'],
  }],
};

export const PROOF_SPACE: RAGSpaceDetail = {
  id: SPACE_ID, name: 'Project Atlas',
  description: 'Demo project: a shared context for the brief, emails and meeting decisions.',
  is_active: true, kind: null, document_count: 4, ready_document_count: 4,
  total_size: 724000, created_at: PROOF_TIME, updated_at: PROOF_TIME,
  documents: [
    { id: 'proof-doc-brief', original_filename: 'Launch plan.pdf', source_type: 'upload', content_type: 'application/pdf', file_size: 420000 },
    { id: 'proof-doc-drive', original_filename: 'Launch checklist.docx', source_type: 'drive', content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', file_size: 40000 },
    { id: 'proof-doc-email', original_filename: 'Supplier · Delivery date.eml', source_type: 'mail', content_type: 'text/plain', file_size: 84000 },
    { id: 'proof-doc-meeting', original_filename: 'Launch review · Minutes.md', source_type: 'meeting', content_type: 'text/markdown', file_size: 180000 },
  ].map(document => ({ ...document, source_type: document.source_type as 'upload' | 'drive' | 'mail' | 'meeting', status: 'ready', error_message: null, error_code: null, chunk_count: 12, embedding_model: 'text-embedding-3-small', embedding_tokens: 8200, embedding_cost_eur: 0.000164, drive_file_id: document.source_type === 'drive' ? 'proof-drive-file' : null, created_at: PROOF_TIME })),
  drive_sources: [{ id: 'proof-drive', folder_id: 'proof-folder', folder_name: 'Atlas · Project documents', sync_status: 'completed', last_sync_at: PROOF_TIME, file_count: 1, synced_file_count: 1, error_message: null, created_at: PROOF_TIME }],
  mail_sources: [{ id: 'proof-mail', label_id: 'proof-label', label_name: 'Atlas / Suppliers', sync_status: 'completed', last_sync_at: PROOF_TIME, thread_count: 1, synced_thread_count: 1, error_message: null, created_at: PROOF_TIME }],
};

export function proofUsers(): AdminUserUsageLimitResponse[] {
  return [
    { email: 'alex@example.test', full_name: 'Alex Demo', cycle_tokens: 185000, cycle_messages: 86, cycle_cost: 3.7, status: 'ok' as const },
    { email: 'morgan@example.test', full_name: 'Morgan Demo', cycle_tokens: 410000, cycle_messages: 174, cycle_cost: 8.2, status: 'warning' as const },
    { email: 'sam@example.test', full_name: 'Sam Demo', cycle_tokens: 92000, cycle_messages: 39, cycle_cost: 1.84, status: 'ok' as const },
  ].map((user, index) => ({ ...user, user_id: `proof-user-${index}`, is_active: true, is_usage_blocked: false, blocked_reason: null, blocked_at: null, blocked_by: null, token_limit_per_cycle: 500000, message_limit_per_cycle: 200, cost_limit_per_cycle: 10, token_limit_absolute: 5000000, message_limit_absolute: 2000, cost_limit_absolute: 100, total_tokens: user.cycle_tokens * 3, total_messages: user.cycle_messages * 3, total_cost: user.cycle_cost * 3, created_at: PROOF_TIME }));
}

export function proofMessages(content: string, question: string, metadata: unknown = null) {
  const result = messages(content, metadata, question);
  return { ...result, messages: result.messages.map(message => ({ ...message, created_at: message.role === 'user' ? '2026-10-10T07:29:00Z' : PROOF_TIME, cost_eur: message.role === 'assistant' ? 0.0018 : undefined })) };
}

export function skillMessages(frame: { html: string; title: string; aspect_ratio: number }) {
  return proofMessages('<div class="lia-response"><h2>Convert measurements here in the conversation</h2><p>This example uses LIA’s existing unit-converter skill. Choose a value and units below; the result updates instantly.</p></div><div class="lia-skill-app" data-registry-id="proof-unit-converter"></div>', 'Give me a converter for the measurements in my project brief.', {
    widgets: { 'proof-unit-converter': { id: 'proof-unit-converter', type: 'SKILL_APP', payload: { skill_name: 'unit-converter', title: frame.title, html_content: frame.html, aspect_ratio: frame.aspect_ratio, is_system_skill: true }, meta: { source: 'skill', timestamp: PROOF_TIME } } },
  });
}

/** The runner checks these against types extracted from the actual Relations hook. */
export const PROOF_RELATIONS = {
  relations: [{ display_name: 'Morgan Demo', identity_confidence: 'exact', open_loops_count: 2, calls_count: 1, peer_messages_count: 1, last_interaction_at: '2026-10-09T16:00:00Z', is_favorite: true, is_peer: true }],
  relations_total: 1, debrief_enabled: true,
};

export const PROOF_RELATION = {
  display_name: 'Morgan Demo', identity_confidence: 'exact',
  open_loops: [
    { id: 'proof-loop-date', subject: 'Confirm the supplier delivery date', direction: 'user_owes', due_hint: 'Before Monday’s review', days_open: 2 },
    { id: 'proof-loop-checklist', subject: 'Morgan will send the launch checklist', direction: 'they_owe', due_hint: '12 October', days_open: 1 },
  ], open_loops_total: 2,
  recent_calls: [{ id: 'proof-call', objective: 'Align on the Atlas launch', outcome: 'objective_met', summary: 'Scope agreed. Supplier date still needs confirmation.', created_at: '2026-10-09T15:00:00Z' }], recent_calls_total: 1,
  memories: [{ id: 'proof-relation-memory', content: 'Morgan prefers a short written recap before project reviews.' }], memories_total: 1,
  peer_messages: [{ id: 'proof-peer-message', direction: 'received', content: 'I will bring the updated checklist to Monday’s review.', occurred_at: '2026-10-09T16:00:00Z' }], peer_messages_total: 1,
  peer_link: { connected_since: '2026-09-01T10:00:00Z', shared_by_me: [{ domain: 'calendar', level: 'availability' }], shared_with_me: [{ domain: 'task', level: 'titles' }] },
  is_favorite: true, is_peer: true, merged_from: [],
};

const contextSection = { status: 'ok' as const, from_cache: true, generated_at: PROOF_TIME, contact: null, emails: [], events: [] };
export const PROOF_RELATION_CONTEXT = {
  contact: { ...contextSection, contact: { display_name: 'Morgan Demo', nickname: null, organization: 'Demo Studio', occupation: 'Project coordinator', birthday: null, biography: null, emails: [{ value: 'morgan@example.test', label: 'work' }], phones: [], addresses: [], relations: [], links: [], important_dates: [], messaging: [] } },
  emails: { ...contextSection, emails: [
    { id: 'proof-email-date', direction: 'received', subject: 'Atlas · Supplier proposes 22 October', occurred_at: '2026-10-09T13:30:00Z', excerpt: 'Can we clarify the difference with the project brief before Monday?' },
    { id: 'proof-email-review', direction: 'sent', subject: 'Monday’s review · agenda and next steps', occurred_at: '2026-10-09T14:00:00Z', excerpt: 'Let’s keep the delivery date open until the supplier confirms.' },
  ] },
  events: { ...contextSection, events: [{ id: 'proof-shared-event', summary: 'Atlas launch review', starts_at: '2026-10-12T08:00:00Z', ends_at: '2026-10-12T08:30:00Z', is_past: false, role: 'attendee', organizer_known: true }] },
  addresses_used: 1, window_days: 90, email_window_days: 365,
};

export const PROOF_RELATION_DEBRIEF = {
  status: 'ready', person: 'Morgan Demo', body: { headline: 'Monday’s review has one unresolved point: the supplier date.', where_we_stand: 'The scope is agreed. Morgan is preparing the checklist; you still owe a date confirmation.', open_points: [], suggested_next_step: 'Clarify the date, then send Morgan a short recap before the review.', notable_facts: [] }, generated_at: PROOF_TIME, generated_for: '2026-10-10', sections_used: ['contact', 'open_commitments', 'emails', 'events'], unavailable: [], can_rebuild: true, usage: null,
};

export const PROOF_MEETING: MeetingDetail = {
  id: MEETING_ID, status: 'ready', stage: null, started_at: '2026-10-09T14:00:00Z', stopped_at: '2026-10-09T14:25:00Z', last_segment_at: '2026-10-09T14:25:00Z', client_timezone: 'Europe/Paris', audio_format: 'webm_opus', segment_count: 25, audio_duration_seconds: 1500, audio_gaps: 0, audio_kept_until: null, audio_purged_at: null, location_lat: null, location_lon: null, location_label: 'Demo Studio · video call', calendar_event_id: 'proof-calendar-review', stt_provider: 'local', stt_model: 'demonstration-engine', stt_detected_language: 'en', stt_diarized: true, stt_cost_eur: 0, synthesis_model: 'demonstration-model', synthesis_tokens_in: 5200, synthesis_tokens_out: 860, synthesis_tokens_cache: 0, synthesis_cost_eur: 0.012, template_selection_usage: [], total_cost_eur: 0.012, has_transcript: true,
  report: { title: 'Atlas launch review · decisions and next steps', participants: [{ label: 'Speaker 1', name: 'Alex Demo', role: 'Project lead' }, { label: 'Speaker 2', name: 'Morgan Demo', role: 'Coordinator' }], sections: [
    { key: 'summary', label: 'Summary', kind: 'paragraph', paragraph: 'The launch scope is agreed. The supplier’s proposed delivery date differs from the brief and remains open until written confirmation.', bullets: [], topics: [], action_items: [], transcript: [] },
    { key: 'decisions', label: 'Decisions', kind: 'bullets', paragraph: null, bullets: ['Keep the agreed scope and the existing launch checklist.', 'Do not circulate a delivery commitment until the supplier confirms.'], topics: [], action_items: [], transcript: [] },
    { key: 'actions', label: 'Actions · owner and due date', kind: 'action_items', paragraph: null, bullets: [], topics: [], action_items: [{ description: 'Ask the supplier to confirm the delivery date', owner: 'Alex Demo', due_date: '2026-10-12' }, { description: 'Share the revised launch checklist before the review', owner: 'Morgan Demo', due_date: '2026-10-12' }], transcript: [] },
  ] }, report_is_edited: false, report_edited_at: null, template_snapshot: null, index_state: 'indexed', indexed_at: PROOF_TIME, email_sent_at: null, last_error_code: null, last_error_message: null, attempts: 1, max_attempts: 3, worker_stale: false, template_ref: 'builtin:meeting', template_name: 'Meeting minutes', template_selection: 'user', template_selection_reason: null, source_meeting_id: null, derived_count: 0, transcript: null,
};

export const PROOF_RADIO: RadioSessionState = {
  session_id: RADIO_ID, status: 'on_air', segments: [
    { seq: 1, format: 'opening', mood: 'calm', title: 'Your morning, with the sources beside you', duration_s: 120, transcript: [
      { role: 'host', text: 'Good morning, Alex. This is a demonstration programme: your day, your commitments and the news you follow, in one place.', offset_s: 0, sources: [] },
      { role: 'host', text: 'Your Atlas review is on Monday at 10:00. One delivery date remains open; keep that question at the top of the agenda.', offset_s: 20, sources: [{ label: 'Your calendar · Atlas review', url: null, published_at: null, article_id: null }, { label: 'Your commitments · delivery confirmation', url: null, published_at: null, article_id: null }] },
      { role: 'anchor', text: 'From the outlets you follow: a demonstration story about repairing everyday devices. Its source is available below; no real-world news claim is made here.', offset_s: 45, sources: [{ label: 'Demo Daily · Repairing everyday devices', url: 'https://example.test/news/repair', published_at: '2026-10-10T06:00:00Z', article_id: 'proof-radio-article' }] },
    ] },
    { seq: 2, format: 'journal', mood: 'calm', title: 'The people and follow-ups worth remembering', duration_s: 120, transcript: [{ role: 'host', text: 'Next, a short personal journal about this week’s project follow-ups.', offset_s: 0, sources: [] }] },
  ], cost_eur: 0.032, stop_at: '2026-10-10T08:00:00Z', startup_estimate_s: 0, end_reason: null, mood: 'calm', station_name: 'Alex’s demo radio', cost_estimate_eur: 0.24, cost_estimate_s: 1800, segment_gap_s: 0, flash: null,
};

export const PROOF_RADIO_ARTICLE: RadioArticle = { id: 'proof-radio-article', outlet: 'Demo Daily', url: 'https://example.test/news/repair', published_at: '2026-10-10T06:00:00Z', title: 'Repairing everyday devices · demonstration article', text: 'This fictional article illustrates how the real radio page presents a cited story alongside the programme. Its contents are demonstration data, not current news.', complete: true, cut: false, translated: false, source_language: 'en', translation_failed: false, budget_reached: false, cost_eur: 0 };

export interface LandingProofRoute {
  url: string | { regex: string };
  json: unknown;
  status?: number;
}

export function landingProofRoutes(): LandingProofRoute[] {
  const routes = publicScreenshotRoutes().flatMap(route => route.json === undefined ? [] : [{ url: route.url === '**/api/v1/psyche/state' ? '**/api/v1/psyche/state*' : typeof route.url === 'string' ? route.url : { regex: route.url.source }, json: route.json, status: route.status }]);
  return [...routes,
    { url: '**/api/v1/config', json: { ...appConfig, features: { ...appConfig.features, tool_approval_enabled: true, rag_spaces_drive_sync_enabled: true, rag_spaces_mail_sync_enabled: true, meetings_enabled: true, radio_enabled: true }, capabilities: { radio: { enabled: true, family: 'media' } } } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/rag-spaces*', json: { spaces: [PROOF_SPACE], total: 1 } },
    { url: `**/api/v1/rag-spaces/${SPACE_ID}`, json: PROOF_SPACE },
    { url: `**/api/v1/rag-spaces/${SPACE_ID}/drive-browse*`, json: { files: [{ id: 'proof-folder', name: 'Atlas · Project documents', mimeType: 'application/vnd.google-apps.folder', modifiedTime: PROOF_TIME }], nextPageToken: null } },
    { url: '**/api/v1/usage-limits/admin/instance-daily-budget', json: { ceiling_eur: '20.00', deployment_ceiling_eur: '25.00', effective_ceiling_eur: '20.00', spent_today_eur: '5.64', runs_today: 84, is_default: false } },
    { url: '**/api/v1/usage-limits/admin/users*', json: { users: proofUsers(), total: 3, page: 1, page_size: 20, total_pages: 1 } },
    { url: '**/api/v1/relations', json: PROOF_RELATIONS },
    { url: '**/api/v1/relations/*', json: PROOF_RELATION },
    { url: '**/api/v1/relations/overview-scope', json: { sections: ['contact', 'open_loops', 'calls', 'memories', 'peer_messages', 'emails', 'events'], directions: ['received', 'sent'], roles: ['attendee', 'organizer'], max_items: 5 } },
    { url: '**/api/v1/relations/*/context', json: PROOF_RELATION_CONTEXT },
    { url: '**/api/v1/relations/*/debrief', json: PROOF_RELATION_DEBRIEF },
    { url: `**/api/v1/meetings/${MEETING_ID}*`, json: PROOF_MEETING },
    { url: '**/api/v1/meetings/active', json: null, status: 204 },
    { url: '**/api/v1/radio/sessions', json: PROOF_RADIO },
    { url: `**/api/v1/radio/sessions/${RADIO_ID}/playhead`, json: PROOF_RADIO },
    { url: `**/api/v1/radio/articles/${PROOF_RADIO_ARTICLE.id}`, json: PROOF_RADIO_ARTICLE },
  ];
}
