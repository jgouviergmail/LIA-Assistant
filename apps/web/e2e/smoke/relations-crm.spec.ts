/**
 * Personal CRM (N-09 + favorites) — the Relations page end to end.
 *
 * Unit tests cover the aggregation service and the presentational components.
 * The browser proves the doors and the journey: Relations holds a first-class
 * NAV slot since 2026-07-30 (it took the `spaces` slot — the chat indicator
 * keeps spaces one click away), the overview renders, the star moves a card
 * into the Favorites band, a card opens the 360° detail (client-state, no
 * route change), and "prepare a 360° point" deep-links the chat with a
 * `?intent=` (ADR-173).
 */
import { test, expect, type MockRoute } from '../fixtures';

const NAME = 'Gérard Dupont';

const OVERVIEW = {
  relations: [
    {
      display_name: NAME,
      identity_confidence: 'exact',
      open_loops_count: 2,
      calls_count: 1,
      peer_messages_count: 2,
      last_interaction_at: '2026-07-28T09:00:00Z',
      is_favorite: false,
      is_peer: true,
    },
    {
      display_name: 'Marie Leroy',
      identity_confidence: 'normalized',
      open_loops_count: 1,
      calls_count: 0,
      peer_messages_count: 0,
      last_interaction_at: '2026-07-20T09:00:00Z',
      is_favorite: false,
      is_peer: false,
    },
  ],
};

const DETAIL = {
  display_name: NAME,
  identity_confidence: 'exact',
  open_loops: [
    {
      id: 'l1',
      subject: 'Rendre la perceuse',
      direction: 'user_owes',
      due_hint: null,
      days_open: 4,
    },
  ],
  recent_calls: [
    {
      id: 'c1',
      objective: 'Anniversaire surprise',
      outcome: 'objective_met',
      summary: 'Il est partant.',
      created_at: '2026-07-25T10:00:00Z',
    },
  ],
  memories: [{ id: 'm1', content: 'Aime la randonnée en montagne.' }],
  open_loops_total: 1,
  recent_calls_total: 1,
  memories_total: 1,
  peer_messages_total: 2,
  peer_messages: [
    {
      id: 'pm1',
      direction: 'received',
      content: 'Gérard vous fait dire qu’il sera en retard.',
      occurred_at: '2026-07-27T18:00:00Z',
    },
    // A message whose text expired keeps its date and says so plainly
    // (retention horizon — ADR-186; anything delivered before it never had a
    // stored text at all).
    { id: 'pm2', direction: 'sent', content: null, occurred_at: '2026-07-26T08:00:00Z' },
  ],
  peer_link: {
    connected_since: '2026-06-01T10:00:00Z',
    shared_by_me: [{ domain: 'calendar', level: 'availability' }],
    shared_with_me: [{ domain: 'task', level: 'titles' }],
  },
  is_favorite: false,
  is_peer: true,
};

const OVERVIEW_SCOPE = {
  sections: ['contact', 'open_loops', 'calls', 'memories', 'peer_messages', 'emails', 'events'],
  directions: ['received', 'sent'],
  roles: ['attendee', 'organizer'],
  max_items: 5,
};

/** The provider-backed half (Bloc C): its own endpoint, its own statuses. */
const CONTEXT = {
  contact: {
    status: 'ok',
    from_cache: false,
    generated_at: '2026-07-30T09:00:00Z',
    // The FULL card contract — the backend always sends every block (Pydantic
    // defaults), so a mock that omits half of it would be testing a shape the
    // API never produces.
    contact: {
      display_name: NAME,
      nickname: null,
      organization: 'Menuiserie Dupont',
      occupation: 'Menuisier',
      birthday: '--04-07',
      biography: null,
      emails: [{ value: 'gerard@example.com', label: 'work' }],
      phones: [{ value: '+33600000000', label: 'mobile' }],
      addresses: [{ value: '12 rue des Lilas, Lyon', label: 'home' }],
      relations: [],
      links: [],
      important_dates: [],
      messaging: [],
    },
    emails: [],
    events: [],
  },
  emails: {
    status: 'ok',
    from_cache: false,
    generated_at: '2026-07-30T09:00:00Z',
    contact: null,
    emails: [
      {
        id: 'm1',
        direction: 'received',
        subject: 'Devis pour la terrasse',
        occurred_at: '2026-07-28T09:00:00Z',
      },
    ],
    events: [],
  },
  events: {
    status: 'ok',
    from_cache: false,
    generated_at: '2026-07-30T09:00:00Z',
    contact: null,
    emails: [],
    events: [
      {
        id: 'e1',
        summary: 'Visite du chantier',
        starts_at: '2026-08-05T09:00:00Z',
        is_past: false,
        role: 'organizer',
        organizer_known: true,
      },
    ],
  },
  addresses_used: 1,
  window_days: 90,
  email_window_days: 365,
};

