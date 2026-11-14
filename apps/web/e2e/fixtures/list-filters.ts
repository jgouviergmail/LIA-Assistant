import { expect, type Locator, type Page } from '@playwright/test';

/** `ListFilters` (`components/ui/list-toolbar.tsx`) folds below Tailwind's `sm`. */
const FOLD_BELOW_PX = 640;

/**
 * Reach a list's controls the way a reader does at the journey's width.
 *
 * On a phone the labelled controls and the filter chips of a list toolbar wait
 * behind « Filters », closed by default: this opens the fold and proves it
 * opened. From `sm` up nothing folds, and this proves THAT instead — the
 * branch is decided by the viewport the journey chose, never by what the page
 * happens to show, so a fold that disappears on a phone (or appears on a
 * desktop) fails here rather than being stepped around.
 *
 * @param scope - The page, or the section whose toolbar is meant (a hub
 *   section carries a fold of its own under the page's).
 * @param title - The fold's title in the journey's language (`common.filters`).
 * @returns The fold's summary on a phone, `null` where nothing folds.
 */
export async function openListFilters(
  scope: Page | Locator,
  title: string
): Promise<Locator | null> {
  const page = 'viewportSize' in scope ? scope : scope.page();
  const width = page.viewportSize()?.width;
  if (width === undefined) throw new Error('openListFilters needs an explicit viewport');
  const summary = scope
    .locator('summary')
    .filter({ has: page.getByText(title, { exact: true }) })
    .first();
  if (width >= FOLD_BELOW_PX) {
    await expect(summary).toHaveCount(0);
    return null;
  }
  const fold = summary.locator('xpath=..');
  await expect(fold).not.toHaveAttribute('open');
  await summary.click();
  await expect(fold).toHaveAttribute('open');
  return summary;
}
