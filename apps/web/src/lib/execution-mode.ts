/**
 * How LIA runs a turn (ADR-070), and the automatic choice between the two (ADR-390).
 *
 * The API's `core.constants` is the authority; the tuples below are held to it,
 * literally, by `apps/api/tests/unit/core/test_execution_mode_frontend_sync.py`.
 *
 * Two vocabularies, never confused — the same split as the API's:
 * - a MODE is what a person, a ticket or a routine chooses: `pipeline`, `react`,
 *   or `auto`, where the router picks the engine turn by turn;
 * - an ENGINE is what actually ran: `pipeline` or `react`. Only an engine is
 *   ever shown as having answered (the badge under an automatic answer).
 */

/** The choices, in the order every surface lists them. */
export const EXECUTION_MODES = ['pipeline', 'react', 'auto'] as const;
export type ExecutionMode = (typeof EXECUTION_MODES)[number];

/** The engines that can answer a turn. */
export const EXECUTION_ENGINES = ['pipeline', 'react'] as const;
export type ExecutionEngine = (typeof EXECUTION_ENGINES)[number];

/**
 * What « auto » does on this instance (`GET /auth/me/execution-mode-preference`):
 * it decides turn by turn, or — without a decision provider — always loops, or —
 * without the loop — always plans in the pipeline.
 */
export type AutoModeResolution = 'decided' | 'always_react' | 'always_pipeline';

/** Whether a value names one of the three choices. */
function isExecutionMode(value: unknown): value is ExecutionMode {
  return EXECUTION_MODES.some(mode => mode === value);
}

/** Whether a value names an engine that answered. */
function isExecutionEngine(value: unknown): value is ExecutionEngine {
  return EXECUTION_ENGINES.some(engine => engine === value);
}

/** The person's mode as stored; anything no choice names reads as the pipeline. */
export function executionModeOf(value: unknown): ExecutionMode {
  return isExecutionMode(value) ? value : 'pipeline';
}

/**
 * The engine an AUTOMATIC turn ran on, read from its bubble's metadata.
 *
 * The ONE reader for a live bubble (the `done` chunk) and a reloaded one (the
 * archived row): both carry `execution_engine` under the same key, and only an
 * automatic turn carries it. Anything else — a chosen mode, a requested mode,
 * a value of another shape — names no engine, so nothing is shown.
 */
export function executionEngineOf(
  metadata: Record<string, unknown> | undefined
): ExecutionEngine | null {
  const engine = metadata?.execution_engine;
  return isExecutionEngine(engine) ? engine : null;
}
