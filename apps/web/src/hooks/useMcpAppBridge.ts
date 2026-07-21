/**
 * useMcpAppBridge — PostMessage JSON-RPC bridge for MCP App iframes.
 *
 * Implements the MCP Apps protocol (ext-apps spec 2026-01-26):
 * 1. View sends `ui/initialize` request → Host responds with capabilities
 * 2. View sends `ui/notifications/initialized` → Host sends tool-input then tool-result
 * 3. Bidirectional: tools/call, resources/read, ui/open-link, ui/download-file
 *
 * Security:
 * - Validates origin === "null" (opaque-origin iframes: srcdoc AND the
 *   sandboxed widget-airlock frame — both serialize their origin to "null")
 * - Validates event.source matches our iframe ref
 * - Only allows https:// URLs for ui/open-link
 * - Mounted guard prevents postMessage to destroyed iframes
 *
 * Structure (audit F011): the protocol is a decision table — one module-level
 * handler per JSON-RPC method in `_METHOD_HANDLERS` — so the effect's listener
 * stays a thin guard/dispatch/respond pipeline. Behavior is pinned by the
 * characterization suite in `__tests__/useMcpAppBridge.test.tsx`.
 *
 * Phase: evolution F2.5 — MCP Apps
 */

import { useEffect, type RefObject } from 'react';
import type { McpAppRegistryPayload, McpAppBridgeMessage } from '@/types/mcp-apps';
import { mcpAppCallTool, mcpAppReadResource } from '@/lib/api/mcp-apps';
import { APP_VERSION } from '@/lib/version';
import { logger } from '@/lib/logger';

export const MCP_APPS_PROTOCOL_VERSION = '2026-01-26';

/**
 * Methods whose arrival proves the widget booted far enough to speak the
 * protocol. Either one is enough: `ui/initialize` is the handshake request,
 * `ui/notifications/initialized` its follow-up.
 */
const _READY_METHODS = new Set(['ui/initialize', 'ui/notifications/initialized']);

/**
 * Fire the host's readiness callback when a message proves the widget is alive.
 *
 * Extracted so the message handler keeps no extra branch: it already sits at
 * the frontend complexity ratchet's limit, and inlining this pushed it over
 * (CC 17). Decompose, never raise the cap.
 *
 * @param method - JSON-RPC method of the incoming message.
 * @param onReady - Host callback, absent when the host does not track liveness.
 */
function _signalReadiness(method: string, onReady?: () => void): void {
  if (onReady && _READY_METHODS.has(method)) onReady();
}

/**
 * Consume a boot-failure relay from the airlock shell; true when handled.
 *
 * The shell installs error hooks on the shared Window before writing the
 * widget document, so the parent — otherwise blind to the opaque-origin
 * frame — learns WHY a widget died (a CDN module that never loaded, an
 * uncaught boot exception). The detail is a length-capped plain string; the
 * caller must only ever render it as text (a hostile widget can post this
 * message itself — it may choose the words, never markup or a link).
 *
 * @param data - Raw `event.data`, already origin/source-validated by the caller.
 * @param onWidgetError - Host callback receiving the relayed detail.
 */
function _consumeWidgetErrorRelay(
  data: unknown,
  onWidgetError?: (detail: string) => void
): boolean {
  const relay = data as { type?: string; detail?: string } | null;
  if (relay?.type !== 'lia:widget-error') return false;
  const detail =
    typeof relay.detail === 'string' && relay.detail ? relay.detail.slice(0, 300) : 'unknown error';
  logger.warn('mcp_widget_boot_error_relayed', { component: 'useMcpAppBridge', detail });
  onWidgetError?.(detail);
  return true;
}

/** Extra wiring the host may attach to the bridge. */
interface McpAppBridgeOptions {
  /**
   * Called the first time the widget speaks the protocol (`ui/initialize` or
   * `ui/notifications/initialized`).
   *
   * This is the only real liveness signal an MCP App has. The airlock shell
   * always loads — measured on WebKit: the four locks pass, the payload is
   * delivered and executes, and the parent sees `event.origin === "null"` — so
   * the frame's `load` event says nothing about whether the third-party widget
   * inside ever came alive. Without this callback a widget that dies on boot
   * stays an opaque rectangle with no message and no log.
   */
  onReady?: () => void;

  /**
   * Called with the boot-failure detail relayed by the airlock shell
   * (see `_consumeWidgetErrorRelay`). Render it as PLAIN TEXT only.
   */
  onWidgetError?: (detail: string) => void;
}

