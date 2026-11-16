/**
 * A dialog's one column never grows past the dialog (owner, 2026-11-14), and a
 * name it quotes wraps (owner, 2026-11-15).
 *
 * An implicit grid track is as wide as the longest unbreakable line it holds.
 * A word wider than a phone's dialog widened the whole column: a line that asks
 * to wrap (`break-words`, which the app's dialogs put on names and messages)
 * could not, the dialog scrolled sideways, and its buttons went past its edge
 * with the column. Both primitives now declare one column that may shrink below
 * its content (`ui/dialog.tsx`, `ui/alert-dialog.tsx`).
 *
 * A title or a description quotes what people named — a server, a file, a
 * discussion — and a name written as one long word, with no rule of its own,
 * ran past the dialog's edge. The primitives' title and description wrap it.
 *
 * Only a laid-out page can prove it, and the oracle is geometry: the word wraps
 * inside the dialog, nothing scrolls sideways, and every button stays within the
 * dialog's edges.
 */
import type { Locator, Page } from '@playwright/test';

import { test, expect, loadedChatRoutes } from '../fixtures';
import { appConfig } from '../fixtures/dashboard-shell';
import { discussionFixture } from '../fixtures/discussions';
import type { UserMCPServer } from '../../src/hooks/useUserMCPServers';
import type { MCPServerBehavior, UserMCPDefaults } from '../../src/lib/mcp-behavior';

const PHONE = { width: 360, height: 740 };
/** A file name as people write them: no space, no hyphen, no place to break. */
const LONG_WORD = 'compte_rendu_du_comite_de_pilotage_du_quatorze_novembre_version_finale.pdf';
const LINE = 'phone-column-long-word';

/** Place the word right under the dialog's heading, as one more line of its column. */
async function placeLongWord(dialog: Locator): Promise<void> {
  await dialog.evaluate(
    (element, { word, line }) => {
      const paragraph = document.createElement('p');
      paragraph.dataset.testid = line;
      paragraph.style.overflowWrap = 'break-word';
      paragraph.textContent = word;
      element.firstElementChild?.after(paragraph);
    },
    { word: LONG_WORD, line: LINE }
  );
}

interface Geometry {
  viewport: number;
  dialogRight: number;
  innerRight: number;
  scrollWidth: number;
  clientWidth: number;
  wordRight: number;
  wordLines: number;
  buttonsPast: string[];
}

/** The dialog's edges, and those of the element holding the long word (`target`). */
async function measure(dialog: Locator, target: string): Promise<Geometry> {
  return dialog.evaluate((element, selector) => {
    const box = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    const innerRight = box.right - parseFloat(style.borderRightWidth);
    const word = element.querySelector<HTMLElement>(selector);
    if (!word) throw new Error(`the dialog holds no ${selector}`);
    // One rectangle per line box the text occupies; its right edge is the text's own.
    const rects: DOMRect[] = [];
    const walker = document.createTreeWalker(word, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const range = document.createRange();
      range.selectNodeContents(node);
      rects.push(...Array.from(range.getClientRects()).filter(rect => rect.width > 0));
    }
    return {
      viewport: document.documentElement.clientWidth,
      dialogRight: box.right,
      innerRight,
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
      wordRight: Math.max(...rects.map(rect => rect.right)),
      wordLines: new Set(rects.map(rect => Math.round(rect.top))).size,
      buttonsPast: Array.from(element.querySelectorAll('button'))
        .filter(button => button.getBoundingClientRect().right > innerRight + 1)
        .map(button => button.textContent?.trim() || button.getAttribute('aria-label') || '?'),
    };
  }, target);
}

/** The entrance zoom scales the box: it is over before anything is measured. */
async function settled(dialog: Locator): Promise<void> {
  await expect(dialog).toBeVisible();
  await dialog.evaluate(element =>
    Promise.all(element.getAnimations().map(animation => animation.finished))
  );
}

