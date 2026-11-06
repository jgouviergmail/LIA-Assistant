/**
 * PageAppWidget — a page the model wrote, in its frame (ADR-370).
 *
 * The sandbox and the bridge ARE the security boundary of a page: what they
 * refuse was measured on Chromium, Firefox and WebKit, and these tests hold the
 * attributes those measures were taken with. A page that freezes takes the tab
 * with it on all three engines, which is why a page read back from history waits
 * for a click.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { act, fireEvent, renderWithProviders, screen } from '@/__tests__/test-utils';
import type { RegistryItem } from '@/types/chat';

const { useRegistryItem } = vi.hoisted(() => ({ useRegistryItem: vi.fn() }));
vi.mock('@/lib/registry-context', () => ({ useRegistryItem }));
vi.mock('@/components/chat/CodeBlock', () => ({
  CodeBlock: ({ language, children }: { language: string; children: string }) => (
    <pre data-testid="codeblock" data-language={language}>
      {children}
    </pre>
  ),
}));

import { PageAppWidget } from '../PageAppWidget';

const PREFIX = '<!DOCTYPE html><meta policy>';
const SOURCE = '<html><body><p>🎃</p></body></html>';

function pageItem(overrides: Partial<RegistryItem> = {}, payload = {}): RegistryItem {
  return {
    id: 'page_app_1',
    type: 'PAGE_APP',
    payload: {
      title: 'Morpion',
      html_content: PREFIX + SOURCE,
      source_offset: PREFIX.length,
      initial_view: 'page',
      ...payload,
    },
    meta: { source: 'interactive_page', timestamp: '2026-11-05T09:00:00Z' },
    ...overrides,
  };
}

const render = () => renderWithProviders(<PageAppWidget registryId="page_app_1" />);
const frame = () => document.querySelector('iframe');

/** A message as the frame itself would post it. */
function postFromFrame(data: unknown, { origin = 'null', source = frame()?.contentWindow } = {}) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent('message', { data, origin, source: source as MessageEventSource })
    );
  });
}

const sizeMessage = (height: number) => ({
  jsonrpc: '2.0',
  method: 'ui/notifications/size-changed',
  params: { height },
});

beforeEach(() => {
  vi.clearAllMocks();
  useRegistryItem.mockReturnValue(pageItem());
});

afterEach(() => {
  vi.restoreAllMocks();
  // jsdom has no `scrollIntoView`: a test that gives it one takes it back.
  Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
});

describe('PageAppWidget — the frame', () => {
  it('runs the page under the exact sandbox that was measured', () => {
    render();
    expect(frame()?.getAttribute('sandbox')).toBe('allow-scripts allow-forms');
  });

  it('never grants the origin, popups, navigation or modals', () => {
    render();
    const sandbox = frame()?.getAttribute('sandbox') ?? '';
    for (const flag of [
      'allow-same-origin',
      'allow-popups',
      'allow-top-navigation',
      'allow-modals',
    ]) {
      expect(sandbox).not.toContain(flag);
    }
  });

  it('gives the frame the composed document and a translated accessible name', () => {
    render();
    expect(frame()?.getAttribute('srcdoc')).toBe(PREFIX + SOURCE);
    expect(frame()?.getAttribute('title')).toBe('page_apps.frame_title');
    expect(screen.getByRole('region', { name: 'page_apps.frame_title' })).toBeTruthy();
    expect(screen.getByText('Morpion')).toBeTruthy();
  });

  it('names a page that gave itself no title', () => {
    useRegistryItem.mockReturnValue(pageItem({}, { title: '' }));
    render();
    expect(screen.getByRole('region').getAttribute('aria-label')).toBeTruthy();
  });

  it('says it is unavailable rather than drawing an empty box', () => {
    useRegistryItem.mockReturnValue(undefined);
    render();
    expect(frame()).toBeNull();
    expect(screen.getByRole('status')).toBeTruthy();
  });

  it('refuses an item of another type', () => {
    useRegistryItem.mockReturnValue(pageItem({ type: 'SKILL_APP' }));
    render();
    expect(frame()).toBeNull();
  });

  it('reads a stored payload rather than assuming it', () => {
    useRegistryItem.mockReturnValue(pageItem({ payload: { html_content: 3 } }));
    render();
    expect(frame()).toBeNull();
    expect(screen.getByRole('status')).toBeTruthy();
  });
});

describe('PageAppWidget — live and restored', () => {
  it('runs a page of the current turn at once', () => {
    render();
    expect(frame()).not.toBeNull();
  });

  it('holds a page read back from history until it is asked for', () => {
    useRegistryItem.mockReturnValue(pageItem({ restored: true }));
    render();
    expect(frame()).toBeNull();
    expect(screen.getByRole('button', { name: 'page_apps.start' })).toBeTruthy();
  });

  it('starts it on a click, shows its top and hands it the focus', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    useRegistryItem.mockReturnValue(pageItem({ restored: true }));
    render();
    fireEvent.click(screen.getByRole('button', { name: 'page_apps.start' }));
    expect(frame()).not.toBeNull();
    expect(document.activeElement).toBe(frame());
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'start' });
  });

  it('never moves the chat for a page that started alone', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    render();
    expect(document.activeElement).not.toBe(frame());
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});

