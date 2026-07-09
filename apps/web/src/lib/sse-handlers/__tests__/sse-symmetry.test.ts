/**
 * SSE contract symmetry — backend event types vs frontend handlers.
 *
 * The backend SSE contract is the `type: Literal[...]` block of
 * apps/api/src/domains/agents/api/schemas.py (ChatStreamChunk). Pydantic
 * enforces it at runtime for every emission path, including the dynamic
 * LangGraph custom-mode passthrough — nothing outside this list can reach
 * the wire.
 *
 * Guarantee enforced here: every backend contract type is either handled by
 * the frontend (SSE_HANDLERS) or EXPLICITLY acknowledged as unhandled below.
 * Adding a new type backend-side therefore forces a conscious frontend
 * decision instead of a silent `sse_unknown_event_type` drop (which is how
 * `hitl_streaming_fallback` went unnoticed).
 *
 * A companion sync test re-parses the backend file when it is accessible
 * (host checkouts and CI; the web dev container only mounts apps/web) so the
 * pinned list below cannot drift from the real contract.
 */

import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';

import { getRegisteredSSEHandlers, hasSSEHandler } from '@/lib/sse-handlers';

/**
 * Pinned copy of the backend ChatStreamChunk `type` Literal.
 * Source of truth: apps/api/src/domains/agents/api/schemas.py
 * (kept in sync by the "pinned contract matches backend" test below).
 */
const BACKEND_CONTRACT_TYPES = [
  'token',
  'content_replacement',
  'router_decision',
  'execution_step',
  'registry_update',
  'debug_metrics',
  'debug_metrics_update',
  'hitl_interrupt',
  'hitl_interrupt_metadata',
  'hitl_question_token',
  'hitl_interrupt_complete',
  'hitl_streaming_fallback',
  'voice_comment_start',
  'voice_audio_chunk',
  'voice_complete',
  'voice_error',
  'browser_screenshot',
  'error',
  'done',
] as const;

/**
 * Contract types with NO frontend handler — each entry must be a conscious,
 * documented decision. Empty since the 2026-07 cleanup: the dead contract
 * entries were removed from the backend Literal and hitl_streaming_fallback
 * got a dedicated awareness handler. Add an entry here ONLY with a written
 * justification for why the type is deliberately not handled.
 */
const ACKNOWLEDGED_UNHANDLED = [] as const;

function parseBackendLiteral(source: string): string[] {
  const literalBlock = source.match(/type:\s*Literal\[([\s\S]*?)\]\s*=\s*Field/);
  if (!literalBlock) {
    throw new Error('Could not locate the ChatStreamChunk type Literal in schemas.py');
  }
  // Strip Python end-of-line comments first: they may quote type names
  // (e.g. `# ... (not "error")`) that must not count as contract entries.
  const withoutComments = literalBlock[1]
    .split('\n')
    .map(line => line.replace(/#.*$/, ''))
    .join('\n');
  return [...withoutComments.matchAll(/"([a-z_]+)"/g)].map(m => m[1]);
}

describe('SSE contract symmetry', () => {
  it('every backend contract type is handled or explicitly acknowledged as unhandled', () => {
    const unaccounted = BACKEND_CONTRACT_TYPES.filter(
      type => !hasSSEHandler(type) && !(ACKNOWLEDGED_UNHANDLED as readonly string[]).includes(type)
    );

    expect(
      unaccounted,
      `Backend SSE type(s) without a frontend handler: ${unaccounted.join(', ')}. ` +
        'Either register a handler in SSE_HANDLERS (lib/sse-handlers/index.ts) or ' +
        'add the type to ACKNOWLEDGED_UNHANDLED with a documented justification.'
    ).toEqual([]);
  });

  it('no type is both handled and acknowledged as unhandled (list hygiene)', () => {
    const contradictions = ACKNOWLEDGED_UNHANDLED.filter(type => hasSSEHandler(type));

    expect(contradictions).toEqual([]);
  });

  it('every registered handler targets a type that exists in the backend contract', () => {
    const phantoms = getRegisteredSSEHandlers().filter(
      type => !(BACKEND_CONTRACT_TYPES as readonly string[]).includes(type)
    );

    expect(
      phantoms,
      `Frontend handler(s) for types absent from the backend contract: ${phantoms.join(', ')}`
    ).toEqual([]);
  });

  it('hasSSEHandler answers consistently with the registered handler list', () => {
    for (const type of getRegisteredSSEHandlers()) {
      expect(hasSSEHandler(type)).toBe(true);
    }
    expect(hasSSEHandler('definitely_not_a_type')).toBe(false);
  });
});

describe('SSE contract sync with backend source', () => {
  // apps/web → apps/api. Absent inside the web dev container (only apps/web
  // is mounted) — the sync check is enforced on host checkouts and in CI.
  const backendSchemaPath = path.resolve(process.cwd(), '../api/src/domains/agents/api/schemas.py');

  it.skipIf(!fs.existsSync(backendSchemaPath))(
    'pinned contract matches the backend Literal (schemas.py)',
    () => {
      const source = fs.readFileSync(backendSchemaPath, 'utf-8');
      const backendTypes = parseBackendLiteral(source);

      expect([...backendTypes].sort()).toEqual([...BACKEND_CONTRACT_TYPES].sort());
    }
  );
});
