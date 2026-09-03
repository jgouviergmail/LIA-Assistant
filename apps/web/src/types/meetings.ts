/**
 * Meeting recording & structured minutes (ADR-258).
 *
 * Mirrors the backend Pydantic contracts in
 * `apps/api/src/domains/meetings/schemas.py`. Field names are the wire names.
 */

/** Lifecycle of a meeting — the durable job state. */
export type MeetingStatus =
  | 'recording'
  | 'interrupted'
  | 'stopped'
  | 'processing'
  | 'ready'
  | 'failed';

/** Where a processing meeting stands. */
export type MeetingStage = 'normalizing' | 'transcribing' | 'synthesizing' | 'indexing';

/** What the client sends, fixed at start for the whole recording. */
export type MeetingAudioFormat = 'pcm_s16le_16' | 'webm_opus' | 'ogg_opus';

export type MeetingSttProvider = 'elevenlabs' | 'openai' | 'local';

export type MeetingSttEnginePreference = 'auto' | 'remote' | 'local';

export type MeetingIndexState = 'pending' | 'indexed' | 'error' | 'disabled';

export type SectionKind = 'paragraph' | 'bullets' | 'topics' | 'action_items' | 'transcript';

/** The section kinds, in the order the template editor offers them. */
export const SECTION_KINDS: readonly SectionKind[] = [
  'paragraph',
  'bullets',
  'topics',
  'action_items',
  'transcript',
];

/** Where a template is filed in the library (ADR-259). */
export type TemplateCategory =
  | 'custom'
  | 'meeting'
  | 'transcript'
  | 'analysis'
  | 'business'
  | 'technical'
  | 'personal'
  | 'learning';

/** Library order: the user's own first, then the built-in categories. */
export const TEMPLATE_CATEGORIES: readonly TemplateCategory[] = [
  'custom',
  'meeting',
  'transcript',
  'analysis',
  'business',
  'technical',
  'personal',
  'learning',
];

/** How the template that wrote a meeting's minutes was chosen (ADR-259). */
export type TemplateSelection = 'auto' | 'user' | 'preference';

/** Statuses under which the recording still accepts segments. */
export const LIVE_MEETING_STATUSES: readonly MeetingStatus[] = ['recording', 'interrupted'];

/** Statuses the detail page keeps polling through. */
export const IN_FLIGHT_MEETING_STATUSES: readonly MeetingStatus[] = ['stopped', 'processing'];

export interface TemplateSection {
  key: string;
  label: string;
  instruction: string;
  kind: SectionKind;
}

/** One library entry, as the list shows it. */
export interface MeetingTemplateSummary {
  /** `builtin:<key>` or `user:<uuid>`. */
  ref: string;
  name: string;
  description: string | null;
  category: TemplateCategory;
  /** A catalogue template: read-only, customized by duplication. */
  builtin: boolean;
  sections_count: number;
  /** Whether automatic selection may pick it (transcript templates: never). */
  auto_selectable: boolean;
}

export interface MeetingTemplateListResponse {
  items: MeetingTemplateSummary[];
  /** How many templates the user may keep (built-ins not counted). */
  max_user_templates: number;
}

/** A template with its sections. */
export interface MeetingTemplate {
  ref: string;
  /** Row id; null for a built-in. */
  id: string | null;
  name: string;
  description: string | null;
  category: TemplateCategory;
  sections: TemplateSection[];
  builtin: boolean;
  /** For a user template: the built-in it was duplicated from. */
  builtin_key: string | null;
  auto_selectable: boolean;
}

/** Create a user template: from sections, or by duplicating a reference. */
export interface MeetingTemplateCreate {
  name?: string;
  description?: string | null;
  category?: TemplateCategory;
  sections?: TemplateSection[];
  duplicate_of?: string;
}

export interface MeetingTemplateUpdate {
  name: string;
  description: string | null;
  category: TemplateCategory;
  sections: TemplateSection[];
}

/** Several template refs to act on together (ADR-259). */
export interface TemplateRefsRequest {
  refs: string[];
}

