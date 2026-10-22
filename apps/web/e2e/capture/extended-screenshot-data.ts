/** Additional public scenes: fictional Atlas data, checked against the actual UI contracts. */
import type { Memory, MemoryListResponse } from '../../src/hooks/useMemories';
import type {
  JournalEntry,
  JournalListResponse,
  JournalPortrait,
  JournalSettings,
} from '../../src/hooks/useJournals';
import type {
  ScheduledAction,
  ScheduledActionListResponse,
  ScheduledActionWeekResponse,
} from '../../src/hooks/useScheduledActions';
import type { Skill, SkillListResponse } from '../../src/hooks/useSkills';
import type { UserStatistics } from '../../src/hooks/useUserStatistics';
import type { PsycheHistoryEntry, PsycheState } from '../../src/types/psyche';
import type { BoardPage, TicketDetail, TicketRow } from '../../src/types/workboard';
import type {
  MeetingDetail,
  MeetingListResponse,
  MeetingSummary,
  MeetingTemplateListResponse,
} from '../../src/types/meetings';
import type { RAGSpaceListResponse } from '../../src/types/rag-spaces';
import type {
  LLMTypeConfig,
  ModelCapabilities,
  ProviderModelsMetadata,
} from '../../src/types/llm-config';
import { psycheEfficacyProfile } from '../fixtures/psyche-efficacy';
import { appConfig } from '../fixtures/dashboard-shell';
import {
  landingProofRoutes,
  MEETING_ID,
  PROOF_MEETING,
  PROOF_SPACE,
  PROOF_TIME,
  type LandingProofRoute,
} from './landing-proof-data';

export const EXTENDED_NAMES = [
  'psyche',
  'psyche-evolution',
  'memory-library',
  'portrait',
  'routine-studio',
  'routine-week',
  'workboard',
  'workboard-dossier',
  'knowledge-library',
  'meeting-transcript',
  'meeting-templates',
  'connections',
  'skills-library',
  'model-routing',
  'consumption',
  'journal',
  'avatar-picker',
  'meetings-list',
] as const;
export type ExtendedName = (typeof EXTENDED_NAMES)[number];
const OWNER = '00000000-0000-4000-8000-000000000001';
export const TICKET_ID = '00000000-0000-4000-8000-000000000e01';

export const EXTENDED_PSYCHE: PsycheState = {
  id: '00000000-0000-4000-8000-000000000e02',
  user_id: OWNER,
  trait_openness: 0.73,
  trait_conscientiousness: 0.66,
  trait_extraversion: 0.48,
  trait_agreeableness: 0.81,
  trait_neuroticism: 0.24,
  mood_pleasure: 0.46,
  mood_arousal: 0.19,
  mood_dominance: 0.32,
  mood_label: 'serene',
  mood_color: '#38bdf8',
  active_emotions: [
    { name: 'curiosity', intensity: 0.64, triggered_at: PROOF_TIME },
    { name: 'joy', intensity: 0.41, triggered_at: PROOF_TIME },
    { name: 'serenity', intensity: 0.3, triggered_at: PROOF_TIME },
  ],
  relationship_stage: 'AFFECTIVE',
  relationship_depth: 0.56,
  relationship_warmth_active: 0.72,
  relationship_trust: 0.81,
  relationship_interaction_count: 127,
  drive_curiosity: 0.69,
  drive_engagement: 0.74,
  self_efficacy: {},
  efficacy_profile: {
    ...psycheEfficacyProfile(),
    domains: psycheEfficacyProfile().domains.map((domain, index) => {
      const success = [8, 12, 4, 6, 9, 5, 10][index];
      const failure = [1, 2, 0, 1, 2, 1, 1][index];
      const helpful = [5, 7, 3, 4, 6, 4, 8][index];
      const unhelpful = [1, 2, 1, 1, 1, 1, 2][index];
      return {
        ...domain,
        status: 'observed',
        results: { success, failure, partial: 1 + (index % 2), unknown: 1 + (index % 3) },
        feedback: { helpful, unhelpful },
        result_count: success + failure,
        feedback_count: helpful + unhelpful,
        result_score: (success + 1) / (success + failure + 2),
        feedback_score: (helpful + 1) / (helpful + unhelpful + 2),
        last_observed_at: PROOF_TIME,
      };
    }),
  },
  created_at: '2026-08-01T08:00:00Z',
  updated_at: PROOF_TIME,
};
export const EXTENDED_HISTORY: PsycheHistoryEntry[] = Array.from({ length: 24 }, (_, index) => ({
  id: `psyche-history-${index}`,
  snapshot_type: 'post_response',
  mood_pleasure: 0.46 - index * 0.012 + Math.sin(index) * 0.08,
  mood_arousal: 0.19 + Math.sin(index * 0.6) * 0.19,
  mood_dominance: 0.32 - index * 0.005,
  dominant_emotion: index % 2 ? 'joy' : 'curiosity',
  relationship_stage: 'AFFECTIVE',
  trait_snapshot: {
    active_emotions: {
      curiosity: 0.64 - index * 0.008,
      joy: 0.41 + Math.sin(index) * 0.1,
      serenity: 0.3 + index * 0.005,
    },
    emotion_intensity: 0.64 - index * 0.008,
    relationship_depth: 0.56 - index * 0.004,
    relationship_warmth: 0.72 - index * 0.006,
    relationship_trust: 0.81 - index * 0.005,
    drive_curiosity: 0.69 - index * 0.004,
    drive_engagement: 0.74 - index * 0.006,
  },
  created_at: new Date(Date.parse(PROOF_TIME) - index * 6 * 3600000).toISOString(),
}));

