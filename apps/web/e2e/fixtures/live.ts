/**
 * Mint live deadlines when the mocked start request arrives, as the API does.
 * Fixed far-future dates overflow the browser's signed 32-bit timer delay and
 * can expire the session immediately, before its first tool result returns.
 */
export function liveSessionDeadlines(sessionMaxMinutes: number, connectWindowSeconds: number) {
  const now = Date.now();
  const expiresAt = new Date(now + sessionMaxMinutes * 60_000).toISOString();
  return {
    credential_expires_at: expiresAt,
    connect_deadline_at: new Date(now + connectWindowSeconds * 1000).toISOString(),
    expires_at: expiresAt,
  };
}