async function expectWordHolds(dialog: Locator, label: string, target: string): Promise<void> {
  const geometry = await measure(dialog, target);
  const report = `${label}: ${JSON.stringify(geometry)}`;
  expect(geometry.dialogRight, `${report} — the dialog stays on the screen`).toBeLessThanOrEqual(
    geometry.viewport
  );
  expect(geometry.wordLines, `${report} — the word wraps`).toBeGreaterThan(1);
  expect(geometry.wordRight, `${report} — the word stays inside`).toBeLessThanOrEqual(
    geometry.innerRight + 1
  );
  expect(geometry.scrollWidth, `${report} — nothing scrolls sideways`).toBeLessThanOrEqual(
    geometry.clientWidth + 1
  );
  expect(geometry.buttonsPast, `${report} — every button within the edges`).toEqual([]);
}

async function expectColumnHolds(dialog: Locator, label: string): Promise<void> {
  await settled(dialog);
  await placeLongWord(dialog);
  await expectWordHolds(dialog, label, `[data-testid="${LINE}"]`);
}

const stamp = '2026-11-15T10:00:00Z';
const serverId = '11111111-1111-4111-8111-1111111111bb';
/** A server the person named after a file, as one long word. */
const server: UserMCPServer = {
  id: serverId,
  name: LONG_WORD,
  url: 'https://notes.example.test/mcp',
  plugin_id: null,
  auth_type: 'none',
  status: 'active',
  is_enabled: true,
  domain_description: 'Personal notes',
  timeout_seconds: 30,
  hitl_required: null,
  iterative_mode: false,
  react_expand_iterative: null,
  suspended_tool_choices: 0,
  header_name: null,
  has_credentials: false,
  has_oauth_credentials: false,
  oauth_scopes: null,
  tool_count: 0,
  tools: [],
  last_connected_at: stamp,
  last_error: null,
  created_at: stamp,
  updated_at: stamp,
};
const defaults: UserMCPDefaults = {
  confirmation_instance: true,
  confirmation_account: null,
  confirmation_effective: true,
  react_direct_tools_default: true,
  dedicated_agents_available: true,
};
const behavior: MCPServerBehavior = {
  confirmation: { always: true, source: 'instance' },
  pipeline: { driver: 'direct', before_task: false, per_call: 'card_after_task' },
  react: { driver: 'direct', before_task: false, per_call: 'in_loop' },
  tools: [],
  unattended_refused: [],
  notes: [],
};

async function openServerBehavior(page: Page): Promise<Locator> {
  await page.goto('/en/dashboard/settings?section=mcp-servers');
  // On a phone a card's actions are in its menu.
  await page.getByRole('button', { name: `Actions — ${LONG_WORD}` }).click();
  await page.getByRole('menuitem', { name: 'What it will do' }).click();
  return page.getByRole('dialog', { name: `What ${LONG_WORD} will do` });
}

test.describe('a dialog read whole on a phone', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(PHONE);
  });

  test('an alert dialog keeps its column when a word is wider than it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'fr' });
    await mockApi(loadedChatRoutes());
    await page.goto('/fr/dashboard/chat');
    await page.locator('textarea').first().waitFor({ state: 'visible' });

    await page.getByRole('button', { name: 'Réinitialiser' }).click();
    await expectColumnHolds(page.getByRole('alertdialog'), 'reset confirmation');
  });

  test('a dialog keeps its column when a word is wider than it', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    const user = await authenticate({ language: 'fr' });
    await mockApi(discussionFixture(user.id).routes);
    await page.goto('/fr/dashboard/chat');
    await expect(page.locator('textarea').first()).toBeEnabled();

    await page.getByRole('button', { name: 'Discussions — Principale', exact: true }).click();
    await expectColumnHolds(
      page.getByRole('dialog', { name: 'Discussions', exact: true }),
      'discussions list'
    );
  });

  test('a title wraps the name it quotes when the name is wider than the dialog', async ({
    page,
    authenticate,
    mockApi,
  }) => {
    await authenticate({ language: 'en' });
    await mockApi([
      {
        url: '**/api/v1/config',
        json: { ...appConfig, features: { ...appConfig.features, mcp_enabled: true } },
      },
      { url: '**/api/v1/notifications/broadcasts/unread', json: { broadcasts: [] } },
      {
        url: '**/api/v1/mcp/servers',
        method: 'GET',
        json: { servers: [server], total: 1, defaults },
      },
      { url: `**/api/v1/mcp/servers/${serverId}/behavior`, method: 'GET', json: behavior },
    ]);

    const dialog = await openServerBehavior(page);
    await settled(dialog);
    await expectWordHolds(dialog, 'server behavior title', 'h2');
  });
});
