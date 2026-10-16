/** Computed neutral surfaces on the actual settings requested in the visual review. */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import type { Locator, Page } from '@playwright/test';
import { test, expect, idleNotificationStream } from '../fixtures';
import {
  surfaceRoutes,
  surfacePeerName,
  surfaceMemoryCategories,
  surfaceJournalTitle,
  surfaceBookmarkAnswer,
} from '../fixtures/settings-surfaces';
import { awaitStyledPage, expectNoOverflow } from './overflow-report';

const dictionary: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/en/translation.json'), 'utf8')
);
const frenchDictionary: unknown = JSON.parse(
  readFileSync(path.join(__dirname, '../../locales/fr/translation.json'), 'utf8')
);
function label(key: string, french = false): string {
  let value: unknown = french ? frenchDictionary : dictionary;
  for (const part of key.split('.')) {
    if (!value || typeof value !== 'object') throw new Error(`Missing label ${key}`);
    value = (value as Record<string, unknown>)[part];
  }
  if (typeof value !== 'string') throw new Error(`Missing label ${key}`);
  return value;
}
const artifacts = path.resolve(
  __dirname,
  '../../../../.tmp/codex-ui-interface-polish/screenshots/surfaces'
);
const variants = [
  { theme: 'light', width: 1440, font: 16 },
  { theme: 'dark', width: 1280, font: 16 },
  { theme: 'oled', width: 360, font: 20 },
] as const;
const panels = [
  'voice-mode',
  'radio',
  'image-generation',
  'bookmarks',
  'health-metrics',
  'psyche',
  'peer-connections',
  'journals',
] as const;
type Panel = (typeof panels)[number];

/** Only painted ancestors are levels; transparent layout wrappers add none. */
async function assertPaintedChain(section: Locator, leaf: Locator, depth: number, name: string) {
  await expect(leaf).toBeVisible();
  const sectionId = await section.getAttribute('id');
  const chain = await leaf.evaluate((node, id) => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Color decoding requires a canvas');
    const levels: { tag: string; id: string; color: string; alpha: number; luminance: number }[] =
      [];
    let current: Element | null = node;
    while (current) {
      const color = getComputedStyle(current).backgroundColor;
      ctx.clearRect(0, 0, 1, 1);
      ctx.fillStyle = color;
      ctx.fillRect(0, 0, 1, 1);
      const rgba = ctx.getImageData(0, 0, 1, 1).data;
      if (rgba[3] > 0) {
        const linear = Array.from(rgba)
          .slice(0, 3)
          .map(value => {
            const c = value / 255;
            return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
          });
        levels.unshift({
          tag: current.tagName,
          id: current.id,
          color,
          alpha: rgba[3],
          luminance: linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722,
        });
      }
      if (current.id === id) return levels;
      current = current.parentElement;
    }
    throw new Error('Surface probe must stay inside its settings section');
  }, sectionId);
  expect(chain[0]?.id, `${name}: the encompassing settings panel is painted`).toBe(sectionId);
  expect(chain, `${name}: exact neutral painted levels`).toHaveLength(depth);
  for (const level of chain)
    expect(level.alpha, `${name}: ${level.tag} ${level.id} must be opaque`).toBe(255);
  for (let i = 1; i < chain.length; i++) {
    const previous = chain[i - 1].luminance;
    const current = chain[i].luminance;
    if (i % 2)
      expect(previous, `${name}: primary is lighter than nested level ${i}`).toBeGreaterThan(
        current
      );
    else
      expect(previous, `${name}: nested is darker than primary level ${i}`).toBeLessThan(current);
  }
  return { name, chain };
}

