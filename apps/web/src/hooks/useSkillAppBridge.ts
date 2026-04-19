/**
 * useSkillAppBridge — Minimal postMessage bridge for Skill App iframes.
 *
 * Unlike `useMcpAppBridge`, this bridge is intentionally minimal: it only
 * supports the handshake, dynamic resize and external link opening. It does
 * NOT expose tool/call or resources/read — skill iframes must not invoke
 * backend tools or fetch arbitrary resources.
 *
 * Supported methods:
 * - `ui/initialize` → responds with host info + theme/locale (no capabilities)
 * - `ui/notifications/initialized` → acknowledges (no tool payload to deliver)
 * - `ui/notifications/size-changed` → resizes the iframe to match the app
 * - `ui/open-link` → opens HTTPS links in a new tab (with banner fallback)
 * - `notifications/message` → forwards MCP logging to the browser console
 * - `ping` → responds with empty result
 *
 * Security:
 * - Validates `event.origin === 'null'` (srcDoc iframes only — external `src`
 *   iframes have a real origin and are intentionally not bridged)
 * - Validates `event.source === iframeRef.current?.contentWindow`
 * - Only `https://` URLs are accepted by `ui/open-link`
 * - The iframe sandbox (applied by SkillAppWidget) omits `allow-same-origin`
 */

import { useEffect, type RefObject } from 'react';
import type { SkillAppBridgeMessage, SkillAppRegistryPayload } from '@/types/skill-apps';
import { APP_VERSION } from '@/lib/version';

export const SKILL_APPS_PROTOCOL_VERSION = '2026-04-18';

