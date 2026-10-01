/**
 * What the wake-word worker does with each message (ADR-329), apart from the
 * worker global so it is tested without one.
 *
 * `load` fetches and parses the language's manifest, builds the verified
 * runtime and a fresh engine, and answers `ready` with the phrase and the
 * spoken commands — or `failed` with the reason. `audio` feeds the engine
 * (silently ignored before `ready`: a capture may start before the models are
 * in), and every detection — of the phrase or of a command — is posted.
 * `reset` restarts the stream, as after a pause in the capture.
 */
import { WAKE_COMMANDS, type WakeCommand } from './commands';
import { WakeWordEngine, type WakeWordRuntime } from './engine';
import { ManifestError, manifestUrl, parseManifest, type WakeManifest } from './manifest';
import { IntegrityError } from './ort-runtime';
import { DetectionPolicy } from './policy';
import type { FromWorker, ToWorker, WakeWordFailure } from './protocol';

export interface WorkerDeps {
  post: (message: FromWorker) => void;
  fetchJson: (url: string) => Promise<unknown>;
  createRuntime: (manifest: WakeManifest) => Promise<WakeWordRuntime>;
}

/** One fresh policy per command the manifest ships, each under its own measured options. */
function commandPolicies(manifest: WakeManifest): Partial<Record<WakeCommand, DetectionPolicy>> {
  const policies: Partial<Record<WakeCommand, DetectionPolicy>> = {};
  for (const command of WAKE_COMMANDS) {
    const model = manifest.commands[command];
    if (model) policies[command] = new DetectionPolicy(model.policy);
  }
  return policies;
}

function failureOf(error: unknown): WakeWordFailure {
  if (error instanceof ManifestError) return 'manifest';
  if (error instanceof IntegrityError) return 'integrity';
  return 'runtime';
}

export function createWorkerHandler(deps: WorkerDeps): (message: ToWorker) => Promise<void> {
  let engine: WakeWordEngine | null = null;
  // A newer `load` supersedes an older one still in flight.
  let generation = 0;

  return async message => {
    if (message.type === 'load') {
      const current = ++generation;
      engine = null;
      try {
        const manifest = parseManifest(
          await deps.fetchJson(manifestUrl(message.language)),
          message.language
        );
        const runtime = await deps.createRuntime(manifest);
        if (current !== generation) return;
        const commands = commandPolicies(manifest);
        engine = new WakeWordEngine(runtime, new DetectionPolicy(manifest.policy), commands);
        deps.post({
          type: 'ready',
          phrase: manifest.phrase,
          commands: WAKE_COMMANDS.filter(command => commands[command]),
        });
      } catch (error) {
        if (current === generation) deps.post({ type: 'failed', reason: failureOf(error) });
      }
      return;
    }
    if (message.type === 'reset') {
      engine?.reset();
      return;
    }
    const current = engine;
    if (!current) return;
    try {
      const results = await current.push(new Int16Array(message.samples));
      // A newer load replaced this engine while it scored: its audio is the
      // previous model's, and nothing it found is reported.
      if (engine !== current) return;
      for (const result of results) {
        if (result.detected) deps.post({ type: 'detected', score: result.score });
        for (const command of result.commands) deps.post({ type: 'command', command });
      }
    } catch {
      if (engine !== current) return;
      engine = null;
      deps.post({ type: 'failed', reason: 'runtime' });
    }
  };
}