async function openNative(section: Locator, key: string) {
  const summary = section.locator('summary').filter({ hasText: label(key) });
  await expect(summary).toHaveCount(1);
  if (!(await summary.locator('..').evaluate(node => (node as HTMLDetailsElement).open)))
    await summary.click();
}
async function probes(page: Page, section: Locator, panel: Panel) {
  if (panel === 'voice-mode') {
    const group = section.getByRole('group', { name: label('settings.voice_mode.stt_mode_label') });
    const local = group.getByRole('button', { name: label('settings.voice_mode.stt_mode_local') });
    const notice = group
      .locator('p')
      .filter({ hasText: /OpenAI/ })
      .last();
    return [
      await assertPaintedChain(section, local, 3, 'unselected engine option'),
      await assertPaintedChain(section, notice, 3, 'engine privacy notice'),
    ];
  }
  if (panel === 'radio') {
    await openNative(section, 'radio.settings.programmes.title');
    return [
      await assertPaintedChain(
        section,
        section.locator('#radio-frequency-headlines'),
        4,
        'programme disclosure/card/select'
      ),
    ];
  }
  if (panel === 'image-generation') {
    return [
      await assertPaintedChain(
        section,
        section.getByRole('combobox', {
          name: label('settings.image_generation.quality'),
          exact: true,
        }),
        3,
        'quality group/select'
      ),
    ];
  }
  if (panel === 'bookmarks')
    return [
      await assertPaintedChain(
        section,
        section.getByText(surfaceBookmarkAnswer, { exact: true }),
        3,
        'bookmark card/answer'
      ),
    ];
  if (panel === 'health-metrics')
    return [
      await assertPaintedChain(
        section,
        section.getByText(label('healthMetrics.stats.hrAvg'), { exact: true }),
        3,
        'statistics fold/tile'
      ),
    ];
  if (panel === 'psyche') {
    const control = section.getByRole('button', {
      name: label('psyche.education.title'),
      exact: true,
    });
    if ((await control.getAttribute('aria-expanded')) !== 'true') await control.click();
    const relationship = section.getByText(label('psyche.presentation.relationship'), {
      exact: true,
    });
    const relationshipWordRects = await relationship.evaluate(node => {
      const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
      let text: Node | null;
      while ((text = walker.nextNode())) {
        const index = text.textContent?.indexOf('relationship') ?? -1;
        if (index < 0) continue;
        const range = document.createRange();
        range.setStart(text, index);
        range.setEnd(text, index + 'relationship'.length);
        return range.getClientRects().length;
      }
      throw new Error('Expected the actual English relationship heading');
    });
    expect(
      relationshipWordRects,
      'the relationship heading never splits its word across lines'
    ).toBe(1);
    return [
      await assertPaintedChain(
        section,
        section.getByRole('button', {
          name: label('psyche.education.overview.title'),
          exact: true,
        }),
        3,
        'psyche panel/education card'
      ),
      { name: 'whole relationship heading word', relationshipWordRects },
    ];
  }
  if (panel === 'peer-connections')
    return [
      await assertPaintedChain(
        section,
        section.getByText(surfacePeerName, { exact: true }).first(),
        3,
        'connections panel/person card'
      ),
    ];
  const category = section.getByRole('button', {
    name: new RegExp(label('journals.themes.self_reflection')),
  });
  if ((await category.getAttribute('aria-expanded')) !== 'true') await category.click();
  const source = section.getByText(/^[^a-zA-Z0-9]*conversation$/);
  const badge = await source.evaluate(node => {
    const icon = node.querySelector('[aria-hidden="true"]');
    const text = Array.from(node.childNodes).find(
      child => child.nodeType === Node.TEXT_NODE && child.textContent?.includes('conversation')
    );
    if (!icon || !text) throw new Error('Expected the real source badge icon and text');
    const range = document.createRange();
    range.selectNode(text);
    const iconRect = icon.getBoundingClientRect();
    const textRect = range.getBoundingClientRect();
    const rect = node.getBoundingClientRect();
    let card = node.parentElement;
    while (card && parseFloat(getComputedStyle(card).borderTopWidth) === 0)
      card = card.parentElement;
    if (!card) throw new Error('Expected the source inside its bordered journal entry');
    const cardRect = card.getBoundingClientRect();
    return {
      iconCenter: iconRect.top + iconRect.height / 2,
      textCenter: textRect.top + textRect.height / 2,
      left: rect.left,
      right: rect.right,
      cardLeft: cardRect.left,
      cardRight: cardRect.right,
    };
  });
  expect(
    Math.abs(badge.iconCenter - badge.textCenter),
    'journal source icon and word share one line'
  ).toBeLessThan(4);
  expect(badge.left, 'source badge remains inside the entry').toBeGreaterThanOrEqual(
    badge.cardLeft
  );
  expect(badge.right, 'source badge remains inside the entry').toBeLessThanOrEqual(badge.cardRight);
  await openNative(section, 'common.details');
  const details = section.locator('summary').filter({ hasText: label('common.details') });
  return [
    await assertPaintedChain(section, details, 4, 'journal category/entry/details'),
    await assertPaintedChain(
      section,
      section.getByText(surfaceJournalTitle, { exact: true }),
      3,
      'journal category/entry'
    ),
    { name: 'journal source icon and word geometry', badge },
  ];
}

