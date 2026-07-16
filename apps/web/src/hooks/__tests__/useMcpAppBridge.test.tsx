/**
 * useMcpAppBridge — golden characterization of the JSON-RPC bridge (audit F011).
 *
 * These tests pin the EXACT current behavior of every protocol method (and the
 * security guards) BEFORE the CC-96 handler is decomposed into a module-level
 * dispatch table. They characterize behavior — they do not prescribe it — so
 * any drift during the decomposition fails loudly here.
 *
 * Harness: renderHook mounts the bridge against a real <iframe> element whose
 * contentWindow is stubbed (jsdom iframes never navigate); protocol messages
 * are dispatched as window MessageEvents with origin "null" (opaque-origin
 * sandbox) and `source` forced to the stubbed contentWindow.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useMcpAppBridge, MCP_APPS_PROTOCOL_VERSION } from '../useMcpAppBridge';
import type { McpAppRegistryPayload } from '@/types/mcp-apps';

const mcpAppCallTool = vi.hoisted(() => vi.fn());
const mcpAppReadResource = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api/mcp-apps', () => ({ mcpAppCallTool, mcpAppReadResource }));

const PAYLOAD: McpAppRegistryPayload = {
  tool_name: 'render_chart',
  server_name: 'TestServer',
  html_content: '<html></html>',
  tool_result: '{"ok": true}',
  server_id: 'srv-1',
  server_key: 'test',
  server_source: 'admin',
  resource_uri: 'ui://test/view',
  tool_arguments: { a: 1 },
};

interface Harness {
  iframe: HTMLIFrameElement;
  contentWindow: Window;
  postMessage: ReturnType<typeof vi.fn>;
  container: HTMLDivElement;
  unmount: () => void;
}

function mountBridge(payload: McpAppRegistryPayload = PAYLOAD): Harness {
  const postMessage = vi.fn();
  const contentWindow = { postMessage } as unknown as Window;
  const iframe = document.createElement('iframe');
  Object.defineProperty(iframe, 'contentWindow', { value: contentWindow, configurable: true });
  const container = document.createElement('div');
  container.appendChild(iframe);
  document.body.appendChild(container);

  const ref = { current: iframe };
  const { unmount } = renderHook(() => useMcpAppBridge(ref, payload));
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

/** Wait until the bridge posted `n` messages back to the iframe. */
async function postedCount(h: Harness, n: number): Promise<void> {
  await vi.waitFor(() => expect(h.postMessage).toHaveBeenCalledTimes(n));
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

beforeEach(() => {
  mcpAppCallTool.mockReset();
  mcpAppReadResource.mockReset();
});

describe('security guards', () => {
  it('ignores messages whose origin is not "null"', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 1, method: 'ping' }, { origin: 'https://evil.tld' });
    await flush();
    expect(harness.postMessage).not.toHaveBeenCalled();
  });

  it('ignores messages whose source is not our iframe', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 1, method: 'ping' }, { source: {} });
    await flush();
    expect(harness.postMessage).not.toHaveBeenCalled();
  });

  it('ignores non-JSON-RPC payloads', async () => {
    harness = mountBridge();
    dispatch(harness, { hello: 'world' });
    dispatch(harness, { jsonrpc: '2.0' }); // no method
    await flush();
    expect(harness.postMessage).not.toHaveBeenCalled();
  });
});

describe('ui/initialize', () => {
  it('responds with protocol version, host info and tool context', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 7, method: 'ui/initialize' });
    await postedCount(harness, 1);

    const response = harness.postMessage.mock.calls[0][0];
    expect(response.id).toBe(7);
    expect(response.result.protocolVersion).toBe(MCP_APPS_PROTOCOL_VERSION);
    expect(response.result.hostInfo.name).toBe('LIA');
    expect(response.result.hostContext.toolInfo.tool.name).toBe('render_chart');
    expect(response.result.hostContext.theme).toBe('light');
    expect(response.result.hostContext.platform).toBe('web');
    expect(response.result.hostCapabilities).toHaveProperty('serverTools');
    expect(response.result.hostCapabilities).toHaveProperty('openLinks');
  });

  it('reports the dark theme when documentElement has the dark class', async () => {
    document.documentElement.classList.add('dark');
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 1, method: 'ui/initialize' });
    await postedCount(harness, 1);
    expect(harness.postMessage.mock.calls[0][0].result.hostContext.theme).toBe('dark');
  });
});