export function useSkillAppBridge(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  payload: SkillAppRegistryPayload
): void {
  useEffect(() => {
    let mounted = true;

    const handler = (event: MessageEvent) => {
      // Bridge only works for srcDoc iframes (origin "null"). External URL
      // iframes own their origin and cannot reach the parent — skip them.
      if (event.origin !== 'null') return;
      if (event.source !== iframeRef.current?.contentWindow) return;

      const msg = event.data as SkillAppBridgeMessage;
      if (msg?.jsonrpc !== '2.0' || !msg.method) return;

      const isRequest = msg.id !== undefined && msg.id !== null;
      let response: SkillAppBridgeMessage | null = null;

      try {
        switch (msg.method) {
          case 'ui/initialize': {
            const theme = document.documentElement.classList.contains('dark')
              ? 'dark'
              : 'light';
            const iframe = iframeRef.current;
            response = {
              jsonrpc: '2.0',
              id: msg.id,
              result: {
                protocolVersion: SKILL_APPS_PROTOCOL_VERSION,
                hostInfo: { name: 'LIA', version: APP_VERSION },
                // Intentionally minimal capabilities — skill frames cannot
                // invoke backend tools or read arbitrary resources.
                hostCapabilities: {
                  openLinks: {},
                },
                hostContext: {
                  skill: {
                    name: payload.skill_name,
                    isSystem: payload.is_system_skill,
                  },
                  theme,
                  containerDimensions: {
                    maxWidth: iframe?.clientWidth || undefined,
                    maxHeight:
                      iframe?.clientHeight || Math.round(window.innerHeight * 0.8),
                  },
                  locale: document.documentElement.lang || 'fr',
                  platform: 'web',
                },
              },
            };
            break;
          }

          case 'ui/notifications/initialized': {
            // Notification — no payload delivery needed (skill frames receive
            // data at render time via URL query params or inline HTML).
            return;
          }

          case 'ui/open-link':
          case 'ui/open': {
            const params = msg.params as { url?: string } | undefined;
            if (
              typeof params?.url === 'string' &&
              params.url.startsWith('https://')
            ) {
              const opened = window.open(params.url, '_blank', 'noopener');
              if (!opened) {
                // Popup blocker — inject a clickable banner fallback
                const container = iframeRef.current?.parentElement;
                if (container) {
                  container
                    .querySelector('.lia-skill-app-widget__link-banner')
                    ?.remove();
                  const banner = document.createElement('div');
                  banner.className = 'lia-skill-app-widget__link-banner';
                  const link = document.createElement('a');
                  link.href = params.url;
                  link.target = '_blank';
                  link.rel = 'noopener';
                  try {
                    link.textContent = `Open: ${new URL(params.url).hostname}`;
                  } catch {
                    link.textContent = 'Open link';
                  }
                  link.addEventListener('click', () => {
                    setTimeout(() => banner.remove(), 200);
                  });
                  const closeBtn = document.createElement('button');
                  closeBtn.textContent = '\u00d7';
                  closeBtn.className = 'lia-skill-app-widget__link-close';
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

          case 'ui/notifications/size-changed': {
            const sizeParams = msg.params as
              | { height?: number; width?: number }
              | undefined;
            const iframe = iframeRef.current;
            if (iframe && typeof sizeParams?.height === 'number' && isFinite(sizeParams.height)) {
              const maxH = window.innerHeight * 0.8;
              const clamped = Math.max(80, Math.min(sizeParams.height, maxH));
              iframe.style.height = `${clamped}px`;
              // Release the initial aspect-ratio placeholder so the explicit
              // height takes full effect without fighting the CSS rule.
              iframe.style.aspectRatio = 'auto';
            }
            return;
          }

          case 'notifications/message': {
            const logParams = msg.params as
              | { level?: string; logger?: string; text?: string }
              | undefined;
            const logMsg = `[Skill App${
              logParams?.logger ? `: ${logParams.logger}` : ''
            }] ${String(logParams?.text ?? '')}`;
            if (logParams?.level === 'error') console.error(logMsg);
            else if (logParams?.level === 'warning') console.warn(logMsg);
            else console.debug(logMsg);
            return;
          }

          case 'ping':
            response = { jsonrpc: '2.0', id: msg.id, result: {} };
            break;

          default: {
            // Explicitly refuse tools/call, resources/read, ui/download-file
            // — skill frames are sandboxed and cannot invoke backend tools.
            if (isRequest) {
              response = {
                jsonrpc: '2.0',
                id: msg.id,
                error: { code: -32601, message: 'Method not found' },
              };
            }
            break;
          }
        }
      } catch (err) {
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

      if (mounted && response) {
        iframeRef.current?.contentWindow?.postMessage(response, '*');
      }
    };

    window.addEventListener('message', handler);
    const iframeEl = iframeRef.current;

    // Push theme/locale to the iframe as JSON-RPC notifications. Two triggers:
    //
    //  1. **Initial load** — called from the iframe ``load`` event (and
    //     immediately if it already loaded). This defeats the race where the
    //     iframe's ``ui/initialize`` handshake fires BEFORE this hook's
    //     ``message`` listener is attached: the iframe may miss the response
    //     and stay on its fallback theme. Pushing unconditionally on load
    //     guarantees the iframe ends up with the correct theme regardless
    //     of handshake ordering.
    //  2. **Live changes** — ``MutationObserver`` on ``<html class>`` /
    //     ``<html lang>`` keeps the iframe in sync when the user toggles
    //     the theme or language mid-session.
    const notifyTheme = () => {
      const theme = document.documentElement.classList.contains('dark')
        ? 'dark'
        : 'light';
      iframeRef.current?.contentWindow?.postMessage(
        {
          jsonrpc: '2.0',
          method: 'ui/theme-changed',
          params: { theme },
        },
        '*'
      );
    };
    const notifyLocale = () => {
      const locale = document.documentElement.lang || 'fr';
      iframeRef.current?.contentWindow?.postMessage(
        {
          jsonrpc: '2.0',
          method: 'ui/locale-changed',
          params: { locale },
        },
        '*'
      );
    };
    const pushInitial = () => {
      // Slight defer so the iframe's inline JS has time to install its
      // ``message`` listener before we push. Two rAFs is the idiomatic
      // "wait for layout + render" beat.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          notifyTheme();
          notifyLocale();
        });
      });
    };

    // If the iframe has already fully loaded by the time this hook runs,
    // push immediately; otherwise wait for ``load``. Some browsers fire
    // load synchronously for srcDoc, so both paths cover all timings.
    if (iframeEl) {
      const hasLoaded =
        iframeEl.contentDocument &&
        iframeEl.contentDocument.readyState === 'complete';
      if (hasLoaded) {
        pushInitial();
      } else {
        iframeEl.addEventListener('load', pushInitial);
      }
    }

    const themeObserver = new MutationObserver(notifyTheme);
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
    const localeObserver = new MutationObserver(notifyLocale);
    localeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['lang'],
    });

    return () => {
      mounted = false;
      window.removeEventListener('message', handler);
      themeObserver.disconnect();
      localeObserver.disconnect();
      iframeEl?.removeEventListener('load', pushInitial);
      iframeEl?.parentElement
        ?.querySelectorAll('.lia-skill-app-widget__link-banner')
        .forEach(el => el.remove());
    };
  }, [iframeRef, payload]);
}