async function assertCategoryGeometry(section: Locator, names: readonly string[]) {
  for (const name of names) {
    const wordGeometry = await section
      .getByText(name, { exact: true })
      .first()
      .evaluate(node => {
        const control = node.closest('button');
        if (!control) throw new Error('Expected a real category accordion control');
        const frame = control.getBoundingClientRect();
        let panel = control.parentElement;
        while (panel && parseFloat(getComputedStyle(panel).borderTopWidth) === 0)
          panel = panel.parentElement;
        if (!panel) throw new Error('Expected the category control inside a bordered panel');
        const container = panel.getBoundingClientRect();
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
        const words: Array<{ word: string; lines: number; left: number; right: number }> = [];
        let text: Node | null;
        while ((text = walker.nextNode()))
          for (const match of (text.textContent ?? '').matchAll(/\S+/g)) {
            const range = document.createRange();
            range.setStart(text, match.index!);
            range.setEnd(text, match.index! + match[0].length);
            const rect = range.getBoundingClientRect();
            words.push({
              word: match[0],
              lines: range.getClientRects().length,
              left: rect.left,
              right: rect.right,
            });
          }
        return {
          controlLeft: frame.left,
          controlRight: frame.right,
          containerLeft: container.left,
          containerRight: container.right,
          words,
        };
      });
    expect
      .soft(wordGeometry.controlLeft, `${name}: control starts inside its panel`)
      .toBeGreaterThanOrEqual(wordGeometry.containerLeft);
    expect
      .soft(wordGeometry.controlRight, `${name}: control ends inside its panel`)
      .toBeLessThanOrEqual(wordGeometry.containerRight);
    for (const word of wordGeometry.words) {
      expect.soft(word.lines, `${name}: whole category word ${word.word}`).toBe(1);
      expect
        .soft(word.left, `${name}: category word starts inside control`)
        .toBeGreaterThanOrEqual(wordGeometry.controlLeft);
      expect
        .soft(word.right, `${name}: category word ends inside control`)
        .toBeLessThanOrEqual(wordGeometry.controlRight);
    }
  }
}

