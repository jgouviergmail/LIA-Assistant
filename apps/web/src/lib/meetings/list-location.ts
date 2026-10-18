/** One bounded, one-based list page contract shared by the list and its detail. */
export function meetingListPage(raw: string | null): number {
  if (!raw || !/^[1-9]\d{0,5}$/.test(raw)) return 1;
  const page = Number(raw);
  return page <= 100000 ? page : 1;
}

/** Input from a deep link follows the API's bounded literal-query contract. */
export function meetingListQuery(raw: string | null): string {
  return (raw ?? '').replace(/\0/g, '').slice(0, 200).trim();
}

/** Shared by list history, detail links and the detail's return destination. */
export function meetingListSearch(page: number, query: string): string {
  const params = new URLSearchParams();
  if (page > 1) params.set('page', String(page));
  const q = meetingListQuery(query);
  if (q) params.set('q', q);
  return params.size ? `?${params}` : '';
}
