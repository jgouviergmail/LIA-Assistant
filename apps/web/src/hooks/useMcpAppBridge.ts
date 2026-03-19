/**
 * useMcpAppBridge — PostMessage JSON-RPC bridge for MCP App iframes.
 *
 * Implements the MCP Apps protocol (ext-apps spec 2026-01-26):
 * 1. View sends `ui/initialize` request → Host responds with capabilities
 * 2. View sends `ui/notifications/initialized` → Host sends tool-input then tool-result
 * 3. Bidirectional: tools/call, resources/read, ui/open-link, ui/download-file
 *
 * Security:
 * - Validates origin === "null" (srcdoc iframes)
 * - Validates event.source matches our iframe ref
 * - Only allows https:// URLs for ui/open-link
 * - Mounted guard prevents postMessage to destroyed iframes
 *
 * Phase: evolution F2.5 — MCP Apps
 */

import { useEffect, type RefObject } from 'react';
import type { McpAppRegistryPayload, McpAppBridgeMessage } from '@/types/mcp-apps';
import { mcpAppCallTool, mcpAppReadResource } from '@/lib/api/mcp-apps';
import { APP_VERSION } from '@/lib/version';

export const MCP_APPS_PROTOCOL_VERSION = '2026-01-26';

export function useMcpAppBridge(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  payload: McpAppRegistryPayload
): void {
  useEffect(() => {
    let mounted = true;

    /** Send tool-input + tool-result notifications (after initialization handshake). */
    const sendToolData = () => {
      if (!mounted || !iframeRef.current?.contentWindow) return;

      // Excalidraw progressive rendering: drip elements one by one via
      // tool-input-partial, then send final tool-input + tool-result.
      // The widget's morphdom + CSS animations handle smooth progressive build.
      if (_isExcalidrawCreateView(payload)) {
        _sendExcalidrawProgressive(iframeRef, payload, () => mounted);
        return;
      }

      const cw = iframeRef.current.contentWindow;

      // Phase 1: ui/notifications/tool-input — complete tool call arguments
      cw.postMessage(
        {
          jsonrpc: '2.0',
          method: 'ui/notifications/tool-input',
          params: { arguments: payload.tool_arguments ?? {} },
        },
        '*'
      );

      // Phase 2: ui/notifications/tool-result — tool execution result
      _sendToolResult(cw, payload);
    };

    const handler = async (event: MessageEvent) => {
      // Security: srcdoc iframes have origin "null"
      if (event.origin !== 'null') return;
      // Security: validate source is our iframe
      if (event.source !== iframeRef.current?.contentWindow) return;

      const msg = event.data as McpAppBridgeMessage;
      if (msg?.jsonrpc !== '2.0' || !msg.method) return;

      // JSON-RPC 2.0: Messages without `id` are notifications — must NOT receive
      // a response. Only messages with `id` are requests that require a response.
      const isRequest = msg.id !== undefined && msg.id !== null;

      let response: McpAppBridgeMessage | null = null;
      try {
        switch (msg.method) {
          // ── MCP Apps protocol handshake ──────────────────────────────
          case 'ui/initialize': {
            // View sends initialize request → Host responds with capabilities.
            const theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
            const iframe = iframeRef.current;
            response = {
              jsonrpc: '2.0',
              id: msg.id,
              result: {
                protocolVersion: MCP_APPS_PROTOCOL_VERSION,
                hostInfo: { name: 'LIA', version: APP_VERSION },
                hostCapabilities: {
                  serverTools: {},
                  serverResources: {},
                  openLinks: {},
                  downloadFile: {},
                },
                hostContext: {
                  toolInfo: {
                    tool: {
                      name: payload.tool_name,
                      inputSchema: payload.tool_input_schema ?? { type: 'object' },
                    },
                  },
                  theme,
                  containerDimensions: {
                    maxWidth: iframe?.clientWidth || undefined,
                    maxHeight: iframe?.clientHeight || Math.round(window.innerHeight * 0.8),
                  },
                  locale: document.documentElement.lang || 'fr',
                  platform: 'web',
                },
              },
            };
            break;
          }
          case 'ui/notifications/initialized': {
            // View confirms initialization complete — deliver tool data.
            sendToolData();
            return; // Notification — no response needed
          }

          // ── MCP tool/resource proxying ───────────────────────────────
          case 'tools/call': {
            const params = msg.params as
              | { name?: string; arguments?: Record<string, unknown> }
              | undefined;
            const apiResult = await mcpAppCallTool(
              payload,
              params?.name ?? '',
              params?.arguments ?? {}
            );
            // Transform API wrapper to MCP CallToolResult format
            if (apiResult.success) {
              const text = apiResult.result ?? '';
              const callToolResult: Record<string, unknown> = {
                content: [{ type: 'text', text }],
              };
              try {
                const parsed = JSON.parse(text);
                if (typeof parsed === 'object' && parsed !== null) {
                  callToolResult.structuredContent = parsed;
                }
              } catch {
                // Not JSON — text content only
              }
              response = { jsonrpc: '2.0', id: msg.id, result: callToolResult };
            } else {
              response = {
                jsonrpc: '2.0',
                id: msg.id,
                result: {
                  content: [{ type: 'text', text: apiResult.error ?? 'Tool call failed' }],
                  isError: true,
                },
              };
            }
            break;
          }
          case 'resources/read': {
            const params = msg.params as { uri?: string } | undefined;
            const apiResult = await mcpAppReadResource(payload, params?.uri ?? '');
            // Transform API wrapper to MCP ReadResourceResult format
            if (apiResult.success) {
              response = {
                jsonrpc: '2.0',
                id: msg.id,
                result: {
                  contents: [
                    {
                      uri: params?.uri ?? '',
                      text: apiResult.content ?? '',
                      mimeType: apiResult.mime_type ?? 'text/plain',
                    },
                  ],
                },
              };
            } else {
              response = {
                jsonrpc: '2.0',
                id: msg.id,
                error: { code: -32000, message: apiResult.error ?? 'Resource not found' },
              };
            }
            break;
          }

          // ── Host capabilities ───────────────────────────────────────
          case 'ui/open-link':
          case 'ui/open': {
            const params = msg.params as { url?: string } | undefined;
            // Security: only allow https:// URLs
            if (typeof params?.url === 'string' && params.url.startsWith('https://')) {
              // window.open may be blocked — postMessage handlers from sandboxed
              // iframes don't carry user activation.
              const opened = window.open(params.url, '_blank', 'noopener');
              if (!opened) {
                // Popup blocked — inject a clickable link banner above the iframe
                const container = iframeRef.current?.parentElement;
                if (container) {
                  // Remove any previous banner
                  container.querySelector('.lia-mcp-app-widget__link-banner')?.remove();
                  const banner = document.createElement('div');
                  banner.className = 'lia-mcp-app-widget__link-banner';
                  const hostname = new URL(params.url).hostname;
                  const link = document.createElement('a');
                  link.href = params.url;
                  link.target = '_blank';
                  link.rel = 'noopener';
                  link.textContent = `Open: ${hostname}`;
                  link.addEventListener('click', () => {
                    setTimeout(() => banner.remove(), 200);
                  });
                  const closeBtn = document.createElement('button');
                  closeBtn.textContent = '\u00d7';
                  closeBtn.className = 'lia-mcp-app-widget__link-close';
                  closeBtn.addEventListener('click', e => {
                    e.preventDefault();
                    banner.remove();
                  });
                  banner.appendChild(link);
                  banner.appendChild(closeBtn);
                  container.insertBefore(banner, iframeRef.current);
                }
              }
            }
            if (isRequest) {
              response = { jsonrpc: '2.0', id: msg.id, result: {} };
            }
            break;
          }
          case 'ui/download-file': {
            // SDK sends EmbeddedResource or ResourceLink per MCP Apps spec
            const params = msg.params as
              | {
                  contents?: Array<{
                    type?: string;
                    resource?: {
                      uri?: string;
                      text?: string;
                      blob?: string;
                      mimeType?: string;
                    };
                    uri?: string;
                    name?: string;
                    mimeType?: string;
                  }>;
                }
              | undefined;
            if (params?.contents) {
              for (const item of params.contents) {
                if (item.type === 'resource' && item.resource) {
                  // EmbeddedResource: {type: "resource", resource: {uri, text|blob, mimeType}}
                  const res = item.resource;
                  const filename = res.uri?.split('/').pop() || 'download';
                  let blob: Blob;
                  if (res.blob) {
                    try {
                      const binary = atob(res.blob);
                      const bytes = new Uint8Array(binary.length);
                      for (let i = 0; i < binary.length; i++) {
                        bytes[i] = binary.charCodeAt(i);
                      }
                      blob = new Blob([bytes], {
                        type: res.mimeType || 'application/octet-stream',
                      });
                    } catch {
                      // Invalid base64 — skip this resource
                      continue;
                    }
                  } else if (res.text) {
                    blob = new Blob([res.text], { type: res.mimeType || 'text/plain' });
                  } else {
                    continue;
                  }
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = filename;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                } else if (item.type === 'resource_link' && item.uri) {
                  // Security: only allow http(s) URLs (prevent javascript: / data: XSS)
                  if (!item.uri.startsWith('https://') && !item.uri.startsWith('http://')) {
                    continue;
                  }
                  // ResourceLink: trigger download via anchor
                  const a = document.createElement('a');
                  a.href = item.uri;
                  a.download = item.name || item.uri.split('/').pop() || 'download';
                  a.target = '_blank';
                  a.rel = 'noopener';
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                }
              }
            }
            if (isRequest) {
              response = { jsonrpc: '2.0', id: msg.id, result: {} };
            }
            break;
          }
          case 'ui/request-display-mode': {
            // Acknowledge — we only support inline mode for now.
            // SDK Zod schema requires { mode: "inline"|"fullscreen"|"pip" }.
            if (isRequest) {
              response = { jsonrpc: '2.0', id: msg.id, result: { mode: 'inline' } };
            }
            break;
          }
          case 'ui/message':
          case 'ui/update-model-context': {
            // Acknowledge but no-op for now (no chat integration yet)
            if (isRequest) {
              response = { jsonrpc: '2.0', id: msg.id, result: {} };
            }
            break;
          }
          case 'ui/resource-teardown': {
            if (isRequest) {
              response = { jsonrpc: '2.0', id: msg.id, result: {} };
            }
            break;
          }

          // ── Notifications from View (no response) ───────────────────
          case 'ui/notifications/size-changed': {
            // Dynamically resize iframe to match app's requested size
            const sizeParams = msg.params as { height?: number; width?: number } | undefined;
            if (iframeRef.current && sizeParams?.height) {
              const maxH = window.innerHeight * 0.8;
              iframeRef.current.style.height = `${Math.min(sizeParams.height, maxH)}px`;
            }
            return;
          }

          // ── MCP logging ──────────────────────────────────────────────
          case 'notifications/message': {
            // Standard MCP logging notification — forward to browser console
            // Spec: { level: string, logger?: string, text: string }
            const logParams = msg.params as
              | { level?: string; logger?: string; text?: string }
              | undefined;
            const logMsg = `[MCP App${logParams?.logger ? `: ${logParams.logger}` : ''}] ${String(logParams?.text ?? '')}`;
            if (logParams?.level === 'error') console.error(logMsg);
            else if (logParams?.level === 'warning') console.warn(logMsg);
            else console.debug(logMsg);
            return; // Notification — no response
          }

          // ── Misc ────────────────────────────────────────────────────
          case 'ping':
            response = { jsonrpc: '2.0', id: msg.id, result: {} };
            break;
          default:
            // Unknown method: only send error response for requests (with id),
            // silently ignore notifications (without id) per JSON-RPC 2.0 spec.
            if (isRequest) {
              response = {
                jsonrpc: '2.0',
                id: msg.id,
                error: { code: -32601, message: 'Method not found' },
              };
            }
            break;
        }
      } catch (err) {
        // Only send error response for requests, not for notifications
        if (isRequest) {
          response = {
            jsonrpc: '2.0',
            id: msg.id,
            error: { code: -32000, message: String(err) },
          };
        } else {
          return;
        }
      }

      // Guard: don't postMessage if component unmounted during await
      if (mounted && response) {
        iframeRef.current?.contentWindow?.postMessage(response, '*');
      }
    };

    window.addEventListener('message', handler);
    const iframeEl = iframeRef.current;

    return () => {
      mounted = false;
      window.removeEventListener('message', handler);
      // Cleanup any injected DOM banners (ui/open-link fallback)
      iframeEl?.parentElement
        ?.querySelectorAll('.lia-mcp-app-widget__link-banner')
        .forEach(el => el.remove());
    };
  }, [iframeRef, payload]);
}

