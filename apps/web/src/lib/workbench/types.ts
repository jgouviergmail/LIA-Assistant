/**
 * What the « Tools » section reads from `GET /workbench` (ADR-369) — the shape of
 * `domains/workbench/schemas/common.py`, kept in step by hand (the backend's
 * vocabulary is closed and small; a drift fails the rail's tests).
 */

/** The six tools, in rail order. */
export type WorkbenchToolId = 'mail' | 'calendar' | 'tasks' | 'contacts' | 'files' | 'lights';

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
  | 'vacation'
  | 'filters'
  | 'all_day'
  | 'conference'
  | 'notify_attendees'
  | 'occurrence_edit'
  | 'list_management'
  | 'subtasks'
  | 'due_date_only'
  | 'multi_valued'
  | 'contact_groups'
  | 'other_contacts'
  | 'export'
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
  calendar_window_max_events: number;
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
}

/** One room of the bridge: the lights its devices own. */
export interface WorkbenchRoom {
  id: string;
  name: string;
  light_ids: string[];
  /** Whether one of its lights is on. */
  on: boolean;
}

/** One scene of the bridge. */
export interface WorkbenchScene {
  id: string;
  name: string;
  room_id: string | null;
  active: boolean;
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
}

/** A system place of a mailbox (`schemas/mail.MailRole`), in the pane's order. */
export type MailRole = 'inbox' | 'starred' | 'sent' | 'drafts' | 'archive' | 'spam' | 'trash';

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
  /** The person's own Gmail labels on it (ids); none elsewhere. */
  label_ids: string[];
}

/** One attachment of a message. */
export interface MailAttachment {
  /** The provider's handle (a Gmail one may expire: the name travels with it). */
  id: string | null;
  filename: string;
  mime_type: string;
  size: number | null;
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

/** Why one item of a selection (a message, a Drive file) was not done. */
export type WorkbenchActStatus = 'not_found' | 'failed' | 'unavailable';

/** What an act on a selection did — never all-or-nothing. */
export interface WorkbenchActOutcome {
  done: string[];
  failed: { id: string; status: WorkbenchActStatus }[];
}

/** What the provider says of a message that left. */
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
  /** Where it forwards them (set in Gmail). */
  forward: string | null;
}

/** One calendar of the account (`schemas/calendar.CalendarInfo`). */
export interface WorkbenchCalendar {
  id: string;
  name: string;
  /** Its colour as the provider keeps it (#rrggbb): data, drawn as it is. */
  color: string | null;
  primary: boolean;
  writable: boolean;
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
}

/** One group of contacts (Google). */
export interface WorkbenchContactGroup {
  id: string;
  name: string;
  count: number | null;
}

/** A Drive item: a folder, a shortcut to one elsewhere, or a file. */
export type DriveKind = 'folder' | 'file' | 'shortcut';

/** A format a Google document exports to. */
export type DriveExportFormat = 'pdf' | 'docx' | 'xlsx' | 'pptx';

/** One Drive item as the list draws it. */
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
