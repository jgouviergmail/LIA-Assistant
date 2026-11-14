/**
 * The header's display circle, walked in a real engine: every press that changes the
 * page changes it INSIDE its reveal, once.
 *
 * A reveal photographs the page, runs the change, and unfolds the live page over the
 * photograph. Two things break it, both seen on this circle (owner report 2026-11-14,
 * ADR-243 follow-up): a change drawn BEFORE the photograph is not revealed, the page
 * snaps — entering automatic by day did, its clock drawing first; and a change UNDONE
 * under the reveal unfolds a page that goes back on itself — the account's effect
 * redrew what the account still said. The page is read in itself: what it shows when
 * the engine runs the change, and every picture it goes through until the reveal ends.
 */
import { test, expect, idleNotificationStream, makeTestUser } from '../fixtures';
import type { MockRoute } from '../fixtures';
import { installApiCatchAll, registerRoutes, stopApiRequests } from '../fixtures/api-mock';
import { appConfig, dashboardShellMocks } from '../fixtures/dashboard-shell';

type Picture = 'light' | 'dark' | 'OLED';
interface Reveal {
  /** The page when the engine ran the change: what its photograph holds. */
  photographed: Picture;
  /** Every picture the page went through from the press to the end of the reveal. */
  shown: Picture[];
}

declare global {
  interface Window {
    /** One entry per finished reveal, in the order the engine ran them. */
    themeReveals?: Reveal[];
    /** Every picture the page went through since `filmPage` ran. */
    themeFilm?: Picture[];
  }
}

/** What the page shows, read where the stylesheet reads it. Runs in the page. */
function pagePicture(): Picture {
  const root = document.documentElement;
  if (!root.classList.contains('dark')) return 'light';
  return root.hasAttribute('data-oled') ? 'OLED' : 'dark';
}

/** Films every picture the page goes through from now on. Runs in the page. */
function filmPage(): void {
  const picture = (): Picture => {
    const root = document.documentElement;
    if (!root.classList.contains('dark')) return 'light';
    return root.hasAttribute('data-oled') ? 'OLED' : 'dark';
  };
  const film: Picture[] = [];
  window.themeFilm = film;
  new MutationObserver(() => {
    if (film.at(-1) !== picture()) film.push(picture());
  }).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class', 'data-oled'],
  });
}

/** Long enough for two tabs answering each other to have done so many times over. */
const QUIET_MS = 1200;

const empty = {
  items: [],
  total: 0,
  revision: 1,
  as_of: '2026-10-19T13:00:00Z',
  next_cursor: null,
};

/** Hours that make the automatic mode show the day, or the night, for two hours around now. */
function schedule(night: boolean): {
  theme_light_start_minute: number;
  theme_dark_start_minute: number;
} {
  const now = new Date();
  const minute = now.getUTCHours() * 60 + now.getUTCMinutes();
  const before = (minute + 1440 - 120) % 1440;
  const after = (minute + 120) % 1440;
  return night
    ? { theme_light_start_minute: after, theme_dark_start_minute: before }
    : { theme_light_start_minute: before, theme_dark_start_minute: after };
}

/** What the SMS page reads besides the account. */
const pageRoutes: MockRoute[] = [
  idleNotificationStream,
  {
    url: '**/api/v1/config',
    json: { ...appConfig, features: { ...appConfig.features, sms_enabled: true } },
  },
  { url: '**/api/v1/sms/search', json: empty },
  { url: '**/api/v1/sms/senders**', json: empty },
  {
    url: '**/api/v1/sms/blocked-senders**',
    json: { blocks: [], total: 0, as_of: empty.as_of, next_cursor: null },
  },
];

/** The header holds another « Passer en… » control, the execution mode's. */
const TOGGLE = /^Passer en (mode (sombre|clair|automatique)|noir OLED)$/;