/** One ref a template batch left untouched, with the stable reason. */
export interface TemplateBulkSkipped {
  ref: string;
  code: string;
}

export interface MeetingTemplateBulkDuplicateResponse {
  created: MeetingTemplateSummary[];
  skipped: TemplateBulkSkipped[];
}

export interface MeetingTemplateBulkDeleteResponse {
  deleted: string[];
  skipped: TemplateBulkSkipped[];
  /** The default-format preference pointed at a deleted row and went back to automatic. */
  preference_reset: boolean;
}

/** Write the minutes again with another template (ADR-259). */
export interface MeetingReformatRequest {
  template_ref: string;
  /** `replace` = these minutes; `new` = new minutes from the same transcript. */
  mode: 'replace' | 'new';
}

export interface MeetingReformatResponse {
  id: string;
  status: MeetingStatus;
  stage: MeetingStage | null;
  source_meeting_id: string | null;
}

export interface Participant {
  label: string;
  name: string | null;
  role: string | null;
}

export interface TopicItem {
  title: string;
  summary: string;
}

export interface ActionItem {
  description: string;
  owner: string | null;
  due_date: string | null;
}

/** One rewritten turn of a `transcript` section (ADR-259). */
export interface TranscriptLine {
  speaker: string;
  start: number;
  text: string;
}

export interface ReportSection {
  key: string;
  label: string;
  kind: SectionKind;
  paragraph: string | null;
  bullets: string[];
  topics: TopicItem[];
  action_items: ActionItem[];
  transcript: TranscriptLine[];
}

export interface MeetingReport {
  title: string;
  participants: Participant[];
  sections: ReportSection[];
}

export interface TranscriptTurn {
  speaker: string;
  start: number;
  end: number;
  text: string;
}

export interface MeetingGeolocation {
  lat: number;
  lon: number;
  accuracy_m: number | null;
}

export interface MeetingStartRequest {
  audio_format: MeetingAudioFormat;
  language: string;
  timezone: string;
  geolocation: MeetingGeolocation | null;
  /** Minutes template chosen for THIS meeting; absent = preference, then automatic. */
  template_ref?: string;
}

export interface MeetingStopRequest {
  segment_count: number;
  allow_gaps: boolean;
}

export interface MeetingPatchRequest {
  title?: string;
  participants?: Participant[];
  sections?: ReportSection[];
  location_label?: string | null;
  /** Minutes template for this meeting, while it is still live or queued. */
  template_ref?: string;
}

export interface MeetingPreferences {
  stt_engine: MeetingSttEnginePreference;
  language: string;
  auto_email: boolean;
  keep_audio_hours: number;
  /** Template applied to every meeting; null = LIA chooses from the transcript. */
  default_template_ref: string | null;
  keep_audio_hours_max: number;
}

export type MeetingPreferencesUpdate = Omit<MeetingPreferences, 'keep_audio_hours_max'>;

export interface EngineInfo {
  provider: MeetingSttProvider;
  model: string | null;
  diarized: boolean;
  cost_per_hour_eur: number | null;
  local_rtf_estimate: number | null;
}

export interface MeetingLimits {
  segment_seconds: number;
  segment_max_seconds: number;
  segment_max_bytes: number;
  max_duration_minutes: number;
  silence_prompt_minutes: number;
}

export interface MeetingStartResponse {
  id: string;
  status: MeetingStatus;
  started_at: string;
  engine: EngineInfo;
  limits: MeetingLimits;
}

export interface MeetingSegmentAck {
  sequence: number;
  segment_count: number;
  audio_bytes: number;
  status: MeetingStatus;
}

export interface MeetingSummary {
  id: string;
  status: MeetingStatus;
  stage: MeetingStage | null;
  title: string | null;
  started_at: string;
  stopped_at: string | null;
  audio_duration_seconds: number | null;
  participants_count: number;
  action_items_count: number;
  index_state: MeetingIndexState | null;
  stt_provider: MeetingSttProvider | null;
  /** Transcription + minutes in EUR; null while nothing priced was spent. */
  total_cost_eur: number | null;
  last_error_code: string | null;
  template_ref: string | null;
  template_name: string | null;
  template_selection: TemplateSelection | null;
  /** The meeting whose transcript produced these minutes (reformat 'new'). */
  source_meeting_id: string | null;
}