/** Truthful favorites server: the PUT flips the state the GET then serves —
 * required because the hook RECONCILES the optimistic star against the fresh
 * overview (a static `is_favorite: false` mock would un-star the card as soon
 * as the refetch lands, which is exactly what CI caught). */
function buildRoutes(relations = OVERVIEW.relations) {
  const state = { starred: new Set<string>() };
  const overview = () => ({
    relations: relations.map(relation => ({
      ...relation,
      is_favorite: state.starred.has(relation.display_name),
    })),
  });
  const routes: MockRoute[] = [
    {
      url: '**/api/v1/relations',
      method: 'GET',
      handler: route => route.fulfill({ json: overview() }),
    },
    {
      url: '**/api/v1/relations/favorites/*',
      method: 'PUT',
      handler: route => {
        const name = decodeURIComponent(route.request().url().split('/').pop() ?? '');
        state.starred.add(name);
        return route.fulfill({ status: 204, body: '' });
      },
    },
    // Declared BEFORE the specific routes, not after: Playwright resolves route
    // handlers LAST-REGISTERED-FIRST (see `fixtures/api-mock.ts`). Measured on
    // 2026-08-01 — with this catch-all declared last it won, and
    // `/relations/overview-scope` was answered with a RelationDetail. The panel
    // then read `scope.sections.length` off an object that has no `sections`
    // and died behind its error boundary, taking seven tests with it.
    { url: '**/api/v1/relations/*', method: 'GET', json: DETAIL },
    { url: '**/api/v1/relations/overview-scope', method: 'GET', json: OVERVIEW_SCOPE },
    { url: '**/api/v1/relations/overview-scope', method: 'PUT', json: OVERVIEW_SCOPE },
    { url: '**/api/v1/relations/*/context', method: 'GET', json: CONTEXT },
  ];
  return routes;
}

/**
 * Open a folded section. Every section starts CLOSED by design: the panel is a
 * compact index of the relationship, and the reader opens what they came for.
 */
async function openSection(page: import('@playwright/test').Page, title: string) {
  await page.getByRole('button', { name: new RegExp(title) }).click();
}

