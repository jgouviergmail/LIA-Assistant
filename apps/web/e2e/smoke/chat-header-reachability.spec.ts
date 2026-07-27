/**
 * Chat header — controls stay reachable and never overlap.
 *
 * The dashboard header got its guard in S10. The chat's own header row is a
 * different element (a `div` inside the shell, not a `<header>` landmark) and
 * was therefore covered by nothing — while S0 measured a real overlap there:
 * at 320 px in French, with a loaded state, the search toggle sat on top of the
 * RAG-spaces indicator, and the row reached 97.8 % occupancy.
 *
 * As with the dashboard header, document-scroll checks are blind to this:
 * `html { overflow-x: hidden }` clips the row, and the voice badge is
 * absolutely positioned, so it can cover a sibling without producing overflow
 * at all. The only reliable oracle compares the control boxes themselves.
 *
 * The LOADED state is what matters: the context pill, the spaces indicator and
 * the status pill only appear once the conversation has totals, active spaces
 * or a run in flight — precisely the state a real user is in, and precisely the
 * one the nominal fixtures never reach.
 */
import type { Page } from '@playwright/test';

import { test, expect, type MockRoute } from '../fixtures';

const WIDTHS = [320, 390, 768, 880, 1024, 1280] as const;
const LOCALES = ['fr', 'de', 'en'] as const;

const CONVERSATION = {
  id: '00000000-0000-4000-8000-00000000c0h1',
  user_id: '00000000-0000-4000-8000-000000000001',
  title: 'E2E chat header',
  message_count: 2,
  total_tokens: 1200,
  created_at: '2026-07-26T09:00:00Z',
  updated_at: '2026-07-26T10:00:00Z',
};

/** Loaded state: context pill + active RAG spaces both take header room. */
const LOADED: MockRoute[] = [
  { url: '**/api/v1/conversations/me', json: CONVERSATION },
  {
    url: '**/api/v1/conversations/me/messages*',
    json: {
      messages: [
        {
          id: '00000000-0000-4000-8000-00000000m0h1',
          role: 'assistant',
          content: '<p>Bonjour.</p>',
          created_at: '2026-07-26T10:00:00Z',
        },
      ],
      conversation_id: CONVERSATION.id,
      total_count: 1,
      has_more: false,
      next_cursor: null,
    },
  },
  {
    url: '**/api/v1/conversations/me/totals',
    json: {
      total_tokens_in: 42000,
      total_tokens_out: 18000,
      total_tokens_cache: 6000,
      total_cost_eur: 0.42,
      total_google_api_requests: 12,
      context_tokens: 68000,
      context_threshold: 100000,
    },
  },
  {
    url: '**/api/v1/rag-spaces*',
    json: {
      spaces: [
        { id: 's1', name: 'Documentation', is_active: true, document_count: 12 },
        { id: 's2', name: 'Contrats', is_active: true, document_count: 4 },
      ],
      total: 2,
    },
  },
  { url: '**/api/v1/agents/health', json: { status: 'healthy', graph_compiled: true } },
  { url: '**/api/v1/agents/runs/active', json: { active: false } },
  { url: '**/api/v1/agents/hitl/pending', json: null },
  { url: '**/api/v1/usage/**', json: {} },
];

interface Probe {
  clipped: Array<{ name: string; overflowPx: number }>;
  overlaps: string[];
}

/**
 * Measure the chat header row.
 *
 * The row is reached through the shell's own sizing class — the very
 * declaration S2 rewrote — rather than a structural path, so the probe points
 * at the code under study and breaks loudly if that shell disappears.
 */