export interface MeetingListResponse {
  items: MeetingSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface MeetingDetail {
  id: string;
  status: MeetingStatus;
  stage: MeetingStage | null;
  started_at: string;
  stopped_at: string | null;
  last_segment_at: string | null;
  client_timezone: string;
  audio_format: MeetingAudioFormat;
  segment_count: number;
  audio_duration_seconds: number | null;
  audio_gaps: number;
  audio_kept_until: string | null;
  audio_purged_at: string | null;
  location_lat: number | null;
  location_lon: number | null;
  location_label: string | null;
  calendar_event_id: string | null;
  stt_provider: MeetingSttProvider | null;
  stt_model: string | null;
  stt_detected_language: string | null;
  stt_diarized: boolean;
  stt_cost_eur: number | null;
  synthesis_model: string | null;
  synthesis_tokens_in: number;
  synthesis_tokens_out: number;
  synthesis_tokens_cache: number;
  /** LLM cost of the minutes, every synthesis pass included; null = model not priced. */
  synthesis_cost_eur: number | null;
  /** Transcription + minutes in EUR; null while nothing priced was spent. */
  total_cost_eur: number | null;
  has_transcript: boolean;
  report: MeetingReport | null;
  report_is_edited: boolean;
  report_edited_at: string | null;
  template_snapshot: TemplateSection[] | null;
  index_state: MeetingIndexState | null;
  indexed_at: string | null;
  email_sent_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  template_ref: string | null;
  template_name: string | null;
  template_selection: TemplateSelection | null;
  /** The model's one-line justification when the template was chosen automatically. */
  template_selection_reason: string | null;
  /** The meeting whose transcript produced these minutes (reformat 'new'). */
  source_meeting_id: string | null;
  /** Minutes produced from this meeting's transcript (reformat 'new'). */
  derived_count: number;
  transcript: TranscriptTurn[] | null;
}

/** One id a bulk operation left untouched, with the stable reason. */
export interface BulkSkipped {
  id: string;
  code: string;
}

/** What happened to every id of a bulk delete (ADR-259). */
export interface MeetingBulkDeleteResponse {
  deleted: string[];
  skipped: BulkSkipped[];
}

export interface MeetingActionResponse {
  id: string;
  status: MeetingStatus;
  stage: MeetingStage | null;
  detail: Record<string, unknown> | null;
}

/**
 * Metadata of the « minutes ready » proactive notification, as the
 * dispatcher publishes it (`processing.py::_notify_ready`).
 */
export interface MeetingNotificationMetadata {
  type: 'proactive_meeting';
  target_id: string;
  meeting_id: string;
  title: string;
  duration_seconds: number;
  participants_count: number;
  action_items_count: number;
  gaps: number;
  /** The paid units of the exchange (ADR-258): transcription audio and minutes tokens. */
  tokens_in?: number;
  tokens_out?: number;
  tokens_cache?: number;
  model_name?: string | null;
  /** LLM cost of the minutes; null when the model has no administered price. */
  llm_cost_eur?: number | null;
  /** Transcription cost; null when the engine's model has no administered price (0 for the local engine). */
  stt_cost_eur?: number | null;
  stt_audio_duration_seconds?: number;
  /** Everything this exchange cost, in EUR — what the bubble footer shows. */
  cost_eur?: number | null;
  /** The template that wrote the minutes (ADR-259). */
  template_name?: string | null;
}

/** Runtime guard for the notification metadata (a shape drift must degrade, never crash). */
export function isMeetingNotificationMetadata(
  value: unknown
): value is MeetingNotificationMetadata {
  if (!value || typeof value !== 'object') return false;
  const meta = value as Record<string, unknown>;
  return (
    meta.type === 'proactive_meeting' &&
    typeof meta.meeting_id === 'string' &&
    meta.meeting_id.length > 0 &&
    typeof meta.title === 'string'
  );
}
