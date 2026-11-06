/**
 * What the « Tools » section reads from `GET /workbench` (ADR-369) — the shape of
 * `domains/workbench/schemas/common.py`, kept in step by hand (the backend's
 * vocabulary is closed and small; a drift fails the rail's tests).
 */

/** How a screen is read again. */
export interface RereadOptions {
  /** Nobody asked (the person came back to the page): it may take nothing away. */
  unasked?: boolean;
}

/** The six tools, in rail order. */
export type WorkbenchToolId = 'mail' | 'calendar' | 'tasks' | 'contacts' | 'files' | 'lights';

/** The tools one search reaches: no task provider searches, and a lamp holds no words. */
export type SearchableTool = Extract<WorkbenchToolId, 'mail' | 'calendar' | 'contacts' | 'files'>;

/** One thing a search found: what a person recognises, and how to open it. */
export interface SearchHit {
  /** What its tool opens: a shortcut's target, never the shortcut. */
  id: string;
  title: string;
  subtitle: string | null;
  mail_folder: string | null;
  calendar_id: string | null;
  /** An event's day, on the person's clock. */
  day: string | null;
  is_folder: boolean;
}

/** What one tool found. */
export interface ToolHits {
  tool: SearchableTool;
  hits: SearchHit[];
  /** It holds more than these. */
  truncated: boolean;
  /** A mailbox searched from its inbox alone. */
  inbox_only: boolean;
}

/** What the tools found, and which of them could not say, or only in part. */
export interface GlobalSearch {
  results: ToolHits[];
  failed: SearchableTool[];
}

/**
 * ready — usable; reconnect_required — its provider needs a new authorisation;
 * not_connected — a provider can be connected in Settings › Connectors;
 * unavailable — the instance offers no provider for it.
 */
export type WorkbenchToolState = 'ready' | 'not_connected' | 'reconnect_required' | 'unavailable';

/** A gesture a provider may or may not accept (closed vocabulary). */
export type WorkbenchFeature =
  | 'mark_read'
  | 'drafts'
  | 'html'
  | 'attachments'
  | 'attachment_filter'
  | 'labels'
  | 'folder_management'
  | 'permanent_delete'
  | 'vacation'
  | 'vacation_subject'
  | 'vacation_open_end'
  | 'filters'
  | 'filter_words'
  | 'send_as'
  | 'all_day'
  | 'conference'
  | 'notify_attendees'
  | 'occurrence_edit'
  | 'event_move'
  | 'event_move_with_guests'
  | 'calendar_management'
  | 'list_management'
  | 'subtasks'
  | 'due_date_only'
  | 'task_steps'
  | 'task_details'
  | 'task_order'
  | 'multi_valued'
  | 'contact_groups'
  | 'other_contacts'
  | 'export'
  | 'file_views'
  | 'scenes';

/** One tool of the rail. */
export interface WorkbenchToolAvailability {
  tool: WorkbenchToolId;
  state: WorkbenchToolState;
  /** The connector type serving it (also when it must be reconnected). */
  provider: string | null;
  /** The gestures this provider accepts (empty when not usable). */
  features: WorkbenchFeature[];
  /** Numeric limits this provider imposes, published because enforced. */
  bounds: Record<string, number>;
}

/** The bounds every workbench route enforces. */
export interface WorkbenchLimits {
  page_size: number;
  bulk_max_items: number;
  download_max_bytes: number;
  /** The largest file sent to a drive. */
  upload_max_bytes: number;
  calendar_window_max_events: number;
  /** How long « Send » waits before a message leaves (0: at once). */
  send_undo_seconds: number;
  /** How long a composer stays quiet before it saves a draft (0: never by itself). */
  draft_autosave_seconds: number;
  /** The longest words one search takes. */
  search_max_chars: number;
}

/** The rail: every tool in rail order, and the bounds. */
export interface WorkbenchAvailability {
  tools: WorkbenchToolAvailability[];
  limits: WorkbenchLimits;
}

/** One lamp of the bridge, and what it can do (`schemas/lights.py`). */
export interface WorkbenchLight {
  id: string;
  name: string;
  room_id: string | null;
  on: boolean;
  /** 0-100; null when the lamp cannot be dimmed. */
  brightness: number | null;
  supports_color: boolean;
  /** Its current colour, drawn at full luminance. */
  color_hex: string | null;
  /** Its colour temperature (mirek); null when it has none. */
  mirek: number | null;
  mirek_min: number | null;
  mirek_max: number | null;
  /** False when the bridge cannot reach it; null when nobody says. */
  reachable: boolean | null;
}

