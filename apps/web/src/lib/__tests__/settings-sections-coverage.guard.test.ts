/**
 * Settings search coverage guard — the index cannot fall behind the page.
 *
 * ## Why this exists
 *
 * `settings-sections.test.ts` checks the table against the components it names:
 * every entry points at a real file, in the right tab, declaring the accordion
 * value it claims. That is the FORWARD direction, and it is blind to the one
 * that actually bites — a section the page renders and the table never heard
 * of. Such a section is unreachable by deep link and, since the search index is
 * keyed off the same table, invisible to search. The user types its exact title
 * and gets "no result" about a section sitting two screens below.
 *
 * That was the state before this lot: thirteen user-facing sections (Language,
 * Appearance, Timezone, Font, Display mode, Strong authentication, My devices,
 * Export my data, Image generation, Open loops, Application MCP, Debug panel,
 * Consumption export) were rendered by the page and absent from the table.
 * Nothing failed, because nothing looked in this direction.
 *
 * ## What it checks
 *
 * Every component the page renders inside a tab panel is CLASSIFIED — indexed,
 * or explicitly excluded with a written reason. There is no third outcome, so a
 * new section forces a decision at the moment it is added.
 *
 * The two exclusion lists are anti-rot: an entry that stops being rendered
 * fails, so they cannot silently accumulate. `ADMIN_TAB_DEFERRED` is the
 * enumerated scope of the phase-2 extension — emptying it IS phase 2.
 */

import { describe, it, expect } from 'vitest';

import { SETTINGS_SECTIONS } from '../settings-sections';
import {
  componentsRenderedIn,
  exportedComponentOf,
  settingsPageBlocks,
  SETTINGS_PAGE,
} from './helpers/settings-page-source';

/** Tab panels that must reach the search index in full. */
const INDEXED_TABS = ['preferences', 'features'] as const;

/**
 * Rendered inside a tab panel without being a settings section.
 *
 * Each is structural: a container, a wrapper or a shortcut. None declares an
 * accordion value, so none can be a search destination.
 */
const STRUCTURAL: Readonly<Record<string, string>> = {
  Accordion: 'the accordion container the sections live in',
  FeatureErrorBoundary: 'error boundary wrapping a section — renders its child or a fallback',
  CatalogueInvalidationProvider: 'context provider around the pricing/config admin sections',
  SettingsGroupLabel: 'group heading between sections, not a section',
  PortraitShortcut:
    'shortcut card that deep-links INTO the journals section; declares no accordion value of its own',
};

/**
 * Administration-tab sections deliberately left out of the search index.
 *
 * Phase-1 scope decision: the index covers the two USER tabs. Listing them one
 * by one is the honest form of that deferral — "the admin tab is not indexed"
 * as prose would drift the moment a section is added there.
 *
 * A superuser is told so in the UI (`settings.search.admin_not_indexed`).
 * Phase 2 = move these into `SETTINGS_SECTIONS` and empty this list.
 */
const ADMIN_TAB_DEFERRED: Readonly<Record<string, string>> = {
  AdminUsersSection: 'admin: user administration',
  AdminUsageLimitsSection: 'admin: usage limits',
  AdminConsumptionExportSection: 'admin: consumption export (wraps ConsumptionExportSection)',
  AdminBroadcastSection: 'admin: broadcast message',
  AdminConnectorsSection: 'admin: connector administration',
  AdminLLMPricingSection: 'admin: LLM text pricing',
  AdminGoogleApiPricingSection: 'admin: Google API pricing',
  AdminImagePricingSection: 'admin: LLM image pricing',
  AdminLLMConfigSection: 'admin: LLM configuration',
  AdminPersonalitiesSection: 'admin: personality administration',
  AdminSkillsSection: 'admin: system skills',
  AdminRAGSpacesSection: 'admin: system RAG administration',
  AdminDebugSettingsSection: 'admin: debug panel settings',
};

const BLOCKS = settingsPageBlocks();
const INDEXED_COMPONENTS = new Set(
  Object.values(SETTINGS_SECTIONS).map(target => exportedComponentOf(target.declaredIn))
);

/** Component name → the tabs whose panels render it. */
const RENDERED = new Map<string, Set<string>>();
for (const block of BLOCKS) {
  for (const component of componentsRenderedIn(block.body)) {
    const tabs = RENDERED.get(component) ?? new Set<string>();
    tabs.add(block.tab);
    RENDERED.set(component, tabs);
  }
}