async function captureFrenchFinal(page: Page, panel: 'psyche' | 'journals', width: number) {
  await page.goto(`/fr/dashboard/settings?section=${panel}`);
  await awaitStyledPage(page, `${panel} final French capture`);
  const section = page.locator(`#settings-section-${panel}`);
  await expect(section).toBeVisible();
  if (width === 360) {
    await page.evaluate(() => {
      document.documentElement.style.setProperty('--lia-text-scale', '2');
      dispatchEvent(new Event('resize'));
    });
  }
  if (panel === 'psyche') {
    for (const key of [
      'psyche.education.title',
      'psyche.settingsSection.title',
      'psyche.presentation.resets',
    ]) {
      await expect(
        section.getByRole('button', { name: label(key, true), exact: true })
      ).toHaveAttribute('aria-expanded', 'false');
    }
    for (const key of [
      'psyche.presentation.mood',
      'psyche.presentation.relationship',
      'psyche.presentation.drivesTitle',
      'psyche.presentation.evolution',
    ]) {
      await expect(
        section.getByRole('button', { name: label(key, true), exact: true })
      ).toHaveAttribute('aria-expanded', 'true');
    }
    await expect(
      section.getByRole('region', { name: label('psyche.presentation.point', true), exact: true })
    ).toBeVisible();
    if (width === 360) {
      for (const key of [
        'psyche.depth',
        'psyche.warmth',
        'psyche.trust',
        'psyche.education.traits.openness',
        'psyche.education.traits.conscientiousness',
        'psyche.education.traits.extraversion',
        'psyche.education.traits.agreeableness',
        'psyche.education.traits.neuroticism',
      ]) {
        const word = section.getByText(label(key, true), { exact: true }).first();
        const lines = await word.evaluate(node => {
          const range = document.createRange();
          range.selectNodeContents(node);
          return range.getClientRects().length;
        });
        expect.soft(lines, `${key} remains a complete word at 200% text`).toBe(1);
        const meterBounds = await section
          .getByRole('meter', { name: label(key, true), exact: true })
          .first()
          .evaluate(node => {
            const frame = node.getBoundingClientRect();
            const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
            const textBounds: Array<{ left: number; right: number }> = [];
            let text: Node | null;
            while ((text = walker.nextNode())) {
              if (!text.textContent?.trim()) continue;
              const range = document.createRange();
              range.selectNodeContents(text);
              textBounds.push(
                ...[...range.getClientRects()].map(rect => ({ left: rect.left, right: rect.right }))
              );
            }
            return { left: frame.left, right: frame.right, textBounds };
          });
        for (const rect of meterBounds.textBounds) {
          expect
            .soft(rect.left, `${key} text starts inside its meter`)
            .toBeGreaterThanOrEqual(meterBounds.left - 1);
          expect
            .soft(rect.right, `${key} text ends inside its meter`)
            .toBeLessThanOrEqual(meterBounds.right + 1);
        }
      }
    }
  } else {
    if (width === 360)
      await assertCategoryGeometry(
        section,
        ['self_reflection', 'user_observations', 'ideas_analyses', 'learnings'].map(key =>
          label(`journals.themes.${key}`, true)
        )
      );
    for (const key of ['journals.groupBy.theme', 'journals.groupBy.level']) {
      const control = section.getByRole('button', { name: label(key, true), exact: true });
      const bounds = await control.evaluate(node => ({
        button: node.getBoundingClientRect().toJSON(),
        row: node.parentElement!.parentElement!.getBoundingClientRect().toJSON(),
      }));
      expect
        .soft(bounds.button.left, `${key} starts within its row`)
        .toBeGreaterThanOrEqual(bounds.row.left);
      expect
        .soft(bounds.button.right, `${key} ends within its row`)
        .toBeLessThanOrEqual(bounds.row.right);
    }
    const category = section.getByRole('button', {
      name: new RegExp(label('journals.themes.self_reflection', true)),
    });
    if ((await category.getAttribute('aria-expanded')) !== 'true') await category.click();
    const source = section.getByText(/^[^a-zA-Z0-9]*conversation$/);
    await expect(source).toBeVisible();
    const geometry = await source.evaluate(node => {
      const icon = node.querySelector('svg,span');
      const text = [...node.childNodes].find(
        child => child.nodeType === Node.TEXT_NODE && child.textContent?.includes('conversation')
      );
      if (!icon || !text) throw new Error('Expected conversation icon and word');
      const range = document.createRange();
      range.selectNodeContents(text);
      const i = icon.getBoundingClientRect(),
        t = range.getBoundingClientRect(),
        b = node.getBoundingClientRect();
      return {
        iconCenter: i.top + i.height / 2,
        textCenter: t.top + t.height / 2,
        left: b.left,
        right: b.right,
      };
    });
    expect(Math.abs(geometry.iconCenter - geometry.textCenter)).toBeLessThan(4);
    expect(geometry.left).toBeGreaterThanOrEqual(0);
    expect(geometry.right).toBeLessThanOrEqual(width);
    writeFileSync(
      path.join(artifacts, `journals-final-fr-${width}.json`),
      JSON.stringify(geometry, null, 2)
    );
  }
  await expectNoOverflow(page, `${panel} final French ${width}px`);
  await section.evaluate(node => {
    const header = document.querySelector('header');
    scrollBy(
      0,
      node.getBoundingClientRect().top - (header?.getBoundingClientRect().bottom ?? 64) - 12
    );
  });
  await page.screenshot({
    path: path.join(artifacts, `${panel}-final-fr-${width}${width === 360 ? '-text200' : ''}.png`),
    animations: 'disabled',
  });
  if (panel === 'journals') {
    await section.getByText(surfaceJournalTitle, { exact: true }).evaluate(node => {
      let card = node.parentElement;
      while (card && parseFloat(getComputedStyle(card).borderTopWidth) === 0)
        card = card.parentElement;
      if (!card) throw new Error('Expected journal entry card');
      const header = document.querySelector('header');
      scrollBy(
        0,
        card.getBoundingClientRect().top - (header?.getBoundingClientRect().bottom ?? 64) - 12
      );
    });
    await page.screenshot({
      path: path.join(
        artifacts,
        `journals-entry-final-fr-${width}${width === 360 ? '-text200' : ''}.png`
      ),
      animations: 'disabled',
    });
  }
  if (panel === 'psyche' && width === 360) {
    await section
      .getByText(label('psyche.education.traits.conscientiousness', true), { exact: true })
      .first()
      .evaluate(node => {
        const row = node.closest('dl');
        if (!row) throw new Error('Expected the actual OCEAN traits list');
        const header = document.querySelector('header');
        scrollBy(
          0,
          row.getBoundingClientRect().top - (header?.getBoundingClientRect().bottom ?? 64) - 12
        );
      });
    await page.screenshot({
      path: path.join(artifacts, 'psyche-traits-final-fr-360-text200.png'),
      animations: 'disabled',
    });
  }
  if (panel === 'psyche') {
    await section
      .getByRole('button', { name: label('psyche.presentation.relationship', true), exact: true })
      .scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(
        artifacts,
        `psyche-relationship-final-fr-${width}${width === 360 ? '-text200' : ''}.png`
      ),
      animations: 'disabled',
    });
  }
}

