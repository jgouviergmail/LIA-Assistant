'use client';

/**
 * McpAppWidget — Interactive MCP App widget rendered in a sandboxed iframe.
 *
 * Replaces the server-rendered sentinel div (`<div class="lia-mcp-app" data-registry-id="...">`)
 * with an interactive iframe + JSON-RPC postMessage bridge.
 *
 * Security:
 * - sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
 * - NO allow-same-origin — blocks access to parent cookies, localStorage, DOM
 * - allow-popups required for ui/open-link (open in new tab)
 * - Bridge validates origin and source before handling messages
 *
 * Phase: evolution F2.5 — MCP Apps
 */

import { useRef } from 'react';
import { useRegistryItem } from '@/lib/registry-context';
import { useMcpAppBridge } from '@/hooks/useMcpAppBridge';
import { useTranslation } from 'react-i18next';
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

  return (
    <div className="lia-mcp-app-widget">
      <div className="lia-mcp-app-widget__header">
        <span className="lia-badge lia-badge--primary">
          MCP Apps &middot; {payload.server_name}
        </span>
      </div>
      <iframe
        ref={iframeRef}
        srcDoc={payload.html_content}
        sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
        className="lia-mcp-app-widget__iframe"
        title={`MCP App: ${payload.tool_name}`}
      />
    </div>
  );
}