/** One room of the bridge, or a zone gathering lamps across rooms. */
export interface WorkbenchRoom {
  id: string;
  name: string;
  kind: 'room' | 'zone';
  light_ids: string[];
  /** Whether one of its lights is on. */
  on: boolean;
  /** Whether one of its lights takes a colour. */
  supports_color: boolean;
  /** The temperatures all its lights accept (mirek); null when they meet on none. */
  mirek_min: number | null;
  mirek_max: number | null;
}

/** One scene of the bridge. */
export interface WorkbenchScene {
  id: string;
  name: string;
  room_id: string | null;
  active: boolean;
  /** Its palette can play in motion. */
  dynamic: boolean;
  /** It is playing in motion now. */
  playing: boolean;
}

/** The bridge, read once. */
export interface WorkbenchLights {
  rooms: WorkbenchRoom[];
  lights: WorkbenchLight[];
  scenes: WorkbenchScene[];
}

/** One list of tasks (`schemas/tasks.py`). */
export interface WorkbenchTaskList {
  id: string;
  title: string;
  /** The default the settings chose. */
  default: boolean;
}

/** One task: its due date is a DAY (`YYYY-MM-DD`), whatever the provider keeps. */
export interface WorkbenchTask {
  id: string;
  title: string;
  notes: string | null;
  completed: boolean;
  due: string | null;
  /** The task it is a subtask of (Google only). */
  parent: string | null;
  /** Its order among its siblings (Google only). */
  position: string | null;
  /** Its steps (To Do only). */
  steps: WorkbenchTaskStep[];
  /** How much it matters (To Do only). */
  importance: WorkbenchTaskImportance | null;
  /** When it reminds, an instant (To Do only). */
  reminder: string | null;
  /** How it repeats; `custom` is a pattern the screen has no word for (To Do only). */
  repeat: WorkbenchTaskRepeat | 'custom' | null;
}

/** One step of a task (To Do only). */
export interface WorkbenchTaskStep {
  id: string;
  title: string;
  checked: boolean;
}

export type WorkbenchTaskImportance = 'low' | 'normal' | 'high';
export type WorkbenchTaskRepeat = 'daily' | 'weekly' | 'monthly' | 'yearly';
/** A view across the lists, decided in the account's day. */
export type WorkbenchTaskView = 'today' | 'overdue' | 'upcoming';

/** What a move did: each task moved says what it is called from now on. */
export interface WorkbenchTaskMoveOutcome extends WorkbenchActOutcome {
  moved: { id: string; new_id: string }[];
}

/** What clearing a list's done tasks did. */
export interface WorkbenchTasksCleared {
  deleted: number;
  remaining: boolean;
}

/** A system place of a mailbox (`schemas/mail.MailRole`), in the pane's order. */
export type MailRole =
  | 'inbox'
  | 'starred'
  | 'sent'
  | 'drafts'
  | 'archive'
  | 'all'
  | 'spam'
  | 'trash';

/** One place of the mailbox: a system one (its role names it) or the person's own. */
export interface MailFolder {
  /** What the listing takes back: `system:<role>`, a Gmail label id or a folder name. */
  id: string;
  kind: 'system' | 'user';
  role: MailRole | null;
  name: string | null;
}

/** One mailbox of a header, read apart. */
export interface MailAddress {
  /** The display name; empty when none was sent. */
  name: string;
  address: string;
}

/** One row of a listing (headers only). */
export interface MailSummary {
  id: string;
  thread_id: string;
  sender: MailAddress | null;
  subject: string;
  snippet: string;
  /** When the mailbox received it (ISO, UTC). */
  received_at: string | null;
  is_read: boolean;
  is_starred: boolean;
  /** Whether it carries files (Graph's word; elsewhere its top-level type). */
  has_attachments: boolean;
  /** The person's own Gmail labels on it (ids); none elsewhere. */
  label_ids: string[];
}

/** What was said around a message: oldest first, drafts left out. */
export interface MailConversation {
  items: MailSummary[];
  /** It holds older messages than these. */
  truncated: boolean;
}

