/**
 * usePageFrameBridge — what a page the model wrote may say to the host (ADR-370).
 *
 * Three notifications, and no request: its height, its first failure, and what
 * its policy refused. The skills' bridge is not reused on purpose: `ui/open-link`
 * makes the HOST open a URL, which is exactly the exit the frame's sandbox
 * closes, and a page has no theme or locale to receive. What is not listed here
 * does not exist.
 *
 * - `event.origin === 'null'`: a sandboxed `srcDoc` frame has no origin.
 * - `event.source`: this frame and no other, whatever it claims to be.
 *
 * A refusal is told by its DIRECTIVE, and read as one of three kinds: the frame
 * never says an address, and the host never shows a word the page chose.
 */

import { useEffect, type RefObject } from 'react';

import { applyFrameHeight } from '@/lib/frame-height';

/** A failure is shown as it is told: bounded, so a page cannot fill the chat. */
const MAX_FAULT_CHARS = 300;

/** What a page was refused, in the terms a person reads. */
export type PageBlockedKind = 'frame' | 'image' | 'resource';

/**
 * The directives that name a kind of their own; every other one is a resource.
 * A Map, because the name comes from the page: `constructor` read on an object
 * literal answers with a function.
 */
const BLOCKED_KINDS: ReadonlyMap<string, PageBlockedKind> = new Map([
  ['frame-src', 'frame'],
  ['child-src', 'frame'],
  ['img-src', 'image'],
]);

interface PageFrameMessage {
  jsonrpc?: unknown;
  method?: unknown;
  params?: { height?: unknown; message?: unknown; directive?: unknown } | null;
}

/**
 * Listen to one page frame.
 *
 * @param iframeRef - The frame.
 * @param onFault - Told the page's uncaught failures, already bounded.
 * @param onBlocked - Told the kind of content the frame's policy refused.
 */
export function usePageFrameBridge(
  iframeRef: RefObject<HTMLIFrameElement | null>,
  onFault: (message: string) => void,
  onBlocked: (kind: PageBlockedKind) => void
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
      } else if (
        message.method === 'ui/notifications/blocked' &&
        typeof message.params?.directive === 'string'
      ) {
        onBlocked(BLOCKED_KINDS.get(message.params.directive) ?? 'resource');
      }
    };

    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [iframeRef, onFault, onBlocked]);
}
