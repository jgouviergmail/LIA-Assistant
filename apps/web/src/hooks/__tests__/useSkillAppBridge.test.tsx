/**
 * useSkillAppBridge — golden characterization of the minimal skill-app bridge
 * (audit F011). Pins the exact behavior of every supported JSON-RPC method and
 * the security guards BEFORE the CC-49 message handler is decomposed into a
 * module-level dispatch table. Characterizes behavior — does not prescribe it —
 * so any drift during decomposition fails loudly here.
 *
 * Harness mirrors the MCP-bridge suite: renderHook mounts the bridge against a
 * real <iframe> with a stubbed contentWindow; protocol messages are dispatched
 * as window MessageEvents with origin "null" (srcDoc) and forced `source`.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useSkillAppBridge, SKILL_APPS_PROTOCOL_VERSION } from '../useSkillAppBridge';
import type { SkillAppRegistryPayload } from '@/types/skill-apps';

const PAYLOAD: SkillAppRegistryPayload = {
  skill_name: 'weather-card',
  html_content: '<html></html>',
  text_summary: 'weather',
  is_system_skill: true,
};

interface Harness {
  iframe: HTMLIFrameElement;
  contentWindow: Window;
  postMessage: ReturnType<typeof vi.fn>;
  container: HTMLDivElement;
  unmount: () => void;
}

function mountBridge(payload: SkillAppRegistryPayload = PAYLOAD): Harness {
  const postMessage = vi.fn();
  const contentWindow = { postMessage } as unknown as Window;
  const iframe = document.createElement('iframe');
  Object.defineProperty(iframe, 'contentWindow', { value: contentWindow, configurable: true });
  // No real srcDoc navigation in jsdom → readyState stays non-complete, so the
  // theme-push machinery waits on the (never-fired) load event and does not
  // interfere with the message-handler assertions.
  const container = document.createElement('div');
  container.appendChild(iframe);
  document.body.appendChild(container);

  const ref = { current: iframe };
  const { unmount } = renderHook(() => useSkillAppBridge(ref, payload));
  return { iframe, contentWindow, postMessage, container, unmount };
}

function dispatch(
  h: Harness,
  data: unknown,
  { origin = 'null', source }: { origin?: string; source?: unknown } = {}
): void {
  const event = new MessageEvent('message', { origin, data });
  Object.defineProperty(event, 'source', { value: source ?? h.contentWindow });
  window.dispatchEvent(event);
}

/** Posts that are handler RESPONSES — the theme/locale push notifications
 * (ui/theme-changed / ui/locale-changed, fired on mount + MutationObserver and
 * unrelated to the message handler under test) are filtered out. Inferred
 * `any[]` (like a vi.fn mock's `calls`) so response fields read ergonomically. */
function responses(h: Harness) {
  return h.postMessage.mock.calls
    .map(c => c[0])
    .filter(m => m.method !== 'ui/theme-changed' && m.method !== 'ui/locale-changed');
}

async function postedCount(h: Harness, n: number): Promise<void> {
  await vi.waitFor(() => expect(responses(h)).toHaveLength(n));
}

const flush = () => new Promise(resolve => setTimeout(resolve, 20));

let harness: Harness | null = null;

afterEach(() => {
  harness?.unmount();
  harness = null;
  document.body.innerHTML = '';
  document.documentElement.classList.remove('dark');
  vi.restoreAllMocks();
});

describe('security guards', () => {
  it('ignores non-"null" origins and source mismatches and non-JSON-RPC payloads', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 1, method: 'ping' }, { origin: 'https://x.tld' });
    dispatch(harness, { jsonrpc: '2.0', id: 1, method: 'ping' }, { source: {} });
    dispatch(harness, { hello: 'world' });
    dispatch(harness, { jsonrpc: '2.0' });
    await flush();
    expect(responses(harness)).toHaveLength(0);
  });
});

describe('ui/initialize', () => {
  it('responds with minimal capabilities (openLinks only) + skill context', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 5, method: 'ui/initialize' });
    await postedCount(harness, 1);

    const r = responses(harness)[0];
    expect(r.id).toBe(5);
    expect(r.result.protocolVersion).toBe(SKILL_APPS_PROTOCOL_VERSION);
    expect(r.result.hostInfo.name).toBe('LIA');
    expect(r.result.hostCapabilities).toEqual({ openLinks: {} });
    expect(r.result.hostCapabilities.serverTools).toBeUndefined();
    expect(r.result.hostContext.skill).toEqual({ name: 'weather-card', isSystem: true });
    expect(r.result.hostContext.theme).toBe('light');
    expect(r.result.hostContext.platform).toBe('web');
  });

  it('reports the dark theme when documentElement has the dark class', async () => {
    document.documentElement.classList.add('dark');
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 1, method: 'ui/initialize' });
    await postedCount(harness, 1);
    expect(responses(harness)[0].result.hostContext.theme).toBe('dark');
  });
});