const memoryExamples: Pick<Memory, 'category' | 'content' | 'trigger_topic'>[] = [
  {
    category: 'procedural',
    content: 'Ask for my approval before sending messages or sharing project documents.',
    trigger_topic: 'Approval and privacy',
  },
  {
    category: 'procedural',
    content: 'When sources disagree, show both dates and ask which commitment is confirmed.',
    trigger_topic: 'Source checking',
  },
  {
    category: 'preference',
    content: 'I prefer concise answers with sources and a practical next step.',
    trigger_topic: 'Communication',
  },
  {
    category: 'preference',
    content: 'Keep a short walk between long meetings when my calendar allows it.',
    trigger_topic: 'Daily rhythm',
  },
  {
    category: 'relationship',
    content: 'Morgan coordinates the Atlas checklist and prefers a short written recap.',
    trigger_topic: 'Morgan Demo',
  },
  {
    category: 'event',
    content: 'The Atlas launch review is on Monday 12 October at 10:00.',
    trigger_topic: 'Project Atlas',
  },
  {
    category: 'personal',
    content: 'I enjoy photography, exhibitions and repairing everyday objects.',
    trigger_topic: 'Hobbies',
  },
  {
    category: 'pattern',
    content: 'I prepare the important decisions before the meeting rather than during it.',
    trigger_topic: 'Meeting preparation',
  },
];
export const EXTENDED_MEMORIES: MemoryListResponse = {
  items: memoryExamples.map((memory, index) => ({
    ...memory,
    id: `atlas-memory-${index}`,
    emotional_weight: 3,
    usage_nuance: 'Fictional example — editable by its owner',
    importance: index < 2 ? 1 : 0.8,
    pinned: index < 2,
    usage_count: 8 + index * 3,
    created_at: '2026-10-09T15:00:00Z',
    updated_at: PROOF_TIME,
    purge_risk: index < 2 ? 'protected' : 'safe',
    retention_score: 0.9,
  })),
  total: memoryExamples.length,
  by_category: { procedural: 2, preference: 2, relationship: 1, event: 1, personal: 1, pattern: 1 },
};

