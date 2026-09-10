/**
 * The workboard as the API speaks it (ADR-276).
 *
 * A mirror of `apps/api/src/domains/workboard/schemas.py`, field for field. The
 * two ordered vocabularies below are the ONE place the frontend spells the
 * columns and the priorities, and they are held to the backend enums by
 * `apps/api/tests/unit/domains/workboard/test_frontend_vocabulary_sync.py` —
 * a second ordering written by hand is how a column ends up in the wrong place
 * on one surface only.
 */

/**
 * The seven columns, in board order.
 *
 * The order IS the board's left-to-right order (`STATUS_ORDER` backend side,
 * itself derived from the enum): a column list written a second time somewhere
 * else is a list that will disagree.
 */
export const TICKET_STATUSES = [
  'idea',
  'todo',
  'in_progress',
  'waiting',
  'confirming',
  'validating',
  'done',
] as const;

/** Columns the board draws only while they hold a ticket. */
export const CONDITIONAL_STATUSES: ReadonlySet<string> = new Set(['confirming']);

/**
 * How LIA executes a ticket nobody is watching.
 *
 * The TICKET's choice, never the chat header's toggle: the loop is the default
 * because a ticket is a multi-step task with nobody there to steer a plan, and
 * the person may change it at any point of the ticket's life — the next run
 * reads what it says.
 */
export const EXECUTION_MODES = ['react', 'pipeline'] as const;
export type ExecutionMode = (typeof EXECUTION_MODES)[number];

export type TicketStatus = (typeof TICKET_STATUSES)[number];

/** The four priority levels, weakest first. */
export const TICKET_PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const;

export type TicketPriority = (typeof TICKET_PRIORITIES)[number];

/**
 * Columns a ticket is no longer worked in.
 *
 * Mirrors `CLOSED_STATUSES`: the « hide closed older than N days » filter and
 * the retention sweep both read it, so the two sides must agree on which
 * columns end a ticket's life. One, since « Annulé » was dropped (lot 8) —
 * what was cancelled is finished, and the history says why.
 */
export const CLOSED_STATUSES: readonly TicketStatus[] = ['done'];

/** Who holds a ticket: a person, or LIA running it out of turn. */
export type AssigneeKind = 'human' | 'lia';

/** Who wrote a row: the account, LIA, or the connected peer. */
export type ActorKind = 'user' | 'lia' | 'peer';

/** How a run ended, as the ticket records it. */
export type RunOutcome =
  | 'success'
  | 'waiting'
  | 'confirming'
  | 'failed'
  | 'skipped_quota'
  | 'skipped_busy';

/** One ticket, exactly as `TicketRow` publishes it. */
export interface TicketRow {
  id: string;
  owner_user_id: string;
  parent_id: string | null;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  start_at: string | null;
  due_at: string | null;
  assignee_kind: string;
  assignee_user_id: string | null;
  /** The account that holds it — the owner when `assignee_user_id` is null. */
  effective_assignee_id: string;
  position: number;
  follow_owner: boolean;
  follow_assignee: boolean;
  created_by: string;
  /** `pipeline` | `react` — how LIA runs THIS ticket, changeable at any time. */
  execution_mode: string;
  status_changed_at: string;
  run_count: number;
  /** Set while a run is IN FLIGHT: the only honest « LIA is on it ». */
  run_claimed_at: string | null;
  last_run_at: string | null;
  last_run_outcome: RunOutcome | null;
  last_run_error: string | null;
  last_run_tokens_in: number | null;
  last_run_tokens_out: number | null;
  last_run_cost_eur: number | null;
  /**
   * What the ticket has cost SINCE IT WAS CREATED, in the vocabulary the chat
   * already shows. A ticket is run up to ten times, and « what did this cost
   * me » is a question about the ticket, not about its last minute.
   */
  total_tokens_in: number;
  total_tokens_out: number;
  total_tokens_cache: number;
  total_google_requests: number;
  total_cost_eur: number;
  created_at: string;
  updated_at: string;
}

/**
 * One page of the board, with the EXACT totals beside it (ADR-185).
 *
 * `counts_by_status` covers every column, zero-filled — never derive a column's
 * count from the rows on the page, which under-reports the moment the board
 * outgrows one page.
 */
export interface BoardPage {
  tickets: TicketRow[];
  total: number;
  counts_by_status: Record<string, number>;
}

export interface CommentRow {
  id: string;
  author_kind: string;
  author_user_id: string | null;
  body: string;
  run_id: string | null;
  created_at: string;
}

export interface EventRow {
  id: string;
  actor_kind: string;
  actor_user_id: string | null;
  kind: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface TicketDetail {
  ticket: TicketRow;
  children: TicketRow[];
  comments: CommentRow[];
  events: EventRow[];
}

export interface NeedsMePage {
  tickets: TicketRow[];
  total: number;
}

/**
 * The board at a glance (`GET /workboard/summary`): every figure an aggregate
 * over the WHOLE board (ADR-185), and the caps the instance enforces (ADR-184).
 */
export interface BoardSummary {
  /** Visible tickets — owned or held. */
  total: number;
  counts_by_status: Record<string, number>;
  overdue: number;
  held_by_lia: number;
  /** Waiting on this account, or late on its board. */
  needs_me: number;
  /** Owned — what the cap counts. */
  owned: number;
  max_tickets: number;
  max_runs_per_ticket: number;
  /** Over the owned tickets: runs and what they spent. */
  runs_total: number;
  tokens_in: number;
  tokens_out: number;
  tokens_cache: number;
  google_requests: number;
  cost_eur: number;
}

export interface DeleteResult {
  /** Rows removed: the ticket and its children. */
  removed: number;
}

/** Which side of the board a filter keeps. */
export type BoardSide = 'me' | 'lia' | 'peer' | 'all';

/** How the board orders what it returns. */
export type BoardSort = 'position' | 'priority' | 'due' | 'updated' | 'created';

/**
 * What the board is asked for.
 *
 * Every field is optional and an absent one is NOT sent (the client drops
 * `undefined`), so an unset filter costs no query parameter and the server
 * keeps its own default.
 */
export interface BoardFilters {
  status?: readonly string[];
  assignee?: BoardSide;
  priority?: readonly string[];
  overdue?: boolean;
  due_before?: string;
  q?: string;
  closed_days?: number;
  sort?: BoardSort;
  limit?: number;
  offset?: number;
}

/** The body of `POST /workboard/tickets`. */
export interface TicketCreateBody {
  title: string;
  description?: string | null;
  priority?: string;
  status?: string;
  start_at?: string | null;
  due_at?: string | null;
  assignee?: 'me' | 'lia';
  assignee_user_id?: string | null;
  parent_id?: string | null;
  execution_mode?: ExecutionMode;
  follow?: boolean;
}

/**
 * The body of `PATCH /workboard/tickets/{id}`.
 *
 * An absent field means « not mentioned »; the two `clear_*` flags are how a
 * date is REMOVED, since `null` and « unchanged » would otherwise be the same
 * wire value.
 */
export interface TicketUpdateBody {
  title?: string;
  description?: string | null;
  priority?: string;
  status?: string;
  start_at?: string | null;
  due_at?: string | null;
  clear_start_at?: boolean;
  clear_due_at?: boolean;
  assignee?: 'me' | 'lia';
  assignee_user_id?: string | null;
  execution_mode?: ExecutionMode;
  follow?: boolean;
}

/** The body of the drag-and-drop write. */
export interface MoveBody {
  status: string;
  /** Index inside the column, 0 first. */
  position: number;
}
