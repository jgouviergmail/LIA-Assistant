/**
 * Guard — chat tables (B2).
 *
 * jsdom applies no stylesheet, so two properties of the table rendering are
 * invisible to every component test and are pinned here, on the CSS text:
 *
 * 1. No cell rule decides by COLUMN POSITION. `white-space: nowrap` on the
 *    first three columns — wrapping allowed from the fourth only — was the
 *    measured root cause (908 px in a 341 px bubble, columns squeezed to
 *    40 px, a row 869 px tall). A column's index says nothing about its text.
 * 2. The stacked-card rules key on the very attribute `ResponsiveTable`
 *    writes, and print the name `rehype-table-labels` writes. A rename on one
 *    side would leave phones with an overflowing table and no error anywhere.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

import { TABLE_STACKED_ATTRIBUTE } from '@/components/chat/ResponsiveTable';

const STYLES = resolve(__dirname, '..');
const globalsCss = readFileSync(resolve(STYLES, 'globals.css'), 'utf8');
const componentsCss = readFileSync(resolve(STYLES, 'lia-components.css'), 'utf8');

/** Every `selector { body }` rule of a sheet, comments removed. */
function rules(css: string): { selector: string; body: string }[] {
  const plain = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const found: { selector: string; body: string }[] = [];
  const pattern = /([^{}]+)\{([^{}]*)\}/g;
  for (let match = pattern.exec(plain); match; match = pattern.exec(plain)) {
    found.push({ selector: match[1].trim(), body: match[2] });
  }
  return found;
}

const tableCellRules = [...rules(globalsCss), ...rules(componentsCss)].filter(rule =>
  /\b(td|th)\b/.test(rule.selector)
);

describe('chat tables — stylesheet guard', () => {
  it('never keeps a table cell on one line', () => {
    const offenders = tableCellRules.filter(rule => /white-space:\s*nowrap/.test(rule.body));
    // The one legitimate `nowrap` is the sr-only recipe that HIDES a header row.
    expect(
      offenders.filter(rule => !/position:\s*absolute/.test(rule.body)).map(rule => rule.selector)
    ).toEqual([]);
  });

  it('never styles a table cell by its column position', () => {
    const offenders = tableCellRules.filter(rule =>
      /\b(td|th):nth-(child|of-type)\(/.test(rule.selector)
    );
    expect(offenders.map(rule => rule.selector)).toEqual([]);
  });

  it('keys the stacked cards on the attribute ResponsiveTable writes', () => {
    expect(TABLE_STACKED_ATTRIBUTE).toBe('data-stacked');
    const stacked = rules(componentsCss).filter(rule =>
      rule.selector.includes(`.table-frame[${TABLE_STACKED_ATTRIBUTE}='true']`)
    );
    expect(stacked.length).toBeGreaterThan(0);
    expect(stacked.some(rule => /display:\s*block/.test(rule.body))).toBe(true);
  });

  it('prints the column name rehype-table-labels writes above each value', () => {
    const labelRule = rules(componentsCss).find(rule =>
      rule.selector.includes('[data-label]::before')
    );
    expect(labelRule?.body).toMatch(/content:\s*attr\(data-label\)/);
  });
});