export function useMcpAppBridge(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  payload: McpAppRegistryPayload,
  options: McpAppBridgeOptions = {}
): void {
  const { onReady, onWidgetError } = options;
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
      if (msg?.jsonrpc !== '2.0' || !msg.method) {
        // Not a protocol message — it may be the shell's boot-failure relay.
        _consumeWidgetErrorRelay(event.data, onWidgetError);
        return;
      }

      // The widget speaks: it booted far enough to run the protocol.
      _signalReadiness(msg.method, onReady);

      let response: McpAppBridgeMessage | null = null;
      try {
        const methodHandler = _METHOD_HANDLERS[msg.method] ?? _handleUnknownMethod;
        response = await methodHandler(msg, { iframeRef, payload, sendToolData });
      } catch (err) {
        // Only send error responses for requests, never for notifications
        // (JSON-RPC 2.0: messages without `id` must not receive a response).
        if (!_isRequest(msg)) return;
        response = {
          jsonrpc: '2.0',
          id: msg.id,
          error: { code: -32000, message: String(err) },
        };
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
  }, [iframeRef, payload, onReady, onWidgetError]);
}

// ---------------------------------------------------------------------------
// Method decision table (audit F011): one handler per JSON-RPC method.
// A handler returns the response to post, or null for notifications /
// suppressed responses. Throwing inside a handler is mapped by the listener to
// a -32000 error for requests and silence for notifications.
// ---------------------------------------------------------------------------

/** Dependencies a method handler may need (owned by the mounting effect). */
interface BridgeContext {
  iframeRef: RefObject<HTMLIFrameElement | null>;
  payload: McpAppRegistryPayload;
  sendToolData: () => void;
}

type MethodHandler = (
  msg: McpAppBridgeMessage,
  ctx: BridgeContext
) => McpAppBridgeMessage | null | Promise<McpAppBridgeMessage | null>;

/** JSON-RPC 2.0: only messages carrying an `id` are requests expecting a response. */
function _isRequest(msg: McpAppBridgeMessage): boolean {
  return msg.id !== undefined && msg.id !== null;
}

/** Empty-result acknowledgement for requests; silence for notifications. */
function _ack(msg: McpAppBridgeMessage): McpAppBridgeMessage | null {
  return _isRequest(msg) ? { jsonrpc: '2.0', id: msg.id, result: {} } : null;
}