describe('ui/notifications/initialized', () => {
  it('delivers tool-input then tool-result (structuredContent when JSON)', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', method: 'ui/notifications/initialized' });
    await postedCount(harness, 2);

    const [input] = harness.postMessage.mock.calls[0];
    expect(input.method).toBe('ui/notifications/tool-input');
    expect(input.params.arguments).toEqual({ a: 1 });

    const [result] = harness.postMessage.mock.calls[1];
    expect(result.method).toBe('ui/notifications/tool-result');
    expect(result.params.content).toEqual([{ type: 'text', text: '{"ok": true}' }]);
    expect(result.params.structuredContent).toEqual({ ok: true });
  });

  it('omits structuredContent when the tool result is not JSON', async () => {
    harness = mountBridge({ ...PAYLOAD, tool_result: 'plain text' });
    dispatch(harness, { jsonrpc: '2.0', method: 'ui/notifications/initialized' });
    await postedCount(harness, 2);
    const [result] = harness.postMessage.mock.calls[1];
    expect(result.params.structuredContent).toBeUndefined();
  });

  it('routes Excalidraw create_view through progressive tool-input-partial', async () => {
    harness = mountBridge({
      ...PAYLOAD,
      tool_name: 'create_view',
      server_name: 'Excalidraw MCP',
      tool_arguments: { elements: JSON.stringify([{ type: 'rectangle', id: 'r1' }]) },
    });
    dispatch(harness, { jsonrpc: '2.0', method: 'ui/notifications/initialized' });
    await vi.waitFor(() => expect(harness!.postMessage).toHaveBeenCalled());
    expect(harness.postMessage.mock.calls[0][0].method).toBe('ui/notifications/tool-input-partial');
  });

  it('drips Excalidraw groups in order: infra, shape+label, standalone, arrows last', async () => {
    // Pins the exact grouping of _groupElementsForDrip before its decomposition:
    // camera+background first, [shape, containerId-label] pairs and standalone
    // elements next (in encounter order), [arrow, free label] pairs at the end.
    const camera = { type: 'cameraUpdate', id: 'cam' };
    const bg = { type: 'rectangle', id: 'bg_main', strokeColor: 'transparent' };
    const rect = { type: 'rectangle', id: 'r1' };
    const rectLabel = { type: 'text', id: 't1', containerId: 'r1' };
    const arrow = { type: 'arrow', id: 'a1' };
    const arrowLabel = { type: 'text', id: 't2' }; // no containerId → arrow label
    const standalone = { type: 'text', id: 't3', containerId: 'zz' }; // not a label of prev
    const elements = [camera, bg, rect, rectLabel, arrow, arrowLabel, standalone];

    vi.useFakeTimers();
    try {
      harness = mountBridge({
        ...PAYLOAD,
        tool_name: 'create_view',
        server_name: 'Excalidraw MCP',
        tool_arguments: { elements: JSON.stringify(elements) },
      });
      dispatch(harness, { jsonrpc: '2.0', method: 'ui/notifications/initialized' });
      // 4 groups → 3 inter-drip delays (120 ms) + final pause (200 ms).
      await vi.advanceTimersByTimeAsync(3 * 120 + 200 + 50);

      const calls = harness.postMessage.mock.calls.map(c => c[0]);
      const partials = calls
        .filter(c => c.method === 'ui/notifications/tool-input-partial')
        .map(c => JSON.parse(c.params.arguments.elements as string));
      // Accumulated snapshots, one per drip group:
      expect(partials).toEqual([
        [camera, bg],
        [camera, bg, rect, rectLabel],
        [camera, bg, rect, rectLabel, standalone],
        [camera, bg, rect, rectLabel, standalone, arrow, arrowLabel],
      ]);
      // Then the final full tool-input + tool-result close the stream.
      expect(calls[calls.length - 2].method).toBe('ui/notifications/tool-input');
      expect(calls[calls.length - 1].method).toBe('ui/notifications/tool-result');
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('tools/call', () => {
  it('proxies to the API and wraps a successful JSON result', async () => {
    mcpAppCallTool.mockResolvedValue({ success: true, result: '{"x": 2}' });
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 3,
      method: 'tools/call',
      params: { name: 'sub_tool', arguments: { q: 'z' } },
    });
    await postedCount(harness, 1);

    expect(mcpAppCallTool).toHaveBeenCalledWith(PAYLOAD, 'sub_tool', { q: 'z' });
    const response = harness.postMessage.mock.calls[0][0];
    expect(response.id).toBe(3);
    expect(response.result.content).toEqual([{ type: 'text', text: '{"x": 2}' }]);
    expect(response.result.structuredContent).toEqual({ x: 2 });
  });

  it('maps an API failure to an isError tool result (not a JSON-RPC error)', async () => {
    mcpAppCallTool.mockResolvedValue({ success: false, error: 'nope' });
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 4, method: 'tools/call', params: { name: 't' } });
    await postedCount(harness, 1);

    const response = harness.postMessage.mock.calls[0][0];
    expect(response.result.isError).toBe(true);
    expect(response.result.content).toEqual([{ type: 'text', text: 'nope' }]);
  });

  it('maps a thrown API error to a JSON-RPC -32000 error for requests', async () => {
    mcpAppCallTool.mockRejectedValue(new Error('boom'));
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 5, method: 'tools/call', params: { name: 't' } });
    await postedCount(harness, 1);

    const response = harness.postMessage.mock.calls[0][0];
    expect(response.error.code).toBe(-32000);
    expect(response.error.message).toContain('boom');
  });
});

