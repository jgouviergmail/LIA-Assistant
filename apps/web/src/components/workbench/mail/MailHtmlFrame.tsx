'use client';

/**
 * MailHtmlFrame — an e-mail as its author laid it out (ADR-369, D3, spec §7).
 *
 * The HTML is the sender's, so it never enters the page: it is the `srcdoc`
 * of a frame sandboxed with NO permission (`sandbox=""` — an opaque origin, no
 * script, no form, no popup, no reach into this page). Its document opens on a
 * policy that refuses every resource but inline styles, BEFORE the sender's
 * first byte: no remote image, font or stylesheet loads, so opening a message
 * tells its sender nothing (a parent policy and this one intersect, the
 * stricter wins). A base target supplies a safe default, and no referrer
 * leaves from inside. Explicit sender targets override that default: links therefore
 * lose their navigation attributes before entering the frame, including in
 * templates and noscript content. A sender's base and refresh are removed.
 * With no script there is no bridge back to the page, so the frame
 * takes a fixed height with its own scroll. It keeps its own light paper in
 * every theme — the author's colours; inverting them breaks layouts and logos —
 * through the light scheme's system colours, never a literal one.
 */
import { useMemo } from 'react';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

const PREAMBLE =
  '<!doctype html><meta charset="utf-8">' +
  '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">' +
  '<meta name="referrer" content="no-referrer">' +
  '<meta name="color-scheme" content="light">' +
  '<style>html{color-scheme:light;background:Canvas;color:CanvasText}</style>' +
  '<base target="_blank">';

export interface MailHtmlFrameProps {
  lng: Language;
  /** The sender's HTML, as the server answered it. */
  html: string;
}

export function MailHtmlFrame({ lng, html }: MailHtmlFrameProps) {
  const { t } = useTranslation(lng);
  const srcDoc = useMemo(() => isolatedMailDocument(html), [html]);
  return (
    <iframe
      sandbox=""
      referrerPolicy="no-referrer"
      title={t('workbench.mail.html_frame_title')}
      srcDoc={srcDoc}
      className="block h-[min(70dvh,48rem)] min-h-64 w-full rounded-md border"
    />
  );
}

/** Browser-only: parse under the frame's policy before any sender content.
 *
 * A link's own target overrides the base target, and default-src does not
 * govern a frame's navigation. Disable links in the parsed tree rather than
 * rewriting markup with a pattern. Template content needs its own walk since
 * selectors do not enter it; noscript is parsed with scripting disabled, as
 * it is in the sandbox. The caller is loaded without SSR in MessageReader.
 */
function isolatedMailDocument(html: string): string {
  const document = new DOMParser().parseFromString(`${PREAMBLE}${html}`, 'text/html');
  const base = document.querySelector('base');
  removeNavigation(document, base);
  return `<!doctype html>${document.documentElement.outerHTML}`;
}

function removeNavigation(root: ParentNode, ownBase: Element | null): void {
  // Array iteration includes the appended fragments without recursing on mail depth.
  const roots: ParentNode[] = [root];
  for (const current of roots) {
    for (const link of current.querySelectorAll('a, area')) {
      link.removeAttribute('href');
      link.removeAttribute('xlink:href');
      link.removeAttributeNS('http://www.w3.org/1999/xlink', 'href');
      link.removeAttribute('target');
    }
    for (const element of current.querySelectorAll('base, meta[http-equiv]')) {
      if (
        (element.localName === 'base' && element !== ownBase) ||
        element.getAttribute('http-equiv')?.trim().toLowerCase() === 'refresh'
      ) {
        element.remove();
      }
    }
    for (const template of current.querySelectorAll('template')) {
      roots.push(template.content);
    }
  }
}
