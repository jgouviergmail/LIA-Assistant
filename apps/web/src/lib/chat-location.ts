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
