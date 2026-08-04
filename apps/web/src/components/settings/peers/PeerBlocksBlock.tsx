'use client';

/**
 * PeerBlocksBlock — the viewer's blocks with unblock (peers program, A2).
 *
 * Deliberately shows only blocks the viewer PLACED — never who blocked them
 * (hide-existence, spec §12.2). Unblocking restores nothing; a new request
 * is needed, which the hint spells out.
 */

import { Button } from '@/components/ui/button';
import type { BlockView } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface PeerBlocksBlockProps {
  lng: Language;
  blocks: BlockView[];
  mutating: boolean;
  onUnblock: (peerId: string) => Promise<boolean>;
}

/**
 * Headerless on purpose: the section shell folds this block behind a
 * `SettingsDisclosure` whose summary already carries the title, the hint and
 * the count — a second heading inside would say the same thing twice.
 */
export function PeerBlocksBlock({ lng, blocks, mutating, onUnblock }: PeerBlocksBlockProps) {
  const { t } = useTranslation(lng);

  return (
    <div className="space-y-2">
      {blocks.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('settings.peers.blocks.empty')}</p>
      ) : (
        <ul className="space-y-2">
          {blocks.map(block => (
            <li key={block.blocked_id} className="flex items-center justify-between gap-2">
              <span className="text-sm">
                {block.blocked_display_name ?? t('settings.peers.blocks.unknown_user')}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={mutating}
                onClick={() => void onUnblock(block.blocked_id)}
              >
                {t('settings.peers.blocks.unblock')}
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
