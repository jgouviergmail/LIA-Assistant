/**
 * The spoken commands the wake-word engine runs beside the phrase (ADR-329): a
 * word the person says TO LIA rather than to wake her — « Stop » cuts her voice
 * while she reads an answer aloud. A module of its own, read by the manifest,
 * the engine and the worker's protocol alike.
 */
export const WAKE_COMMANDS = ['stop'] as const;
export type WakeCommand = (typeof WAKE_COMMANDS)[number];
