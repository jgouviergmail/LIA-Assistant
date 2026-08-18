/**
 * Source-level primitives shared by the settings-table guards.
 *
 * The master-detail settings page renders FROM the tables, so the former
 * parsing of the page's `TabsContent` layouts (`settingsPageBlocks`,
 * `componentGroupsIn`) is gone with the drift class it guarded against. What
 * remains source-level is the component identity each `declaredIn` names —
 * used by the registry and icon guards to hold the render layer to the table.
 *
 * Not a `.test.ts`, so vitest's `include` never collects it, and it sits under
 * `__tests__/` so coverage excludes it.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Absolute path of `apps/web/src`. */
export const SRC = join(process.cwd(), 'src');

/**
 * The component a section file exports.
 *
 * Read from the SOURCE, never built from the file name: `theme-selector.tsx`
 * exports `ThemeSelector`, and a name derived from the file name yields the
 * needle `<theme-selector `, which matches nothing — an entry checked that way
 * passes vacuously.
 *
 * One exported component per section file is the convention; when a file also
 * exports a helper component for ITS OWN tests (`AdminLLMPricingSection`
 * exports `ModelPricingModal`), the section is the export named after the
 * file — checked against the source, so a rename still fails loudly instead of
 * silently picking one of several.
 *
 * @param declaredIn - Path relative to `src/`.
 * @returns The exported component name.
 * @throws If the file exports zero components, or several with none matching
 *   the file name.
 */
export function exportedComponentOf(declaredIn: string): string {
  const source = readFileSync(join(SRC, declaredIn), 'utf8');
  const names = [...source.matchAll(/^export (?:default )?function (\w+)/gm)].map(
    match => match[1]
  );
  if (names.length === 1) return names[0];
  const basename = declaredIn.slice(declaredIn.lastIndexOf('/') + 1).replace(/\.tsx?$/, '');
  const matching = names.filter(name => name === basename);
  if (matching.length === 1) return matching[0];
  throw new Error(
    `${declaredIn}: expected exactly one exported component (or one named after the file), found [${names.join(', ')}]`
  );
}