// ---------------------------------------------------------------------------
// Excalidraw progressive rendering helpers (isolated — no core changes)
// ---------------------------------------------------------------------------

/** Delay between progressive element sends (ms). */
const _EXCALIDRAW_DRIP_DELAY = 120;

/** Detect Excalidraw create_view calls. */
function _isExcalidrawCreateView(payload: McpAppRegistryPayload): boolean {
  return (
    payload.tool_name === 'create_view' &&
    payload.server_name.toLowerCase().includes('excalidraw') &&
    typeof payload.tool_arguments?.elements === 'string'
  );
}

/** Send tool-result notification (shared by normal and progressive paths). */
function _sendToolResult(cw: Window, payload: McpAppRegistryPayload): void {
  const resultParams: Record<string, unknown> = {
    content: [{ type: 'text', text: payload.tool_result }],
  };
  try {
    const parsed = JSON.parse(payload.tool_result);
    if (typeof parsed === 'object' && parsed !== null) {
      resultParams.structuredContent = parsed;
    }
  } catch {
    // Not JSON — content-only is fine
  }
  cw.postMessage(
    { jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: resultParams },
    '*'
  );
}

/**
 * Excalidraw progressive rendering: drip elements one by one via
 * ``tool-input-partial``, then send final ``tool-input`` + ``tool-result``.
 *
 * The Excalidraw widget natively handles ``ontoolinputpartial``:
 * - Parses partial JSON (closes array at last complete ``}``)
 * - Renders via ``exportToSvg`` + ``morphdom`` (only new elements animate)
 * - CSS animations: shapes fade in (0.5s), lines draw on (0.6s)
 * - Pencil sound effects for each new element
 * - Camera viewport lerps smoothly to fit content
 *
 * This simulates the streaming experience that would normally come from
 * ``ontoolinputpartial`` during LLM token generation in Claude Desktop.
 */