const entries: JournalEntry[] = [
  {
    theme: 'user_observations',
    title: 'Make uncertainty useful',
    content:
      'When two sources disagree, Alex wants the discrepancy stated before a recommendation. For Atlas, keep 19 and 22 October visible until the supplier confirms.',
    level: 'L3',
    mood: 'reflective',
  },
  {
    theme: 'user_observations',
    title: 'A practical working rhythm',
    content:
      'Alex prepares decisions in advance and prefers concise written recaps. Leave room for a short break between demanding meetings.',
    level: 'L2',
    mood: 'curious',
  },
  {
    theme: 'learnings',
    title: 'Separate a draft from an action',
    content:
      'A useful draft is ready for review. It is not a sent message. Keep approval explicit and report the result only after execution.',
    level: 'L1',
    mood: 'satisfied',
  },
  {
    theme: 'ideas_analyses',
    title: 'One context for the launch review',
    content:
      'The project brief, supplier email and meeting decisions belong in one knowledge space so the next review starts from the same evidence.',
    level: 'L1',
    mood: 'inspired',
  },
  {
    theme: 'self_reflection',
    title: 'Ask one precise question',
    content:
      'The delivery date is the unresolved point. A focused clarification is more useful than another long summary.',
    level: 'L0',
    mood: 'reflective',
  },
].map((entry, index) => ({
  ...entry,
  theme: entry.theme as JournalEntry['theme'],
  level: entry.level as JournalEntry['level'],
  mood: entry.mood as JournalEntry['mood'],
  id: `atlas-journal-${index}`,
  status: 'active',
  source: 'conversation',
  personality_code: null,
  char_count: entry.content.length,
  search_hints: ['Atlas', 'review', 'sources'],
  injection_count: 4 + index,
  last_injected_at: PROOF_TIME,
  confidence: 'medium',
  evidence_count: 3 + index,
  contradiction_count: 0,
  revision: 1,
  created_at: '2026-10-09T15:00:00Z',
  updated_at: PROOF_TIME,
}));
const journalChars = entries.reduce((sum, entry) => sum + entry.char_count, 0);
export const EXTENDED_JOURNAL: JournalListResponse = {
  entries,
  total: entries.length,
  by_theme: ['self_reflection', 'user_observations', 'ideas_analyses', 'learnings'].map(theme => ({
    theme: theme as JournalEntry['theme'],
    count: entries.filter(entry => entry.theme === theme).length,
  })),
  total_chars: journalChars,
  max_total_chars: 40000,
  usage_pct: journalChars / 400,
};
export const EXTENDED_JOURNAL_SETTINGS: JournalSettings = {
  journals_enabled: true,
  journal_consolidation_enabled: true,
  journal_consolidation_with_history: true,
  journal_max_total_chars: 40000,
  journal_context_max_chars: 2400,
  journal_max_entry_chars: 1500,
  journal_context_max_results: 5,
  size_info: { total_chars: journalChars, max_total_chars: 40000, usage_pct: journalChars / 400 },
  last_cost: {
    tokens_in: 4200,
    tokens_cache: 1600,
    tokens_out: 680,
    cost_eur: 0.0042,
    timestamp: PROOF_TIME,
    source: 'consolidation',
  },
};
export const EXTENDED_PORTRAIT: JournalPortrait = {
  full: 'Alex prepares decisions before meetings and values a clear link between a claim and its source. In the Atlas project, the launch scope is agreed while the supplier’s delivery date remains open.\n\nA concise recap, visible uncertainty and one practical next step fit this working rhythm. Morgan coordinates the checklist; Alex owns the delivery clarification.\n\nStanding instructions remain explicit: ask before sending or sharing, and preserve the distinction between a proposal and a completed action.',
  brief:
    'Prepare the decision, cite the sources, keep uncertainty visible and ask before acting. Atlas: clarify the supplier date before Monday’s review.',
  compiled_at: PROOF_TIME,
  stale: false,
  sources: {
    version: 1,
    journal_entries: entries.length,
    sources: {
      memories: { status: 'used', used: 8, total: 8 },
      open_loops: { status: 'used', used: 2, total: 2 },
      workboard: { status: 'used', used: 8, total: 8 },
      routines: { status: 'used', used: 3, total: 3 },
      relation_debriefs: { status: 'used', used: 1, total: 1 },
    },
    omitted_claims: 0,
    withdrawn_claims: 0,
    portrait_pending: false,
  },
};

