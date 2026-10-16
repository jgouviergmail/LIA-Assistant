/** One bounded, one-based list page contract shared by the list and its detail. */
export function meetingListPage(raw: string | null): number {
  if (!raw || !/^[1-9]\d{0,5}$/.test(raw)) return 1;
  const page = Number(raw);
  return page <= 100000 ? page : 1;
}
