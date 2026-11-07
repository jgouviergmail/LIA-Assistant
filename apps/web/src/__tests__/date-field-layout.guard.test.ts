/**
 * A date or a time stays inside its box on an iPhone (owner, 2026-11-06).
 *
 * Safari on iOS gives these fields its own display and width, so a field of `width: 100%` could
 * pass the edge of its panel; no engine this suite can run behaves that way (measured: Chromium
 * and Linux WebKit keep the box), so the recipe itself is held here: no native appearance on every
 * temporal type, and a value that keeps a usable width and height once it has none.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const css = readFileSync(join(process.cwd(), 'src/styles/globals.css'), 'utf8');

function ruleOf(selector: RegExp): string {
  const found = css.match(new RegExp(`${selector.source}[^{]*\\{([^}]*)\\}`));
  if (!found) throw new Error(`no rule for ${selector.source}`);
  return found[1] ?? '';
}

describe('the base rule of a temporal field', () => {
  it.each(['date', 'time', 'datetime-local', 'month', 'week'])('covers %s', type => {
    const selector = css.match(/input:is\(([^)]*)\)/)?.[1] ?? '';

    expect(selector).toContain(`[type='${type}']`);
  });

  it('takes the native appearance off and lets the field shrink with its box', () => {
    const rule = ruleOf(/input:is\(/);

    expect(rule).toMatch(/appearance:\s*none/);
    expect(rule).toMatch(/min-width:\s*0/);
    expect(rule).toMatch(/max-width:\s*100%/);
  });

  it('keeps a usable value, whose height an empty field would otherwise lose', () => {
    const rule = ruleOf(/input::-webkit-date-and-time-value/);

    expect(rule).toMatch(/min-width:/);
    expect(rule).toMatch(/height:\s*1\.5em/);
    expect(rule).toMatch(/margin:\s*0/);
    expect(rule).toMatch(/text-align:\s*start/);
  });
});