function routine(index: number, title: string, hour: number): ScheduledAction {
  const weekdays = [1, 2, 3, 4, 5];
  const slots = weekdays.map(day => ({
    day,
    date: `2026-10-${11 + day}`,
    slot_at: `2026-10-${11 + day}T${String(hour - 2).padStart(2, '0')}:00:00Z`,
    hour,
    minute: 0,
  }));
  return {
    id: `00000000-0000-4000-8000-000000000f0${index}`,
    user_id: OWNER,
    title,
    action_prompt:
      index === 1
        ? 'Prepare my day from the calendar, open commitments and the Atlas project space. Cite the sources.'
        : 'Summarise the Atlas follow-ups and prepare any supplier message as a draft for my approval.',
    recurrence: {
      freq: 'weekly',
      times: { mode: 'at', at: [{ hour, minute: 0 }] },
      anchor_date: '2026-10-12',
      interval: 1,
      byweekday: weekdays,
      bymonthday: [],
      nth_weekday: null,
      bymonth: [],
      end: { kind: 'never' },
    },
    user_timezone: 'Europe/Paris',
    trigger_kind: 'time',
    condition_config: null,
    requires_approval: index === 2,
    execution_mode: 'react',
    next_trigger_at:
      slots.find(slot => Date.parse(slot.slot_at) > Date.parse(PROOF_TIME))?.slot_at ?? null,
    is_enabled: true,
    status: 'active',
    last_executed_at: index === 1 ? '2026-10-12T07:00:00Z' : null,
    execution_count: index === 1 ? 12 : 4,
    consecutive_failures: 0,
    last_error: null,
    schedule_display: `Every weekday at ${hour}:00`,
    next_occurrences: slots
      .map(slot => slot.slot_at)
      .filter(at => Date.parse(at) > Date.parse(PROOF_TIME)),
    times_of_day: [`${String(hour).padStart(2, '0')}:00`],
    runs_per_day: 1,
    week_slots: slots,
    created_at: '2026-10-01T08:00:00Z',
    updated_at: PROOF_TIME,
  };
}
export const ROUTINES = [
  routine(1, 'Morning sources and priorities', 9),
  routine(2, 'Atlas follow-up · propose before sending', 16),
  {
    ...routine(3, 'Watch supplier delivery updates', 11),
    recurrence: null,
    trigger_kind: 'condition' as const,
    condition_config: { type: 'mail_match' as const, query: 'Atlas delivery', until: '2026-10-23' },
    requires_approval: true,
    schedule_display: 'When a new email matches “Atlas delivery”',
    next_trigger_at: '2026-10-12T07:40:00Z',
    next_occurrences: [],
    week_slots: [],
    check_interval_minutes: 10,
    last_checked_at: PROOF_TIME,
    last_check_error: null,
  },
];
export const EXTENDED_ROUTINES: ScheduledActionListResponse = {
  scheduled_actions: ROUTINES,
  total: ROUTINES.length,
  condition_check_minutes: {
    calendar_event: 10,
    document_added: 10,
    mail_match: 10,
    task_overdue: 10,
    weather_change: 60,
  },
  condition_max_fires_per_day: 12,
  weather_condition_rule: {
    horizon_hours: 4,
    min_precipitation_percent: 60,
    source: 'google_weather',
  },
};
export const EXTENDED_WEEK: ScheduledActionWeekResponse = {
  actions: ROUTINES.map((action, index) => ({
    id: action.id,
    timezone: action.user_timezone,
    week_start: '2026-10-12',
    today: 1,
    cells: (action.week_slots ?? []).map(slot => ({
      ...slot,
      outcome: index === 0 && slot.day === 1 ? 'success' : null,
      run_at: index === 0 && slot.day === 1 ? '2026-10-12T07:00:00Z' : null,
      error: null,
      manual: false,
    })),
  })),
  generated_at: PROOF_TIME,
};