/** One attachment of a message. */
export interface MailAttachment {
  /** The provider's handle (a Gmail one may expire: the name travels with it). */
  id: string | null;
  filename: string;
  mime_type: string;
  size: number | null;
  /** Something can be read of it through the API. */
  previewable?: boolean;
}

/** One message, as the reader draws it. */
export interface MailMessage extends Omit<MailSummary, 'snippet'> {
  reply_to: MailAddress[];
  to: MailAddress[];
  cc: MailAddress[];
  /** Its text, the quoted history left out. */
  body: string;
  attachments: MailAttachment[];
}

/** A message as its author laid it out (D3), for the sandboxed frame alone. */
export interface MailHtml {
  /** Its HTML body; null when it has none (the text reader shows instead). */
  html: string | null;
  /** Cut at the published ceiling: only the beginning is shown. */
  truncated: boolean;
}

/** An image a message carries inside itself, as its frame draws it. */
export interface MailInlineImage {
  /** The name its HTML uses. */
  cid: string;
  data_url: string;
}

/** The images of a message, and how many were left out. */
export interface MailInlineImages {
  images: MailInlineImage[];
  skipped: number;
}

/** The ways out of a mailing list a message names. */
export interface MailUnsubscribe {
  web_url: string | null;
  mail_to: string | null;
  one_click: boolean;
}

/** Why one item of a selection (a message, a Drive file) was not done. */
export type WorkbenchActStatus =
  | 'not_found'
  | 'failed'
  | 'unavailable'
  | 'name_taken'
  | 'task_left_behind';

/** What an act on a selection did — never all-or-nothing. */
/** What a move did, and what each message is called from now on. */
export interface MailMoveOutcome extends WorkbenchActOutcome {
  moved: { id: string; new_id: string | null }[];
}

/** What the mailbox leaves unread, each figure keyed as the pane names its folder. */
export interface MailCounts {
  counts: Record<string, number>;
  truncated: boolean;
}

/** What emptying the trash did. */
export interface MailTrashEmptied {
  deleted: number;
  remaining: boolean;
}

export interface WorkbenchActOutcome {
  done: string[];
  failed: { id: string; status: WorkbenchActStatus }[];
}

/** What the provider says of a message that left. */
/** An address of the mailbox a message may leave from. */
export interface MailSender {
  address: string;
  name: string;
  is_default: boolean;
}

/** The addresses a message may leave from. */
export interface MailSenders {
  items: MailSender[];
}

/** What the active mailbox signs with. */
export interface MailSignature {
  text: string;
  /** What a plain-text body gains to carry it. */
  block: string;
}

/** Who a reply would reach, by the rule the provider sends with. */
export interface MailReplyRecipients {
  to: MailAddress[];
  cc: MailAddress[];
}

export interface MailSent {
  id: string | null;
  thread_id: string | null;
}

/** One row of the drafts listing. */
export interface MailDraftSummary {
  /** The draft's id (iCloud gives a new one on every save). */
  id: string;
  to: MailAddress[];
  subject: string;
  snippet: string;
  updated_at: string | null;
}

/** One draft, whole, with the revision an edit or a send is made against. */
export interface MailDraft {
  id: string;
  revision: string;
  /** Where it leaves from, when it says. */
  sender: MailAddress | null;
  to: MailAddress[];
  cc: MailAddress[];
  bcc: MailAddress[];
  subject: string;
  body: string;
  attachments: MailAttachment[];
  updated_at: string | null;
}

/** One of the person's own files a new message may carry. */
export interface AttachableFile {
  id: string;
  filename: string;
  mime_type: string;
  size: number;
  origin: string;
  /** When it goes; null when kept. */
  expires_at: string | null;
}

/** One page of the files a message may carry, and their exact total. */
export interface AttachablePage {
  items: AttachableFile[];
  total: number;
  next_offset: number | null;
}

/** The vacation responder, in the account's days (`YYYY-MM-DD`, the last one included). */
export interface MailVacation {
  enabled: boolean;
  subject: string;
  body: string;
  start_date: string | null;
  end_date: string | null;
}

