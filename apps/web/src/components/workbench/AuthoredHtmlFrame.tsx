'use client';

/**
 * AuthoredHtmlFrame — an e-mail or a Word file as its author laid it out (ADR-369, D3, spec §7, A1,
 * lot 14).
 *
 * The HTML is the sender's, so it never enters the page: it is the `srcdoc` of a
 * sandboxed frame — an opaque origin, no script, no form, no reach into this page —
 * whose one permission is to open a new tab, free of the sandbox so the page it
 * opens works. Its document opens on a policy that refuses every resource but
 * inline styles and embedded images, BEFORE the sender's first byte: no remote
 * image, font or stylesheet loads, so opening a message tells its sender nothing
 * (a parent policy and this one intersect, the stricter wins). Remote images load
 * on the reader's click alone, for this message. The images the message carries
 * inside itself ask nobody for anything: they come as `data:` addresses, and only of
 * an image type. No referrer leaves from inside.
 *
 * A link survives only as a web or mail address, rewritten to a new tab that cannot
 * reach back, whatever target its sender gave it; any other keeps its words and
 * loses its address. A sender's base and refresh are removed. All of it happens on
 * the parsed tree, templates and noscript content included. With no script there is
 * no bridge back to the page, so the frame takes a fixed height with its own scroll.
 * It lays a light paper through the light scheme's system colours, never a literal
 * one. A dark theme turns the whole page down, whatever colours its author wrote and
 * wherever: rewriting them one by one would miss those of a class or a table. Its
 * images and pictures are turned back, so a photo and a logo keep their colours, and
 * the sender's own colours are one click away.
 */
