/**
 * Two chat deep links in a row, through the REAL journey — the defect of
 * 2026-08-01, measured in production and reproduced here.
 *
 * Production evidence (v1.27.5, deployed): a 360° on one person, then a second
 * person's card opened and launched, sent the FIRST person's sentence — four
 * rows in `conversation_messages`, the same name, and three semantic-pivot
 * cache HITS, which only happen when the very same string arrives.
 *
 * Root cause, isolated in this browser: the App Router **restores the search
 * params of the entry it already holds for a route**. A client-side
 * `router.push('/dashboard/chat?draft=…Paul…')` came back as the previous
 * visit's `?intent=…Marie…` — a URL the application never built. Three
 * candidate causes were ruled out by experiment: static prerendering (route
 * forced dynamic, defect unchanged), our own one-shot URL cleanup (a first
 * visit carrying no query and no cleanup still poisons), and the i18n rewrite
 * of the default locale (identical in `en`, where no rewrite applies).
 *
 * Why the existing `chat-360-deep-link` spec never caught it: it uses
 * `page.goto`, a full document load that rebuilds the router from the URL. The
 * defect only exists on client-side navigation to a route already visited.
 *
 * Hermetic: one dispatcher serves the whole `/relations` family, and the chat
 * POST bodies are captured so the assertions are about WHAT was sent.
 */
import { test, expect, type MockRoute } from '../fixtures';

const FIRST = 'Marie Dupont';
const SECOND = 'Paul Martin';

interface ChatBody {
  message?: string;
  directive?: { capability?: string; subject?: string };
}

const SCOPE = {
  sections: ['contact', 'open_loops', 'calls', 'memories', 'peer_messages', 'emails', 'events'],
  directions: ['received', 'sent'],
  roles: ['attendee', 'organizer'],
  max_items: 5,
};

const EMPTY_SECTION = {
  status: 'not_configured',
  from_cache: false,
  generated_at: '2026-08-01T04:00:00Z',
  contact: null,
  emails: [],
  events: [],
};

const CONTEXT = {
  contact: EMPTY_SECTION,
  emails: EMPTY_SECTION,
  events: EMPTY_SECTION,
  addresses_used: 0,
  window_days: 90,
  email_window_days: 365,
};

function overviewRow(name: string) {
  return {
    display_name: name,
    identity_confidence: 'exact',
    open_loops_count: 0,
    calls_count: 0,
    peer_messages_count: 0,
    last_interaction_at: '2026-07-28T09:00:00Z',
    is_favorite: false,
    is_peer: true,
  };
}

/** A detail payload that ALWAYS names the person the endpoint was asked for. */
function detailFor(name: string) {
  return {
    display_name: name,
    identity_confidence: 'exact',
    open_loops: [],
    open_loops_total: 0,
    recent_calls: [],
    recent_calls_total: 0,
    memories: [],
    memories_total: 0,
    peer_messages: [],
    peer_messages_total: 0,
    peer_link: null,
    is_favorite: false,
    is_peer: true,
  };
}

/**
 * ONE dispatcher for the whole `/relations` family.
 *
 * Playwright resolves route handlers last-registered-first, and every one of
 * these paths matches `**​/relations/*`. Dispatching on the parsed path inside a
 * single handler removes that ambiguity entirely — a mock whose precedence
 * depends on declaration order can silently serve a detail payload as a scope.
 */
function relationsRoutes(): MockRoute[] {
  return [
    {
      url: '**/api/v1/relations**',
      handler: async route => {
        const url = new URL(route.request().url());
        const path = decodeURIComponent(url.pathname.replace('/api/v1/relations', ''));
        const json = (body: unknown) =>
          route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(body),
          });

        if (path === '' || path === '/') {
          return json({ relations: [overviewRow(FIRST), overviewRow(SECOND)] });
        }
        if (path === '/overview-scope') return json(SCOPE);
        if (path.endsWith('/context')) return json(CONTEXT);
        return json(detailFor(path.replace(/^\//, '')));
      },
    },
  ];
}

function chatRoutes(bodies: ChatBody[]): MockRoute[] {
  return [
    { url: '**/api/v1/conversations/me/totals', json: {} },
    {
      url: '**/api/v1/conversations/me/messages*',
      json: {
        messages: [],
        conversation_id: '00000000-0000-4000-8000-0000000000ff',
        total_count: 0,
        has_more: false,
        next_cursor: null,
      },
    },
    { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
    { url: '**/api/v1/agents/runs/active', json: { active: false } },
    { url: '**/api/v1/agents/hitl/pending', json: null },
    { url: '**/api/v1/usage/**', json: {} },
    {
      url: '**/api/v1/agents/chat/stream',
      method: 'POST',
      handler: async route => {
        bodies.push((route.request().postDataJSON() ?? {}) as ChatBody);
        await route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body:
            'data: {"type":"token","content":"Voici le point.","metadata":null}\n\n' +
            'data: {"type":"done","content":"","metadata":null}\n\n',
        });
      },
    },
  ];
}

