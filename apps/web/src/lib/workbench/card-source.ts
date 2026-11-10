/** Carry a card's opaque source proof only to its currently displayed tool family. */
export const CARD_SOURCE_PARAM = 'card_source';
export const CARD_SOURCE_HEADER = 'X-LIA-Card-Source';
const TOOL_ROUTE = /(?:^|\/)dashboard\/tools\/(mail|calendar|tasks|contacts|files|lights)\/?$/;
const TOOL_ENDPOINT = /^\/workbench\/(mail|calendar|tasks|contacts|files|lights)(?:[/?]|$)/;

/** Read at request time: nothing persists beyond the page that owns the source. */
export function cardSourceHeaders(
  endpoint: string,
  location: Pick<Location, 'pathname' | 'search'> | null = typeof window === 'undefined'
    ? null
    : window.location
): Record<string, string> {
  if (!location) return {};
  const family = TOOL_ROUTE.exec(location.pathname)?.[1];
  if (!family || TOOL_ENDPOINT.exec(endpoint)?.[1] !== family) return {};
  const token = new URLSearchParams(location.search).get(CARD_SOURCE_PARAM);
  return token ? { [CARD_SOURCE_HEADER]: token } : {};
}

/** Direct downloads cannot carry fetch headers; their signed proof uses the same API gate. */
export function cardSourceEndpoint(endpoint: string): string {
  const token = cardSourceHeaders(endpoint)[CARD_SOURCE_HEADER];
  if (!token) return endpoint;
  const url = new URL(endpoint, 'https://lia-card-source.invalid');
  url.searchParams.set(CARD_SOURCE_PARAM, token);
  return `${url.pathname}${url.search}${url.hash}`;
}