/** One Gmail filter: what it matches, what it does. */
export interface MailFilter {
  id: string;
  sender: string | null;
  recipient: string | null;
  subject: string | null;
  query: string | null;
  has_attachment: boolean;
  add_label_ids: string[];
  archive: boolean;
  mark_read: boolean;
  /** Where it forwards them (set at the provider). */
  forward: string | null;
  /** What Outlook calls it; Gmail has no name. */
  name: string | null;
  /** It can only be changed at the provider. */
  read_only: boolean;
}

/** One calendar of the account (`schemas/calendar.CalendarInfo`). */
export interface WorkbenchCalendar {
  id: string;
  name: string;
  /** Its colour as the provider keeps it (#rrggbb): data, drawn as it is. */
  color: string | null;
  primary: boolean;
  /** The default the settings chose. */
  default: boolean;
  writable: boolean;
  /** Whether the person may rename and delete it. */
  manageable: boolean;
}

/** One event as a view draws it. */
export interface CalendarEvent {
  /** An OCCURRENCE's own id within a series. */
  id: string;
  calendar_id: string;
  summary: string;
  all_day: boolean;
  /** A day (all-day) or an instant in UTC. */
  start: string;
  /** A day, EXCLUSIVE (all-day), or an instant in UTC. */
  end: string;
  location: string | null;
  recurring: boolean;
  conference_url: string | null;
}

/** What an attendee answered (Google's words, the three providers mapped to them). */
export type AttendeeResponse = 'accepted' | 'declined' | 'tentative' | 'needsAction';

export interface CalendarAttendee {
  email: string;
  name: string | null;
  response: AttendeeResponse;
}

/** One event, whole. */
export interface CalendarEventDetail extends CalendarEvent {
  description: string | null;
  attendees: CalendarAttendee[];
  organizer: string | null;
  link: string | null;
  /** Its own reminder, in minutes before; null when it has none of its own. */
  reminder_minutes: number | null;
  /** Whether its time shows as taken. */
  busy: boolean;
  /** Whether its details stay private. */
  private: boolean;
  /** The zone it was set in (IANA); null when the provider says none, or UTC. */
  zone: string | null;
  /** What the person answered; null for an event with nothing for them to answer. */
  my_response: AttendeeResponse | null;
}

/** One open task with a date, as a calendar draws it. */
export interface DueTask {
  id: string;
  list_id: string;
  title: string;
  /** The day it is due, `YYYY-MM-DD`. */
  due: string;
}

/** The open tasks due over the days shown, from every list. */
export interface DueTasks {
  tasks: DueTask[];
  truncated: boolean;
  /** The lists that could not be read. */
  failed: string[];
}

/** An answer the person can give; `needsAction` is only ever read. */
export type EventAnswer = Exclude<AttendeeResponse, 'needsAction'>;

/** What a search of the calendars found. */
export interface CalendarSearchAnswer {
  events: CalendarEvent[];
  truncated: boolean;
  /** The calendars that could not be read. */
  failed: string[];
}

/** One calendar over a window — or why it could not be read. */
export interface CalendarWindow {
  calendar_id: string;
  events: CalendarEvent[];
  /** Cut at the published bound (`limits.calendar_window_max_events`). */
  truncated: boolean;
  /** Events whose times could not be read. */
  skipped: number;
  /** The refusal code that kept it unread. */
  error: string | null;
}

export interface CalendarEventsWindow {
  calendars: CalendarWindow[];
}

/** An e-mail address or a phone number, and its kind (null when unsaid). */
export interface ContactValue {
  value: string;
  type: string | null;
}

/** A postal address on one line, and its kind. */
export interface ContactAddress {
  formatted: string;
  type: string | null;
}

/** One contact as the list draws it. */
export interface WorkbenchContactSummary {
  id: string;
  /** The name the provider shows (the one the editor writes). */
  name: string;
  /** Its parts, when the provider holds them: the list reads « Given Family ». */
  given_name: string | null;
  family_name: string | null;
  email: string | null;
  phone: string | null;
  organization: string | null;
  /** The name folded by the API (`fold_name`): what « see the relationship » matches. */
  name_key: string;
}

/** One contact, whole and typed. */
export interface WorkbenchContact extends WorkbenchContactSummary {
  emails: ContactValue[];
  phones: ContactValue[];
  addresses: ContactAddress[];
  notes: string | null;
  job_title: string | null;
  /** Its first website, as written: followed only through `LinkedText`. */
  website: string | null;
  /** An ISO day, or `--MM-DD` when the provider holds no year. */
  birthday: string | null;
}

