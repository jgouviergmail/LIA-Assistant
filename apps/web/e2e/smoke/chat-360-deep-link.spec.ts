/**
 * The 360° deep link, end to end — the journey production broke twice.
 *
 * Two defects, both measured on 2026-08-01, both invisible to a unit test
 * because they live in the seam between the URL, the history load and the send:
 *
 * 1. **The wrong person.** A 360° on one person, then another, then a third
 *    sent the FIRST one's sentence three times: the intent was captured at
 *    mount and the query was cleared through `window.history.replaceState`,
 *    behind the App Router's back.
 * 2. **The vanished message.** The auto-send raced the history load, whose
 *    `setMessages(page.messages)` — a server list that predated the send —
 *    wiped the optimistic bubble. The user saw the answer with no question
 *    above it, and the message reappeared only after a page refresh.
 * 3. **The unguaranteed capability** (ADR-191). Only prose travelled, so the
 *    planner was free to ignore the 360° tool — measured: it scored 0.853, the
 *    best of the whole catalogue, and the plan called the generic mail tool.
 *
 * A fourth behaviour surfaced while writing this file and is documented rather
 * than asserted: `?intent=` does not leave the URL when its removal is the only
 * router navigation of the page's life. See the note in the first test.
 *
 * Hermetic: every API call is mocked, the SSE body is scripted, and the POST
 * body is captured so the assertions are about WHAT was sent, not merely that
 * something was.
 */
import { test, expect, type MockRoute } from '../fixtures';

const SUBJECT = 'Paul Martin';
const INTENT = `Prépare un point 360° sur ${SUBJECT}`;

interface ChatBody {
  message?: string;
  directive?: { capability?: string; subject?: string };
}

/** History the server already holds — deliberately NOT empty (see below). */
const ARCHIVED = {
  id: '00000000-0000-4000-8000-000000000001',
  role: 'assistant',
  content: 'Bonjour, que puis-je faire ?',
  created_at: '2026-08-01T05:00:00Z',
};

const BASE: MockRoute[] = [
  { url: '**/api/v1/conversations/me/totals', json: {} },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
];

/** A slow history load, so the auto-send has every chance to win the race. */
function slowHistory(delayMs: number): MockRoute {
  return {
    url: '**/api/v1/conversations/me/messages*',
    handler: async route => {
      await new Promise(resolve => setTimeout(resolve, delayMs));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          messages: [ARCHIVED],
          conversation_id: '00000000-0000-4000-8000-0000000000ff',
          total_count: 1,
          has_more: false,
          next_cursor: null,
        }),
      });
    },
  };
}

function sseAnswer(text: string): string {
  return (
    `data: {"type":"token","content":${JSON.stringify(text)},"metadata":null}\n\n` +
    'data: {"type":"done","content":"","metadata":null}\n\n'
  );
}

/** Capture every chat POST body while answering with a scripted stream. */
function captureChat(bodies: ChatBody[], answer: string): MockRoute {
  return {
    url: '**/api/v1/agents/chat/stream',
    method: 'POST',
    handler: async route => {
      bodies.push((route.request().postDataJSON() ?? {}) as ChatBody);
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseAnswer(answer),
      });
    },
  };
}

test.describe('360° deep link', () => {
  test('the request carries its capability and survives the history load', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });

    const bodies: ChatBody[] = [];
    await mockApi([...BASE, slowHistory(600), captureChat(bodies, 'Voici le point.')]);

    await page.goto(
      `/fr/dashboard/chat?intent=${encodeURIComponent(INTENT)}` +
        `&capability=person_overview&subject=${encodeURIComponent(SUBJECT)}`
    );

    // 1. The capability travelled as DATA, not as a hint buried in prose.
    await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(1);
    expect(bodies[0].message).toBe(INTENT);
    expect(bodies[0].directive).toEqual({ capability: 'person_overview', subject: SUBJECT });

    // 2. The user's own message is ON SCREEN — the defect that made it
    // reappear only after a refresh. The archived bubble proves the history
    // load really landed, so this is not a race the test simply won.
    await expect(page.getByText(INTENT)).toBeVisible();
    await expect(page.getByText(ARCHIVED.content)).toBeVisible();
    await expect(page.getByText('Voici le point.')).toBeVisible();

    // 3. Exactly ONE send — the latch holds whatever the URL does.
    //
    // NOT asserted here, deliberately: that the deep link left the URL. It
    // does not when `clearIntent` is the ONLY router navigation of the page's
    // life — measured in this very browser, and reproduced with a PLAIN
    // `?intent=` carrying no directive at all, so it predates ADR-191. Two
    // explanations were tested and both disproved (see `useDeepLinkParams`).
    // Asserting it would ship a red test; weakening it into a green one that
    // checks nothing would be worse. The consequence is scoped and stated: a
    // page RELOAD re-executes the request; nothing replays within a session.
    await page.waitForTimeout(1500);
    expect(bodies).toHaveLength(1);
  });

  test('a second 360° on another person sends THAT person', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });

    const bodies: ChatBody[] = [];
    await mockApi([...BASE, slowHistory(0), captureChat(bodies, 'Voici le point.')]);

    await page.goto(
      `/fr/dashboard/chat?intent=${encodeURIComponent('Point 360° sur Marie Dupont')}` +
        '&capability=person_overview&subject=Marie%20Dupont'
    );
    await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(1);

    // Same route, new query: Next does NOT remount the page. This is exactly
    // where the mount-captured value kept replaying the first request.
    await page.goto(
      `/fr/dashboard/chat?intent=${encodeURIComponent(INTENT)}` +
        `&capability=person_overview&subject=${encodeURIComponent(SUBJECT)}`
    );

    await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(2);
    expect(bodies[1].message).toContain(SUBJECT);
    expect(bodies[1].message).not.toContain('Marie Dupont');
    expect(bodies[1].directive?.subject).toBe(SUBJECT);
  });

  test('a plain intent still travels without a directive', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    // Non-regression for every briefing card: their links carry prose only and
    // must keep producing the exact same request they always did.
    await authenticate({ language: 'fr' });

    const bodies: ChatBody[] = [];
    await mockApi([...BASE, slowHistory(0), captureChat(bodies, 'Il fera beau.')]);

    await page.goto(`/fr/dashboard/chat?intent=${encodeURIComponent('Quel temps demain ?')}`);

    await expect.poll(() => bodies.length, { timeout: 15_000 }).toBe(1);
    expect(bodies[0].message).toBe('Quel temps demain ?');
    expect(bodies[0].directive).toBeUndefined();
  });
});