const ticketNames = [
  'Confirm Atlas delivery date',
  'Prepare Monday’s launch review',
  'Compare supplier options',
  'Collect the revised checklist',
  'Review the message before sending',
  'Validate the source-backed recap',
  'Archive Friday’s review decisions',
  'Check the delivery decision with Morgan',
];
export const TICKETS: TicketRow[] = [
  'todo',
  'in_progress',
  'idea',
  'waiting',
  'todo',
  'validating',
  'done',
  'waiting',
].map((status, index) => ({
  id: index === 0 ? TICKET_ID : `00000000-0000-4000-8000-000000000e1${index}`,
  owner_user_id: OWNER,
  parent_id: null,
  title: ticketNames[index],
  description:
    index === 0
      ? 'The brief targets 19 October. The supplier proposes 22 October. Compare the sources, ask for a confirmed date, and prepare a short written recap for approval.'
      : 'A fictional Atlas project task, with a clear owner and a visible next step.',
  status,
  priority: index === 0 ? 'urgent' : index < 3 ? 'high' : 'medium',
  start_at: '2026-10-09T08:00:00Z',
  due_at: index < 2 ? '2026-10-12T08:00:00Z' : '2026-10-13T14:00:00Z',
  assignee_kind: index % 2 ? 'lia' : 'human',
  assignee_user_id: null,
  effective_assignee_id: OWNER,
  position: 0,
  follow_owner: true,
  follow_assignee: true,
  created_by: 'user',
  execution_mode: 'react',
  status_changed_at: PROOF_TIME,
  run_count: index === 0 ? 2 : 1,
  run_claimed_at: status === 'in_progress' ? PROOF_TIME : null,
  last_run_at: '2026-10-09T15:00:00Z',
  last_run_outcome: status === 'confirming' ? 'confirming' : 'success',
  last_run_error: null,
  last_run_tokens_in: 5200,
  last_run_tokens_out: 820,
  last_run_tokens_cache: 1200,
  last_run_google_requests: 0,
  last_run_cost_eur: 0.0084,
  total_tokens_in: 10400,
  total_tokens_out: 1640,
  total_tokens_cache: 3200,
  total_google_requests: 2,
  total_cost_eur: 0.0168,
  created_at: '2026-10-09T08:00:00Z',
  updated_at: PROOF_TIME,
}));
const boardCounts = TICKETS.reduce<Record<string, number>>(
  (counts, ticket) => ({ ...counts, [ticket.status]: (counts[ticket.status] ?? 0) + 1 }),
  { idea: 0, todo: 0, in_progress: 0, waiting: 0, confirming: 0, validating: 0, done: 0 }
);
export const EXTENDED_BOARD: BoardPage = {
  tickets: TICKETS,
  total: TICKETS.length,
  counts_by_status: boardCounts,
};
export const EXTENDED_TICKET: TicketDetail = {
  ticket: TICKETS[0],
  children: [
    'Compare the brief with the supplier email',
    'Check Friday’s agreed scope',
    'Draft the delivery clarification for approval',
  ].map((title, index) => ({
    ...TICKETS[0],
    id: `atlas-step-${index}`,
    parent_id: TICKET_ID,
    title,
    status: index < 2 ? 'done' : 'todo',
    priority: 'medium',
    position: index,
  })),
  comments: [
    {
      id: 'atlas-comment-1',
      author_kind: 'user',
      author_user_id: OWNER,
      body: 'Keep both proposed dates visible. Prepare a clarification for the supplier and ask me before sending.',
      run_id: null,
      created_at: '2026-10-09T14:55:00Z',
    },
    {
      id: 'atlas-comment-2',
      author_kind: 'lia',
      author_user_id: null,
      body: 'Sources checked: Launch plan.pdf targets 19 October; the supplier email proposes 22 October. The scope agrees with Friday’s minutes.\n\nNext step: ask for a date the supplier can commit to. A draft is ready for your review; nothing has been sent.',
      run_id: 'atlas-run-1',
      created_at: '2026-10-09T15:00:00Z',
    },
  ],
  events: [
    {
      id: 'atlas-event-1',
      actor_kind: 'user',
      actor_user_id: OWNER,
      kind: 'created',
      payload: { status: 'todo' },
      created_at: '2026-10-09T08:00:00Z',
    },
    {
      id: 'atlas-event-2',
      actor_kind: 'lia',
      actor_user_id: null,
      kind: 'assigned',
      payload: { to_kind: 'human', reason: 'handed_back' },
      created_at: '2026-10-09T15:00:00Z',
    },
  ],
};

export const EXTENDED_SPACES: RAGSpaceListResponse = {
  spaces: [
    PROOF_SPACE,
    {
      ...PROOF_SPACE,
      id: '00000000-0000-4000-8000-000000000e31',
      name: 'Research and repair',
      description: 'Product manuals, repair notes and source-backed comparisons.',
      is_active: true,
      document_count: 7,
      ready_document_count: 7,
      total_size: 1840000,
    },
    {
      ...PROOF_SPACE,
      id: '00000000-0000-4000-8000-000000000e32',
      name: 'Photography notebook',
      description: 'Exhibition notes, camera guides and ideas for the next weekend.',
      is_active: false,
      document_count: 5,
      ready_document_count: 5,
      total_size: 920000,
    },
    {
      ...PROOF_SPACE,
      id: '00000000-0000-4000-8000-000000000e33',
      name: 'Team meeting archive',
      description: 'Agreed scope, decisions and action items from recent reviews.',
      is_active: true,
      document_count: 9,
      ready_document_count: 9,
      total_size: 1140000,
    },
    {
      ...PROOF_SPACE,
      id: '00000000-0000-4000-8000-000000000e34',
      name: 'Writing and communication',
      description: 'Approved message examples, tone preferences and reference notes.',
      is_active: false,
      document_count: 6,
      ready_document_count: 6,
      total_size: 420000,
    },
    {
      ...PROOF_SPACE,
      id: '00000000-0000-4000-8000-000000000e35',
      name: 'Workshop and manuals',
      description: 'Repair checklists, measurements and product documentation.',
      is_active: false,
      document_count: 8,
      ready_document_count: 8,
      total_size: 2380000,
    },
  ],
  total: 6,
};
export const EXTENDED_MEETING: MeetingDetail = {
  ...PROOF_MEETING,
  transcript: [
    {
      speaker: 'Alex Demo',
      start: 0,
      end: 18,
      text: 'The launch scope is agreed. Before Monday’s review, I want to clarify the supplier’s delivery commitment.',
    },
    {
      speaker: 'Morgan Demo',
      start: 18,
      end: 42,
      text: 'The brief says 19 October, but the latest email proposes 22 October. I will bring the revised checklist.',
    },
    {
      speaker: 'Alex Demo',
      start: 42,
      end: 65,
      text: 'Let’s keep both dates in the recap until we have written confirmation. I will prepare a message for approval.',
    },
    {
      speaker: 'Morgan Demo',
      start: 65,
      end: 91,
      text: 'Agreed. No change to the scope. The date stays open, and the checklist is due before the review.',
    },
  ],
};
export const EXTENDED_TEMPLATES: MeetingTemplateListResponse = {
  items: [
    {
      ref: 'user:00000000-0000-4000-8000-000000000e41',
      name: 'Atlas decision review',
      description: 'Decisions, unresolved evidence, owners and next steps.',
      category: 'custom',
      builtin: false,
      sections_count: 4,
      auto_selectable: true,
    },
    {
      ref: 'builtin:meeting',
      name: 'Meeting minutes',
      description: 'Summary, topics, decisions and action items.',
      category: 'meeting',
      builtin: true,
      sections_count: 4,
      auto_selectable: true,
    },
    {
      ref: 'builtin:transcript_clean',
      name: 'Clean transcript',
      description: 'A readable transcript with speakers and timestamps.',
      category: 'transcript',
      builtin: true,
      sections_count: 1,
      auto_selectable: false,
    },
    {
      ref: 'builtin:intent_analysis',
      name: 'Intent analysis',
      description: 'Primary intent, observable evidence and a response strategy.',
      category: 'analysis',
      builtin: true,
      sections_count: 3,
      auto_selectable: true,
    },
  ],
  max_user_templates: 20,
};

