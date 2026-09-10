/**
 * The board's filters, in and out of the URL (ADR-276).
 *
 * A narrowed board is a link somebody can send: the open ticket already
 * travels as `?ticket=`, and the filters take the same road so the settings
 * page can point at « what is late » or « what LIA holds ». Unknown values are
 * DROPPED rather than trusted — a hand-typed `?assignee=bob` reads as `all` —
 * and the defaults write nothing, so a plain board keeps a plain URL.
 *
 * The URL FOLLOWS the filters here, never the other way round while a person
 * types: a controlled search box whose value came back through an async
 * router drops every second keystroke.
 */
import {
  TICKET_PRIORITIES,
  TICKET_STATUSES,
  type BoardFilters,
  type BoardSide,
  type BoardSort,
} from '@/types/workboard';

/**
 * Longest title fragment the board search accepts.
 *
 * The API declares it (`q: str | None = Query(max_length=200)`), and a bound
 * the producer cannot read is a bound it walks into (ADR-184): a pasted
 * paragraph answered 422 and the board showed a generic failure for what is
 * simply a search too long to be one. The field stops at the same number, and
 * a URL carrying more is TRIMMED rather than sent to be refused.
 */
export const SEARCH_MAX_CHARS = 200;

const SIDES: readonly BoardSide[] = ['all', 'me', 'lia', 'peer'];
const SORTS: readonly BoardSort[] = ['position', 'priority', 'due', 'updated', 'created'];
/** The query keys the filters own; everything else in the URL is left alone. */
const FILTER_KEYS = ['status', 'priority', 'assignee', 'sort', 'overdue', 'q'] as const;

/** A board with nothing narrowed. */
export const DEFAULT_FILTERS: BoardFilters = { assignee: 'all', sort: 'position' };

function isSide(value: string | null): value is BoardSide {
  return value !== null && (SIDES as readonly string[]).includes(value);
}

function isSort(value: string | null): value is BoardSort {
  return value !== null && (SORTS as readonly string[]).includes(value);
}

function isStatus(value: string): boolean {
  return (TICKET_STATUSES as readonly string[]).includes(value);
}

function isPriority(value: string): boolean {
  return (TICKET_PRIORITIES as readonly string[]).includes(value);
}

/**
 * Read the filters a URL carries.
 *
 * Args:
 *   params: The page's query string.
 *
 * Returns:
 *   The filters, every unknown or empty value dropped.
 */
export function filtersFromParams(params: URLSearchParams): BoardFilters {
  const statuses = params.getAll('status').filter(isStatus);
  const priorities = params.getAll('priority').filter(isPriority);
  const assignee = params.get('assignee');
  const sort = params.get('sort');
  const q = params.get('q');
  return {
    assignee: isSide(assignee) ? assignee : 'all',
    sort: isSort(sort) ? sort : 'position',
    ...(statuses.length > 0 ? { status: statuses } : {}),
    ...(priorities.length > 0 ? { priority: priorities } : {}),
    ...(params.get('overdue') === '1' ? { overdue: true } : {}),
    ...(q?.trim() ? { q: q.slice(0, SEARCH_MAX_CHARS) } : {}),
  };
}

/**
 * Write the filters into a query string, keeping what is not theirs.
 *
 * Args:
 *   params: The current query string (`?ticket=` and the like survive).
 *   filters: What the board shows.
 *
 * Returns:
 *   A new query string; the defaults leave no trace.
 */
export function writeFilters(params: URLSearchParams, filters: BoardFilters): URLSearchParams {
  const next = new URLSearchParams(params);
  for (const key of FILTER_KEYS) next.delete(key);
  for (const status of filters.status ?? []) next.append('status', status);
  for (const priority of filters.priority ?? []) next.append('priority', priority);
  if (filters.assignee && filters.assignee !== 'all') next.set('assignee', filters.assignee);
  if (filters.sort && filters.sort !== 'position') next.set('sort', filters.sort);
  if (filters.overdue) next.set('overdue', '1');
  if (filters.q?.trim()) next.set('q', filters.q);
  return next;
}

/**
 * A deep link into the board, narrowed.
 *
 * Args:
 *   lng: The locale segment.
 *   filters: What the board should show on arrival.
 *
 * Returns:
 *   The localized href.
 */
export function boardHref(lng: string, filters: BoardFilters = DEFAULT_FILTERS): string {
  const query = writeFilters(new URLSearchParams(), filters).toString();
  return `/${lng}/dashboard/workboard${query ? `?${query}` : ''}`;
}