test.describe('relations CRM (N-09)', () => {
  test('is reached from the navigation bar', async ({ page, authenticate, mockApi }) => {
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes());
    await page.goto('/fr/dashboard');

    // Relations holds a first-class nav slot since 2026-07-30 (default-locale
    // hrefs carry no /fr prefix — assert the journey, not the string).
    const navLink = page.getByRole('navigation').getByRole('link', { name: 'Relations' });
    await expect(navLink).toBeVisible();
    await navLink.click();
    await page.waitForURL(/\/dashboard\/relations/, { timeout: 30_000 });
    await expect(page.getByRole('heading', { level: 1, name: 'Relations' })).toBeVisible();
  });

  test('the star moves a card into the Favorites band without opening it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes());
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });

    // No favorites yet: a single band.
    await expect(page.getByRole('heading', { name: /Favoris/ })).toHaveCount(0);
    await page.getByRole('button', { name: `Ajouter ${NAME} aux favoris` }).click();
    // Optimistic: the Favorites band appears with the starred card inside.
    const favoritesBand = page.locator('section', {
      has: page.getByRole('heading', { name: /Favoris/ }),
    });
    await expect(favoritesBand.getByText(NAME)).toBeVisible();
    // The 360° detail did NOT open (starring is not opening).
    await expect(page.getByText('Rendre la perceuse')).toHaveCount(0);
  });

  test('starring never wipes the filter the user is typing', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Starring refetches the overview. Staging a spinner on that refetch
    // unmounted the whole list — including the toolbar — so the filter text,
    // the sort choice and the chips vanished on every star.
    const many = [
      ...OVERVIEW.relations,
      ...Array.from({ length: 9 }, (_, index) => ({
        ...OVERVIEW.relations[1],
        display_name: `Contact Numero ${index}`,
        is_peer: false,
      })),
    ];
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes(many));
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });

    // The toolbar only appears past the volumetry threshold — hence 11 rows.
    // `searchbox`, not `textbox`: the field is a native `input type="search"`.
    const filterBox = page.getByRole('searchbox', { name: 'Filtrer par nom…' });
    await expect(filterBox).toBeVisible();
    await filterBox.fill('Numero 3');
    await expect(page.getByText('Contact Numero 3')).toBeVisible();
    await expect(page.getByText(NAME)).toHaveCount(0);

    await page.getByRole('button', { name: /Ajouter Contact Numero 3 aux favoris/ }).click();

    // The refetch lands: the filter, its text and its effect all survive.
    await expect(page.getByRole('heading', { name: /Favoris/ })).toBeVisible();
    await expect(filterBox).toHaveValue('Numero 3');
    await expect(page.getByText(NAME)).toHaveCount(0);
  });

  test('lists relationships and opens a 360° view that deep-links the chat', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes());
    await page.goto('/fr/dashboard/relations');

    // Overview: both people appear.
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('Marie Leroy')).toBeVisible();

    // Open the 360° detail (client state — the URL stays on /relations).
    // Anchored: the sibling star button is named "Ajouter <name> aux favoris"
    // and must not match (two buttons carry the name since favorites).
    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();
    // Folded by default: the headings are the index, the content opens on demand.
    await expect(page.getByRole('button', { name: /Engagements/ })).toHaveAttribute(
      'aria-expanded',
      'false',
      { timeout: 30_000 }
    );
    await openSection(page, 'Engagements');
    await expect(page.getByText('Rendre la perceuse')).toBeVisible();
    await openSection(page, 'Appels récents');
    await expect(page.getByText('Anniversaire surprise')).toBeVisible();
    await openSection(page, 'Souvenirs');
    await expect(page.getByText('Aime la randonnée en montagne.')).toBeVisible();

    // Run the 360° → chat intent (ADR-173). The ONLY entry point is inside
    // the scope section, next to the checkboxes that decide what it reads —
    // a header shortcut would have skipped that choice.
    await openSection(page, 'Point 360');
    await page.getByRole('button', { name: /Lancer le point 360/ }).click();
    await page.waitForURL(/\/dashboard\/chat\?intent=/, { timeout: 30_000 });
  });

  test('the 360° view carries relayed messages and replies with a PREFILL', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes());
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();

    // Both directions render; the one with no text left says so. Scoped to
    // the relayed-messages card: "Reçu"/"Envoyé" label the mail section too
    // (same words, same meaning — the section is what tells them apart).
    const messages = page.locator('section', {
      has: page.getByRole('heading', { name: 'Messages' }),
    });
    await openSection(page, '^Messages');
    await expect(messages.getByText(/sera en retard/)).toBeVisible({ timeout: 30_000 });
    await expect(messages.getByText('Reçu')).toBeVisible();
    await expect(messages.getByText('Envoyé')).toBeVisible();
    await expect(messages.getByText('Texte non conservé')).toBeVisible();

    // The LIA connection block states BOTH share directions. It is NOT a
    // collapsible section — a live connection is context the reader needs
    // without asking, so there is no toggle to open (and a test that tried to
    // click one waited ninety seconds for a button that never existed).
    await expect(page.getByText('Connexion LIA')).toBeVisible();
    await expect(page.getByText('Calendrier — disponibilités')).toBeVisible();
    await expect(page.getByText('Tâches — titres')).toBeVisible();

    // Writing must PREFILL, never send (A4 contract — `?intent=` is auto-sent,
    // QW-24/ADR-173). The oracle is the COMPOSER, not the address bar: since
    // ADR-192 the one-shot param really leaves the URL as soon as it is
    // consumed, so `?draft=` is gone by the time anyone could read it — and a
    // test that waited for it was passing on a defect.
    await page.getByRole('button', { name: 'Écrire', exact: true }).click();
    await page.waitForURL(/\/dashboard\/chat/, { timeout: 30_000 });
    await expect(page.getByRole('textbox').first()).toHaveValue(new RegExp(NAME), {
      timeout: 30_000,
    });
    expect(page.url()).not.toContain('intent=');
  });

  test('the connected accounts fill in behind the 360° view', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes());
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();

    // The database-local half is on screen; the provider half arrives behind it.
    await openSection(page, 'Engagements');
    await expect(page.getByText('Rendre la perceuse')).toBeVisible({ timeout: 30_000 });

    await openSection(page, 'Fiche contact');
    await expect(page.getByText('Menuiserie Dupont')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('gerard@example.com')).toBeVisible();
    await openSection(page, 'Emails échangés');
    await expect(page.getByText('Devis pour la terrasse')).toBeVisible();
    await openSection(page, 'Rendez-vous partagés');
    await expect(page.getByText('Visite du chantier')).toBeVisible();
    await expect(page.getByText('À venir')).toBeVisible();

    // The SCOPE is stated, never a total a provider page cannot prove.
    await expect(page.getByText(/90 derniers jours/)).toBeVisible();
  });

  test('the sections follow the asked order, fold, and hand a selection to the chat', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes());
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();
    await expect(page.getByRole('heading', { name: 'Fiche contact' })).toBeVisible({
      timeout: 30_000,
    });

    // ORDER: 360° scope, contact card, commitments, memories, calls, mail,
    // meetings. The scope comes FIRST — it decides what the assistant will
    // read, so it belongs before the data it governs.
    const titles = await page.getByRole('heading', { level: 3 }).allInnerTexts();
    const rank = (needle: string) => titles.findIndex(title => title.includes(needle));
    expect(rank('Point 360')).toBeGreaterThanOrEqual(0);
    expect(rank('Point 360')).toBeLessThan(rank('Fiche contact'));
    expect(rank('Fiche contact')).toBeGreaterThanOrEqual(0);
    expect(rank('Fiche contact')).toBeLessThan(rank('Engagements'));
    expect(rank('Engagements')).toBeLessThan(rank('Souvenirs'));
    expect(rank('Souvenirs')).toBeLessThan(rank('Appels récents'));
    expect(rank('Appels récents')).toBeLessThan(rank('Emails échangés'));
    expect(rank('Emails échangés')).toBeLessThan(rank('Rendez-vous partagés'));

    // FOLD: closed by default, opens on demand, and says so to assistive tech.
    const contactToggle = page.getByRole('button', { name: /Fiche contact/ });
    await expect(contactToggle).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByText('Menuiserie Dupont')).toBeHidden();
    await contactToggle.click();
    await expect(contactToggle).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByText('Menuiserie Dupont')).toBeVisible();

    // MEETINGS: the role is words, not a colour. Scoped to the section: the
    // scope selector above offers "Organisateur" as a checkbox too, and an
    // unscoped text match would now be ambiguous.
    await openSection(page, 'Rendez-vous partagés');
    const meetings = page
      .getByRole('button', { name: /Rendez-vous partagés/ })
      .locator('xpath=ancestor::section[1]');
    await expect(meetings.getByText('Organisateur')).toBeVisible();

    // SELECTION → chat: an auto-sent intent, never a draft.
    await openSection(page, 'Emails échangés');
    await page.getByRole('checkbox', { name: /Devis pour la terrasse/ }).check();
    await page.getByRole('button', { name: /Résumer/ }).click();
    await page.waitForURL(/\/dashboard\/chat\?intent=/, { timeout: 30_000 });
    // `+` is the form encoding of a space; decodeURIComponent leaves it as is.
    const sent = decodeURIComponent(page.url()).replace(/\+/g, ' ');
    expect(sent).toContain('Devis pour la terrasse');
  });

  test('each cached section can be refreshed on demand', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The contact card lives up to six hours in the cache: without this
    // control, a correction in the address book stays invisible half a day.
    const asked: string[] = [];
    await authenticate({ language: 'fr' });
    await mockApi([
      ...buildRoutes().filter(route => !String(route.url).endsWith('/context')),
      {
        url: '**/api/v1/relations/*/context*',
        method: 'GET',
        handler: async route => {
          asked.push(new URL(route.request().url()).searchParams.get('refresh') ?? '');
          await route.fulfill({ json: CONTEXT });
        },
      },
    ]);
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();
    await expect(page.getByRole('heading', { name: 'Fiche contact' })).toBeVisible({
      timeout: 30_000,
    });

    // Per section: only that one is asked for live (the control sits on the
    // header, so a folded section can still be refreshed).
    await page.getByRole('button', { name: 'Rafraîchir cette section' }).first().click();
    await expect.poll(() => asked.at(-1), { timeout: 10_000 }).toBe('contact');

    // Globally: all three.
    await page.getByRole('button', { name: /Rafraîchir ce qui vient/ }).click();
    await expect.poll(() => asked.at(-1), { timeout: 10_000 }).toBe('contact,emails,events');
  });

  test('every control on a phone screen is big enough to hit', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // WCAG 2.5.5 / Apple HIG / Material converge on ~44 CSS px for a touch
    // target. Icon-only controls are the ones that fail it silently: the icon
    // looks fine, the box around it does not.
    await page.setViewportSize({ width: 390, height: 844 });
    await authenticate({ language: 'fr' });
    await mockApi(buildRoutes());
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });

    const tooSmall = async () => {
      const boxes = await page.evaluate(() =>
        Array.from(document.querySelectorAll('button, input[type="checkbox"], select'))
          .filter(el => (el as HTMLElement).offsetParent !== null)
          .map(el => {
            const rect = el.getBoundingClientRect();
            // A label wrapping a checkbox IS the target — measure that instead.
            const target = el.closest('label') ?? el;
            const box = target.getBoundingClientRect();
            return {
              name: (el.getAttribute('aria-label') ?? el.textContent ?? '').trim().slice(0, 40),
              w: Math.max(rect.width, box.width),
              h: Math.max(rect.height, box.height),
            };
          })
          .filter(item => item.h < 44 || item.w < 44)
      );
      return boxes;
    };

    expect(await tooSmall(), 'controls under 44 CSS px on the overview').toEqual([]);

    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();
    await expect(page.getByRole('heading', { name: 'Fiche contact' })).toBeVisible({
      timeout: 30_000,
    });
    await openSection(page, 'Emails échangés');
    expect(await tooSmall(), 'controls under 44 CSS px on the 360° card').toEqual([]);

    // And the page still must not scroll sideways.
    const overflow = await page.evaluate(() => {
      const el = document.scrollingElement ?? document.documentElement;
      return el.scrollWidth - el.clientWidth;
    });
    expect(overflow).toBeLessThanOrEqual(1);

    // The companion's MINIMIZED state is a screen of its own, and the only way
    // back is a 12 px dot — measured here because no other journey ever reaches
    // it, so it went unmeasured while looking covered.
    await page.getByRole('button', { name: 'Réduire le compagnon' }).click();
    await expect(page.getByRole('button', { name: 'Afficher le compagnon LIA' })).toBeVisible();
    expect(await tooSmall(), 'controls under 44 CSS px once minimized').toEqual([]);
  });

  test('an unconnected account says so once, not three times', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const blank = {
      status: 'not_configured',
      from_cache: false,
      generated_at: '2026-07-30T09:00:00Z',
      contact: null,
      emails: [],
      events: [],
    };
    await authenticate({ language: 'fr' });
    await mockApi([
      ...buildRoutes().filter(route => !String(route.url).endsWith('/context')),
      {
        url: '**/api/v1/relations/*/context',
        method: 'GET',
        json: {
          contact: blank,
          emails: blank,
          events: blank,
          addresses_used: 0,
          window_days: 90,
          email_window_days: 365,
        },
      },
    ]);
    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(NAME)).toBeVisible({ timeout: 30_000 });
    await page.getByRole('button', { name: new RegExp(`^${NAME}`) }).click();

    // The ADDRESS BOOK is the keystone: mail and calendar are queried by an
    // address, and only the contact card can produce one — so that is what
    // the invitation names.
    const invite = page.getByText(/Connectez votre carnet d.adresses/);
    await expect(invite).toBeVisible({ timeout: 30_000 });
    // One invitation, not one per section.
    await expect(invite).toHaveCount(1);
    // The HEADING, not the text: the invitation sentence itself contains the
    // words "fiche contact", and getByText matches substrings.
    await expect(page.getByRole('heading', { name: 'Fiche contact' })).toHaveCount(0);
  });
});