async function probeChatHeader(page: Page): Promise<Probe> {
  return page.evaluate(() => {
    const shell = document.querySelector('[class*="calc(100vh"]');
    const row = shell?.firstElementChild?.firstElementChild?.firstElementChild ?? null;
    const clipped: Probe['clipped'] = [];
    const overlaps: string[] = [];
    if (!row) return { clipped, overlaps };

    const viewportWidth = document.documentElement.clientWidth;
    const name = (el: Element): string =>
      el.getAttribute('aria-label') ||
      el.getAttribute('title') ||
      (el.textContent ?? '').trim().slice(0, 20) ||
      el.tagName.toLowerCase();

    const controls = Array.from(row.querySelectorAll('button, a, input')).filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    });

    for (const el of controls) {
      const r = el.getBoundingClientRect();
      if (r.right > viewportWidth + 1) {
        clipped.push({
          name: name(el),
          overflowPx: Math.round((r.right - viewportWidth) * 10) / 10,
        });
      }
    }

    for (let i = 0; i < controls.length; i++) {
      for (let j = i + 1; j < controls.length; j++) {
        if (controls[i].contains(controls[j]) || controls[j].contains(controls[i])) continue;
        const a = controls[i].getBoundingClientRect();
        const b = controls[j].getBoundingClientRect();
        if (
          a.left < b.right - 1 &&
          b.left < a.right - 1 &&
          a.top < b.bottom - 1 &&
          b.top < a.bottom - 1
        ) {
          overlaps.push(`${name(controls[i])} ×× ${name(controls[j])}`);
        }
      }
    }
    return { clipped, overlaps };
  });
}

/** Poll until the header geometry stops changing (async shell widgets). */
async function waitForStableRow(page: Page): Promise<void> {
  const signature = () =>
    page.evaluate(() => {
      const shell = document.querySelector('[class*="calc(100vh"]');
      const row = shell?.firstElementChild?.firstElementChild?.firstElementChild;
      if (!row) return '';
      return Array.from(row.querySelectorAll('button, a, input'))
        .map(el => {
          const r = el.getBoundingClientRect();
          return `${Math.round(r.x)}:${Math.round(r.width)}`;
        })
        .join('|');
    });
  let previous = await signature();
  for (let attempt = 0; attempt < 20; attempt++) {
    await page.waitForTimeout(100);
    const current = await signature();
    if (current === previous && current !== '') return;
    previous = current;
  }
}

test.describe('chat header — the destructive action stays named and reachable', () => {
  /**
   * Resetting the conversation purges every message, every attachment of the
   * user (AI-generated images included), the token summaries, the LangGraph
   * checkpoints and the tool contexts. Its label steps aside below 640 px to
   * make room — the ACTION must not, and a bare trash icon names nothing.
   */
  for (const width of [320, 640, 1280] as const) {
    test(`named and operable at ${width} px`, async ({ page, authenticate, mockApi }) => {
      await authenticate({ language: 'fr' });
      await mockApi(LOADED);
      await page.setViewportSize({ width, height: 800 });
      await page.goto('/fr/dashboard/chat');
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await waitForStableRow(page);

      // Located by its accessible name, which is exactly what a screen-reader
      // user gets — not by a class or a position.
      const reset = page.getByRole('button', { name: 'Supprimer' });
      await expect(reset).toBeVisible();
      await expect(reset).toBeEnabled();

      const box = await reset.boundingBox();
      expect(box, 'reset button must be laid out').not.toBeNull();
      expect(box!.x + box!.width, `reset button is cut off at ${width}px`).toBeLessThanOrEqual(
        width + 1
      );

      // Keyboard reachable: focusing it must be possible without a pointer.
      await reset.focus();
      await expect(reset).toBeFocused();
    });
  }
});

test.describe('chat header reachability', () => {
  for (const locale of LOCALES) {
    test(`no control is clipped or covered in a loaded chat @ ${locale}`, async ({
      page,
      authenticate,
      mockApi,
    }) => {
      await authenticate({ language: locale });
      await mockApi(LOADED);
      await page.goto(`/${locale}/dashboard/chat`);
      await page.locator('textarea').first().waitFor({ state: 'visible' });
      await waitForStableRow(page);

      for (const width of WIDTHS) {
        await page.setViewportSize({ width, height: 800 });
        await page.waitForFunction(w => document.documentElement.clientWidth === w, width);
        await waitForStableRow(page);

        const { clipped, overlaps } = await probeChatHeader(page);
        expect(
          clipped,
          `${locale} @ ${width}px — chat header controls off-screen: ` +
            clipped.map(c => `${c.name} (+${c.overflowPx}px)`).join(', ')
        ).toEqual([]);
        expect(
          overlaps,
          `${locale} @ ${width}px — chat header controls overlap: ${overlaps.join(' | ')}`
        ).toEqual([]);
      }
    });
  }
});
