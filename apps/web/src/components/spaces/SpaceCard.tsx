'use client';

import { useTranslation } from 'react-i18next';
import { Library, Pencil, Trash2 } from 'lucide-react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { SpaceActivationToggle } from './SpaceActivationToggle';
import { formatFileSize } from '@/lib/format';
import type { RAGSpace } from '@/types/rag-spaces';

interface SpaceCardProps {
  space: RAGSpace;
  onClick: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
  toggling?: boolean;
}

export function SpaceCard({
  space,
  onClick,
  onEdit,
  onDelete,
  onToggle,
  toggling,
}: SpaceCardProps) {
  const { t } = useTranslation();

  return (
    <Card
      variant="interactive"
      className="group cursor-pointer"
      role="link"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={e => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <CardHeader className="p-4 sm:p-6 flex-row items-start gap-3 space-y-0">
        {/* Icon */}
        <div className="rounded-lg bg-primary/10 p-2.5 shrink-0">
          <Library className="h-5 w-5 text-primary" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold truncate">{space.name}</h3>
          {space.description && (
            <p className="mt-1 text-sm text-muted-foreground line-clamp-2">{space.description}</p>
          )}
        </div>

        {/* Toggle */}
        <SpaceActivationToggle isActive={space.is_active} onToggle={onToggle} disabled={toggling} />
      </CardHeader>

      <CardContent className="p-4 sm:p-6 pt-0">
        {/* Stats + Actions */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <Badge variant={space.is_active ? 'success' : 'outline'}>
              {space.is_active ? t('common.active') : t('common.inactive')}
            </Badge>
            <span>
              {space.document_count}{' '}
              {space.document_count === 1 ? t('spaces.doc_singular') : t('spaces.docs_plural')}
            </span>
            {space.total_size > 0 && <span>{formatFileSize(space.total_size)}</span>}
          </div>

          {/* Actions */}
          <div className="flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={e => {
                e.stopPropagation();
                onEdit();
              }}
              title={t('common.edit')}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={e => {
                e.stopPropagation();
                onDelete();
              }}
              title={t('common.delete')}
            >
              <Trash2 className="h-3.5 w-3.5 text-destructive" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