for (const variant of variants)
  for (const panel of panels) {
    test(`${panel}: opaque alternating surfaces at ${variant.width}px ${variant.theme} ${variant.font}px text`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await page.setViewportSize({ width: variant.width, height: 1000 });
      const user = await authenticate({
        language: 'en',
        theme: variant.theme,
        font_size: variant.font,
        voice_enabled: false,
        voice_stt_mode: 'remote',
      });
      Object.assign(user, { health_metrics_enabled: true, image_generation_enabled: true });
      await page.addInitScript(() =>
        localStorage.setItem(
          'lia_eyes_widget_prefs',
          JSON.stringify({ state: { visible: false }, version: 0 })
        )
      );
      const unexpected: string[] = [];
      const errors: string[] = [];
      page.on('response', response => {
        if (response.status() === 501 && new URL(response.url()).pathname.startsWith('/api/'))
          unexpected.push(response.url());
      });
      page.on('pageerror', error => errors.push(error.message));
      await mockApi([...surfaceRoutes, idleNotificationStream]);
      const token = panel === 'bookmarks' ? 'generated-assets' : panel;
      await page.goto(
        `/en/dashboard/settings?section=${token}${panel === 'bookmarks' ? '&tab=bookmarks' : ''}`
      );
      await awaitStyledPage(page, `${panel} surfaces`);
      const section = page.locator(
        `#settings-section-${panel === 'health-metrics' ? 'health_metrics' : token}`
      );
      await expect(section).toBeVisible();
      await page.mouse.move(0, 0);
      const measurements = await probes(page, section, panel);
      await expectNoOverflow(page, `${panel} ${variant.width}px ${variant.theme}`);
      mkdirSync(artifacts, { recursive: true });
      const basename = `${panel}-${variant.theme}-${variant.width}`;
      writeFileSync(
        path.join(artifacts, `${basename}.json`),
        JSON.stringify(measurements, null, 2)
      );
      await section.screenshot({
        path: path.join(artifacts, `${basename}-section.png`),
        animations: 'disabled',
      });
      // A viewport capture preserves the real sticky header without placing it
      // over the section title (element screenshots scroll a tall panel to y=0).
      await section.evaluate(node => {
        const banner = document.querySelector('header');
        const top = (banner?.getBoundingClientRect().bottom ?? 64) + 12;
        scrollBy(0, node.getBoundingClientRect().top - top);
      });
      await page.screenshot({
        path: path.join(artifacts, `${basename}.png`),
        animations: 'disabled',
      });
      if ((panel === 'psyche' || panel === 'journals') && variant.theme !== 'dark')
        await captureFrenchFinal(page, panel, variant.width);
      if (panel === 'journals' && variant.width === 360) {
        await page.goto('/fr/dashboard/settings?section=memories');
        await awaitStyledPage(page, 'Memory categories at 200% text');
        await page.evaluate(() => {
          document.documentElement.style.setProperty('--lia-text-scale', '2');
          dispatchEvent(new Event('resize'));
        });
        const memories = page.locator('#settings-section-memories');
        await expect(memories).toBeVisible();
        await assertCategoryGeometry(
          memories,
          surfaceMemoryCategories.map(key => label(`memories.categories.${key}`, true))
        );
        const firstCategory = memories.getByRole('button', {
          name: new RegExp(label('memories.categories.preference', true)),
        });
        await firstCategory.evaluate(node => {
          const header = document.querySelector('header');
          scrollBy(
            0,
            node.getBoundingClientRect().top - (header?.getBoundingClientRect().bottom ?? 64) - 12
          );
        });
        await expectNoOverflow(page, 'Memory categories at 200% text');
        await page.screenshot({
          path: path.join(artifacts, 'memories-categories-final-fr-360-text200.png'),
          animations: 'disabled',
        });
      }
      expect(unexpected, 'all screen API calls have exact mocked payloads').toEqual([]);
      expect(errors, 'actual screen renders without uncaught error').toEqual([]);
    });
  }
