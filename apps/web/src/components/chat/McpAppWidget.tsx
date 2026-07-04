'use client';

/**
 * McpAppWidget — Interactive MCP App widget rendered in a sandboxed iframe.
 *
 * Replaces the server-rendered sentinel div (`<div class="lia-mcp-app" data-registry-id="...">`)
 * with an interactive iframe + JSON-RPC postMessage bridge.
 *
 * Rendering goes through the widget airlock (ADR-098): the iframe loads the
 * same-origin shell `/widget-frame.html` — whose HTTP response carries its
 * own permissive CSP — and the widget HTML is delivered to it via
 * postMessage on load. A srcDoc iframe would inherit the strict app CSP,
 * which blocks the external CDNs (esm.sh, …) third-party widgets load their
 * runtime from.
 *
 * Security:
 * - sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
 * - NO allow-same-origin — the iframe is an opaque origin: no parent
 *   cookies, localStorage, or DOM, even though the shell URL is same-origin
 * - allow-popups required for ui/open-link (open in new tab)
 * - Bridge validates origin ("null") and source before handling messages —
 *   both identical to the former srcDoc rendering (document.write keeps the
 *   same Window)
 *
 * Phase: evolution F2.5 — MCP Apps
 */

import { useCallback, useRef } from 'react';
import { useRegistryItem } from '@/lib/registry-context';
import { useMcpAppBridge } from '@/hooks/useMcpAppBridge';
import { useTranslation } from 'react-i18next';
import { WIDGET_FRAME_PATH } from '@/lib/csp';
import type { McpAppRegistryPayload } from '@/types/mcp-apps';

interface McpAppWidgetProps {
  registryId: string;
}

export function McpAppWidget({ registryId }: McpAppWidgetProps) {
  const item = useRegistryItem(registryId);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const { t } = useTranslation();

  if (!item || item.type !== 'MCP_APP') {
    return (
      <div className="lia-mcp-app__placeholder">
        <span className="text-sm text-muted-foreground">{t('mcp_apps.error')}</span>
      </div>
    );
  }

  const payload = item.payload as unknown as McpAppRegistryPayload;

  return <McpAppWidgetInner iframeRef={iframeRef} payload={payload} />;
}

/**
 * Inner component that always calls useMcpAppBridge (satisfies Rules of Hooks).
 * Separated from the conditional early return in McpAppWidget.
 */
function McpAppWidgetInner({
  iframeRef,
  payload,
}: {
  iframeRef: React.RefObject<HTMLIFrameElement | null>;
  payload: McpAppRegistryPayload;
}) {
  useMcpAppBridge(iframeRef, payload);

  // Deliver the widget HTML to the airlock shell once it has loaded (its
  // message listener is installed synchronously before the load event, so
  // there is no race). targetOrigin MUST be '*': the sandboxed shell is an
  // opaque origin and can never match a concrete origin string. The payload
  // is not sensitive (it is the HTML we render anyway) and the target is our
  // own iframe handle.
  const handleFrameLoad = useCallback(() => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: 'lia:widget-html', html: payload.html_content },
      '*'
    );
  }, [iframeRef, payload.html_content]);

  return (
    <div className="lia-mcp-app-widget">
      <div className="lia-mcp-app-widget__header">
        <span className="lia-badge lia-badge--primary">
          MCP Apps &middot; {payload.server_name}
        </span>
      </div>
      <iframe
        ref={iframeRef}
        src={WIDGET_FRAME_PATH}
        onLoad={handleFrameLoad}
        sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
        className="lia-mcp-app-widget__iframe"
        title={`MCP App: ${payload.tool_name}`}
      />
    </div>
  );
}
