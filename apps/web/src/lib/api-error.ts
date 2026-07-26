/**
 * Reading the detail a failed API call carries.
 *
 * The backend answers every error with FastAPI's envelope — `{"detail": ...}`
 * — and both HTTP clients surface it the same way: `ApiError` (browser,
 * `@/lib/api-client`) and `ServerApiError` (Server Actions, `@/lib/api-server`)
 * both expose the parsed body on `.data`. Neither wraps it in a `.response`
 * field: that shape belongs to axios, which this app dropped for native fetch.
 *
 * This module is the single place that knows the envelope. It duck-types on
 * `.data` rather than importing either error class, so a Server Action can use
 * it without pulling browser-only code into the server bundle.
 *
 * `detail` has three shapes on the wire:
 * - a plain string — the common case (`ResourceNotFoundError`, `ConflictError`…);
 * - `{"errors": [{"field": ..., "message": ...}]}` — `ConnectorValidationError`;
 * - a list of `{"loc": ..., "msg": ...}` — Pydantic/`StructuredValidationError`.
 *
 * @module api-error
 */

/** Narrow to an indexable object (arrays included — callers check first). */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** Human-readable text of one error entry, whatever key the layer used. */
function entryMessage(entry: unknown): string | undefined {
  if (typeof entry === 'string') {
    return entry.trim() || undefined;
  }
  if (!isRecord(entry)) {
    return undefined;
  }
  const candidate = entry.message ?? entry.msg;
  return typeof candidate === 'string' ? candidate.trim() || undefined : undefined;
}

/** Join the entries that carry a message; `undefined` when none does. */
function joinEntries(entries: readonly unknown[]): string | undefined {
  const messages = entries
    .map(entryMessage)
    .filter((message): message is string => message !== undefined);
  return messages.length > 0 ? messages.join(', ') : undefined;
}

/**
 * Read the human-readable reason out of a parsed error BODY.
 *
 * Used by both HTTP clients to build `ApiError.message`: a `detail` that is a
 * Pydantic list would otherwise be handed to `new Error(...)`, which stringifies
 * it to `[object Object]` — the literal text a user then reads on a refused
 * form.
 *
 * @param data - Parsed response body (anything the server sent).
 * @returns The reason, or `undefined` when the body carries none.
 */
export function readErrorDetail(data: unknown): string | undefined {
  // An Error is not a response body. `ServerApiError` stores the original
  // exception on `.data` when the transport itself failed, and reading its
  // `.message` would surface "fetch failed" to the user instead of the
  // caller's translated fallback.
  if (!isRecord(data) || data instanceof Error) {
    return undefined;
  }

  // `message` first: a few endpoints answer with that key instead of `detail`.
  if (typeof data.message === 'string' && data.message.trim()) {
    return data.message.trim();
  }

  const detail = data.detail;

  if (typeof detail === 'string') {
    return detail.trim() || undefined;
  }
  if (Array.isArray(detail)) {
    return joinEntries(detail);
  }
  if (isRecord(detail) && Array.isArray(detail.errors)) {
    return joinEntries(detail.errors);
  }

  return undefined;
}

/**
 * Extract the server-provided error text from a rejected API call.
 *
 * Returns `undefined` — never a fabricated string — when the failure carries
 * no usable detail (network error, HTML error page, empty body). Call sites
 * keep their own translated fallback:
 *
 * ```ts
 * toast.error(getApiErrorDetail(error) ?? t('settings.connectors.error'));
 * ```
 *
 * @param error - Anything a `catch` block received.
 * @returns The detail text, or `undefined` when there is none.
 */
export function getApiErrorDetail(error: unknown): string | undefined {
  if (!isRecord(error)) {
    return undefined;
  }

  return readErrorDetail((error as { data?: unknown }).data);
}
