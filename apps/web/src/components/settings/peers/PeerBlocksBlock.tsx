'use client';

/**
 * PeerBlocksBlock — the viewer's blocks with unblock (peers program, A2).
 *
 * Deliberately shows only blocks the viewer PLACED — never who blocked them
 * (hide-existence, spec §12.2). Unblocking restores nothing; a new request
 * is needed, which the hint spells out.
 */

import { ShieldOff } from 'lucide-react';

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

export function PeerBlocksBlock({ lng, blocks, mutating, onUnblock }: PeerBlocksBlockProps) {
  const { t } = useTranslation(lng);

  return (
    <div className="space-y-2">
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <ShieldOff className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        {t('settings.peers.blocks.title')}
      </h4>
      <p className="text-xs text-muted-foreground">{t('settings.peers.blocks.hint')}</p>
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