async function _sendExcalidrawProgressive(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  payload: McpAppRegistryPayload,
  isMounted: () => boolean
): Promise<void> {
  const elementsStr = payload.tool_arguments?.elements as string;
  let elements: unknown[];
  try {
    elements = JSON.parse(elementsStr);
    if (!Array.isArray(elements)) {
      // Not a valid array — fall back to normal send
      _sendNormal(iframeRef, payload);
      return;
    }
  } catch {
    _sendNormal(iframeRef, payload);
    return;
  }

  // Group elements for progressive sending:
  // - Camera + background first (instant)
  // - Then shape+label pairs (one drip per component)
  // - Then arrows (one drip per arrow)
  const groups = _groupElementsForDrip(elements);

  // Send each group as a partial update
  const accumulated: unknown[] = [];
  for (let i = 0; i < groups.length; i++) {
    if (!isMounted() || !iframeRef.current?.contentWindow) return;

    accumulated.push(...groups[i]);
    const partialJson = JSON.stringify(accumulated);

    iframeRef.current.contentWindow.postMessage(
      {
        jsonrpc: '2.0',
        method: 'ui/notifications/tool-input-partial',
        params: { arguments: { elements: partialJson } },
      },
      '*'
    );

    // Wait between drips (skip delay for the last group)
    if (i < groups.length - 1) {
      await new Promise(r => setTimeout(r, _EXCALIDRAW_DRIP_DELAY));
    }
  }

  // Small pause before final send
  await new Promise(r => setTimeout(r, 200));
  if (!isMounted() || !iframeRef.current?.contentWindow) return;

  const cw = iframeRef.current.contentWindow;

  // Send final complete tool-input
  cw.postMessage(
    {
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-input',
      params: { arguments: payload.tool_arguments ?? {} },
    },
    '*'
  );

  // Send tool-result
  _sendToolResult(cw, payload);
}

