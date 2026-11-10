/** The real companion picker, persistent selection and assistant identity; API traffic is hermetic. */
import { test, expect, chatRoutes, waitForHydration, type MockRoute } from '../fixtures';
import en from '../../locales/en/translation.json';
import fr from '../../locales/fr/translation.json';
import { companionBodyAsset } from '../../src/components/spirit/companion-catalogue';

const CHARACTERS = ['bip', 'spirit', 'moss', 'lumen'] as const;
const PREFS_KEY = 'lia_eyes_widget_prefs';
const ROUTES: MockRoute[] = [
  { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
  { url: '**/api/v1/scheduled-actions**', json: { actions: [], total: 0 } },
  { url: '**/api/v1/usage/**', json: {} },
];

for (const [language, width] of [
  ['en', 320],
  ['fr', 375],
  ['en', 640],
  ['fr', 768],
] as const) {
  test(`companion cards expose both identities and preserve keyboard selection at ${language}/${width}`, async ({
    page,
    authenticate,
    mockApi,
    baseURL,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await authenticate({ language });
    if (!baseURL) throw new Error('The hermetic app origin is required');
    await page.context().addCookies([{ name: 'NEXT_LOCALE', value: language, url: baseURL }]);
    await mockApi(ROUTES);
    const labels = (language === 'fr' ? fr : en).eyes;
    await page.goto(`${language === 'fr' ? '' : '/en'}/dashboard/settings?section=eyes-style`);
    await page.mouse.move(1, 1);
    const section = page.locator('#settings-section-eyes-style');
    await expect(section).toBeVisible();
    for (const character of CHARACTERS) {
      const card = section.getByRole('button', {
        name: labels.styles[character].name,
        exact: true,
      });
      await expect(card).toBeVisible();
      await expect(card).toContainText(labels.variants.female);
      await expect(card).toContainText(labels.variants.male);
      await expect(card.locator('[data-spirit-companion]')).toHaveCount(2);
      await expect(card.locator('canvas')).toHaveCount(0);
      for (const face of await card.locator('.lia-eyes').all()) {
        await expect(face).toHaveAttribute('data-motion', 'off');
        await expect(face).toHaveAttribute('data-expression', 'neutral');
      }
      // Exercise the real focus wake-up before measuring the GPU preview.
      await card.focus();
      for (const variant of ['female', 'male'] as const) {
        const face = card.locator(
          `[data-character="${character}"][data-spirit-companion="${variant}"] .lia-eyes`
        );
        await expect(face).toHaveAttribute('data-expression', 'neutral');
        await expect(face).toHaveAttribute('data-volume-ready', 'true');
        const geometry = await face.evaluate(async root => {
          const width = root.getBoundingClientRect().width;
          const image = new Image();
          const background = getComputedStyle(
            root.querySelector('.lia-head')!,
            '::before'
          ).backgroundImage;
          image.src = background.match(/url\(["']?(.*?)["']?\)/)![1];
          await image.decode();
          return {
            width,
            source: new URL(image.src).pathname,
            bitmapWidth: image.naturalWidth,
          };
        });
        expect(geometry.width).toBeCloseTo(52, 1);
        expect(geometry.source).toBe(companionBodyAsset(character, variant));
        expect(geometry.bitmapWidth).toBe(192);
      }
      await card.screenshot({
        path: testInfo.outputPath(`card-${character}-${language}-${width}.png`),
      });
    }
    const bounds = await section.evaluate(section => ({
      viewport: innerWidth,
      pageWidth: document.documentElement.scrollWidth,
      cards: [...section.querySelectorAll('button')].map(card => ({
        left: card.getBoundingClientRect().left,
        right: card.getBoundingClientRect().right,
        width: card.clientWidth,
        content: card.scrollWidth,
      })),
    }));
    expect(bounds.pageWidth).toBeLessThanOrEqual(bounds.viewport + 1);
    for (const card of bounds.cards) {
      expect(card.left).toBeGreaterThanOrEqual(0);
      expect(card.right).toBeLessThanOrEqual(bounds.viewport + 1);
      expect(card.content).toBeLessThanOrEqual(card.width + 1);
    }
    if (language === 'fr' && width === 768) {
      await section.evaluate(
        (section, names) => {
          const cards = [...section.querySelectorAll('button')]
            .filter(card => names.includes(card.getAttribute('aria-label') ?? ''))
            .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
          const first = cards[0];
          if (!first) throw new Error('The native companion cards must be mounted');
          first.scrollIntoView({ block: 'start', inline: 'nearest', behavior: 'instant' });
          for (let parent = first.parentElement; parent; parent = parent.parentElement) {
            if (
              parent.scrollHeight > parent.clientHeight &&
              /auto|scroll/.test(getComputedStyle(parent).overflowY)
            ) {
              parent.scrollBy({ top: -24, behavior: 'instant' });
              return;
            }
          }
          window.scrollBy({ top: -24, behavior: 'instant' });
        },
        CHARACTERS.map(character => labels.styles[character].name)
      );
      const clip = await section.evaluate(
        (section, names) => {
          const boxes = [...section.querySelectorAll('button')]
            .filter(card => names.includes(card.getAttribute('aria-label') ?? ''))
            .map(card => card.getBoundingClientRect());
          const x = Math.min(...boxes.map(box => box.left));
          const y = Math.min(...boxes.map(box => box.top));
          return {
            x,
            y,
            width: Math.max(...boxes.map(box => box.right)) - x,
            height: Math.max(...boxes.map(box => box.bottom)) - y,
          };
        },
        CHARACTERS.map(character => labels.styles[character].name)
      );
      expect(clip.y).toBeGreaterThanOrEqual(0);
      const path = testInfo.outputPath('four-gender-cards-fr-actual.png');
      await page.screenshot({ path, clip });
      await testInfo.attach('four-gender-cards-fr-actual', { path, contentType: 'image/png' });
    }
    const chosen = section.getByRole('button', { name: labels.styles.lumen.name, exact: true });
    await chosen.focus();
    await page.keyboard.press('Space');
    await expect(chosen).toHaveAttribute('aria-current', 'true');
    await expect(chosen).toBeFocused();
    expect(
      await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).state.style, PREFS_KEY)
    ).toBe('lumen');
    await page.keyboard.press('Enter');
    await expect(chosen).toBeFocused();
    await page.reload();
    const restored = page
      .locator('#settings-section-eyes-style')
      .getByRole('button', { name: labels.styles.lumen.name, exact: true });
    await expect(restored).toHaveAttribute('aria-current', 'true');
  });
}

for (const character of ['moss', 'lumen'] as const) {
  test(`selected ${character} keeps its native face and shared gender preference in chat`, async ({
    page,
    authenticate,
    mockApi,
    baseURL,
  }, testInfo) => {
    if (!baseURL) throw new Error('The hermetic app origin is required');
    await authenticate();
    await page.context().addCookies([{ name: 'lia_gender', value: 'male', url: baseURL }]);
    // This journey exercises the responsive 'auto' setting and its first
    // size-cycle step, independently of the default Bip/XL presentation.
    await page.addInitScript(() => {
      // Init scripts also run on the later chat navigation and reload.
      // Seed the fresh device once, so the real picker selection persists.
      if (localStorage.getItem('lia_eyes_widget_prefs') !== null) return;
      localStorage.setItem(
        'lia_eyes_widget_prefs',
        JSON.stringify({ state: { visible: true, style: 'bip', size: 'auto' }, version: 0 })
      );
    });
    await mockApi([...ROUTES, ...chatRoutes([])]);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/en/dashboard/settings?section=eyes-style');
    const choice = page.locator('#settings-section-eyes-style').getByRole('button', {
      name: en.eyes.styles[character].name,
      exact: true,
    });
    await choice.focus();
    await page.keyboard.press('Enter');
    await expect(choice).toHaveAttribute('aria-current', 'true');
    await expect(choice).toBeFocused();
    await page.goto('/en/dashboard/chat');
    const widget = page.getByRole('group', { name: /LIA's expressive eyes/ });
    const identity = widget.locator(`[data-character="${character}"]`);
    const face = identity.locator('.lia-eyes');
    await expect(face).toBeVisible();
    await waitForHydration(page, `[data-character="${character}"] .lia-eyes`);
    await expect(face).toHaveClass(/lia-eyes--lg/);
    await widget.focus();
    // Move the floating controls clear of the sticky header through their
    // actual keyboard interaction before exercising pointer size controls.
    for (let step = 0; step < 16; step++) await page.keyboard.press('ArrowDown');
    const resize = widget.getByRole('button', { name: en.eyes.cycle_size });
    for (const [size, diameter] of [
      ['md', 78],
      ['lg', 114.4],
      ['xl', 166.4],
      ['sm', 52],
      ['md', 78],
      ['lg', 114.4],
    ] as const) {
      await resize.click();
      await expect(face).toHaveClass(new RegExp(`lia-eyes--${size}`));
      await expect
        .poll(() => face.evaluate(root => root.getBoundingClientRect().width))
        .toBeCloseTo(diameter, 1);
    }
    const originalFace = await face.elementHandle();
    for (const variant of ['male', 'female'] as const) {
      if (variant === 'female') {
        await page.evaluate(() => {
          document.cookie = 'lia_gender=female; path=/; SameSite=Lax';
          window.dispatchEvent(new Event('lia-gender-change'));
        });
      }
      await expect(identity).toHaveAttribute('data-spirit-companion', variant);
      await expect(face).toHaveAttribute('data-style', 'billes');
      await expect(face.locator('.lia-eye-pupil-clip')).toHaveCount(2);
      await expect(face.locator('[data-rig-mouth]')).toHaveCount(1);
      const readBody = () =>
        face
          .locator('.lia-head')
          .evaluate(head => getComputedStyle(head, '::before').backgroundImage);
      const firstBody = await readBody();
      // The variant attribute commits before inherited custom properties
      // finish propagating to the pseudo-element in Chromium.
      await expect.poll(readBody).toContain(companionBodyAsset(character, variant));
      await testInfo.attach(`${character}-${variant}-body-update`, {
        body: JSON.stringify({
          firstBody,
          settledBody: await readBody(),
          declaredBody: await identity.evaluate(root =>
            (root as HTMLElement).style.getPropertyValue('--spirit-body-url')
          ),
        }),
        contentType: 'application/json',
      });
      expect(await face.evaluate((root, previous) => root === previous, originalFace)).toBe(true);
      await face.screenshot({ path: testInfo.outputPath(`${character}-${variant}-actual.png`) });
    }
    expect(
      await page.evaluate(key => JSON.parse(localStorage.getItem(key)!).state.style, PREFS_KEY)
    ).toBe(character);
    await page.reload();
    await expect(
      page.locator(`[data-character="${character}"][data-spirit-companion="female"] .lia-eyes`)
    ).toBeVisible();
  });
}