/** ui/initialize — respond with host capabilities and tool context. */
function _handleInitialize(msg: McpAppBridgeMessage, ctx: BridgeContext): McpAppBridgeMessage {
  const theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
  const iframe = ctx.iframeRef.current;
  return {
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
            name: ctx.payload.tool_name,
            inputSchema: ctx.payload.tool_input_schema ?? { type: 'object' },
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
}

/** ui/notifications/initialized — deliver tool data; notification, no response. */
function _handleInitialized(_msg: McpAppBridgeMessage, ctx: BridgeContext): null {
  ctx.sendToolData();
  return null;
}

/** tools/call — proxy to the backend and wrap into MCP CallToolResult format. */
async function _handleToolsCall(
  msg: McpAppBridgeMessage,
  ctx: BridgeContext
): Promise<McpAppBridgeMessage> {
  const params = msg.params as { name?: string; arguments?: Record<string, unknown> } | undefined;
  const apiResult = await mcpAppCallTool(ctx.payload, params?.name ?? '', params?.arguments ?? {});
  if (!apiResult.success) {
    return {
      jsonrpc: '2.0',
      id: msg.id,
      result: {
        content: [{ type: 'text', text: apiResult.error ?? 'Tool call failed' }],
        isError: true,
      },
    };
  }
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
  return { jsonrpc: '2.0', id: msg.id, result: callToolResult };
}

/** resources/read — proxy to the backend and wrap into MCP ReadResourceResult format. */
async function _handleResourcesRead(
  msg: McpAppBridgeMessage,
  ctx: BridgeContext
): Promise<McpAppBridgeMessage> {
  const params = msg.params as { uri?: string } | undefined;
  const apiResult = await mcpAppReadResource(ctx.payload, params?.uri ?? '');
  if (!apiResult.success) {
    return {
      jsonrpc: '2.0',
      id: msg.id,
      error: { code: -32000, message: apiResult.error ?? 'Resource not found' },
    };
  }
  return {
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
}

/** ui/open-link / ui/open — open https URLs; on blocked popups inject a banner. */
function _handleOpenLink(msg: McpAppBridgeMessage, ctx: BridgeContext): McpAppBridgeMessage | null {
  const params = msg.params as { url?: string } | undefined;
  // Security: only allow https:// URLs
  if (typeof params?.url === 'string' && params.url.startsWith('https://')) {
    // window.open may be blocked — postMessage handlers from sandboxed
    // iframes don't carry user activation.
    const opened = window.open(params.url, '_blank', 'noopener');
    if (!opened) {
      _injectLinkBanner(ctx.iframeRef, params.url);
    }
  }
  return _ack(msg);
}

/** Popup-blocked fallback: inject a clickable link banner above the iframe. */
function _injectLinkBanner(iframeRef: RefObject<HTMLIFrameElement | null>, url: string): void {
  const container = iframeRef.current?.parentElement;
  if (!container) return;
  // Remove any previous banner
  container.querySelector('.lia-mcp-app-widget__link-banner')?.remove();
  const banner = document.createElement('div');
  banner.className = 'lia-mcp-app-widget__link-banner';
  const hostname = new URL(url).hostname;
  const link = document.createElement('a');
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener';
  link.textContent = `Open: ${hostname}`;
  link.addEventListener('click', () => {
    setTimeout(() => banner.remove(), 200);
  });
  const closeBtn = document.createElement('button');
  closeBtn.textContent = '×';
  closeBtn.className = 'lia-mcp-app-widget__link-close';
  closeBtn.addEventListener('click', e => {
    e.preventDefault();
    banner.remove();
  });
  banner.appendChild(link);
  banner.appendChild(closeBtn);
  container.insertBefore(banner, iframeRef.current);
}

/** One downloadable item of a ui/download-file request (MCP Apps spec). */
interface DownloadItem {
  type?: string;
  resource?: { uri?: string; text?: string; blob?: string; mimeType?: string };
  uri?: string;
  name?: string;
  mimeType?: string;
}

/** ui/download-file — EmbeddedResource or ResourceLink downloads per spec. */
function _handleDownloadFile(msg: McpAppBridgeMessage): McpAppBridgeMessage | null {
  const params = msg.params as { contents?: DownloadItem[] } | undefined;
  if (params?.contents) {
    for (const item of params.contents) {
      if (item.type === 'resource' && item.resource) {
        _downloadEmbeddedResource(item.resource);
      } else if (item.type === 'resource_link' && item.uri) {
        _downloadResourceLink(item);
      }
    }
  }
  return _ack(msg);
}

/** EmbeddedResource: {type: "resource", resource: {uri, text|blob, mimeType}}. */
function _downloadEmbeddedResource(res: NonNullable<DownloadItem['resource']>): void {
  const filename = res.uri?.split('/').pop() || 'download';
  let blob: Blob;
  if (res.blob) {
    try {
      const binary = atob(res.blob);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
      }
      blob = new Blob([bytes], { type: res.mimeType || 'application/octet-stream' });
    } catch {
      // Invalid base64 — skip this resource
      return;
    }
  } else if (res.text) {
    blob = new Blob([res.text], { type: res.mimeType || 'text/plain' });
  } else {
    return;
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** ResourceLink: trigger the download via a temporary anchor (http(s) only). */
function _downloadResourceLink(item: DownloadItem): void {
  // Security: only allow http(s) URLs (prevent javascript: / data: XSS)
  if (!item.uri || (!item.uri.startsWith('https://') && !item.uri.startsWith('http://'))) {
    return;
  }
  const a = document.createElement('a');
  a.href = item.uri;
  a.download = item.name || item.uri.split('/').pop() || 'download';
  a.target = '_blank';
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

/** ui/request-display-mode — acknowledge; only inline mode is supported. */
function _handleDisplayMode(msg: McpAppBridgeMessage): McpAppBridgeMessage | null {
  // SDK Zod schema requires { mode: "inline"|"fullscreen"|"pip" }.
  return _isRequest(msg) ? { jsonrpc: '2.0', id: msg.id, result: { mode: 'inline' } } : null;
}

/** ui/message & co — acknowledge but no-op for now (no chat integration yet). */
function _handleAckOnly(msg: McpAppBridgeMessage): McpAppBridgeMessage | null {
  return _ack(msg);
}

/** ui/notifications/size-changed — resize the iframe to the app's request. */
function _handleSizeChanged(msg: McpAppBridgeMessage, ctx: BridgeContext): null {
  const sizeParams = msg.params as { height?: number; width?: number } | undefined;
  if (ctx.iframeRef.current && sizeParams?.height) {
    const maxH = window.innerHeight * 0.8;
    ctx.iframeRef.current.style.height = `${Math.min(sizeParams.height, maxH)}px`;
  }
  return null;
}

/** notifications/message — standard MCP logging, forwarded to the console. */
function _handleLogMessage(msg: McpAppBridgeMessage): null {
  // Spec: { level: string, logger?: string, text: string }
  const logParams = msg.params as { level?: string; logger?: string; text?: string } | undefined;
  const logMsg = `[MCP App${logParams?.logger ? `: ${logParams.logger}` : ''}] ${String(logParams?.text ?? '')}`;
  if (logParams?.level === 'error') console.error(logMsg);
  else if (logParams?.level === 'warning') console.warn(logMsg);
  else console.debug(logMsg);
  return null;
}

/** ping — always answered (historic behavior, even for id-less pings). */
function _handlePing(msg: McpAppBridgeMessage): McpAppBridgeMessage {
  return { jsonrpc: '2.0', id: msg.id, result: {} };
}

/** Unknown method: -32601 for requests; notifications are silently ignored. */
function _handleUnknownMethod(msg: McpAppBridgeMessage): McpAppBridgeMessage | null {
  if (!_isRequest(msg)) return null;
  return {
    jsonrpc: '2.0',
    id: msg.id,
    error: { code: -32601, message: 'Method not found' },
  };
}

const _METHOD_HANDLERS: Record<string, MethodHandler> = {
  // MCP Apps protocol handshake
  'ui/initialize': _handleInitialize,
  'ui/notifications/initialized': _handleInitialized,
  // MCP tool/resource proxying
  'tools/call': _handleToolsCall,
  'resources/read': _handleResourcesRead,
  // Host capabilities
  'ui/open-link': _handleOpenLink,
  'ui/open': _handleOpenLink,
  'ui/download-file': _handleDownloadFile,
  'ui/request-display-mode': _handleDisplayMode,
  'ui/message': _handleAckOnly,
  'ui/update-model-context': _handleAckOnly,
  'ui/resource-teardown': _handleAckOnly,
  // Notifications from View (no response)
  'ui/notifications/size-changed': _handleSizeChanged,
  // MCP logging
  'notifications/message': _handleLogMessage,
  // Misc
  ping: _handlePing,
};

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

/** Camera frames and the transparent/`bg_main` background rectangle. */
function _isInfraElement(el: Record<string, unknown>): boolean {
  const elType = el?.type;
  if (elType === 'cameraUpdate') return true;
  return elType === 'rectangle' && (el?.strokeColor === 'transparent' || el?.id === 'bg_main');
}

/** True when `next` is the text label attached to the shape `el` (containerId). */
function _isShapeLabel(next: Record<string, unknown>, el: Record<string, unknown>): boolean {
  return (next?.type as string) === 'text' && next?.containerId === el?.id;
}

/** True when `next` is a free-floating arrow label (text without containerId). */
function _isArrowLabel(next: Record<string, unknown>): boolean {
  return (next?.type as string) === 'text' && !next?.containerId;
}

/**
 * Take `typed[i]` plus its label when the following element matches.
 *
 * Returns the drip group and the index of the first unconsumed element.
 */
function _takeElementWithLabel(
  typed: Array<Record<string, unknown>>,
  i: number,
  isLabel: (next: Record<string, unknown>) => boolean
): [unknown[], number] {
  if (i + 1 < typed.length && isLabel(typed[i + 1])) {
    return [[typed[i], typed[i + 1]], i + 2];
  }
  return [[typed[i]], i + 1];
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
  const infraGroup: unknown[] = []; // camera, background
  const componentPairs: unknown[][] = []; // [shape, label] pairs + standalones
  const arrowGroups: unknown[][] = []; // [arrow, optional label]

  const typed = elements as Array<Record<string, unknown>>;
  let i = 0;
  while (i < typed.length) {
    const el = typed[i];
    const elType = el?.type as string | undefined;

    if (_isInfraElement(el)) {
      infraGroup.push(el);
      i++;
    } else if (elType === 'rectangle' || elType === 'ellipse' || elType === 'diamond') {
      // Shape — consume its label too when the next element carries it
      const [group, next] = _takeElementWithLabel(typed, i, n => _isShapeLabel(n, el));
      componentPairs.push(group);
      i = next;
    } else if (elType === 'arrow') {
      const [group, next] = _takeElementWithLabel(typed, i, _isArrowLabel);
      arrowGroups.push(group);
      i = next;
    } else {
      // Other elements (standalone text, etc.) — add individually
      componentPairs.push([el]);
      i++;
    }
  }

  // Build final groups: infra first, then components, then arrows
  const groups: unknown[][] = [];
  if (infraGroup.length > 0) groups.push(infraGroup);
  for (const pair of componentPairs) groups.push(pair);
  for (const arrow of arrowGroups) groups.push(arrow);

  return groups;
}
