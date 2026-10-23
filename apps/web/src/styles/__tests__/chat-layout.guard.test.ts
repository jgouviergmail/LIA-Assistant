/**
 * Guard — chat layout on a phone and beside a place map.
 *
 * jsdom applies no stylesheet, so these rules are invisible to every component
 * test. They were measured in a browser on 2026-10-22 and are pinned here, on
 * the CSS text:
 *
 * 1. On a phone a bubble may take its whole column. A wide answer (a card, a
 *    table, code) held at 95 % sat right-aligned with a 16 px strip on its
 *    left edge alone; the 95 % belongs beside the avatar, from 880 px up.
 * 2. Beside the map, the place list is centred on the MAP's height, by auto
 *    margins: `justify-content: center` on that scroll container would push a
 *    list longer than the map out at the top too, beyond the reach of its
 *    scroll.
 * 3. On a phone the place list starts at the left edge.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

const STYLES = resolve(__dirname, '..');

interface Rule {
  /** One entry per selector of the list, whitespace collapsed. */
  selectors: string[];
  /** The `@media` / `@container` preludes around the rule, outermost first. */
  conditions: string[];
  declarations: Map<string, string>;
}

function declarations(body: string): Map<string, string> {
  const found = new Map<string, string>();
  for (const part of body.split(';')) {
    const colon = part.indexOf(':');
    if (colon > 0) found.set(part.slice(0, colon).trim(), part.slice(colon + 1).trim());
  }
  return found;
}

/** Every style rule of a sheet, with the conditional groups it sits in. */
function rules(css: string): Rule[] {
  const plain = css
    .replace(/\/\*[\s\S]*?\*\//g, '')
    // A brace inside a string (`@source '../**/*.{ts,tsx}'`) opens no block.
    .replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g, quoted => quoted.replace(/[{}]/g, ' '));
  const found: Rule[] = [];
  const open: { prelude: string; body: string }[] = [];
  let buffer = '';
  for (const char of plain) {
    if (char === '{') {
      const cut = buffer.lastIndexOf(';');
      if (open.length > 0) open[open.length - 1].body += buffer.slice(0, cut + 1);
      open.push({ prelude: buffer.slice(cut + 1).trim(), body: '' });
      buffer = '';
    } else if (char === '}') {
      const block = open.pop();
      if (block && !block.prelude.startsWith('@')) {
        found.push({
          selectors: block.prelude
            .split(/,(?![^(]*\))/)
            .map(selector => selector.replace(/\s+/g, ' ').trim()),
          conditions: open
            .map(group => group.prelude)
            .filter(prelude => /^@(media|container)\b/.test(prelude)),
          declarations: declarations(block.body + buffer),
        });
      }
      buffer = '';
    } else {
      buffer += char;
    }
  }
  return found;
}

const globals = rules(readFileSync(resolve(STYLES, 'globals.css'), 'utf8'));
const cards = rules(readFileSync(resolve(STYLES, 'lia-cards.css'), 'utf8'));

const besideAvatar = (rule: Rule) => rule.conditions.some(c => /min-width:\s*880px/.test(c));
const onPhone = (rule: Rule) => rule.conditions.some(c => /max-width:\s*639px/.test(c));
const inWideCard = (rule: Rule) =>
  rule.conditions.some(c => /^@container card \(min-width:\s*45rem\)$/.test(c));
const find = (sheet: Rule[], selector: string, where: (rule: Rule) => boolean) =>
  sheet.find(rule => where(rule) && rule.selectors.includes(selector));

describe('chat bubbles on a phone', () => {
  const bubbles = globals.filter(rule =>
    rule.selectors.some(selector => selector.includes('.message-bubble'))
  );

  it('never narrows a bubble below its column under the avatar breakpoint', () => {
    const narrowed = bubbles
      .filter(rule => !besideAvatar(rule))
      .flatMap(rule =>
        ['width', 'max-width']
          .filter(property => (rule.declarations.get(property) ?? '100%') !== '100%')
          .map(property => `${rule.selectors.join(', ')} { ${property} }`)
      );
    expect(narrowed).toEqual([]);
  });

  it('gives a card or a table its whole column on a phone, 95 % beside the avatar', () => {
    for (const selector of [
      '.message-bubble:has(table)',
      '.message-bubble-assistant:has(.lia-card)',
    ]) {
      // A WIDTH on both sides: the bubble is a cross-axis flex item that would
      // otherwise follow its content (see globals.css).
      expect(find(bubbles, selector, rule => !besideAvatar(rule))?.declarations.get('width')).toBe(
        '100%'
      );
      expect(find(bubbles, selector, besideAvatar)?.declarations.get('width')).toBe('95%');
    }
  });
});

describe('the place list', () => {
  const SIDE_LIST =
    ".lia-place-position__content[data-map-shown='true'] > .lia-place-position__choices";

  it('beside the map, is centred on the map alone and keeps its first places reachable', () => {
    const list = find(cards, SIDE_LIST, inWideCard);
    expect(list?.declarations.get('grid-row')).toBe('1');
    expect(list?.declarations.get('overflow-y')).toBe('auto');
    expect(list?.declarations.get('justify-content') ?? 'normal').toMatch(
      /^(normal|start|flex-start)$/
    );
    expect(
      find(cards, `${SIDE_LIST} > li:first-child`, inWideCard)?.declarations.get('margin-top')
    ).toBe('auto');
    expect(
      find(cards, `${SIDE_LIST} > li:last-child`, inWideCard)?.declarations.get('margin-bottom')
    ).toBe('auto');
  });

  it('starts at the left edge on a phone', () => {
    for (const selector of [
      ".lia-place-position__content[data-map-shown='false'] > .lia-place-position__choices",
      '.lia-place-position__fallback',
    ]) {
      expect(find(cards, selector, onPhone)?.declarations.get('justify-content')).toBe(
        'flex-start'
      );
    }
  });
});
