'use client';

import { Globe2 } from 'lucide-react';
import { useState } from 'react';

/** A discreet site mark, requested from that site's own origin only. */
export function RadioSourceLogo({ url }: { url: string }) {
  const [failed, setFailed] = useState(false);
  let favicon: string | null = null;
  try {
    const origin = new URL(url);
    if (origin.protocol === 'https:') favicon = new URL('/favicon.ico', origin.origin).href;
  } catch {
    // An invalid or non-HTTPS feed still gets a stable visual marker.
  }

  return (
    <span className="flex min-h-9 w-9 shrink-0 self-stretch items-center justify-center overflow-hidden rounded-md border bg-background">
      {favicon && !failed ? (
        // The images are tiny remote site marks; image optimization cannot know their hosts.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={favicon}
          alt=""
          aria-hidden="true"
          referrerPolicy="no-referrer"
          loading="lazy"
          className="size-full object-contain"
          onError={() => setFailed(true)}
        />
      ) : (
        <Globe2 className="size-5 text-muted-foreground" aria-hidden="true" />
      )}
    </span>
  );
}