describe('ui/notifications/initialized', () => {
  it('is a notification — no response', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', method: 'ui/notifications/initialized' });
    await flush();
    expect(responses(harness)).toHaveLength(0);
  });
});

describe('ui/open-link', () => {
  it('opens https URLs and acks the request', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 9,
      method: 'ui/open-link',
      params: { url: 'https://example.com/x' },
    });
    await postedCount(harness, 1);
    expect(open).toHaveBeenCalledWith('https://example.com/x', '_blank', 'noopener');
    expect(responses(harness)[0].result).toEqual({});
    expect(harness.container.querySelector('.lia-skill-app-widget__link-banner')).toBeNull();
  });

  it('refuses non-https URLs (no open) but still acks', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 10,
      method: 'ui/open',
      params: { url: 'http://insecure.tld' },
    });
    await postedCount(harness, 1);
    expect(open).not.toHaveBeenCalled();
    expect(responses(harness)[0].result).toEqual({});
  });

  it('injects a clickable banner when the popup is blocked', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 11,
      method: 'ui/open-link',
      params: { url: 'https://docs.example.com/y' },
    });
    await postedCount(harness, 1);
    const banner = harness.container.querySelector('.lia-skill-app-widget__link-banner');
    expect(banner).not.toBeNull();
    const link = banner!.querySelector('a')!;
    expect(link.href).toBe('https://docs.example.com/y');
    expect(link.textContent).toBe('Open: docs.example.com');
    expect(link.rel).toBe('noopener');
  });
});

describe('ui/notifications/size-changed', () => {
  it('clamps the iframe height to [80, 80% viewport] and releases the aspect ratio', async () => {
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'ui/notifications/size-changed',
      params: { height: 300 },
    });
    await flush();
    expect(harness.iframe.style.height).toBe('300px');
    expect(harness.iframe.style.aspectRatio).toBe('auto');
    expect(responses(harness)).toHaveLength(0);

    // Below the floor → clamped up to 80.
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'ui/notifications/size-changed',
      params: { height: 10 },
    });
    await flush();
    expect(harness.iframe.style.height).toBe('80px');

    // Above the cap → clamped to 80% of viewport.
    const cap = window.innerHeight * 0.8;
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'ui/notifications/size-changed',
      params: { height: 999999 },
    });
    await flush();
    expect(harness.iframe.style.height).toBe(`${cap}px`);
  });

  it('ignores a non-finite height', async () => {
    harness = mountBridge();
    harness.iframe.style.height = '123px';
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'ui/notifications/size-changed',
      params: { height: Infinity },
    });
    await flush();
    expect(harness.iframe.style.height).toBe('123px'); // unchanged
  });
});

describe('notifications/message', () => {
  it('forwards to the matching console level, no response', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const dbg = vi.spyOn(console, 'debug').mockImplementation(() => undefined);
    harness = mountBridge();

    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'notifications/message',
      params: { level: 'error', logger: 'w', text: 'boom' },
    });
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'notifications/message',
      params: { level: 'warning', text: 'meh' },
    });
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'notifications/message',
      params: { level: 'info', text: 'fyi' },
    });
    await flush();

    expect(err).toHaveBeenCalledWith('[Skill App: w] boom');
    expect(warn).toHaveBeenCalledWith('[Skill App] meh');
    expect(dbg).toHaveBeenCalledWith('[Skill App] fyi');
    expect(responses(harness)).toHaveLength(0);
  });
});

describe('ping + unknown methods', () => {
  it('answers ping', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 3, method: 'ping' });
    await postedCount(harness, 1);
    expect(responses(harness)[0]).toEqual({ jsonrpc: '2.0', id: 3, result: {} });
  });

  it('refuses unknown request methods with -32601, ignores unknown notifications', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', method: 'tools/call' }); // notification → silent
    await flush();
    expect(responses(harness)).toHaveLength(0);

    dispatch(harness, { jsonrpc: '2.0', id: 4, method: 'resources/read' });
    await postedCount(harness, 1);
    expect(responses(harness)[0].error).toEqual({
      code: -32601,
      message: 'Method not found',
    });
  });
});

describe('lifecycle', () => {
  it('stops handling and removes banners on unmount', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 7,
      method: 'ui/open-link',
      params: { url: 'https://example.com/z' },
    });
    await postedCount(harness, 1);
    expect(harness.container.querySelector('.lia-skill-app-widget__link-banner')).not.toBeNull();

    harness.unmount();
    expect(harness.container.querySelector('.lia-skill-app-widget__link-banner')).toBeNull();

    dispatch(harness, { jsonrpc: '2.0', id: 8, method: 'ping' });
    await flush();
    expect(responses(harness)).toHaveLength(1); // no new response post-unmount
  });
});