const systemSkills: Skill[] = [
  [
    'preparation-reunion',
    'Prepare a meeting from your calendar, documents and the questions still open.',
    'Productivity',
    false,
    true,
  ],
  [
    'synthese-recherche',
    'Cross-check a subject and produce a structured synthesis with sources.',
    'Research',
    false,
    true,
  ],
  [
    'redaction-professionnelle',
    'Draft a clear message, adapt the tone and review before sharing.',
    'Writing',
    false,
    true,
  ],
  [
    'unit-converter',
    'Convert measurements in an interactive application inside the conversation.',
    'Interactive',
    true,
    false,
  ],
  [
    'pomodoro-timer',
    'A working timer with focused sessions and pauses.',
    'Interactive',
    true,
    false,
  ],
  [
    'calendar-month',
    'Explore a month in a compact interactive calendar.',
    'Interactive',
    true,
    false,
  ],
].map(
  ([name, description, category, hasScripts, dialogue]) =>
    ({
      name: String(name),
      description: String(description),
      descriptions: null,
      scope: 'admin' as const,
      category: String(category),
      priority: 10,
      always_loaded: false,
      has_scripts: Boolean(hasScripts),
      has_plan_template: false,
      enabled_for_user: true,
      admin_enabled: true,
      dialogue: Boolean(dialogue),
      outputs: hasScripts ? ['app'] : ['text'],
      provenance: 'system' as const,
    }) satisfies Skill
);
export const EXTENDED_SKILLS: SkillListResponse = {
  skills: [
    ...systemSkills,
    ...[
      [
        'atlas-review',
        'Prepare our Atlas review with the brief, supplier date and a decision checklist.',
      ],
      [
        'repair-notebook',
        'Turn workshop notes into a clear repair checklist with measurements and safety reminders.',
      ],
    ].map(
      ([name, description]) =>
        ({
          name,
          description,
          descriptions: null,
          scope: 'user' as const,
          category: 'Personal workflow',
          priority: 10,
          always_loaded: false,
          has_scripts: false,
          has_plan_template: false,
          enabled_for_user: true,
          admin_enabled: true,
          dialogue: true,
          outputs: ['text'],
          provenance: 'authored' as const,
        }) satisfies Skill
    ),
  ],
  total: 8,
};

