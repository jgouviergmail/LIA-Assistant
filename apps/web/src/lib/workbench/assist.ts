/**
 * What LIA answers from the Tools (ADR-372): the routes' shapes and addresses.
 *
 * Every answer is a proposal, and says what it cost, or nothing when it was already held.
 */
import type { LLMUsage } from '@/types/llm-usage';

/** Non-streaming assists stop before the web proxy's idle ceiling. */
export const ASSIST_TIMEOUT_MS = 85_000;

/** Where a click asks. */
export const ASSIST_PATHS = {
  mailSummary: '/tool-assists/mail/summary',
  mailReply: '/tool-assists/mail/reply',
  mailCompose: '/tool-assists/mail/compose',
  mailSubject: '/tool-assists/mail/subject',
  mailTranslate: '/tool-assists/mail/translate',
  textRewrite: '/tool-assists/text/rewrite',
  textTranslate: '/tool-assists/text/translate',
  textWrite: '/tool-assists/text/write',
  textPassage: '/tool-assists/text/passage',
  mailSearch: '/tool-assists/mail/search',
  mailFilter: '/tool-assists/mail/filter',
  mailTriage: '/tool-assists/mail/triage',
  mailConversation: '/tool-assists/mail/conversation',
  mailAttachment: '/tool-assists/mail/attachment',
  fileSummary: '/tool-assists/files/summary',
  mailEvent: '/tool-assists/mail/event',
  mailTask: '/tool-assists/mail/task',
  eventFromWords: '/tool-assists/calendar/from-words',
  taskFromWords: '/tool-assists/tasks/from-words',
  taskSteps: '/tool-assists/tasks/steps',
  contactComplete: '/tool-assists/contacts/complete',
  contactFromCard: '/tool-assists/contacts/from-card',
  contactFromWords: '/tool-assists/contacts/from-words',
  readAloud: '/tool-assists/read-aloud',
  keepFile: '/tool-assists/spaces/keep-file',
  keepAttachment: '/tool-assists/spaces/keep-attachment',
} as const;

/** One change a person can ask of their own words (`text.RewriteTone`). */
export type RewriteTone = 'fix' | 'shorter' | 'formal' | 'warm';

/** What a text is for (`text.WritingKind`). */
export type WritingKind =
  | 'event_description'
  | 'task_notes'
  | 'contact_notes'
  | 'auto_reply'
  | 'signature'
  | 'document';

/** What every answer carries. */
export interface AssistAnswer {
  usage: LLMUsage | null;
}

/** The digest of a message. */
export interface MailSummaryAnswer extends AssistAnswer {
  gist: string;
  key_points: string[];
  actions: string[];
}

/** An event as a form can take it: what is null or empty was not said, or not readable. */
export interface ProposedEvent {
  summary: string;
  start_date: string | null;
  start_time: string | null;
  end_date: string | null;
  end_time: string | null;
  all_day: boolean;
  location: string;
  description: string;
  attendees: string[];
  repeat: 'none' | 'daily' | 'weekly' | 'monthly' | 'yearly';
  /** A video call is to be made with it: the text asked for one and gave no link. */
  conference: boolean;
}

/** A task as a form can take it. */
export interface ProposedTask {
  title: string;
  notes: string;
  due: string | null;
  list_name: string | null;
  /** `high` when the text says it is urgent; else the provider's own. */
  importance: 'high' | null;
}

export interface EventAnswer extends AssistAnswer {
  event: ProposedEvent;
}

export interface TaskAnswer extends AssistAnswer {
  task: ProposedTask;
}

export interface StepsAnswer extends AssistAnswer {
  steps: string[];
}

/** Words proposed: the person reads them before anything is done with them. */
export interface TextAnswer extends AssistAnswer {
  text: string;
  /** The subject written with it, for a whole message. */
  subject?: string | null;
  /** Only the beginning of its source was read. */
  cut?: boolean;
}

/** Words heard: the file, whether it stops short, and what the voice cost. */
export interface ReadAloudAnswer extends AssistAnswer {
  /** The MP3, base64. */
  audio: string;
  cut: boolean;
  cost_eur: number;
}

/** A search read from a sentence, as the screen can take it. */
export interface ProposedSearch {
  words: string;
  unread: boolean;
  attachments: boolean;
  first_day: string | null;
  last_day: string | null;
}

export interface SearchAnswer extends AssistAnswer {
  search: ProposedSearch;
}

/** A filter read from a sentence, as its form can take it. */
export interface ProposedFilter {
  sender: string;
  recipient: string;
  subject: string;
  words: string;
  has_attachment: boolean;
  label: string | null;
  archive: boolean;
  mark_read: boolean;
}

export interface FilterAnswer extends AssistAnswer {
  filter: ProposedFilter;
}

/** What one message weighs. */
export interface TriagedMessage {
  id: string;
  importance: string;
  category: string;
}

export interface TriageAnswer extends AssistAnswer {
  items: TriagedMessage[];
  /** How many could not be read: they keep their place. */
  skipped: number;
}

/** A value a contact's card lacks, with the message that says it. */
export interface ProposedValue {
  field: string;
  value: string;
  message_id: string;
  subject: string;
  received_at: string | null;
}

export interface ContactValuesAnswer extends AssistAnswer {
  values: ProposedValue[];
}

/** A business card read, as the editor can take it. */
export interface ProposedContact {
  given_name: string;
  family_name: string;
  organization: string;
  job_title: string;
  website: string;
  emails: string[];
  phones: string[];
  address: string;
}

export interface CardAnswer extends AssistAnswer {
  contact: ProposedContact;
}
