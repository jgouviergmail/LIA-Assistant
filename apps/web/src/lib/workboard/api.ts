/**
 * Typed calls of the workboard API (ADR-276) — one place for every endpoint.
 *
 * The hook calls these; nothing else spells a `/workboard/...` path. The
 * board's two multi-valued filters (`status`, `priority`) travel as REPEATED
 * query parameters, which is what `list[str] = Query(...)` reads server-side —
 * `apiClient` learnt that shape once so no caller hand-builds a query string.
 */
import { apiClient, type QueryParamValue } from '@/lib/api-client';
import type {
  BoardFilters,
  BoardPage,
  BoardSummary,
  CategoryCreateBody,
  CategoryDeleteResult,
  CategoryList,
  CategoryRow,
  CategoryUpdateBody,
  CommentRow,
  DeleteResult,
  MoveBody,
  NeedsMePage,
  TicketCreateBody,
  TicketDetail,
  TicketRow,
  TicketUpdateBody,
} from '@/types/workboard';

const BASE = '/workboard';

/** What the tickets must BE to be on the board: column, rank, holder, lateness, words. */
function narrowingParams(filters: BoardFilters): Record<string, QueryParamValue> {
  const params: Record<string, QueryParamValue> = {};
  if (filters.status?.length) params.status = filters.status;
  if (filters.priority?.length) params.priority = filters.priority;
  if (filters.assignee) params.assignee = filters.assignee;
  if (filters.overdue) params.overdue = true;
  if (filters.due_before) params.due_before = filters.due_before;
  if (filters.q?.trim()) params.q = filters.q.trim();
  if (filters.closed_days !== undefined) params.closed_days = filters.closed_days;
  return params;
}

/**
 * Which lanes: categories, and what is not filed yet.
 *
 * Two halves that WIDEN each other server-side — « Home, and what is not
 * filed » — each sent only when it says something.
 */
function laneParams(filters: BoardFilters): Record<string, QueryParamValue> {
  const params: Record<string, QueryParamValue> = {};
  if (filters.category?.length) params.category = filters.category;
  if (filters.uncategorized) params.uncategorized = true;
  return params;
}

/** How the answer is ordered and paged — it changes the page, never the set. */
function pagingParams(filters: BoardFilters): Record<string, QueryParamValue> {
  const params: Record<string, QueryParamValue> = {};
  if (filters.sort) params.sort = filters.sort;
  if (filters.limit !== undefined) params.limit = filters.limit;
  if (filters.offset !== undefined) params.offset = filters.offset;
  return params;
}

/**
 * Turn the board's filters into query parameters.
 *
 * Absent and EMPTY values are dropped rather than sent: an unset filter must
 * cost no parameter, and `?q=` is not the same request as no `q` at all —
 * server-side it is an empty needle the folding would match everything with.
 *
 * @param filters - What the reader asked the board for.
 * @returns The parameters, ready for `apiClient`.
 */
export function boardParams(filters: BoardFilters): Record<string, QueryParamValue> {
  return { ...narrowingParams(filters), ...laneParams(filters), ...pagingParams(filters) };
}

export const workboardApi = {
  board: (filters: BoardFilters) =>
    apiClient.get<BoardPage>(`${BASE}/tickets`, { params: boardParams(filters) }),
  summary: () => apiClient.get<BoardSummary>(`${BASE}/summary`),
  needsMe: (limit: number, offset: number) =>
    apiClient.get<NeedsMePage>(`${BASE}/needs-me`, { params: { limit, offset } }),
  detail: (id: string) => apiClient.get<TicketDetail>(`${BASE}/tickets/${id}`),
  create: (body: TicketCreateBody) => apiClient.post<TicketRow>(`${BASE}/tickets`, body),
  update: (id: string, body: TicketUpdateBody) =>
    apiClient.patch<TicketRow>(`${BASE}/tickets/${id}`, body),
  move: (id: string, body: MoveBody) =>
    apiClient.post<TicketRow>(`${BASE}/tickets/${id}/move`, body),
  runNow: (id: string) => apiClient.post<TicketRow>(`${BASE}/tickets/${id}/run-now`, {}),
  comment: (id: string, body: string) =>
    apiClient.post<CommentRow>(`${BASE}/tickets/${id}/comments`, { body }),
  remove: (id: string) => apiClient.delete<DeleteResult>(`${BASE}/tickets/${id}`),
  // Categories — the lanes of the board. Deleting one deletes no ticket: its
  // tickets go back to the unfiled lane, and the answer says how many.
  categories: () => apiClient.get<CategoryList>(`${BASE}/categories`),
  createCategory: (body: CategoryCreateBody) =>
    apiClient.post<CategoryRow>(`${BASE}/categories`, body),
  updateCategory: (id: string, body: CategoryUpdateBody) =>
    apiClient.patch<CategoryRow>(`${BASE}/categories/${id}`, body),
  removeCategory: (id: string) =>
    apiClient.delete<CategoryDeleteResult>(`${BASE}/categories/${id}`),
};