function slot(
  llm_type: string,
  display_name: string,
  category: string,
  provider: string,
  model: string,
  reasoning = false
): LLMTypeConfig {
  const effective = {
    provider,
    model,
    provider_config: '{}',
    temperature: 0.3,
    top_p: 1,
    frequency_penalty: 0,
    presence_penalty: 0,
    max_tokens: reasoning ? 8192 : 4096,
    timeout_seconds: 60,
    reasoning_effort: reasoning
      ? { level: 'medium' as const, budget_tokens: null, exclude_from_output: false }
      : null,
    context_window: 128000,
  };
  return {
    llm_type,
    info: {
      llm_type,
      display_name,
      category,
      description_key: `settings.admin.llmConfig.types.${llm_type}`,
      required_capabilities: ['supports_tools'],
      power_tier: reasoning ? 'high' : 'medium',
      required_kind: 'chat',
    },
    effective,
    defaults: effective,
    overrides: {},
    is_overridden: false,
  };
}
const modelSlots = [
  slot('query_analyzer', 'Query Analyzer', 'pipeline', 'openai', 'gpt-4.1-mini'),
  slot('planner', 'Planner', 'pipeline', 'anthropic', 'claude-sonnet-4-6', true),
  slot('react_agent', 'ReAct Agent', 'pipeline', 'anthropic', 'claude-sonnet-4-6', true),
  slot('contacts_agent', 'Contacts Agent', 'domain_agents', 'openai', 'gpt-4.1-mini'),
  slot('calendar_agent', 'Calendar Agent', 'domain_agents', 'openai', 'gpt-4.1-mini'),
  slot('response', 'Response', 'query_response', 'openai', 'gpt-4.1'),
];
function model(model_id: string, reasoning: boolean): ModelCapabilities {
  return {
    model_id,
    kind: 'chat',
    max_output_tokens: reasoning ? 64000 : 32768,
    vouched_max_output_tokens: reasoning ? 64000 : 32768,
    supports_tools: true,
    supports_structured_output: true,
    supports_vision: true,
    is_reasoning_model: reasoning,
    reasoning_family: reasoning ? 'anthropic_adaptive' : 'none',
    reasoning_levels: reasoning ? ['low', 'medium', 'high'] : [],
    reasoning_can_disable: reasoning,
    reasoning_supports_budget: false,
    reasoning_supports_exclude: false,
    reasoning_budget_range: null,
    reasoning_doc_i18n_key: null,
    supports_temperature: !reasoning,
    supports_top_p: !reasoning,
    supports_frequency_penalty: !reasoning,
    supports_presence_penalty: !reasoning,
    cost_input: null,
    cost_output: null,
  };
}
const modelMetadata: ProviderModelsMetadata = {
  providers: {
    openai: [model('gpt-4.1-mini', false), model('gpt-4.1', false)],
    anthropic: [model('claude-sonnet-4-6', true)],
  },
};
export const EXTENDED_STATISTICS: UserStatistics = {
  total_since: '2026-09-01T00:00:00Z',
  total_messages: 420,
  total_prompt_tokens: 420000,
  total_completion_tokens: 80000,
  total_cached_tokens: 120000,
  total_cost_eur: 2.84,
  total_google_api_requests: 64,
  total_google_api_cost_eur: 0.06,
  cycle_messages: 48,
  cycle_prompt_tokens: 42000,
  cycle_completion_tokens: 8000,
  cycle_cached_tokens: 12000,
  cycle_cost_eur: 0.28,
  cycle_google_api_requests: 8,
  cycle_google_api_cost_eur: 0.008,
  current_cycle_start: '2026-10-01T00:00:00Z',
};

const meetingSummary = (overrides: Partial<MeetingSummary>): MeetingSummary => ({
  id: MEETING_ID,
  status: 'ready',
  stage: null,
  title: 'Atlas launch review · decisions and next steps',
  started_at: '2026-10-09T14:00:00Z',
  stopped_at: '2026-10-09T14:25:00Z',
  audio_duration_seconds: 1500,
  participants_count: 2,
  action_items_count: 2,
  index_state: 'indexed',
  stt_provider: 'local',
  total_cost_eur: 0.012,
  last_error_code: null,
  template_ref: 'builtin:meeting',
  template_name: 'Meeting minutes',
  template_selection: 'user',
  source_meeting_id: null,
  ...overrides,
});

export const EXTENDED_MEETING_LIST: MeetingListResponse = {
  items: [
    meetingSummary({
      id: '00000000-0000-4000-8000-000000000e31',
      title: 'Workshop debrief · measurements and repair options',
      status: 'processing',
      stage: 'synthesizing',
      started_at: '2026-10-12T07:00:00Z',
      stopped_at: '2026-10-12T07:18:00Z',
      audio_duration_seconds: 1080,
      participants_count: 0,
      action_items_count: 0,
      index_state: 'pending',
      total_cost_eur: null,
      template_selection: 'auto',
    }),
    meetingSummary({}),
    meetingSummary({
      id: '00000000-0000-4000-8000-000000000e32',
      title: 'Atlas checklist · owners and handover',
      started_at: '2026-10-09T08:00:00Z',
      stopped_at: '2026-10-09T08:35:00Z',
      audio_duration_seconds: 2100,
      participants_count: 3,
      action_items_count: 4,
      total_cost_eur: 0.0168,
    }),
  ],
  total: 3,
  limit: 20,
  offset: 0,
};