describe('resources/read', () => {
  it('wraps a successful read into MCP contents', async () => {
    mcpAppReadResource.mockResolvedValue({
      success: true,
      content: 'data',
      mime_type: 'text/csv',
    });
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 6,
      method: 'resources/read',
      params: { uri: 'ui://x/y' },
    });
    await postedCount(harness, 1);

    expect(mcpAppReadResource).toHaveBeenCalledWith(PAYLOAD, 'ui://x/y');
    const response = harness.postMessage.mock.calls[0][0];
    expect(response.result.contents).toEqual([
      { uri: 'ui://x/y', text: 'data', mimeType: 'text/csv' },
    ]);
  });

  it('maps a failed read to a JSON-RPC -32000 error', async () => {
    mcpAppReadResource.mockResolvedValue({ success: false, error: 'missing' });
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 8, method: 'resources/read', params: { uri: 'u' } });
    await postedCount(harness, 1);
    const response = harness.postMessage.mock.calls[0][0];
    expect(response.error).toEqual({ code: -32000, message: 'missing' });
  });
});

describe('ui/open-link', () => {
  it('opens https URLs in a new tab and acks the request', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 9,
      method: 'ui/open-link',
      params: { url: 'https://example.com/page' },
    });
    await postedCount(harness, 1);

    expect(open).toHaveBeenCalledWith('https://example.com/page', '_blank', 'noopener');
    expect(harness.postMessage.mock.calls[0][0].result).toEqual({});
    expect(harness.container.querySelector('.lia-mcp-app-widget__link-banner')).toBeNull();
  });

  it('refuses non-https URLs (no window.open) but still acks', async () => {
    const open = vi.spyOn(window, 'open').mockReturnValue({} as Window);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 10,
      method: 'ui/open-link',
      params: { url: 'javascript:alert(1)' },
    });
    await postedCount(harness, 1);
    expect(open).not.toHaveBeenCalled();
    expect(harness.postMessage.mock.calls[0][0].result).toEqual({});
  });

  it('injects a clickable banner when the popup is blocked', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null); // popup blocked
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 11,
      method: 'ui/open-link',
      params: { url: 'https://docs.example.com/x' },
    });
    await postedCount(harness, 1);

    const banner = harness.container.querySelector('.lia-mcp-app-widget__link-banner');
    expect(banner).not.toBeNull();
    const link = banner!.querySelector('a')!;
    expect(link.href).toBe('https://docs.example.com/x');
    expect(link.textContent).toBe('Open: docs.example.com');
    expect(link.rel).toBe('noopener');
  });
});

