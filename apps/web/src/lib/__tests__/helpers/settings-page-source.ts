/**
 * Structured read of `settings/page.tsx`, shared by the guards that hold the
 * deep-link / search table against the page it describes.
 *
 * Two tests need the same three primitives — which tab block a component is
 * rendered in, which components a block renders, and which component a section
 * file exports. Duplicating the parsing is how the two would drift into
 * disagreeing about the same file.
 *
 * Not a `.test.ts`, so vitest's `include` never collects it, and it sits under
 * `__tests__/` so coverage excludes it.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/** Absolute path of `apps/web/src`. */
export const SRC = join(process.cwd(), 'src');

/** The settings page, relative to `src/`. */
export const SETTINGS_PAGE = 'app/[lng]/dashboard/settings/page.tsx';

export interface SettingsTabBlock {
  /** Radix tab value the block belongs to. */
  tab: string;
  /** Source between the opening and closing `TabsContent` tags. */
  body: string;
}

/**
 * The page's `TabsContent` blocks, one per rendered tab panel.
 *
 * Sliced to the MATCHING `</TabsContent>`, not to the next opener. The page
 * declares two layouts (a superuser gets a third tab), so between one panel's
 * close and the next panel's open sit `</Tabs>`, the second `<Tabs>` and its
 * `<SettingsTabsBar>` — all of which a next-opener slice would attribute to the
 * preceding tab. Harmless when looking for one known component, wrong when
 * enumerating everything a tab renders.
 *
 * @returns One block per `TabsContent`, in source order.
 * @throws If a block is unterminated or nested, which would silently corrupt
 *   every consumer's view of the page.
 */
export function settingsPageBlocks(): SettingsTabBlock[] {
  const page = readFileSync(join(SRC, SETTINGS_PAGE), 'utf8');
  const opener = /<TabsContent value="([a-z]+)">/g;
  const blocks: SettingsTabBlock[] = [];

  for (const match of page.matchAll(opener)) {
    const from = match.index + match[0].length;
    const to = page.indexOf('</TabsContent>', from);
    if (to === -1) {
      throw new Error(`${SETTINGS_PAGE}: <TabsContent value="${match[1]}"> is never closed`);
    }
    const body = page.slice(from, to);
    if (body.includes('<TabsContent')) {
      throw new Error(
        `${SETTINGS_PAGE}: nested <TabsContent> inside "${match[1]}" — this parser assumes flat panels`
      );
    }
    blocks.push({ tab: match[1], body });
  }

  if (blocks.length === 0) {
    throw new Error(`${SETTINGS_PAGE}: no <TabsContent> found — every scan would pass vacuously`);
  }
  return blocks;
}

/**
 * Component names a block renders, deduplicated.
 *
 * Opening tags only: `</Foo>` cannot match because `/` is not an upper-case
 * letter, so a component is counted once however it is closed.
 *
 * @param body - A block body from {@link settingsPageBlocks}.
 * @returns Component names in first-seen order.
 */
export function componentsRenderedIn(body: string): string[] {
  return [...new Set([...body.matchAll(/<([A-Z][A-Za-z0-9]*)[\s/>]/g)].map(match => match[1]))];
}

/**
 * Which group heading each component sits under, in one tab panel.
 *
 * The page expresses grouping by ORDER, not by nesting: a `<SettingsGroupLabel
 * label={t('settings.groups.security')} …>` is a sibling of the sections it
 * introduces. So the only way to read a section's group is to walk the panel in
 * source order and remember the last heading seen — which is exactly what the
 * reader's eye does.
 *
 * `SettingsGroupLabel` is skipped as a component: its own tag opens before the
 * group marker it carries, and counting it would attribute every section to the
 * heading BEFORE its own.
 *
 * A component rendered before the first heading — the `<Accordion>` that opens
 * every panel — gets `null` rather than an exception. Reporting it is the
 * caller's job: a container legitimately has no group, whereas a SECTION with a
 * null group is a real defect the caller will see as a mismatch.
 *
 * @param body - A block body from {@link settingsPageBlocks}.
 * @returns One entry per rendered component, in source order.
 */
export function componentGroupsIn(
  body: string
): Array<{ component: string; group: string | null }> {
  const markers = [
    ...[...body.matchAll(/settings\.groups\.(\w+)/g)].map(match => ({
      at: match.index,
      group: match[1],
      component: null as string | null,
    })),
    ...[...body.matchAll(/<([A-Z][A-Za-z0-9]*)[\s/>]/g)]
      .filter(match => match[1] !== 'SettingsGroupLabel')
      .map(match => ({ at: match.index, group: null as string | null, component: match[1] })),
  ].sort((left, right) => left.at - right.at);

  const found: Array<{ component: string; group: string | null }> = [];
  let current: string | null = null;
  for (const marker of markers) {
    if (marker.group) {
      current = marker.group;
      continue;
    }
    found.push({ component: marker.component as string, group: current });
  }
  return found;
}

/**
 * The component a section file exports.
 *
 * Read from the SOURCE, never built from the file name: `theme-selector.tsx`
 * exports `ThemeSelector`, and a name derived from the file name yields the
 * needle `<theme-selector `, which matches nothing — an entry checked that way
 * passes vacuously.
 *
 * One exported component per section file is the convention across all of them;
 * anything else is ambiguous and fails loudly rather than silently picking one.
 *
 * @param declaredIn - Path relative to `src/`.
 * @returns The exported component name.
 * @throws If the file exports zero or several components.
 */
export function exportedComponentOf(declaredIn: string): string {
  const source = readFileSync(join(SRC, declaredIn), 'utf8');
  const names = [...source.matchAll(/^export (?:default )?function (\w+)/gm)].map(
    match => match[1]
  );
  if (names.length !== 1) {
    throw new Error(
      `${declaredIn}: expected exactly one exported component, found [${names.join(', ')}]`
    );
  }
  return names[0];
}
