/**
 * Guard: one copy of each Radix layer primitive that keeps its state in its module.
 *
 * A focus trap pauses the trap beneath it through a stack held by its MODULE
 * (`@radix-ui/react-focus-scope`); the same holds for the layer stack and the body
 * pointer lock (`react-dismissable-layer`) and for the edge focus guards
 * (`react-focus-guards`). Two versions in the tree are two modules that never see each
 * other. Measured 2026-11-13: the `Select` (2.3.8, focus-scope 1.2.0) inside a `Dialog`
 * (1.3.1, focus-scope 1.3.1) each trapped the focus on its own, and as soon as the
 * selection bubble had paused the dialog's trap the page froze in a focus() ping-pong
 * (4 000 calls in a few milliseconds), in production too. Every Radix primitive that
 * renders a layer must therefore come from releases sharing these three modules.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

const LOCKFILE = path.resolve(__dirname, '../../../../../..', 'pnpm-lock.yaml');
const SINGLETONS = [
  '@radix-ui/react-focus-scope',
  '@radix-ui/react-dismissable-layer',
  '@radix-ui/react-focus-guards',
] as const;

/** The `packages:` section: one entry per resolved version, before any peer suffix. */
function resolvedVersions(lock: string, name: string): string[] {
  const start = lock.indexOf('\npackages:\n');
  const end = lock.indexOf('\nsnapshots:\n');
  if (start < 0 || end < start) throw new Error('unexpected pnpm-lock.yaml layout');
  const section = lock.slice(start, end);
  const escaped = name.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');
  const entry = new RegExp(`^ {2}'?${escaped}@([0-9][^'(:]*)'?:$`, 'gm');
  return Array.from(section.matchAll(entry), match => match[1]);
}

describe('Radix layer primitives', () => {
  const lock = readFileSync(LOCKFILE, 'utf8');

  it.each(SINGLETONS)('%s resolves to exactly one version', name => {
    const versions = resolvedVersions(lock, name);
    // Present at all: a guard that finds nothing proves nothing.
    expect(versions.length).toBeGreaterThan(0);
    expect(versions).toHaveLength(1);
  });
});