export function extendedScreenshotRoutes(): LandingProofRoute[] {
  return [
    ...landingProofRoutes(),
    {
      url: '**/api/v1/config',
      json: {
        ...appConfig,
        features: {
          ...appConfig.features,
          journals_enabled: true,
          skills_enabled: true,
          meetings_enabled: true,
          tool_approval_enabled: true,
          rag_spaces_drive_sync_enabled: true,
          rag_spaces_mail_sync_enabled: true,
        },
        capabilities: { skills: { enabled: true, family: 'knowledge' } },
      },
    },
    { url: { regex: '\\/api\\/v1\\/psyche\\/state(?:\\?.*)?$' }, json: EXTENDED_PSYCHE },
    { url: '**/api/v1/psyche/history*', json: EXTENDED_HISTORY },
    {
      url: '**/api/v1/psyche/settings',
      json: {
        psyche_enabled: true,
        psyche_display_avatar: true,
        psyche_sensitivity: 50,
        psyche_stability: 65,
      },
    },
    { url: '**/api/v1/memories', json: EXTENDED_MEMORIES },
    { url: '**/api/v1/journals', json: EXTENDED_JOURNAL },
    { url: '**/api/v1/journals/settings', json: EXTENDED_JOURNAL_SETTINGS },
    { url: '**/api/v1/journals/portrait', json: EXTENDED_PORTRAIT },
    {
      url: '**/api/v1/journals/themes',
      json: {
        themes: EXTENDED_JOURNAL.by_theme.map(theme => ({ code: theme.theme, label: theme.theme })),
      },
    },
    { url: '**/api/v1/scheduled-actions', json: EXTENDED_ROUTINES },
    { url: '**/api/v1/scheduled-actions/week*', json: EXTENDED_WEEK },
    { url: '**/api/v1/workboard/tickets*', json: EXTENDED_BOARD },
    { url: `**/api/v1/workboard/tickets/${TICKET_ID}`, json: EXTENDED_TICKET },
    { url: '**/api/v1/peers/connections', json: [] },
    { url: '**/api/v1/rag-spaces*', json: EXTENDED_SPACES },
    { url: `**/api/v1/meetings/${MEETING_ID}*`, json: EXTENDED_MEETING },
    { url: { regex: '\\/api\\/v1\\/meetings(?:\\?.*)?$' }, json: EXTENDED_MEETING_LIST },
    { url: '**/api/v1/meetings/templates', json: EXTENDED_TEMPLATES },
    {
      url: '**/api/v1/meetings/preferences',
      json: {
        stt_engine: 'auto',
        language: 'en',
        auto_email: false,
        keep_audio_hours: 0,
        default_template_ref: null,
        keep_audio_hours_max: 72,
      },
    },
    {
      url: { regex: '\\/api\\/v1\\/connectors(?:\\?fresh=true)?$' },
      json: {
        connectors: [
          'google_gmail',
          'google_calendar',
          'google_drive',
          'google_contacts',
          'google_tasks',
        ].map((connector_type, index) => ({
          id: `atlas-connector-${index}`,
          connector_type,
          status: 'active',
          created_at: '2026-09-01T08:00:00Z',
          oauth_grant_id: 'atlas-google-grant',
          metadata: { oauth_account_email: 'alex@example.test' },
          bulk_reconnect_provider: 'google',
        })),
      },
    },
    {
      url: '**/api/v1/connectors/*/preferences',
      json: {
        preferences: {
          default_calendar_name: 'Project Atlas',
          default_task_list_name: 'Atlas next steps',
        },
      },
    },
    {
      url: '**/api/v1/connectors/*/calendars',
      json: {
        items: [
          { name: 'Project Atlas', is_default: true, access_role: 'owner' },
          { name: 'Personal', is_default: false, access_role: 'owner' },
        ],
      },
    },
    {
      url: '**/api/v1/connectors/*/task-lists',
      json: {
        items: [
          { name: 'Atlas next steps', is_default: true },
          { name: 'Personal', is_default: false },
        ],
      },
    },
    { url: '**/api/v1/skills', json: EXTENDED_SKILLS },
    { url: '**/api/v1/plugins', json: { plugins: [], total: 0 } },
    { url: '**/api/v1/admin/llm-config/types', json: { configs: modelSlots } },
    { url: '**/api/v1/admin/llm-config/metadata/models*', json: modelMetadata },
    { url: '**/api/v1/chat/users/me/statistics', json: EXTENDED_STATISTICS },
  ];
}
