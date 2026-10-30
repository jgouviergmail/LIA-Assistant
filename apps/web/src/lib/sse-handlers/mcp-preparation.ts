/**
 * Personal-server preparation notices (spec 2026-10-21 §5.6, M5).
 *
 * While a turn waits for the person's own MCP servers, the backend streams
 * `execution_step` chunks with `step_type: "mcp_preparation"`:
 *
 * - the generic progress step (`i18n_key: "mcp_preparation"`, with its emoji)
 *   is NOT handled here — the step accumulator draws it like every step;
 * - a server still discovering past the notice delay sends « slow », then its
 *   terminal phase (ready, failed, deferred).
 *
 * One toast per server per run (`mcp-prep:{run}:{server}`), updated in place
 * by its terminal phase and never raised again once settled — a replay or a
 * reconnection re-delivers chunks the person already saw. Past three slow
 * servers the run speaks with ONE grouped toast, which still NAMES them — the
 * first few, then how many others. A run that ends (done or
 * error) closes what it still shows and is forgotten. The name is the person's own
 * text: a bounded string (never markup), isolated so a right-to-left name
 * cannot reorder the sentence around it. No action button: the toast informs,
 * the settings are where a server is turned off.
 */

import { toast } from 'sonner';

import type { ChatStreamChunk } from '@/types/chat';

import type { SSEHandlerContext } from './types';

export const MCP_PREPARATION_STEP_TYPE = 'mcp_preparation';

/** The longest server name a notice shows; longer ones end with an ellipsis. */
export const MCP_PREPARATION_NAME_MAX_CHARS = 60;

/** More slow servers than this in one run speak through one grouped toast. */
const GROUP_THRESHOLD = 3;

/** How many names a grouped toast shows before « and N others ». */
const GROUP_NAMES_SHOWN = 3;

const SETTLED_DURATION_MS = 4000;
const ISSUE_DURATION_MS = 8000;

/** Unicode first-strong isolate and its pop: the name keeps its own direction. */
const FSI = '⁨';
const PDI = '⁩';

type ServerKey =
  | 'chat.mcp_preparation.slow'
  | 'chat.mcp_preparation.ready'
  | 'chat.mcp_preparation.failed'
  | 'chat.mcp_preparation.deferred';

const SERVER_KEYS = new Set<string>([
  'chat.mcp_preparation.slow',
  'chat.mcp_preparation.ready',
  'chat.mcp_preparation.failed',
  'chat.mcp_preparation.deferred',
]);

interface ServerNotice {
  key: ServerKey;
  server: string;
  name: string;
}

interface RunNotices {
  /** Servers currently slow: id → displayed name. */
  slow: Map<string, string>;
  /** Servers whose notice ended, never raised again. */
  settled: Set<string>;
  /** Grouped servers left out of the run (deferred or failed), as displayed. */
  leftOut: string[];
  grouped: boolean;
}

const runs = new Map<string, RunNotices>();

function runOf(id: string): RunNotices {
  let state = runs.get(id);
  if (!state) {
    state = { slow: new Map(), settled: new Set(), leftOut: [], grouped: false };
    runs.set(id, state);
  }
  return state;
}

const toastId = (run: string, server: string) => `mcp-prep:${run}:${server}`;

/** The name as a notice shows it: bounded, direction-isolated, never markup. */
export function displayedServerName(name: string): string {
  const bounded =
    name.length > MCP_PREPARATION_NAME_MAX_CHARS
      ? `${name.slice(0, MCP_PREPARATION_NAME_MAX_CHARS)}…`
      : name;
  return `${FSI}${bounded}${PDI}`;
}

function parseServerNotice(metadata: Record<string, unknown>): ServerNotice | null {
  const { i18n_key: key, server_key: server, server_name: name } = metadata;
  if (typeof key !== 'string' || !SERVER_KEYS.has(key)) return null;
  if (typeof server !== 'string' || !server || typeof name !== 'string') return null;
  return { key: key as ServerKey, server, name };
}

/**
 * Intercept a preparation chunk; the generic progress step is left to the accumulator.
 *
 * @returns True when the chunk was consumed (a server notice, even malformed).
 */
export function handleMcpPreparationStep(
  chunk: ChatStreamChunk,
  context: SSEHandlerContext
): boolean {
  const metadata = chunk.metadata as Record<string, unknown> | undefined;
  if (metadata?.step_type !== MCP_PREPARATION_STEP_TYPE) return false;
  if (metadata.i18n_key === MCP_PREPARATION_STEP_TYPE) return false;
  const notice = parseServerNotice(metadata);
  if (notice) applyNotice(notice, context);
  return true;
}

