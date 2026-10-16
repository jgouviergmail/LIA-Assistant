'use client';

/**
 * PeerBlocksBlock — the viewer's blocks with unblock (peers program, A2).
 *
 * Deliberately shows only blocks the viewer PLACED — never who blocked them
 * (hide-existence, spec §12.2). Unblocking restores nothing; a new request
 * is needed, which the hint spells out.
 */

import { useRef, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { BlockView } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface PeerBlocksBlockProps {
  lng: Language;
  blocks: BlockView[];
  mutating: boolean;
  onUnblock: (peerId: string) => Promise<boolean>;
  onResolved?: () => void;
}

/**
 * Headerless on purpose: the section shell folds this block behind a
 * `Disclosure` whose summary already carries the title, the hint and
 * the count — a second heading inside would say the same thing twice.
 */
export function PeerBlocksBlock({
  lng,
  blocks,
  mutating,
  onUnblock,
  onResolved,
}: PeerBlocksBlockProps) {
  const { t } = useTranslation(lng);
  const lock = useRef(false);
  const [pending, setPending] = useState(false);
  const perform = async (peerId: string) => {
    if (mutating || lock.current) return;
    lock.current = true;
    setPending(true);
    try {
      if (await onUnblock(peerId)) onResolved?.();
    } finally {
      lock.current = false;
      setPending(false);
    }
  };

  return (
    <div className="space-y-2">
      {blocks.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('settings.peers.blocks.empty')}</p>
      ) : (
        <ul className="space-y-2">
          {blocks.map(block => (
            <li
              key={block.blocked_id}
              className="space-y-3 rounded-xl border border-border/50 bg-card p-3"
            >
              <span className="block break-words text-sm">
                {block.blocked_display_name ?? t('settings.peers.blocks.unknown_user')}
              </span>
              <Button
                type="button"
                variant="default"
                size="sm"
                aria-disabled={mutating || pending}
                onClick={() => void perform(block.blocked_id)}
              >
                <ShieldCheck aria-hidden="true" />
                {t('settings.peers.blocks.unblock')}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