import { useTheme } from 'next-themes';
import { useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { safeAddress } from '@/lib/text-links';
import { cn } from '@/lib/utils';
import type { MailInlineImage } from '@/lib/workbench/types';

/** The frame's permissions: a new tab, and nothing else. */
const SANDBOX = 'allow-popups allow-popups-to-escape-sandbox';
/** What a mail's link may be (A1): among the addresses `safeAddress` follows, no call. */
const MAIL_LINK = /^(?:https?|mailto):/;
/** What holds an image from elsewhere; one the message carries asks nobody for anything. */
const REMOTE_IMAGE =
  'img[src]:not([src^="data:" i]):not([src^="cid:" i]), [srcset], [background]:not([background^="cid:" i]), [style*="url(" i]';
/** What a message's own image may be, whatever an answer says. */
const INLINE_IMAGE = /^data:image\/(?:png|jpeg|gif|webp);base64,/;
/** Everything a link could do but open, taken off before its address is written back. */
const LINK_ATTRIBUTES = [
  'href',
  'xlink:href',
  'target',
  'rel',
  'ping',
  'download',
  'referrerpolicy',
] as const;

/** The page turned down, and what must keep its colours turned back. */
const NIGHT_PAPER =
  '<style>html{filter:invert(1) hue-rotate(180deg) contrast(.92)}' +
  'img,video,[background],[style*="url(" i]{filter:invert(1) hue-rotate(180deg)}</style>';

function preamble(images: boolean, night: boolean): string {
  const sources = images ? 'https: data:' : 'data:';
  return (
    '<!doctype html><meta charset="utf-8">' +
    `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src ${sources}">` +
    '<meta name="referrer" content="no-referrer">' +
    '<meta name="color-scheme" content="light">' +
    '<style>html{color-scheme:light;background:Canvas;color:CanvasText}</style>' +
    (night ? NIGHT_PAPER : '') +
    '<base target="_blank">'
  );
}

const NO_IMAGES: readonly MailInlineImage[] = [];

export interface AuthoredHtmlFrameProps {
  lng: Language;
  /** The author's HTML, as it arrived. */
  html: string;
  /** What the frame is called. */
  title: string;
  /** The reader asked for this document's remote images. */
  images?: boolean;
  /** Offers its remote images: without it, nothing is offered and none ever loads. */
  onShowImages?: () => void;
  /** The images a message carries, read apart. */
  inline?: readonly MailInlineImage[];
  /** Its height, where the default does not suit. */
  className?: string;
}

export function AuthoredHtmlFrame({
  lng,
  html,
  title,
  images = false,
  onShowImages,
  inline = NO_IMAGES,
  className,
}: AuthoredHtmlFrameProps) {
  const { t } = useTranslation(lng);
  const { resolvedTheme } = useTheme();
  const [ownColours, setOwnColours] = useState(false);
  const frame = useRef<HTMLIFrameElement>(null);
  const dark = resolvedTheme === 'dark';
  const night = dark && !ownColours;
  const mail = useMemo(
    () => isolatedMailDocument(html, images, inline, night),
    [html, images, inline, night]
  );
  const offersImages = onShowImages !== undefined && mail.remoteImages && !images;
  return (
    <>
      {(offersImages || dark) && (
        <div className="flex flex-wrap items-center gap-x-4">
          {offersImages && (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={() => {
                onShowImages?.();
                // The button leaves with the answer: the message it asked for takes the focus.
                frame.current?.focus({ preventScroll: true });
              }}
            >
              {t('workbench.mail.show_images')}
            </Button>
          )}
          {dark && (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={() => setOwnColours(own => !own)}
            >
              {t(
                ownColours ? 'workbench.mail.colours_of_theme' : 'workbench.mail.colours_of_author'
              )}
            </Button>
          )}
        </div>
      )}
      <iframe
        ref={frame}
        sandbox={SANDBOX}
        referrerPolicy="no-referrer"
        title={title}
        srcDoc={mail.source}
        className={cn('block h-[min(70dvh,48rem)] min-h-64 w-full rounded-md border', className)}
      />
    </>
  );
}

interface IsolatedMail {
  /** The frame's document. */
  source: string;
  /** It holds an image from elsewhere: the reader has something to ask for. */
  remoteImages: boolean;
}

/** Browser-only: parse under the frame's policy before any sender content.
 *
 * A link's own target overrides the base target, and default-src does not
 * govern a frame's navigation: links are rewritten in the parsed tree rather
 * than by a pattern over the markup. Template content needs its own walk since
 * selectors do not enter it; noscript is parsed with scripting disabled, as
 * it is in the sandbox. The caller is loaded without SSR in MessageReader.
 */
function isolatedMailDocument(
  html: string,
  images: boolean,
  inline: readonly MailInlineImage[],
  night: boolean
): IsolatedMail {
  const document = new DOMParser().parseFromString(
    `${preamble(images, night)}${html}`,
    'text/html'
  );
  const remoteImages = disarm(document, document.querySelector('base'));
  drawOwnImages(document, inline);
  return { source: `<!doctype html>${document.documentElement.outerHTML}`, remoteImages };
}

/** @returns Whether what it walked holds an image from elsewhere. */
function disarm(root: ParentNode, ownBase: Element | null): boolean {
  let remoteImages = false;
  // Array iteration includes the appended fragments without recursing on mail depth.
  const roots: ParentNode[] = [root];
  for (const current of roots) {
    for (const link of current.querySelectorAll('a, area')) rewriteLink(link);
    for (const element of current.querySelectorAll('base, meta[http-equiv]')) {
      if (
        (element.localName === 'base' && element !== ownBase) ||
        element.getAttribute('http-equiv')?.trim().toLowerCase() === 'refresh'
      ) {
        element.remove();
      }
    }
    remoteImages ||= holdsRemoteImage(current);
    for (const template of current.querySelectorAll('template')) {
      roots.push(template.content);
    }
  }
  return remoteImages;
}

/** Sets each image the message carries on the places its HTML names it. */
function drawOwnImages(root: ParentNode, inline: readonly MailInlineImage[]): void {
  const known = new Map(
    inline.filter(image => INLINE_IMAGE.test(image.data_url)).map(i => [i.cid, i.data_url])
  );
  for (const attribute of ['src', 'background']) {
    for (const element of root.querySelectorAll(`[${attribute}^="cid:" i]`)) {
      const name = element.getAttribute(attribute)?.slice('cid:'.length) ?? '';
      const drawn = known.get(ownName(name));
      if (drawn) element.setAttribute(attribute, drawn);
    }
  }
}

function ownName(name: string): string {
  try {
    return decodeURIComponent(name);
  } catch {
    return name;
  }
}

function rewriteLink(link: Element): void {
  const asked = link.getAttribute('href');
  const address = asked === null ? null : safeAddress(asked);
  for (const attribute of LINK_ATTRIBUTES) link.removeAttribute(attribute);
  link.removeAttributeNS('http://www.w3.org/1999/xlink', 'href');
  if (address === null || !MAIL_LINK.test(address.href)) return;
  link.setAttribute('href', address.href);
  link.setAttribute('target', '_blank');
  link.setAttribute('rel', 'noopener noreferrer');
}

function holdsRemoteImage(root: ParentNode): boolean {
  if (root.querySelector(REMOTE_IMAGE) !== null) return true;
  return Array.from(root.querySelectorAll('style')).some(style =>
    style.textContent?.includes('url(')
  );
}