function applyNotice(notice: ServerNotice, context: SSEHandlerContext): void {
  const run = context.assistantMessageId;
  const state = runOf(run);
  if (state.settled.has(notice.server)) return;
  if (notice.key === 'chat.mcp_preparation.slow') {
    // A replayed « slow » is remembered, not shown: its terminal phase may follow live.
    state.slow.set(notice.server, displayedServerName(notice.name));
    if (!context.isReplay) showSlow(run, state, notice.server, context);
    return;
  }
  const name = state.slow.get(notice.server);
  if (name === undefined) return; // never slow: nothing was announced
  state.slow.delete(notice.server);
  state.settled.add(notice.server);
  if (context.isReplay) {
    toast.dismiss(toastId(run, notice.server));
  } else if (state.grouped) {
    settleGrouped(run, state, notice.key, name, context);
  } else {
    settleOne(run, notice, name, context);
  }
}

function showSlow(run: string, state: RunNotices, server: string, context: SSEHandlerContext) {
  if (!state.grouped && state.slow.size > GROUP_THRESHOLD) {
    state.grouped = true;
    for (const other of state.slow.keys()) {
      if (other !== server) toast.dismiss(toastId(run, other));
    }
  }
  if (state.grouped) {
    toast(slowGroupMessage(state, context), { id: toastId(run, 'group'), duration: Infinity });
    return;
  }
  toast(context.t('chat.mcp_preparation.slow', { name: state.slow.get(server) }), {
    id: toastId(run, server),
    duration: Infinity,
  });
}

function settleOne(
  run: string,
  notice: ServerNotice,
  name: string,
  context: SSEHandlerContext
): void {
  const message = context.t(notice.key, { name });
  const options = { id: toastId(run, notice.server) };
  if (notice.key === 'chat.mcp_preparation.ready') {
    toast.success(message, { ...options, duration: SETTLED_DURATION_MS });
  } else {
    toast.warning(message, { ...options, duration: ISSUE_DURATION_MS });
  }
}

/**
 * The names a grouped toast shows: the first few in the language's own quotes, then
 * « N others ». The list itself is joined by the locale (``{{names, list}}``).
 */
function namedList(names: string[], context: SSEHandlerContext): string[] {
  const shown = names
    .slice(0, GROUP_NAMES_SHOWN)
    .map(name => context.t('chat.mcp_preparation.quoted_name', { name }));
  const others = names.length - shown.length;
  return others > 0
    ? [...shown, context.t('chat.mcp_preparation.others', { count: others })]
    : shown;
}

function slowGroupMessage(state: RunNotices, context: SSEHandlerContext): string {
  const names = [...state.slow.values()];
  return context.t('chat.mcp_preparation.slow_group', {
    count: names.length,
    names: namedList(names, context),
  });
}

function settleGrouped(
  run: string,
  state: RunNotices,
  key: ServerKey,
  name: string,
  context: SSEHandlerContext
): void {
  if (key !== 'chat.mcp_preparation.ready') state.leftOut.push(name);
  const id = toastId(run, 'group');
  if (state.slow.size > 0) {
    toast(slowGroupMessage(state, context), { id, duration: Infinity });
  } else if (state.leftOut.length > 0) {
    const message = context.t('chat.mcp_preparation.deferred_group', {
      count: state.leftOut.length,
      names: namedList(state.leftOut, context),
    });
    toast.warning(message, { id, duration: ISSUE_DURATION_MS });
  } else {
    toast.dismiss(id);
  }
}

/**
 * A run that ended says nothing more: close the notices it still shows and forget it.
 *
 * A notice of a server still « slow » never times out by itself, and its terminal phase
 * never comes once the run stopped; a settled notice keeps its own short life.
 */
export function endMcpPreparationRun(run: string): void {
  const state = runs.get(run);
  if (!state) return;
  for (const server of state.slow.keys()) toast.dismiss(toastId(run, server));
  if (state.grouped && state.slow.size > 0) toast.dismiss(toastId(run, 'group'));
  runs.delete(run);
}

/** Forget every run's notices and close their toasts — an account switch or a sign-out. */
export function resetMcpPreparationNotices(): void {
  for (const [run, state] of runs) {
    for (const server of state.slow.keys()) toast.dismiss(toastId(run, server));
    if (state.grouped) toast.dismiss(toastId(run, 'group'));
  }
  runs.clear();
}
