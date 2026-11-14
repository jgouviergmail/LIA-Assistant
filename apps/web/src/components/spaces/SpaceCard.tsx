'use client';

import { useTranslation } from 'react-i18next';
import { Library, Pencil, ShieldCheck, Star, Trash2 } from '@/lib/icons';
import { ExpandableDescription } from '@/components/ui/expandable-description';
import { Card, CardContent, CardHeader, type CardProps } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import { SpaceActivationToggle } from './SpaceActivationToggle';
import { formatFileSize } from '@/lib/format';
import type { RAGSpace } from '@/types/rag-spaces';
import { lifecycleTone } from '@/lib/status-tone';
import { cn } from '@/lib/utils';

interface SpaceCardProps {
  space: RAGSpace;
  onClick: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
  onToggleFavorite: () => void;
  favoriting?: boolean;
  toggling?: boolean;
  surface?: CardProps['surface'];
}

export function SpaceCard({
  space,
  onClick,
  onEdit,
  onDelete,
  onToggle,
  onToggleFavorite,
  favoriting,
  toggling,
  surface = 'primary',
}: SpaceCardProps) {
  const { t } = useTranslation();
  // A space another domain manages by role (meetings, kept answers): the
  // owner would re-create it at the next projection, so deleting it is
  // refused server-side and not offered here. Rename and toggle stay.
  const managed = space.kind !== null && space.kind !== undefined;
  const actions: RowAction[] = [
    { key: 'edit', label: t('common.edit'), icon: Pencil, onSelect: onEdit },
    ...(managed
      ? []
      : [
          {
            key: 'delete',
            label: t('common.delete'),
            icon: Trash2,
            tone: 'destructive' as const,
            onSelect: onDelete,
          },
        ]),
  ];

  return (
    <Card
      surface={surface}
      variant="interactive"
      className="group flex h-full min-w-0 flex-col cursor-pointer"
      role="link"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={e => {
        // Only the card's OWN keys open it: Space on the activation switch or
        // Enter on an action bubbles up here, and must toggle or act instead.
        if (e.target !== e.currentTarget) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <CardHeader className="p-4 flex-row items-start gap-3 space-y-0">
        {/* Icon */}
        <div className="rounded-lg bg-primary/10 p-2.5 shrink-0">
          <Library className="h-5 w-5 text-primary" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold break-words">{space.name}</h3>
          {managed && (
            <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-muted-foreground">
              <ShieldCheck className="h-3 w-3" aria-hidden="true" />
              {t('spaces.managed.hint')}
            </p>
          )}
          {space.description && (
            <div className="mt-1">
              <ExpandableDescription text={space.description} />
            </div>
          )}
        </div>

        {/* Toggle */}
        <SpaceActivationToggle isActive={space.is_active} onToggle={onToggle} busy={toggling} />
      </CardHeader>

      <CardContent className="mt-auto p-4 pt-0">
        {/* Stats + Actions, under a rule — the skill and MCP cards' own footer
            (owner request 2026-10-22). */}
        <div className="flex items-center justify-between gap-2 border-t pt-3">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <Badge variant={lifecycleTone(space.is_active ? 'active' : 'inactive')}>
              {space.is_active ? t('common.active') : t('common.inactive')}
            </Badge>
            <span>
              {space.document_count}{' '}
              {space.document_count === 1 ? t('spaces.doc_singular') : t('spaces.docs_plural')}
            </span>
            {space.total_size > 0 && <span>{formatFileSize(space.total_size)}</span>}
          </div>

          {/* Actions (ADR-208): always visible, never revealed by a hover. The
              wrapper keeps their clicks — and the menu's, which React bubbles
              through the portal — from opening the space. */}
          <div
            className="flex shrink-0 items-center"
            onClick={e => e.stopPropagation()}
            role="presentation"
          >
            <button
              type="button"
              onClick={onToggleFavorite}
              disabled={favoriting}
              data-space-favorite={space.id}
              aria-label={t(space.is_favorite ? 'spaces.favorite_remove' : 'spaces.favorite_add', {
                name: space.name,
              })}
              aria-pressed={space.is_favorite}
              className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-full transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              <Star
                aria-hidden="true"
                className={cn(
                  'h-4 w-4',
                  space.is_favorite ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground'
                )}
              />
            </button>
            <RowActions
              actions={actions}
              menuLabel={t('common.actions_for', { name: space.name })}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