/** `+` is the form encoding of a space; decodeURIComponent leaves it as is. */
function readableUrl(page: import('@playwright/test').Page): string {
  return decodeURIComponent(page.url()).replace(/\+/g, ' ');
}

/** Open one person's card from the overview and launch their 360°. */
async function launchOverviewFor(page: import('@playwright/test').Page, name: string) {
  // Anchored: the sibling star button is also named after the person.
  await page.getByRole('button', { name: new RegExp(`^${name}`) }).click();
  await expect(page.getByRole('heading', { level: 2, name })).toBeVisible({ timeout: 30_000 });
  // Every section is folded by design — the launch button lives inside the
  // scope section, next to the checkboxes that decide what it will read.
  await page.getByRole('button', { name: /Point 360/ }).click();
  await page.getByRole('button', { name: /Lancer le point 360/ }).click();
}

/** Back to the list the way a user does it — a client-side navigation. */
async function backToRelations(page: import('@playwright/test').Page) {
  await page.getByRole('navigation').getByRole('link', { name: 'Relations' }).click();
  await page.waitForURL(/\/dashboard\/relations/, { timeout: 30_000 });
}

test.describe('two chat deep links in a row', () => {
  test('the SECOND person is the one the chat receives', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    const bodies: ChatBody[] = [];
    await mockApi([...relationsRoutes(), ...chatRoutes(bodies)]);

    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(FIRST)).toBeVisible({ timeout: 30_000 });

    await launchOverviewFor(page, FIRST);
    await page.waitForURL(/\/dashboard\/chat/, { timeout: 30_000 });
    await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(1);
    expect(bodies[0].message).toContain(FIRST);
    expect(bodies[0].directive?.subject).toBe(FIRST);

    await backToRelations(page);
    await expect(page.getByText(SECOND)).toBeVisible({ timeout: 30_000 });

    await launchOverviewFor(page, SECOND);
    await page.waitForURL(/\/dashboard\/chat/, { timeout: 30_000 });

    await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(2);
    expect(bodies[1].message).toContain(SECOND);
    expect(bodies[1].message).not.toContain(FIRST);
    expect(bodies[1].directive?.subject).toBe(SECOND);

    // One-shot means one-shot: the params leave the URL once consumed, so a
    // page RELOAD cannot re-run the request behind the user's back.
    await page.waitForTimeout(1_000);
    expect(readableUrl(page)).not.toContain('intent=');
    expect(readableUrl(page)).not.toContain('subject=');
  });

  test('a ?draft= link must never come back as somebody else’s ?intent=', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // The sharpest form of the defect, and the dangerous one: a PREFILL link
    // that returns as a previous AUTO-SENT intent does not merely show the
    // wrong text — it executes a request the user never made on this click.
    await authenticate({ language: 'fr' });
    const bodies: ChatBody[] = [];
    await mockApi([...relationsRoutes(), ...chatRoutes(bodies)]);

    await page.goto('/fr/dashboard/relations');
    await expect(page.getByText(FIRST)).toBeVisible({ timeout: 30_000 });
    await launchOverviewFor(page, FIRST);
    await page.waitForURL(/\/dashboard\/chat/, { timeout: 30_000 });
    await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(1);

    await backToRelations(page);
    await page.getByRole('button', { name: new RegExp(`^${SECOND}`) }).click();
    await expect(page.getByRole('heading', { level: 2, name: SECOND })).toBeVisible({
      timeout: 30_000,
    });

    await page.getByRole('button', { name: 'Appeler' }).click();
    await page.waitForURL(/\/dashboard\/chat/, { timeout: 30_000 });

    // The COMPOSER is the oracle, not the address bar: `?draft=` is consumed
    // during render and leaves the URL immediately. What must never happen is
    // the previous `?intent=` coming back — it would be auto-sent.
    await expect(page.getByRole('textbox').first()).toHaveValue(new RegExp(SECOND), {
      timeout: 30_000,
    });
    // Give any late router write the chance to land before concluding.
    await page.waitForTimeout(1_000);
    expect(readableUrl(page)).not.toContain('intent=');
    expect(readableUrl(page)).not.toContain(FIRST);
    // And nothing was executed: a prefill never sends.
    expect(bodies).toHaveLength(1);
  });
});