for (const [hour, night] of [
  ['by day', false],
  ['by night', true],
] as const) {
  test(`the display circle reveals every change it makes ${hour}`, async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await page.addInitScript(() => {
      // The page's own copy of `pagePicture`: an init script carries no closure.
      const picture = (): Picture => {
        const root = document.documentElement;
        if (!root.classList.contains('dark')) return 'light';
        return root.hasAttribute('data-oled') ? 'OLED' : 'dark';
      };
      const reveals: Reveal[] = [];
      window.themeReveals = reveals;
      const start = document.startViewTransition.bind(document);
      document.startViewTransition = (change?: () => void | Promise<void>) => {
        // Filmed from the press: a change drawn ahead of the photograph is on the film.
        const shown: Picture[] = [];
        const film = new MutationObserver(() => {
          if (shown.at(-1) !== picture()) shown.push(picture());
        });
        film.observe(document.documentElement, {
          attributes: true,
          attributeFilter: ['class', 'data-oled'],
        });
        let photographed: Picture = picture();
        const transition = start(() => {
          photographed = picture();
          return change?.();
        });
        const ended = () => {
          film.disconnect();
          reveals.push({ photographed, shown });
        };
        // `finished` settles when the reveal ends, animated or skipped.
        transition.finished.then(ended, ended);
        return transition;
      };
    });
    // The suite asks for reduced motion, under which the circle changes with no
    // reveal at all: this journey is about the reveal.
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.setViewportSize({ width: 1280, height: 900 });
    let account = makeTestUser({
      language: 'fr',
      timezone: 'UTC',
      theme: 'light',
      ...schedule(night),
    });
    await authenticate(account);
    const saved: unknown[] = [];
    await mockApi([
      ...pageRoutes,
      // The account as a server keeps it, answering at once — the hardest case: a
      // save and its read both return within the frame the reveal waits for.
      {
        url: '**/api/v1/auth/me',
        handler: route => route.fulfill({ json: account }),
      },
      {
        url: `**/api/v1/users/${account.id}`,
        method: 'PATCH',
        handler: async route => {
          const patch = route.request().postDataJSON() as Partial<typeof account>;
          saved.push(patch.theme);
          account = { ...account, ...patch };
          await route.fulfill({ json: account });
        },
      },
    ]);
    await page.goto('/fr/dashboard/sms');
    await expect(page.getByRole('heading', { level: 1, name: 'Mes SMS' })).toBeVisible();

    const toggle = page.getByRole('button', { name: TOGGLE });
    const picture = () => page.evaluate(pagePicture);
    const reveals = () => page.evaluate(() => window.themeReveals ?? []);
    await expect(toggle).toHaveAccessibleName('Passer en mode sombre');
    expect(await picture()).toBe('light');

    // What automatic shows at this hour.
    const automatic: Picture = night ? 'OLED' : 'light';
    const walk: { name: string; shows: Picture }[] = [
      { name: 'Passer en mode sombre', shows: 'dark' },
      { name: 'Passer en noir OLED', shows: 'OLED' },
      { name: 'Passer en mode automatique', shows: automatic },
      { name: 'Passer en mode clair', shows: 'light' },
      { name: 'Passer en mode sombre', shows: 'dark' },
    ];
    for (const [index, stop] of walk.entries()) {
      const before = await picture();
      await expect(toggle).toHaveAccessibleName(stop.name);
      await toggle.click();
      await expect
        .poll(async () => (await reveals()).length, { message: stop.name })
        .toBe(index + 1);
      const reveal = (await reveals())[index];
      const told = `${stop.name}, from ${before}`;
      // Nothing drew the change ahead of its reveal…
      expect(reveal.photographed, told).toBe(before);
      // …the page never came back to a picture it had left…
      const walked = [before, ...reveal.shown];
      expect(new Set(walked).size, `${told}: ${walked.join(' → ')}`).toBe(walked.length);
      // …and it ends on the stop the press named.
      expect(walked.at(-1), told).toBe(stop.shows);
      expect(await picture(), told).toBe(stop.shows);
      await expect.poll(() => saved.length, { message: stop.name }).toBe(index + 1);
    }
    expect(saved).toEqual(['dark', 'oled', 'auto', 'light', 'dark']);
  });
}

test('a second tab of the account follows a press instead of answering it', async ({
  page,
  context,
  authenticate,
  mockApi,
}) => {
  // `next-themes` shares the choice between tabs through storage, and the other tab's
  // account still says light: it is not told of the save. Redrawing its account there
  // wrote light back to the shared storage, and the two tabs threw the theme at each
  // other — the pressed tab was undone under its own reveal.
  const opened = makeTestUser({
    language: 'fr',
    timezone: 'UTC',
    theme: 'light',
    ...schedule(false),
  });
  let account = opened;
  await authenticate(opened);
  await mockApi([
    ...pageRoutes,
    { url: '**/api/v1/auth/me', handler: route => route.fulfill({ json: account }) },
    {
      url: `**/api/v1/users/${opened.id}`,
      method: 'PATCH',
      handler: async route => {
        account = { ...account, ...(route.request().postDataJSON() as Partial<typeof opened>) };
        await route.fulfill({ json: account });
      },
    },
  ]);
  const other = await context.newPage();
  try {
    await installApiCatchAll(other);
    await registerRoutes(other, [
      ...dashboardShellMocks,
      ...pageRoutes,
      { url: '**/api/v1/auth/me', json: opened },
    ]);
    for (const tab of [other, page]) {
      await tab.goto('/fr/dashboard/sms');
      await expect(tab.getByRole('heading', { level: 1, name: 'Mes SMS' })).toBeVisible();
      await expect(tab.getByRole('button', { name: TOGGLE })).toHaveAccessibleName(
        'Passer en mode sombre'
      );
      await tab.evaluate(filmPage);
    }

    await page.getByRole('button', { name: TOGGLE }).click();
    await expect.poll(() => page.evaluate(pagePicture)).toBe('dark');
    await expect.poll(() => other.evaluate(pagePicture)).toBe('dark');
    await page.waitForTimeout(QUIET_MS);

    // Each tab changed once, and the shared choice is the one that was pressed.
    expect(await page.evaluate(() => window.themeFilm)).toEqual(['dark']);
    expect(await other.evaluate(() => window.themeFilm)).toEqual(['dark']);
    expect(await page.evaluate(() => localStorage.getItem('theme'))).toBe('dark');
    expect(account.theme).toBe('dark');
  } finally {
    try {
      await stopApiRequests(other);
    } finally {
      await other.close();
    }
  }
});
