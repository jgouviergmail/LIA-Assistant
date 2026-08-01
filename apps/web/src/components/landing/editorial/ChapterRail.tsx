'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { CHAPTERS } from './chapters-data';

/**
 * Fixed chapter rail (desktop only): five numerals + the transparency
 * diamond, scroll-spied. A real <nav> of anchor links — each labelled with
 * its chapter title — so it is keyboard- and screen-reader-usable, not
 * decoration.
 *
 * Inactive links carry FULL `text-muted-foreground`, never a dimmed variant:
 * at 10px bold the token itself is the AA floor (7.4:1 dark / 5.8:1 light over
 * the section backgrounds it flies over), and `/50` measured 2.68:1 — a WCAG
 * 1.4.3 failure axe only sees when the rail happens to fly over an opaque
 * section (2026-08-01). The active link stays `text-primary`, which is what
 * carries the state.
 */

const TRANSPARENCY_ANCHOR = 'transparency';

export function ChapterRail() {
  const { t } = useTranslation();
  const [active, setActive] = useState<string>('');

  useEffect(() => {
    const ids = [...CHAPTERS.map(c => c.anchor), TRANSPARENCY_ANCHOR];
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.isIntersecting) setActive(entry.target.id);
        }
      },
      { rootMargin: '-35% 0px -55% 0px' }
    );
    const sections = ids
      .map(id => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);
    sections.forEach(el => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <nav
      aria-label={t('landing.rail.aria')}
      className="fixed left-4 top-1/2 z-30 hidden -translate-y-1/2 flex-col items-center gap-3 xl:flex"
    >
      {CHAPTERS.map(chapter => (
        <a
          key={chapter.anchor}
          href={`#${chapter.anchor}`}
          aria-label={t(`landing.chapters.${chapter.key}.title`)}
          aria-current={active === chapter.anchor ? 'true' : undefined}
          className={cn(
            'rounded px-1 text-[10px] font-bold tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            active === chapter.anchor
              ? 'text-primary'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {chapter.num}
        </a>
      ))}
      <a
        href={`#${TRANSPARENCY_ANCHOR}`}
        aria-label={t('landing.transparency.title')}
        aria-current={active === TRANSPARENCY_ANCHOR ? 'true' : undefined}
        className={cn(
          'rounded px-1 text-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          active === TRANSPARENCY_ANCHOR
            ? 'text-primary'
            : 'text-muted-foreground hover:text-foreground'
        )}
      >
        ◈
      </a>
    </nav>
  );
}
