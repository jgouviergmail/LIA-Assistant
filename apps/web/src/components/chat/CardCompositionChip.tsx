'use client';

import { X, Reply, Forward, BellOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { CardCompositionDraft } from '@/types/card-actions';

export function CardCompositionChip({
  composition,
  onRemove,
}: {
  composition: CardCompositionDraft | null;
  onRemove: () => void;
}) {
  const { t } = useTranslation();
  if (!composition) return null;
  const Icon = { reply: Reply, forward: Forward, cancel_reminder: BellOff }[
    composition.selection.action
  ];
  return (
    <div
      className="mb-2 flex min-w-0 items-center gap-2 rounded-lg border border-border bg-muted/50 pl-3 text-sm"
      role="group"
      aria-label={t('chat.card_actions.selected_context')}
    >
      <Icon className="size-4 shrink-0 text-primary" aria-hidden="true" />
      <div className="min-w-0 flex-1 py-2">
        <span className="block font-medium">
          {t(`chat.card_actions.${composition.selection.action}`)}
        </span>
        <span className="block break-words text-muted-foreground [overflow-wrap:anywhere]">
          {composition.label || t('chat.card_actions.selected_item')}
        </span>
      </div>
      <button
        type="button"
        className="flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-lg hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label={t('chat.card_actions.remove_context')}
        onClick={onRemove}
      >
        <X className="size-4" aria-hidden="true" />
      </button>
    </div>
  );
}
