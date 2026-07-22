'use client';

/**
 * PortraitShortcut — "What LIA understands about you" entry (QW-10).
 *
 * Sits at the head of the Identity & Memory settings group and jumps to the
 * portrait section inside Journals (a different group/tab) — surfacing one of
 * the product's most distinctive artifacts, buried three levels deep until
 * now. Rendered ONLY when a compiled portrait exists (arbitration #6: no
 * teaser for users without one) — so it never advertises an empty page.
 */

import { ChevronRight, UserSquare2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { useJournalPortrait } from '@/hooks/useJournalPortrait';
import { Card } from '@/components/ui/card';

export interface PortraitShortcutProps {
  /** Opens (tab + accordion + scroll) the Journals section holding the portrait. */
  onOpen: () => void;
}

export function PortraitShortcut({ onOpen }: PortraitShortcutProps) {
  const { t } = useTranslation();
  const { hasPortrait } = useJournalPortrait();

  if (!hasPortrait) return null;

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center gap-4 px-6 py-4 text-left hover:bg-accent/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="rounded-lg bg-primary/10 p-2.5">
          <UserSquare2 className="h-6 w-6 text-primary" aria-hidden />
        </span>
        <span className="flex-1 min-w-0">
          <span className="block text-base font-semibold leading-tight">
            {t('settings.portrait_shortcut.title')}
          </span>
          <span className="mt-1 block text-sm text-muted-foreground">
            {t('settings.portrait_shortcut.subtitle')}
          </span>
        </span>
        <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground" aria-hidden />
      </button>
    </Card>
  );
}
