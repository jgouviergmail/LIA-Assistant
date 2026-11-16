/** One door for local chat URL changes, preserving the hash and the rest of the query. */
export function replaceChatQuery(params: URLSearchParams): void {
  const query = params.toString();
  const { pathname, hash } = window.location;
  window.history.replaceState(null, '', `${pathname}${query ? `?${query}` : ''}${hash}`);
}

/** A manual switch never transfers one-shot requests from the previous discussion. */
export function replaceChatDiscussion(id: string | null): void {
  const params = new URLSearchParams(window.location.search);
  if (params.get('conversation') === id && !params.has('conversation_revision')) return;
  for (const key of [
    'intent',
    'capability',
    'subject',
    'iid',
    'draft',
    'voice',
    'attach',
    'conversation_revision',
  ]) {
    params.delete(key);
  }
  if (id === null) params.delete('conversation');
  else params.set('conversation', id);
  replaceChatQuery(params);
}

const CHAT_PATH = /^\/(?:(?:fr|en|es|de|it|zh)\/)?dashboard\/chat\/?$/;
const DISCUSSION_ID = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i;

/**
 * The annex the chat page shows, read where the chat reads it: its URL.
 *
 * What an act begun from anywhere in the dashboard names as its discussion (a
 * meeting recorded from the header while an annex is open, ADR-378 amendment
 * 2026-11-14): its return comes back there. Main carries no parameter, and
 * any other page shows no discussion.
 *
 * @param location - The page's `pathname` and `search`.
 * @returns The annex's id, or `null`.
 */
export function chatDiscussionOnScreen(location: {
  pathname: string;
  search: string;
}): string | null {
  if (!CHAT_PATH.test(location.pathname)) return null;
  const id = new URLSearchParams(location.search).get('conversation');
  return id !== null && DISCUSSION_ID.test(id) ? id.toLowerCase() : null;
}
