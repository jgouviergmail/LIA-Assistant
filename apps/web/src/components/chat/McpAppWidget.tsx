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

import { useCallback, useRef, useState } from 'react';
import { useRegistryItem } from '@/lib/registry-context';
import { useMcpAppBridge } from '@/hooks/useMcpAppBridge';
import { useFrameLoadWatchdog } from '@/hooks/useFrameLoadWatchdog';
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
  const { t } = useTranslation();
  // Bumping this remounts the shell iframe and re-arms the watchdog.
  const [attempt, setAttempt] = useState(0);
  // Liveness for an MCP App is the protocol handshake, NOT the frame's load
  // event: the airlock shell always loads (measured on WebKit, where every
  // part of LIA's path works and a third-party widget can still die on boot).
  const [isReady, setReady] = useState(false);
  // Boot-failure detail relayed by the airlock shell (plain text ONLY — a
  // hostile widget can forge it; it gets words, never markup or links).
  const [bootError, setBootError] = useState<string | null>(null);
  const handleReady = useCallback(() => setReady(true), []);
  const handleWidgetError = useCallback((detail: string) => setBootError(detail), []);
  useMcpAppBridge(iframeRef, payload, { onReady: handleReady, onWidgetError: handleWidgetError });
  const watchdogStatus = useFrameLoadWatchdog(iframeRef, {
    kind: 'mcp',
    label: payload.tool_name,
    readiness: 'bridge-ready',
    isReady,
    attempt,
  });

  // Deliver the widget HTML to the airlock shell once it has loaded. The
  // ordering is structural, not lucky: the shell's inline script installs its
  // message listener while the document parses, and `load` only fires once
  // parsing is complete — measured 10/10 including at 20x CPU throttling on
  // Slow 3G. targetOrigin MUST be '*': the sandboxed shell is an opaque origin
  // and can never match a concrete origin string. The payload is not sensitive
  // (it is the HTML we render anyway) and the target is our own iframe handle.
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
      {/* NON-DESTRUCTIVE on purpose. Unlike a skill frame that never loaded —
          where there is literally nothing to preserve — the airlock shell here
          HAS loaded and the widget may be painting something even if it never
          spoke the protocol. The spec makes the handshake the precondition for
          receiving tool data, so a silent widget should be empty; but that is a
          specification argument, not a measurement, and destroying a possibly
          working widget (and any state the user built in it) to display an
          error would be the worse failure. The notice sits ABOVE the frame. */}
      {watchdogStatus === 'timeout' ? (
        <div className="lia-skill-app-widget__fallback" role="status">
          <p className="lia-skill-app-widget__fallback-text">{t('mcp_apps.frame_timeout')}</p>
          {bootError ? (
            // The one line that makes a phone report actionable without a
            // console: the shell-relayed failure (e.g. a CDN module that
            // never loaded). Rendered as text — see handleWidgetError.
            <p className="lia-skill-app-widget__fallback-detail">
              {t('mcp_apps.frame_error_detail')} {bootError}
            </p>
          ) : null}
          <div className="lia-skill-app-widget__fallback-actions">
            <button
              type="button"
              className="lia-skill-app-widget__fallback-retry"
              onClick={() => {
                setReady(false);
                setBootError(null);
                setAttempt(n => n + 1);
              }}
            >
              {t('mcp_apps.frame_retry')}
            </button>
          </div>
        </div>
      ) : null}
      <iframe
        key={attempt}
        ref={iframeRef}
        src={WIDGET_FRAME_PATH}
        onLoad={handleFrameLoad}
        sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
        className="lia-mcp-app-widget__iframe"
        // Transparent so a widget that renders nothing shows the page through
        // instead of an opaque slab (`--lia-bg` reads as a black rectangle in
        // dark mode — that is what "frame noir" was). Mirrors SkillAppWidget.
        style={{ background: 'transparent' }}
        title={`MCP App: ${payload.tool_name}`}
      />
    </div>
  );
}