/** What an import did: never all-or-nothing (`schemas/contacts.ContactsImported`). */
export interface ContactsImported {
  done: number;
  /** The cards that became no contact: their place in the file, and the name they carry. */
  failed: { position: number; name: string }[];
}

/** One group of contacts: a Google group, a Graph category, an iCloud group card. */
export interface WorkbenchContactGroup {
  id: string;
  name: string;
  /** How many it holds; null where that cannot be exact. */
  count: number | null;
  /** The person's: it can be renamed and deleted (Google keeps some for itself). */
  own: boolean;
}

/** A Drive item: a folder, a shortcut to one elsewhere, or a file. */
export type DriveKind = 'folder' | 'file' | 'shortcut';

/** A format a Google document exports to. */
export type DriveExportFormat = 'pdf' | 'docx' | 'xlsx' | 'pptx';

/** One Drive item as the list draws it. */
/** What became of a source's read: nothing found is `used`, with empty lists. */
export type ContactHistorySource = 'used' | 'disabled' | 'unavailable';

/** One message exchanged with a contact. */
export interface ContactHistoryMail {
  id: string;
  subject: string;
  at: string | null;
}

/** One meeting with a contact. */
export interface ContactHistoryMeeting {
  id: string;
  title: string;
  at: string | null;
  /** Its day, on the person's clock. */
  day: string | null;
  all_day: boolean;
  calendar_id: string;
}

/** The latest exchanges with a contact. */
export interface WorkbenchContactHistory {
  mail: ContactHistorySource;
  received: ContactHistoryMail[];
  sent: ContactHistoryMail[];
  calendar: ContactHistorySource;
  organized_by_them: ContactHistoryMeeting[];
  organized_by_you: ContactHistoryMeeting[];
  /** Meetings with them whose organiser nobody named. */
  shared: ContactHistoryMeeting[];
  /** How far back the calendar was read. */
  meetings_window_days: number;
  /** A window held more events than were read. */
  meetings_cut: boolean;
}

/** A text file's words, and the version a change must name. */
export interface WorkbenchFileText {
  text: string;
  tag: string;
}

export interface WorkbenchDriveItem {
  id: string;
  name: string;
  kind: DriveKind;
  mime_type: string;
  modified_at: string | null;
  /** Its size in bytes; null for a Google document. */
  size: number | null;
  /** Where Drive opens it — Google's own https address, else null. */
  web_url: string | null;
  /** A shortcut's target, and what it is. */
  target_id: string | null;
  target_kind: DriveKind | null;
  /** The formats a Google document exports to (the first the default). */
  formats: DriveExportFormat[];
  /** It has bytes, or a Google document with an export. */
  downloadable: boolean;
  /** The person starred it (a drive that keeps stars). */
  starred: boolean;
  /** Something can be shown of it. */
  previewable: boolean;
  /** Its words can be changed here. */
  editable: boolean;
}

/** Someone who reaches a file. */
export interface WorkbenchSharedPerson {
  id: string;
  email: string | null;
  name: string | null;
  role: 'owner' | 'writer' | 'reader';
}

/** Who reaches a file, and the link anyone can follow, if it has one. */
export interface WorkbenchFileSharing {
  people: WorkbenchSharedPerson[];
  link: { id: string; url: string | null } | null;
}

/** What the account uses of its drive; an unlimited one has no total. */
export interface WorkbenchDriveQuota {
  used: number;
  total: number | null;
}

/** A copy, or none while the provider finishes one it answered for early. */
export interface WorkbenchFileCopied {
  item: WorkbenchDriveItem | null;
}

/** One folder of a breadcrumb. */
export interface WorkbenchFileAncestor {
  id: string;
  name: string;
}

/** One Drive item, and where it lives. */
export interface WorkbenchFileDetail extends WorkbenchDriveItem {
  owners: string[];
  description: string | null;
  created_at: string | null;
  /** Its folders from the top down, My Drive itself left out. */
  ancestors: WorkbenchFileAncestor[];
  /** The walk reached My Drive. */
  in_my_drive: boolean;
  /** The walk stopped at its depth: folders above it are not shown. */
  ancestors_truncated: boolean;
}
