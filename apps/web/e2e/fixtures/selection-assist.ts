/** Native selection journeys share the same declared Tools and selection contracts. */
import { expect, type Locator } from '@playwright/test';
import type { MockRoute } from './api-mock';
import { appConfig } from './dashboard-shell';

/** Replay the native-selection event gap; the OS menu itself is outside browser automation. */
export async function beginNativeTouchSelection(
  field: Locator,
  terminal: 'missing' | 'cancelled'
): Promise<void> {
  await field.evaluate((element, ended) => {
    element.dispatchEvent(
      new PointerEvent('pointerdown', { bubbles: true, pointerId: 12, pointerType: 'touch' })
    );
    // Replay the touches list the observer reads without depending on a mobile
    // Touch constructor in desktop engines or replacing application code.
    const touch = new Event('touchstart', { bubbles: true });
    Object.defineProperty(touch, 'touches', { value: [{ identifier: 52 }] });
    element.dispatchEvent(touch);
    if (ended === 'cancelled')
      element.dispatchEvent(
        new PointerEvent('pointercancel', { bubbles: true, pointerId: 12, pointerType: 'touch' })
      );
    if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement)
      element.setSelectionRange(7, 16);
    else {
      const range = document.createRange();
      range.setStart(element.firstChild!, 7);
      range.setEnd(element.firstChild!, 16);
      window.getSelection()?.removeAllRanges();
      window.getSelection()?.addRange(range);
    }
    element.dispatchEvent(new Event('selectionchange', { bubbles: false }));
  }, terminal);
}

export async function endNativeTouchSelection(field: Locator): Promise<void> {
  await field.evaluate(element => {
    const touch = new Event('touchend', { bubbles: true });
    Object.defineProperty(touch, 'touches', { value: [] });
    element.dispatchEvent(touch);
  });
}

export async function undoNativeEdit(
  field: Locator,
  browserName: 'chromium' | 'firefox' | 'webkit'
): Promise<void> {
  await field.focus();
  await expect(field).toBeFocused();
  if (browserName === 'webkit' && process.platform === 'linux') {
    // The WebKitGTK test embedder does not bind Ctrl+Z, even in a bare input.
    // Exercise its actual undo stack, never a value setter or a simulated input.
    expect(await field.evaluate(element => element.ownerDocument.queryCommandEnabled('undo'))).toBe(
      true
    );
    expect(await field.evaluate(element => element.ownerDocument.execCommand('undo'))).toBe(true);
    return;
  }
  await field.press('ControlOrMeta+z');
}

export const selectionOffer = {
  text_max_chars: 8000,
  question_max_chars: 500,
  language_max_chars: 40,
  internet_available: true,
  read_aloud_available: true,
  internet_timeout_seconds: 360,
  call_timeout_seconds: 120,
  heartbeat_seconds: 10,
  destinations: [],
};
export const selectionRoutes: MockRoute[] = [
  {
    url: '**/api/v1/config',
    json: {
      ...appConfig,
      capabilities: {
        workbench: { enabled: true, family: 'work' },
        tool_assists: { enabled: true, family: 'work' },
      },
    },
  },
  { url: '**/api/v1/tool-assists/selection', json: selectionOffer },
  {
    url: '**/api/v1/workbench',
    json: {
      tools: ['mail', 'tasks', 'calendar', 'contacts', 'files', 'lights'].map(tool => ({
        tool,
        state: tool === 'mail' ? 'ready' : 'not_connected',
        provider: tool === 'mail' ? 'google_gmail' : null,
        features: [],
        bounds: {
          recipient_query_min_chars: 2,
          recipients_max: 100,
          recipient_max_chars: 320,
          subject_max_chars: 998,
          body_max_chars: 100000,
        },
      })),
      limits: {
        page_size: 25,
        search_max_chars: 500,
        assist_text_max_chars: 8000,
        assist_instruction_max_chars: 500,
        send_undo_seconds: 0,
        draft_autosave_seconds: 0,
      },
    },
  },
  {
    url: '**/api/v1/workbench/mail/folders',
    json: { folders: [{ id: 'system:inbox', kind: 'system', role: 'inbox', name: null }] },
  },
  { url: '**/api/v1/workbench/mail/counts', json: { unread: {}, total_unread: 0 } },
  { url: '**/api/v1/workbench/mail/messages*', json: { items: [], next_page_token: null } },
  { url: '**/api/v1/workbench/mail/signature*', json: { text: '', html: '' } },
  { url: '**/api/v1/workbench/mail/recipients*', json: { items: [] } },
];

export const dictationEnabled = {
  url: '**/api/v1/config',
  json: {
    ...appConfig,
    capabilities: {
      workbench: { enabled: true, family: 'work' },
      tool_assists: { enabled: true, family: 'work' },
      stt: { enabled: true, family: 'voice' },
    },
  },
};