describe('PageAppWidget — the code', () => {
  it('shows the page as written, without what wraps it', async () => {
    render();
    fireEvent.click(screen.getByRole('button', { name: 'page_apps.show_code' }));
    const code = await screen.findByTestId('codeblock');
    expect(code.textContent).toBe(SOURCE);
    expect(code.getAttribute('data-language')).toBe('html');
  });

  it('keeps a running page alive behind the code, so a game is not lost', async () => {
    render();
    const running = frame();
    fireEvent.click(screen.getByRole('button', { name: 'page_apps.show_code' }));
    await screen.findByTestId('codeblock');
    expect(frame()).toBe(running);
    expect(running?.hidden).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'page_apps.show_page' }));
    expect(frame()).toBe(running);
    expect(running?.hidden).toBe(false);
  });

  it('opens on the code when that is what was asked, and runs nothing', async () => {
    useRegistryItem.mockReturnValue(pageItem({}, { initial_view: 'code' }));
    render();
    expect((await screen.findByTestId('codeblock')).textContent).toBe(SOURCE);
    expect(frame()).toBeNull();
  });

  it('asks before running a page opened on its code', async () => {
    useRegistryItem.mockReturnValue(pageItem({}, { initial_view: 'code' }));
    render();
    await screen.findByTestId('codeblock');
    fireEvent.click(screen.getByRole('button', { name: 'page_apps.show_page' }));
    expect(frame()).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'page_apps.start' }));
    expect(frame()).not.toBeNull();
  });
});

describe('PageAppWidget — what the frame may say', () => {
  it('follows the height of the page', () => {
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(1000);
    render();
    postFromFrame(sizeMessage(640));
    expect(frame()?.style.height).toBe('640px');
  });

  it('bounds that height', () => {
    vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(1000);
    render();
    postFromFrame(sizeMessage(99_999));
    expect(frame()?.style.height).toBe('800px');
    postFromFrame(sizeMessage(1));
    expect(frame()?.style.height).toBe('80px');
  });

  it('hears nobody but its own frame', () => {
    render();
    postFromFrame(sizeMessage(640), { source: window });
    expect(frame()?.style.height).toBe('');
  });

  it('hears nothing from a real origin', () => {
    render();
    postFromFrame(sizeMessage(640), { origin: 'https://example.org' });
    expect(frame()?.style.height).toBe('');
  });

  it('never opens a link for the page: the host is the exit the sandbox closes', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    render();
    for (const method of ['ui/open-link', 'ui/open']) {
      postFromFrame({ jsonrpc: '2.0', id: 1, method, params: { url: 'https://example.org/?x=1' } });
    }
    expect(open).not.toHaveBeenCalled();
  });

  it('shows the first failure of the page, as text', () => {
    render();
    const message = '<img src=x onerror=alert(1)> is not defined';
    postFromFrame({ jsonrpc: '2.0', method: 'ui/notifications/error', params: { message } });
    postFromFrame({
      jsonrpc: '2.0',
      method: 'ui/notifications/error',
      params: { message: 'second' },
    });
    const notice = screen.getByRole('status');
    expect(notice.textContent).toContain(message);
    expect(notice.textContent).not.toContain('second');
    expect(notice.querySelector('img')).toBeNull();
  });

  it('bounds a failure it is told, whatever the frame sends', () => {
    render();
    postFromFrame({
      jsonrpc: '2.0',
      method: 'ui/notifications/error',
      params: { message: 'x'.repeat(5000) },
    });
    expect((screen.getByRole('status').textContent ?? '').length).toBeLessThan(400);
  });

  it('ignores a malformed message', () => {
    render();
    postFromFrame(null);
    postFromFrame({ jsonrpc: '2.0', method: 'ui/notifications/error', params: { message: 3 } });
    postFromFrame({ jsonrpc: '2.0', method: 'ui/notifications/size-changed', params: {} });
    expect(screen.queryByRole('status')).toBeNull();
    expect(frame()?.style.height).toBe('');
  });
});

describe('PageAppWidget — restart', () => {
  it('runs the page anew and forgets its failure', () => {
    render();
    const before = frame();
    postFromFrame({ jsonrpc: '2.0', method: 'ui/notifications/error', params: { message: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'page_apps.restart' }));
    expect(frame()).not.toBe(before);
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('offers no restart before the page runs', () => {
    useRegistryItem.mockReturnValue(pageItem({ restored: true }));
    render();
    expect(screen.queryByRole('button', { name: 'page_apps.restart' })).toBeNull();
  });
});
