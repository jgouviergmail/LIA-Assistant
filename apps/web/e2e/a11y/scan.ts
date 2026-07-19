/**
 * Shared axe scan helper (audit AC-002).
 *
 * Runs an axe-core WCAG 2.x A/AA analysis, archives a per-page JSON report as
 * a test attachment (stable selector, rule, and — for color-contrast — the
 * computed fg/bg colors, font size/weight and observed vs required ratio
 * straight from axe), and returns the blocking critical/serious set with a
 * human-readable summary for the assertion message.
 */
import AxeBuilder from '@axe-core/playwright';
import type { Page, TestInfo } from '@playwright/test';

// @axe-core/playwright types its `page` against a different playwright-core
// version than @playwright/test 1.60 (which added localStorage/sessionStorage
// to Page), so the structural types diverge. Bridge them with the exact type
// AxeBuilder expects rather than reaching for `any`.
type AxePage = ConstructorParameters<typeof AxeBuilder>[0]['page'];

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];
const BLOCKING_IMPACTS = new Set(['critical', 'serious']);
const CONTRAST_RULE = 'color-contrast';

export async function scanPage(page: Page, testInfo: TestInfo, label: string) {
  // `next dev` compiles style chunks on demand: a page can be interactive
  // BEFORE the app stylesheet is applied. Scanning that unstyled window
  // yields phantom contrast violations — every <a> renders with Chromium's
  // dark-UA link color (#9e9eff) over the default white canvas, implicating
  // the palette for a server-side hiccup (observed: 6 such "violations" on a
  // degraded dev server; the same scan is clean once styles are applied).
  // The palette IS the subject under test, so wait for the design-system
  // tokens to resolve, and fail with an actionable message if they never do.
  await page
    .waitForFunction(
      () =>
        getComputedStyle(document.documentElement).getPropertyValue('--color-background').trim() !==
        '',
      undefined,
      { timeout: 30_000 }
    )
    .catch(() => {
      throw new Error(
        `axe scan aborted on ${label}: the app stylesheet never applied ` +
          '(design-system tokens unresolved after 30s) — the server under ' +
          'test is degraded (next dev compiling or broken). Contrast results ' +
          'would reflect UA default colors, not the palette. Restart the dev ' +
          'server (purge .next if it keeps returning 500) and re-run.'
      );
    });

  const results = await new AxeBuilder({ page: page as unknown as AxePage })
    .withTags(WCAG_TAGS)
    .analyze();
  const blocking = results.violations.filter(v => BLOCKING_IMPACTS.has(v.impact ?? ''));

  const report = blocking.map(v => ({
    rule: v.id,
    impact: v.impact,
    help: v.help,
    nodes: v.nodes.map(n => ({
      selector: n.target.join(' '),
      summary: n.failureSummary,
      ...(v.id === CONTRAST_RULE ? { contrast: n.any[0]?.data ?? null } : {}),
    })),
  }));
  await testInfo.attach(`axe-${label.replace(/\W+/g, '-')}.json`, {
    body: JSON.stringify(
      { page: label, violations: report, passes: results.passes.length },
      null,
      2
    ),
    contentType: 'application/json',
  });

  const summary = report
    .map(
      v =>
        `${v.impact} · ${v.rule} (${v.nodes.length})\n` +
        v.nodes
          .map(
            n =>
              `    ${n.selector}${'contrast' in n && n.contrast ? ` — ${JSON.stringify(n.contrast)}` : ''}`
          )
          .join('\n')
    )
    .join('\n');

  return { blocking, summary };
}
