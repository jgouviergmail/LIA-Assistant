/**
 * usePageFrameBridge — what a page the model wrote may say to the host (ADR-370).
 *
 * Two notifications, and no request: its height and its first failure. The
 * skills' bridge is not reused on purpose: `ui/open-link` makes the HOST open a
 * URL, which is exactly the exit the frame's sandbox closes, and a page has no
 * theme or locale to receive. What is not listed here does not exist.
 *
 * - `event.origin === 'null'`: a sandboxed `srcDoc` frame has no origin.
 * - `event.source`: this frame and no other, whatever it claims to be.
 */

import { useEffect, type RefObject } from 'react';

import { applyFrameHeight } from '@/lib/frame-height';

/** A failure is shown as it is told: bounded, so a page cannot fill the chat. */
const MAX_FAULT_CHARS = 300;

interface PageFrameMessage {
  jsonrpc?: unknown;
  method?: unknown;
  params?: { height?: unknown; message?: unknown } | null;
}

/**
 * Listen to one page frame.
 *
 * @param iframeRef - The frame.
 * @param onFault - Told the page's uncaught failures, already bounded.
 */
export function usePageFrameBridge(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  onFault: (message: string) => void
): void {
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const iframe = iframeRef.current;
      if (!iframe || event.origin !== 'null' || event.source !== iframe.contentWindow) return;

      const message = event.data as PageFrameMessage | null;
      if (message?.jsonrpc !== '2.0') return;
      if (message.method === 'ui/notifications/size-changed') {
        applyFrameHeight(iframe, message.params?.height);
      } else if (
        message.method === 'ui/notifications/error' &&
        typeof message.params?.message === 'string'
      ) {
        onFault(message.params.message.slice(0, MAX_FAULT_CHARS));
      }
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [iframeRef, onFault]);
}
