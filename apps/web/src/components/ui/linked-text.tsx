/**
 * LinkedText — a plain text whose addresses can be followed (ADR-369).
 *
 * It draws words and links inline, so whatever holds it keeps deciding how the
 * text wraps. `textLinks` decides what is an address and which may be followed.
 */
import { Fragment, useMemo } from 'react';

import { linkSegments, type TextLink } from '@/lib/text-links';

/** What every followed address looks like, a long one breaking inside the line. */
const LINK_CLASS =
  'rounded-sm text-primary underline underline-offset-2 [overflow-wrap:anywhere] hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/** A page of its own for an address; a mail or a call opens where the system sends it. */
function opensAPage(href: string): boolean {
  return href.startsWith('http');
}

export function OutboundLink({ link }: { link: TextLink }) {
  return (
    <a
      href={link.href}
      title={link.href}
      {...(opensAPage(link.href) ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
      className={LINK_CLASS}
    >
      {link.text}
    </a>
  );
}

export function LinkedText({ text }: { text: string }) {
  const segments = useMemo(() => linkSegments(text), [text]);
  return (
    <>
      {segments.map((segment, index) => (
        <Fragment key={index}>
          {segment.kind === 'link' ? <OutboundLink link={segment} /> : segment.text}
        </Fragment>
      ))}
    </>
  );
}