/** Fallback: send tool-input + tool-result normally. */
function _sendNormal(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  payload: McpAppRegistryPayload
): void {
  const cw = iframeRef.current?.contentWindow;
  if (!cw) return;

  cw.postMessage(
    {
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-input',
      params: { arguments: payload.tool_arguments ?? {} },
    },
    '*'
  );
  _sendToolResult(cw, payload);
}

/**
 * Group Excalidraw elements for progressive rendering.
 *
 * Returns an array of groups, where each group is rendered as one "drip":
 * 1. [cameraUpdate, background rectangle] — instant setup
 * 2. [shape, label] — one component at a time
 * 3. [arrow, optional arrow label] — one connection at a time
 */
function _groupElementsForDrip(elements: unknown[]): unknown[][] {
  const groups: unknown[][] = [];
  const infraGroup: unknown[] = []; // camera, background
  const componentPairs: unknown[][] = []; // [shape, label] pairs
  const arrowGroups: unknown[][] = []; // [arrow, optional label]

  const typed = elements as Array<Record<string, unknown>>;
  let i = 0;
  while (i < typed.length) {
    const el = typed[i];
    const elType = el?.type as string | undefined;

    if (elType === 'cameraUpdate') {
      infraGroup.push(el);
      i++;
    } else if (
      elType === 'rectangle' &&
      (el?.strokeColor === 'transparent' || el?.id === 'bg_main')
    ) {
      // Background rectangle
      infraGroup.push(el);
      i++;
    } else if (elType === 'rectangle' || elType === 'ellipse' || elType === 'diamond') {
      // Shape — check if next element is its label
      const group: unknown[] = [el];
      if (i + 1 < typed.length) {
        const next = typed[i + 1];
        if (
          (next?.type as string) === 'text' &&
          (next as Record<string, unknown>)?.containerId === el?.id
        ) {
          group.push(next);
          i++;
        }
      }
      componentPairs.push(group);
      i++;
    } else if (elType === 'arrow') {
      const group: unknown[] = [el];
      // Check if next element is an arrow label
      if (i + 1 < typed.length) {
        const next = typed[i + 1];
        if ((next?.type as string) === 'text' && !(next as Record<string, unknown>)?.containerId) {
          group.push(next);
          i++;
        }
      }
      arrowGroups.push(group);
      i++;
    } else {
      // Other elements (standalone text, etc.) — add individually
      componentPairs.push([el]);
      i++;
    }
  }

  // Build final groups: infra first, then components, then arrows
  if (infraGroup.length > 0) groups.push(infraGroup);
  for (const pair of componentPairs) groups.push(pair);
  for (const arrow of arrowGroups) groups.push(arrow);

  return groups;
}