describe('settings search coverage', () => {
  it('parses both layouts of the page', () => {
    // The page renders two layouts (superuser gets a third tab), so every tab
    // value must appear — a rename that dropped one would shrink the scanned
    // surface without failing anything else.
    expect(new Set(BLOCKS.map(block => block.tab))).toEqual(
      new Set(['preferences', 'features', 'administration'])
    );
    expect(BLOCKS.length, 'two layouts = five panels').toBe(5);
  });

  it('indexes every section of the user-facing tabs', () => {
    // A Set, not an array: the page declares the same panel twice (one layout
    // per superuser flag), so an unindexed section would otherwise be reported
    // once per layout and read as two distinct defects.
    const unindexedSet = new Set<string>();
    for (const block of BLOCKS) {
      if (!INDEXED_TABS.includes(block.tab as (typeof INDEXED_TABS)[number])) continue;
      for (const component of componentsRenderedIn(block.body)) {
        if (INDEXED_COMPONENTS.has(component)) continue;
        if (component in STRUCTURAL) continue;
        // Deliberately NOT accepting ADMIN_TAB_DEFERRED here: an admin section
        // moved into a user tab becomes user-facing and must be indexed.
        unindexedSet.add(`${component} (rendered in the "${block.tab}" tab)`);
      }
    }
    const unindexed = [...unindexedSet];
    expect(
      unindexed,
      `${SETTINGS_PAGE} renders sections the search index does not know about:\n  ${unindexed.join('\n  ')}\n` +
        'Add them to SETTINGS_SECTIONS (+ SETTINGS_SEARCH_META), or to STRUCTURAL with a reason.'
    ).toEqual([]);
  });

  it('classifies every component of the administration tab too', () => {
    const admin = BLOCKS.find(block => block.tab === 'administration');
    expect(admin, 'no administration panel found').toBeDefined();
    const unclassified = componentsRenderedIn(admin!.body).filter(
      component =>
        !INDEXED_COMPONENTS.has(component) &&
        !(component in STRUCTURAL) &&
        !(component in ADMIN_TAB_DEFERRED)
    );
    expect(
      unclassified,
      `unclassified in the administration tab: ${unclassified.join(', ')} — add to ADMIN_TAB_DEFERRED with a reason, or index it`
    ).toEqual([]);
  });

  it('keeps the deferred admin list free of entries the page no longer renders', () => {
    const stale = Object.keys(ADMIN_TAB_DEFERRED).filter(
      component => !RENDERED.get(component)?.has('administration')
    );
    expect(
      stale,
      `deferred but not rendered in the administration tab: ${stale.join(', ')}`
    ).toEqual([]);
  });

  it('keeps the structural list free of entries the page no longer renders', () => {
    const stale = Object.keys(STRUCTURAL).filter(component => !RENDERED.has(component));
    expect(stale, `structural but never rendered: ${stale.join(', ')}`).toEqual([]);
  });

  it('never lets a deferred admin component be indexed at the same time', () => {
    // The two lists must stay disjoint from the table: an entry in both would
    // read as "excluded" while actually being searchable.
    const both = Object.keys(ADMIN_TAB_DEFERRED)
      .concat(Object.keys(STRUCTURAL))
      .filter(component => INDEXED_COMPONENTS.has(component));
    expect(both, `excluded AND indexed: ${both.join(', ')}`).toEqual([]);
  });

  it('holds the phase-1 invariant: the table spans the user tabs only', () => {
    // Stated as the SET of tabs in use rather than as a `=== 'administration'`
    // filter: with no admin entry today, `target.tab` narrows to
    // `'preferences' | 'features'` and `tsc` rejects the comparison as
    // impossible. `String()` widens honestly — no cast, and the assertion still
    // fails the day an administration entry is added without revisiting the
    // deferral list.
    const tabsInUse = new Set(Object.values(SETTINGS_SECTIONS).map(target => String(target.tab)));
    expect(
      [...tabsInUse].sort(),
      'phase 1 indexes the user tabs only; indexing the administration tab means emptying ADMIN_TAB_DEFERRED too'
    ).toEqual(['features', 'preferences']);
  });
});