describe('ui/download-file', () => {
  beforeEach(() => {
    (URL as unknown as Record<string, unknown>).createObjectURL = vi.fn(() => 'blob:fake');
    (URL as unknown as Record<string, unknown>).revokeObjectURL = vi.fn();
  });

  it('downloads an embedded text resource via a temporary anchor', async () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 12,
      method: 'ui/download-file',
      params: {
        contents: [
          {
            type: 'resource',
            resource: { uri: 'ui://f/report.txt', text: 'hello', mimeType: 'text/plain' },
          },
        ],
      },
    });
    await postedCount(harness, 1);

    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake');
    expect(click).toHaveBeenCalledTimes(1);
    expect(harness.postMessage.mock.calls[0][0].result).toEqual({});
  });

  it('skips resource_link items with non-http(s) schemes (XSS guard)', async () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 13,
      method: 'ui/download-file',
      params: {
        contents: [
          { type: 'resource_link', uri: 'javascript:alert(1)', name: 'x' },
          { type: 'resource_link', uri: 'https://example.com/ok.pdf', name: 'ok.pdf' },
        ],
      },
    });
    await postedCount(harness, 1);
    // Only the https link triggered a download click.
    expect(click).toHaveBeenCalledTimes(1);
  });

  it('skips invalid base64 blobs without failing the request', async () => {
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 14,
      method: 'ui/download-file',
      params: {
        contents: [{ type: 'resource', resource: { uri: 'ui://f/x.bin', blob: '!!not-b64!!' } }],
      },
    });
    await postedCount(harness, 1);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(harness.postMessage.mock.calls[0][0].result).toEqual({});
  });
});

describe('notifications and acks', () => {
  it('resizes the iframe on size-changed, capped at 80% of the viewport', async () => {
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'ui/notifications/size-changed',
      params: { height: 50 },
    });
    await flush();
    expect(harness.iframe.style.height).toBe('50px');
    expect(harness.postMessage).not.toHaveBeenCalled(); // notification: no response

    const cap = window.innerHeight * 0.8; // NOT rounded by the implementation
    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'ui/notifications/size-changed',
      params: { height: 999999 },
    });
    await flush();
    expect(harness.iframe.style.height).toBe(`${cap}px`);
  });

  it('forwards notifications/message to the matching console level', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const dbg = vi.spyOn(console, 'debug').mockImplementation(() => undefined);
    harness = mountBridge();

    dispatch(harness, {
      jsonrpc: '2.0',
      method: 'notifications/message',
      params: { level: 'error', logger: 'widget', text: 'kaboom' },
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

    expect(err).toHaveBeenCalledWith('[MCP App: widget] kaboom');
    expect(warn).toHaveBeenCalledWith('[MCP App] meh');
    expect(dbg).toHaveBeenCalledWith('[MCP App] fyi');
    expect(harness.postMessage).not.toHaveBeenCalled();
  });

  it('acks ui/request-display-mode with inline mode', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 15, method: 'ui/request-display-mode' });
    await postedCount(harness, 1);
    expect(harness.postMessage.mock.calls[0][0].result).toEqual({ mode: 'inline' });
  });

  it('acks ui/message, ui/update-model-context and ui/resource-teardown requests', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 16, method: 'ui/message' });
    dispatch(harness, { jsonrpc: '2.0', id: 17, method: 'ui/update-model-context' });
    dispatch(harness, { jsonrpc: '2.0', id: 18, method: 'ui/resource-teardown' });
    await postedCount(harness, 3);
    for (const call of harness.postMessage.mock.calls) {
      expect(call[0].result).toEqual({});
    }
  });

  it('answers ping', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', id: 19, method: 'ping' });
    await postedCount(harness, 1);
    expect(harness.postMessage.mock.calls[0][0]).toEqual({ jsonrpc: '2.0', id: 19, result: {} });
  });

  it('returns -32601 for unknown request methods, stays silent for unknown notifications', async () => {
    harness = mountBridge();
    dispatch(harness, { jsonrpc: '2.0', method: 'ui/unknown-notification' });
    await flush();
    expect(harness.postMessage).not.toHaveBeenCalled();

    dispatch(harness, { jsonrpc: '2.0', id: 20, method: 'ui/unknown-request' });
    await postedCount(harness, 1);
    expect(harness.postMessage.mock.calls[0][0].error).toEqual({
      code: -32601,
      message: 'Method not found',
    });
  });
});

describe('lifecycle', () => {
  it('stops handling messages and removes banners on unmount', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    harness = mountBridge();
    dispatch(harness, {
      jsonrpc: '2.0',
      id: 21,
      method: 'ui/open-link',
      params: { url: 'https://example.com/x' },
    });
    await postedCount(harness, 1);
    expect(harness.container.querySelector('.lia-mcp-app-widget__link-banner')).not.toBeNull();

    harness.unmount();
    expect(harness.container.querySelector('.lia-mcp-app-widget__link-banner')).toBeNull();

    dispatch(harness, { jsonrpc: '2.0', id: 22, method: 'ping' });
    await flush();
    expect(harness.postMessage).toHaveBeenCalledTimes(1); // no new response after unmount
  });
});
